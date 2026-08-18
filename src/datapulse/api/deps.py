"""Database session dependency for FastAPI."""

from sqlalchemy.orm import Session

from datapulse.db.engine import get_engine, get_session_factory, init_db

# Initialize database on import
_engine = None
_session_factory = None


def _get_or_create_engine():
    global _engine, _session_factory
    if _engine is None:
        _engine = init_db()
        _session_factory = get_session_factory(_engine)
    return _session_factory


def get_db():
    """
    FastAPI dependency — yields a database session.
    Automatically commits on success, rolls back on error.
    """
    factory = _get_or_create_engine()
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
