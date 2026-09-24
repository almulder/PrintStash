"""An existing Artifact survives PostgreSQL's native-enum to text upgrade."""

from uuid import uuid4

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import make_url
from sqlmodel import Session, select

from alembic import command
from app.db.migrate import _alembic_config
from app.db.models import File, FileType, Model
from app.db.url import normalize_database_url
from tests.factories.migration_rows import (
    RELEASED_V0121_REVISION,
    create_released_v0121_postgres_schema,
)

PREDECESSOR = "a23d2e57ff0c"
REVISION = "6f27f2e6090a"


def _exercise_upgrade(url: str, *, postgres: bool) -> None:
    config = _alembic_config(url)
    engine = create_engine(url)
    try:
        if postgres:
            with engine.begin() as connection:
                create_released_v0121_postgres_schema(connection)
            command.stamp(config, RELEASED_V0121_REVISION)
        command.upgrade(config, PREDECESSOR)
        with Session(engine) as session:
            model = Model(name="Existing", slug="dxf-migration-existing", hash="a" * 64)
            session.add(model)
            session.flush()
            session.add(
                File(
                    model_id=model.id,
                    path="/library/existing.stl",
                    original_filename="existing.stl",
                    file_type=FileType.STL,
                    version=1,
                    size_bytes=3,
                    sha256="b" * 64,
                )
            )
            session.commit()

        command.upgrade(config, REVISION)

        with Session(engine) as session:
            existing = session.exec(
                select(File).where(File.original_filename == "existing.stl")
            ).one()
            assert existing.file_type == FileType.STL
            assert existing.sha256 == "b" * 64
            session.add(
                File(
                    model_id=existing.model_id,
                    path="/library/drawing.dxf",
                    original_filename="drawing.dxf",
                    file_type=FileType.DXF,
                    version=2,
                    size_bytes=12,
                    sha256="c" * 64,
                )
            )
            session.commit()
            assert session.exec(
                select(File).where(File.file_type == FileType.DXF)
            ).one().original_filename == "drawing.dxf"

        indexes = {row["name"] for row in inspect(engine).get_indexes("files")}
        assert "uq_files_live_recommended_gcode_text" in indexes
        with pytest.raises(RuntimeError, match="DXF Artifacts"):
            command.downgrade(config, "-1")
        with Session(engine) as session:
            assert {row.original_filename for row in session.exec(select(File))} == {
                "existing.stl", "drawing.dxf"
            }
    finally:
        engine.dispose()


class TestDxfFiletypeMigration:
    def test_sqlite_upgrade_preserves_existing_artifact(self, tmp_path) -> None:
        _exercise_upgrade(f"sqlite:///{tmp_path / 'dxf-upgrade.sqlite'}", postgres=False)

    @pytest.mark.postgres
    def test_postgres_upgrade_preserves_existing_artifact(self) -> None:
        from tests.containers import postgres_url

        root_url = normalize_database_url(postgres_url())
        database = f"dxf_upgrade_{uuid4().hex}"
        admin = create_engine(root_url, isolation_level="AUTOCOMMIT")
        with admin.connect() as connection:
            connection.exec_driver_sql(f'CREATE DATABASE "{database}"')
        isolated_url = (
            make_url(root_url)
            .set(database=database)
            .render_as_string(hide_password=False)
        )
        try:
            _exercise_upgrade(isolated_url, postgres=True)
        finally:
            with admin.connect() as connection:
                connection.exec_driver_sql(f'DROP DATABASE "{database}" WITH (FORCE)')
            admin.dispose()
