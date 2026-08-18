"""SQLAlchemy base class for all DataPulse models."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Shared base for every table in the control database."""
    pass
