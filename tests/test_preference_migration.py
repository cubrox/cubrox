"""Migration cycle test for the preference table (revision 005).

Mirrors the AUTH-1 / COMP-1 / INGEST-1 migration tests: verifies the
migration applies cleanly on a fresh DB, can be downgraded, and can be
reapplied.
"""

from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from alembic import command

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def alembic_cfg(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Config:
    db_path = tmp_path / "preference_migration_test.db"
    db_url = f"sqlite:///{db_path}"

    monkeypatch.setenv("DATABASE_URL", db_url)
    from app.config import get_settings

    get_settings.cache_clear()

    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", db_url)
    return cfg


def test_upgrade_creates_preference_table(alembic_cfg: Config) -> None:
    command.upgrade(alembic_cfg, "005")

    db_url = alembic_cfg.get_main_option("sqlalchemy.url")
    assert db_url is not None
    engine = create_engine(db_url)
    inspector = inspect(engine)

    assert "preference" in inspector.get_table_names()

    cols = {c["name"] for c in inspector.get_columns("preference")}
    assert cols == {"user_id", "values", "updated_at"}

    pk = inspector.get_pk_constraint("preference")
    assert pk["constrained_columns"] == ["user_id"]

    fks = inspector.get_foreign_keys("preference")
    assert any(fk["referred_table"] == "user" and fk["referred_columns"] == ["id"] for fk in fks)


def test_upgrade_downgrade_upgrade_cycle(alembic_cfg: Config) -> None:
    command.upgrade(alembic_cfg, "005")
    command.downgrade(alembic_cfg, "004")

    db_url = alembic_cfg.get_main_option("sqlalchemy.url")
    assert db_url is not None
    engine = create_engine(db_url)
    inspector = inspect(engine)

    assert "preference" not in inspector.get_table_names()
    # Earlier migrations untouched.
    assert "passage" in inspector.get_table_names()
    assert "user" in inspector.get_table_names()

    command.upgrade(alembic_cfg, "005")
    inspector = inspect(engine)
    assert "preference" in inspector.get_table_names()
