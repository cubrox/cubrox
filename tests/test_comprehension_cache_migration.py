"""Migration cycle test for the comprehension question cache.

Validates that revision 002 applies cleanly on a fresh database, can be
downgraded, and can be reapplied — catching the common "downgrade is
broken" bug before it reaches production.
"""

from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from alembic import command

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def alembic_cfg(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Config:
    db_path = tmp_path / "migration_test.db"
    db_url = f"sqlite:///{db_path}"

    # Settings reads DATABASE_URL via env; alembic/env.py reads it from Settings.
    # get_settings is lru-cached, so clear the cache so this test's URL is picked up.
    monkeypatch.setenv("DATABASE_URL", db_url)
    from app.config import get_settings

    get_settings.cache_clear()

    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", db_url)
    return cfg


def test_upgrade_creates_table_with_composite_pk(alembic_cfg: Config) -> None:
    command.upgrade(alembic_cfg, "002")

    db_url = alembic_cfg.get_main_option("sqlalchemy.url")
    assert db_url is not None
    engine = create_engine(db_url)
    inspector = inspect(engine)

    assert "comprehension_question_cache" in inspector.get_table_names()
    pk = inspector.get_pk_constraint("comprehension_question_cache")
    assert set(pk["constrained_columns"]) == {
        "passage_hash",
        "question_type",
        "model_id",
        "prompt_version",
    }


def test_upgrade_downgrade_upgrade_cycle(alembic_cfg: Config) -> None:
    command.upgrade(alembic_cfg, "002")
    command.downgrade(alembic_cfg, "001")

    db_url = alembic_cfg.get_main_option("sqlalchemy.url")
    assert db_url is not None
    engine = create_engine(db_url)
    inspector = inspect(engine)
    assert "comprehension_question_cache" not in inspector.get_table_names()

    command.upgrade(alembic_cfg, "002")
    inspector = inspect(engine)
    assert "comprehension_question_cache" in inspector.get_table_names()
