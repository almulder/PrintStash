"""Choosing storage after the first owner already exists.

An owner provisioned from ``VAULT_SETUP_ADMIN_*`` signs in before any storage has
been chosen, so the choice the browser wizard makes in one request happens here in a
second one. Two properties matter. The choice is checked before it is persisted, so a
mistyped remote setting is refused and the owner can try again. And once storage has
been chosen it cannot be chosen again through this path, which would otherwise be a
way to repoint a live vault at an empty directory.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlmodel import Session

from app.core.config import _overlay
from app.core.errors import ErrorKind, OperationError
from app.db.models import SystemConfig
from app.modules.administration import setup_storage
from app.modules.storage.storage_backend.runtime import get_backend
from app.schemas.setup import SetupStorageRequest

CONFIGURED_AT = datetime(2026, 1, 1, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def runtime_dirs(tmp_path: Path) -> Path:
    """Point every managed root at the test's own tmp dir."""
    _overlay["staging_dir"] = tmp_path / "staging"
    _overlay["backup_dir"] = tmp_path / "backups"
    _overlay["data_dir"] = tmp_path / "files"
    _overlay["thumb_dir"] = tmp_path / "thumbs"
    return tmp_path


@pytest.fixture
def provisioned_owner(make_user, make_system_config) -> SystemConfig:
    """What startup leaves behind for ``VAULT_SETUP_ADMIN_*``: an owner, no storage."""
    make_user("store-owner", superuser=True)
    return make_system_config(configured_at=CONFIGURED_AT, setup_storage_pending=True)


def _local_choice(root: Path) -> SetupStorageRequest:
    return SetupStorageRequest(
        storage_backend="local",
        data_dir=str(root / "chosen-files"),
        thumb_dir=str(root / "chosen-thumbs"),
    )


class TestChoiceRequired:
    def test_holds_for_an_owner_without_storage(
        self, provisioned_owner: SystemConfig
    ) -> None:
        assert setup_storage.choice_required(provisioned_owner) is True

    def test_does_not_hold_before_the_installation_has_an_owner(
        self, make_system_config
    ) -> None:
        config = make_system_config(setup_storage_pending=True)

        assert setup_storage.choice_required(config) is False

    def test_does_not_hold_without_a_configuration_row(self) -> None:
        assert setup_storage.choice_required(None) is False

    @pytest.mark.parametrize(
        "source",
        [
            pytest.param({"storage_backend": "local"}, id="local-backend"),
            pytest.param({"storage_provider": "webdav"}, id="typed-provider"),
        ],
    )
    def test_does_not_hold_once_a_storage_source_is_persisted(
        self, make_system_config, source: dict[str, str]
    ) -> None:
        # Chosen but not yet activated is a retry, never a second choice.
        config = make_system_config(
            configured_at=CONFIGURED_AT, setup_storage_pending=True, **source
        )

        assert setup_storage.choice_required(config) is False

    def test_does_not_hold_once_storage_is_prepared(self, make_system_config) -> None:
        config = make_system_config(configured_at=CONFIGURED_AT)

        assert setup_storage.choice_required(config) is False


class TestChoose:
    def test_activates_the_chosen_local_storage(
        self, db_session: Session, provisioned_owner: SystemConfig, tmp_path: Path
    ) -> None:
        setup_storage.choose(db_session, _local_choice(tmp_path))

        backend = get_backend()
        destination = tmp_path / "chosen-files" / "first-upload.bin"
        backend.create_bytes(b"ready", str(destination))
        assert destination.read_bytes() == b"ready"

    def test_finishes_the_pending_setup(
        self, db_session: Session, provisioned_owner: SystemConfig, tmp_path: Path
    ) -> None:
        setup_storage.choose(db_session, _local_choice(tmp_path))

        assert db_session.get(SystemConfig, 1).setup_storage_pending is False

    def test_pins_the_chosen_roots(
        self, db_session: Session, provisioned_owner: SystemConfig, tmp_path: Path
    ) -> None:
        # An unpinned root would let a later environment change reinterpret the
        # stored rows against a different mount.
        setup_storage.choose(db_session, _local_choice(tmp_path))

        config = db_session.get(SystemConfig, 1)
        assert config.data_dir == str((tmp_path / "chosen-files").resolve())

    def test_refuses_a_second_choice(
        self, db_session: Session, provisioned_owner: SystemConfig, tmp_path: Path
    ) -> None:
        setup_storage.choose(db_session, _local_choice(tmp_path))

        with pytest.raises(
            OperationError, match="^setup_storage_already_chosen$"
        ) as exc:
            setup_storage.choose(db_session, _local_choice(tmp_path / "elsewhere"))

        assert exc.value.kind is ErrorKind.CONFLICT

    def test_refuses_a_populated_root_without_persisting_it(
        self, db_session: Session, provisioned_owner: SystemConfig, tmp_path: Path
    ) -> None:
        populated = tmp_path / "chosen-files"
        populated.mkdir()
        (populated / "someone-elses-model.stl").write_text("solid")

        with pytest.raises(OperationError, match="^data_dir_not_empty$"):
            setup_storage.choose(db_session, _local_choice(tmp_path))

        db_session.expire_all()
        assert setup_storage.choice_required(db_session.get(SystemConfig, 1)) is True

    def test_refuses_unreachable_remote_storage_without_persisting_it(
        self, db_session: Session, provisioned_owner: SystemConfig
    ) -> None:
        # The integration socket guard refuses the connection, as a mistyped
        # endpoint would.
        unreachable = SetupStorageRequest(
            storage_backend="s3",
            s3_bucket="typo-bucket",
            s3_endpoint_url="http://127.0.0.1:9",
        )

        with pytest.raises(OperationError, match="^setup_remote_storage_unavailable$"):
            setup_storage.choose(db_session, unreachable)

        db_session.expire_all()
        assert setup_storage.choice_required(db_session.get(SystemConfig, 1)) is True
