"""Migration cycle test for the rate_bucket table (revision 006).

Mirrors the existing migration tests: verifies the migration applies
cleanly on a fresh DB, can be downgraded, and can be reapplied.
"""

from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from alembic import command

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def alembic_cfg(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Config:
    db_path = tmp_path / "rate_bucket_migration_test.db"
    db_url = f"sqlite:///{db_path}"

    monkeypatch.setenv("DATABASE_URL", db_url)
    from app.config import get_settings

    get_settings.cache_clear()

    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", db_url)
    return cfg


def test_upgrade_creates_rate_bucket_table(alembic_cfg: Config) -> None:
    command.upgrade(alembic_cfg, "006")

    db_url = alembic_cfg.get_main_option("sqlalchemy.url")
    assert db_url is not None
    engine = create_engine(db_url)
    inspector = inspect(engine)

    assert "rate_bucket" in inspector.get_table_names()

    cols = {c["name"] for c in inspector.get_columns("rate_bucket")}
    assert cols == {"key", "tokens", "refilled_at"}

    pk = inspector.get_pk_constraint("rate_bucket")
    assert pk["constrained_columns"] == ["key"]


def test_upgrade_downgrade_upgrade_cycle(alembic_cfg: Config) -> None:
    command.upgrade(alembic_cfg, "006")
    command.downgrade(alembic_cfg, "005")

    db_url = alembic_cfg.get_main_option("sqlalchemy.url")
    assert db_url is not None
    engine = create_engine(db_url)
    inspector = inspect(engine)

    assert "rate_bucket" not in inspector.get_table_names()
    # Earlier migrations untouched.
    assert "preference" in inspector.get_table_names()
    assert "user" in inspector.get_table_names()

    command.upgrade(alembic_cfg, "006")
    inspector = inspect(engine)
    assert "rate_bucket" in inspector.get_table_names()
