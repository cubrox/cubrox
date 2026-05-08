"""Migration cycle test for the passage table (revision 004).

Mirrors test_user_migration.py and test_comprehension_cache_migration.py:
verifies the migration applies cleanly on a fresh DB, can be downgraded,
and can be reapplied — catching a broken downgrade() before production.
"""

from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from alembic import command

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def alembic_cfg(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Config:
    db_path = tmp_path / "passage_migration_test.db"
    db_url = f"sqlite:///{db_path}"

    monkeypatch.setenv("DATABASE_URL", db_url)
    from app.config import get_settings

    get_settings.cache_clear()

    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", db_url)
    return cfg


def test_upgrade_creates_passage_table_with_columns_and_fk(alembic_cfg: Config) -> None:
    command.upgrade(alembic_cfg, "004")

    db_url = alembic_cfg.get_main_option("sqlalchemy.url")
    assert db_url is not None
    engine = create_engine(db_url)
    inspector = inspect(engine)

    assert "passage" in inspector.get_table_names()

    cols = {c["name"] for c in inspector.get_columns("passage")}
    assert cols == {
        "id",
        "user_id",
        "text",
        "text_hash",
        "source_type",
        "source_filename",
        "created_at",
    }

    fks = inspector.get_foreign_keys("passage")
    assert any(fk["referred_table"] == "user" and fk["referred_columns"] == ["id"] for fk in fks)

    indexes = {ix["name"] for ix in inspector.get_indexes("passage")}
    assert "ix_passage_text_hash" in indexes
    assert "ix_passage_user_id_created_at" in indexes


def test_upgrade_downgrade_upgrade_cycle(alembic_cfg: Config) -> None:
    command.upgrade(alembic_cfg, "004")
    command.downgrade(alembic_cfg, "003")

    db_url = alembic_cfg.get_main_option("sqlalchemy.url")
    assert db_url is not None
    engine = create_engine(db_url)
    inspector = inspect(engine)

    table_names = inspector.get_table_names()
    assert "passage" not in table_names
    # Earlier migrations untouched.
    assert "user" in table_names
    assert "magic_link_token" in table_names
    assert "comprehension_question_cache" in table_names

    command.upgrade(alembic_cfg, "004")
    inspector = inspect(engine)
    assert "passage" in inspector.get_table_names()
