"""An installation gets exactly one first owner, from the browser or the environment.

PostgreSQL locks must exclude peers until the transaction ends, then recheck
committed configuration even when a peer has already cached the unconfigured row.

``VAULT_SETUP_ADMIN_*`` is the other door. It exists for app-store and unattended
installs that cannot reach the browser flow, and it must stay a door that opens once:
a variable left in a compose file must never reset a password or add an owner to a
running installation, and the password must never reach a log line.
"""

from datetime import datetime, timezone
from typing import Iterator

import pytest
from fastapi.testclient import TestClient
from psycopg.errors import LockNotAvailable
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.schema import CreateSchema, DropSchema
from sqlmodel import Session, SQLModel, create_engine, select

from app.core.config import _overlay
from app.core.errors import ErrorKind, OperationError
from app.db.models import SystemConfig, User
from app.db.url import normalize_database_url
from app.modules.administration import runtime_config, setup_bootstrap, setup_storage
from tests.containers import postgres_url
from tests.factories import build_system_config
from tests.fakes.setup_process import race_setup_workers

ENV_USERNAME = "store-owner"
ENV_PASSWORD = "StoreFormPassword123"


@pytest.fixture
def postgres_setup_engine() -> Iterator[Engine]:
    """Isolate setup rows from other contracts using the shared PostgreSQL server."""
    schema = "setup_bootstrap"
    engine = create_engine(
        normalize_database_url(postgres_url()),
        connect_args={"options": f"-csearch_path={schema}"},
    )
    try:
        with engine.begin() as connection:
            connection.execute(CreateSchema(schema))
        try:
            SQLModel.metadata.create_all(engine)
            yield engine
        finally:
            with engine.begin() as connection:
                connection.execute(DropSchema(schema, cascade=True))
    finally:
        engine.dispose()


class TestLockInstallation:
    @pytest.mark.postgres
    def test_excludes_a_competing_postgres_setup_transaction(
        self, postgres_setup_engine: Engine
    ) -> None:
        with (
            Session(postgres_setup_engine) as first,
            Session(postgres_setup_engine) as peer,
        ):
            setup_bootstrap.lock_installation(first)
            peer.execute(text("SET LOCAL lock_timeout = '100ms'"))

            with pytest.raises(OperationalError) as exc:
                setup_bootstrap.lock_installation(peer)

            assert isinstance(exc.value.orig, LockNotAvailable)

    @pytest.mark.postgres
    def test_rejects_postgres_setup_after_configuration_commits(
        self, postgres_setup_engine: Engine
    ) -> None:
        with (
            Session(postgres_setup_engine) as first,
            Session(postgres_setup_engine) as peer,
        ):
            config = build_system_config(first)
            cached = peer.get(SystemConfig, config.id)
            assert cached is not None
            assert cached.configured_at is None
            setup_bootstrap.lock_installation(first)
            config.configured_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
            first.commit()

            with pytest.raises(OperationError, match="^already_configured$") as exc:
                setup_bootstrap.lock_installation(peer)

            assert exc.value.kind is ErrorKind.CONFLICT


class TestFirstOwnerConcurrency:
    def test_two_sqlite_api_processes_create_exactly_one_owner(self, tmp_path):
        url = f"sqlite:///{tmp_path / 'first-owner.sqlite'}"
        engine = create_engine(url)
        SQLModel.metadata.create_all(engine)
        try:
            results = race_setup_workers(url, tmp_path)
            assert sorted(code for code, _ in results) == [201, 409], results
            with Session(engine) as session:
                assert (
                    len(session.exec(select(User).where(User.is_superuser)).all()) == 1
                )
        finally:
            engine.dispose()


@pytest.fixture
def environment_admin(monkeypatch: pytest.MonkeyPatch):
    """Set ``VAULT_SETUP_ADMIN_*`` the way an install form would."""

    def configure(
        username: str = ENV_USERNAME, password: str = ENV_PASSWORD, email: str = ""
    ) -> None:
        monkeypatch.setitem(_overlay, "setup_admin_username", username)
        monkeypatch.setitem(_overlay, "setup_admin_password", SecretStr(password))
        monkeypatch.setitem(_overlay, "setup_admin_email", email)

    return configure


class TestProvisionFromEnvironment:
    def test_creates_a_superuser_from_the_variables(
        self, db_session: Session, environment_admin
    ) -> None:
        environment_admin()

        setup_bootstrap.provision_from_environment(db_session)

        owner = db_session.exec(select(User)).one()
        assert (owner.username, owner.is_superuser) == (ENV_USERNAME, True)

    def test_provisioned_owner_signs_in_with_the_password(
        self, client: TestClient, db_session: Session, environment_admin
    ) -> None:
        environment_admin()
        setup_bootstrap.provision_from_environment(db_session)

        response = client.post(
            "/api/v1/auth/login",
            json={"username": ENV_USERNAME, "password": ENV_PASSWORD},
        )

        assert response.status_code == 200, response.text

    def test_records_the_optional_email(
        self, db_session: Session, environment_admin
    ) -> None:
        environment_admin(email=" owner@example.test ")

        setup_bootstrap.provision_from_environment(db_session)

        assert db_session.exec(select(User)).one().email == "owner@example.test"

    def test_trims_the_username(self, db_session: Session, environment_admin) -> None:
        environment_admin(username=f"  {ENV_USERNAME}  ")

        setup_bootstrap.provision_from_environment(db_session)

        assert db_session.exec(select(User)).one().username == ENV_USERNAME

    def test_closes_first_ownership(
        self, db_session: Session, environment_admin
    ) -> None:
        environment_admin()

        setup_bootstrap.provision_from_environment(db_session)

        assert runtime_config.is_configured(db_session) is True

    def test_leaves_storage_for_the_owner_to_choose(
        self, db_session: Session, environment_admin
    ) -> None:
        environment_admin()

        setup_bootstrap.provision_from_environment(db_session)

        config = db_session.get(SystemConfig, 1)
        assert setup_storage.choice_required(config) is True

    @pytest.mark.parametrize(
        ("username", "password"),
        [
            pytest.param("", "", id="unset"),
            pytest.param("   ", "", id="blank-form-fields"),
        ],
    )
    def test_does_nothing_without_the_variables(
        self, db_session: Session, environment_admin, username: str, password: str
    ) -> None:
        environment_admin(username=username, password=password)

        result = setup_bootstrap.provision_from_environment(db_session)

        assert (result, db_session.exec(select(User)).all()) == (None, [])

    @pytest.mark.parametrize(
        ("username", "password"),
        [
            pytest.param(ENV_USERNAME, "", id="username-only"),
            pytest.param("", ENV_PASSWORD, id="password-only"),
        ],
    )
    def test_refuses_half_a_credential(
        self,
        db_session: Session,
        environment_admin,
        caplog: pytest.LogCaptureFixture,
        username: str,
        password: str,
    ) -> None:
        environment_admin(username=username, password=password)

        setup_bootstrap.provision_from_environment(db_session)

        assert db_session.exec(select(User)).all() == []
        assert "must both be set" in caplog.text

    @pytest.mark.parametrize(
        ("username", "password", "field"),
        [
            pytest.param("ab", ENV_PASSWORD, "username", id="short-username"),
            pytest.param(ENV_USERNAME, "short", "password", id="short-password"),
        ],
    )
    def test_rejects_a_credential_below_the_wizard_minimum(
        self,
        db_session: Session,
        environment_admin,
        caplog: pytest.LogCaptureFixture,
        username: str,
        password: str,
        field: str,
    ) -> None:
        environment_admin(username=username, password=password)

        setup_bootstrap.provision_from_environment(db_session)

        assert db_session.exec(select(User)).all() == []
        assert f"rejected ({field})" in caplog.text

    def test_never_logs_a_rejected_password(
        self,
        db_session: Session,
        environment_admin,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        # A validation error echoes its input; the log must name the field only.
        environment_admin(password="leak-me")

        setup_bootstrap.provision_from_environment(db_session)

        assert "leak-me" not in caplog.text

    def test_never_logs_the_provisioned_password(
        self,
        db_session: Session,
        environment_admin,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        environment_admin()

        setup_bootstrap.provision_from_environment(db_session)

        assert ENV_PASSWORD not in caplog.text

    def test_leaves_an_existing_owner_untouched(
        self, db_session: Session, make_user, environment_admin
    ) -> None:
        make_user("existing-owner", superuser=True)
        environment_admin()

        setup_bootstrap.provision_from_environment(db_session)

        assert [user.username for user in db_session.exec(select(User))] == [
            "existing-owner"
        ]

    def test_never_resets_the_provisioned_password_on_a_later_start(
        self, client: TestClient, db_session: Session, environment_admin
    ) -> None:
        environment_admin()
        setup_bootstrap.provision_from_environment(db_session)
        environment_admin(password="EditedInTheStoreForm456")

        setup_bootstrap.provision_from_environment(db_session)

        response = client.post(
            "/api/v1/auth/login",
            json={"username": ENV_USERNAME, "password": ENV_PASSWORD},
        )
        assert response.status_code == 200, response.text

    def test_leaves_a_completed_installation_without_users_closed(
        self, db_session: Session, environment_admin
    ) -> None:
        # A completion marker never reopens first ownership, from either door.
        runtime_config.mark_configured(db_session)
        environment_admin()

        result = setup_bootstrap.provision_from_environment(db_session)

        assert (result, db_session.exec(select(User)).all()) == (None, [])
