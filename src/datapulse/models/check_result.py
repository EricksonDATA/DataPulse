"""CheckResult model — the outcome of a single validation check."""

import enum

from sqlalchemy import Integer, String, JSON, Enum, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from datapulse.db.base import Base


class CheckStatus(str, enum.Enum):
    """Possible states for a check result."""

    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"


class CheckType(str, enum.Enum):
    """Types of checks DataPulse can run."""

    SOURCE_READABILITY = "source_readability"
    SCHEMA_COMPATIBILITY = "schema_compatibility"
    TARGET_SCHEMA_COMPATIBILITY = "target_schema_compatibility"
    ROW_COUNT = "row_count"
    FRESHNESS = "freshness"


class CheckResult(Base):
    """
    The outcome of one validation check against a pipeline run.

    Stores both the expected and observed values so failures
    are explainable without re-running anything.
    """

    __tablename__ = "check_results"
    __table_args__ = (
        Index("ix_checks_run_type", "pipeline_run_id", "check_type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pipeline_run_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("pipeline_runs.id"), nullable=False
    )
    check_type: Mapped[CheckType] = mapped_column(Enum(CheckType), nullable=False)
    status: Mapped[CheckStatus] = mapped_column(Enum(CheckStatus), nullable=False)
    expected: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    observed: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    message: Mapped[str | None] = mapped_column(String, nullable=True)

    # Relationships
    pipeline_run: Mapped["PipelineRun"] = relationship(back_populates="check_results")  # noqa: F821
