"""Database session management.

Uses SQLModel (Pydantic + SQLAlchemy) with connection pooling suitable for
Cloud Run. The pool is small because Cloud Run instances are short-lived
and Neon's PgBouncer pooled endpoint handles cross-instance pooling.
"""

from collections.abc import Generator

from sqlmodel import Session, SQLModel, create_engine

from app.config import get_settings

_settings = get_settings()

# Small pool: Cloud Run instances are ephemeral, Neon's pooled URL handles
# global connection multiplexing. Never use the direct Neon URL from
# Cloud Run — exhausts connections fast. See docs/PATTERN-LIBRARY.md.
engine = create_engine(
    _settings.database_url,
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,  # Neon compute wakes on first query; pre-ping reconnects
    pool_recycle=300,
)


def get_session() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a database session."""
    with Session(engine) as session:
        yield session


def create_db_and_tables() -> None:
    """Create all tables. Used for tests and local dev.

    In production, Supabase CLI migrations (`supabase/migrations/*.sql`)
    are the source of truth — do NOT call this on startup.
    """
    SQLModel.metadata.create_all(engine)
