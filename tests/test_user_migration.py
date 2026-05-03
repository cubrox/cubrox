"""Migration cycle test for user + magic_link_token (revision 003).

Mirrors test_comprehension_cache_migration.py: verifies the migration
applies cleanly on a fresh DB, can be downgraded, and can be reapplied —
catching broken downgrade() before production.
"""

from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from alembic import command

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def alembic_cfg(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Config:
    db_path = tmp_path / "auth_migration_test.db"
    db_url = f"sqlite:///{db_path}"

    monkeypatch.setenv("DATABASE_URL", db_url)
    from app.config import get_settings

    get_settings.cache_clear()

    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", db_url)
    return cfg


def test_upgrade_creates_user_and_token_tables(alembic_cfg: Config) -> None:
    command.upgrade(alembic_cfg, "003")

    db_url = alembic_cfg.get_main_option("sqlalchemy.url")
    assert db_url is not None
    engine = create_engine(db_url)
    inspector = inspect(engine)

    table_names = inspector.get_table_names()
    assert "user" in table_names
    assert "magic_link_token" in table_names

    user_cols = {c["name"] for c in inspector.get_columns("user")}
    assert user_cols == {"id", "email", "created_at", "last_login"}

    user_pk = inspector.get_pk_constraint("user")
    assert user_pk["constrained_columns"] == ["id"]

    user_uniques = inspector.get_unique_constraints("user")
    assert any(set(c["column_names"]) == {"email"} for c in user_uniques)

    token_cols = {c["name"] for c in inspector.get_columns("magic_link_token")}
    assert token_cols == {"token_hash", "user_id", "expires_at", "consumed_at"}

    token_pk = inspector.get_pk_constraint("magic_link_token")
    assert token_pk["constrained_columns"] == ["token_hash"]

    token_fks = inspector.get_foreign_keys("magic_link_token")
    assert any(
        fk["referred_table"] == "user" and fk["referred_columns"] == ["id"]
        for fk in token_fks
    )


def test_upgrade_downgrade_upgrade_cycle(alembic_cfg: Config) -> None:
    command.upgrade(alembic_cfg, "003")
    command.downgrade(alembic_cfg, "002")

    db_url = alembic_cfg.get_main_option("sqlalchemy.url")
    assert db_url is not None
    engine = create_engine(db_url)
    inspector = inspect(engine)

    table_names = inspector.get_table_names()
    assert "user" not in table_names
    assert "magic_link_token" not in table_names
    # Earlier migrations untouched.
    assert "comprehension_question_cache" in table_names

    command.upgrade(alembic_cfg, "003")
    inspector = inspect(engine)
    assert "user" in inspector.get_table_names()
    assert "magic_link_token" in inspector.get_table_names()
