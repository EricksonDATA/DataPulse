"""Incident model — an actionable failure record."""

import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from datapulse.db.base import Base


class IncidentSeverity(str, enum.Enum):
    """How urgent the incident is."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class IncidentStatus(str, enum.Enum):
    """Lifecycle of an incident."""

    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"


class Incident(Base):
    """
    An actionable failure record created when a run fails,
    arrives late, or violates a contract.

    Links back to the run and the check that caused it.
    """

    __tablename__ = "incidents"
    __table_args__ = (Index("ix_incidents_status_owner", "status", "owner"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pipeline_run_id: Mapped[int] = mapped_column(Integer, ForeignKey("pipeline_runs.id"), nullable=False)
    incident_type: Mapped[str] = mapped_column(String, nullable=False)
    severity: Mapped[IncidentSeverity] = mapped_column(Enum(IncidentSeverity), nullable=False)
    owner: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[IncidentStatus] = mapped_column(Enum(IncidentStatus), default=IncidentStatus.OPEN, nullable=False)
    retryable: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    failure_summary: Mapped[str | None] = mapped_column(String, nullable=True)
    first_observed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    # Relationships
    pipeline_run: Mapped["PipelineRun"] = relationship(back_populates="incidents")  # noqa: F821
