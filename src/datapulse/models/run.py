"""PipelineRun model — one execution attempt of a pipeline."""

import enum
from datetime import datetime

from sqlalchemy import Integer, String, DateTime, Enum, ForeignKey, UniqueConstraint, Text, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from datapulse.db.base import Base


class RunStatus(str, enum.Enum):
    """Possible states for a pipeline run."""

    REGISTERED = "registered"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    LATE = "late"


class PipelineRun(Base):
    """
    A single pipeline execution attempt.

    Identified by (pipeline_id, run_id) — submitting the same
    run_id twice must NOT create a duplicate row.
    """

    __tablename__ = "pipeline_runs"
    __table_args__ = (
        UniqueConstraint("pipeline_id", "run_id", name="uq_run_per_pipeline"),
        Index("ix_runs_pipeline_started", "pipeline_id", "started_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pipeline_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("pipelines.id"), nullable=False
    )
    run_id: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[RunStatus] = mapped_column(
        Enum(RunStatus), default=RunStatus.REGISTERED, nullable=False
    )
    source_row_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    target_row_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    contract_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Relationships
    pipeline: Mapped["Pipeline"] = relationship(back_populates="runs")  # noqa: F821
    check_results: Mapped[list["CheckResult"]] = relationship(  # noqa: F821
        back_populates="pipeline_run", cascade="all, delete-orphan"
    )
    incidents: Mapped[list["Incident"]] = relationship(  # noqa: F821
        back_populates="pipeline_run", cascade="all, delete-orphan"
    )
