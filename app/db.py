"""Database session management.

Uses SQLModel (Pydantic + SQLAlchemy) with connection pooling suitable
for Cloud Run. The pool is small because Cloud Run instances are
short-lived and Supabase's pooler (Supavisor) handles cross-instance
pooling. `DATABASE_URL` should be the pooled connection string from
Supabase Dashboard → Project Settings → Database.
"""

from collections.abc import Generator

from sqlmodel import Session, SQLModel, create_engine

from app.config import get_settings

_settings = get_settings()

# Small pool: Cloud Run instances are ephemeral; Supabase's pooled URL
# (Supavisor) handles global connection multiplexing. Never use the
# direct DB URL from Cloud Run — exhausts connections fast. See
# docs/PATTERN-LIBRARY.md.
engine = create_engine(
    _settings.database_url,
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,  # Reconnect after pooler drops idle conns
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
