"""Database engine and session factory for DataPulse."""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from datapulse.db.base import Base


def get_engine(url: str | None = None):
    """Create a SQLAlchemy engine. Uses config DATABASE_URL if no url provided."""
    if url is None:
        from datapulse.config import DATABASE_URL

        url = DATABASE_URL
    return create_engine(url, echo=False)


def get_session_factory(engine=None):
    """Create a session factory bound to the engine."""
    if engine is None:
        engine = get_engine()
    return sessionmaker(bind=engine)


def init_db(engine=None):
    """Create all tables if they don't exist. For test setup only — use migrations in production."""
    if engine is None:
        engine = get_engine()
    # Import all models so Base.metadata knows about them
    import datapulse.models  # noqa: F401

    Base.metadata.create_all(engine)
    return engine
