"""Contract model — versioned schema and quality expectations for a dataset."""

from sqlalchemy import JSON, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from datapulse.db.base import Base


class Contract(Base):
    """
    A versioned data contract for a dataset.

    Stores the expected schema, freshness rules, and quality thresholds.
    Each version is immutable — a new contract version is a new row.
    """

    __tablename__ = "contracts"
    __table_args__ = (UniqueConstraint("dataset_id", "version", name="uq_contract_version_per_dataset"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dataset_id: Mapped[int] = mapped_column(Integer, ForeignKey("datasets.id"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    schema_definition: Mapped[dict] = mapped_column(JSON, nullable=False)
    freshness: Mapped[dict] = mapped_column(JSON, nullable=False)
    quality_rules: Mapped[dict] = mapped_column(JSON, nullable=False)

    # Relationships
    dataset: Mapped["Dataset"] = relationship(back_populates="contracts")  # noqa: F821
