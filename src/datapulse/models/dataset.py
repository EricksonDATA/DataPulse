"""Dataset model — a source or target dataset within a pipeline."""

from sqlalchemy import Integer, String, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from datapulse.db.base import Base


class Dataset(Base):
    """
    A dataset that belongs to a pipeline.

    Example: 'inventory_snapshot' is a SOURCE dataset
    in the 'ecommerce_inventory' pipeline.
    """

    __tablename__ = "datasets"
    __table_args__ = (
        UniqueConstraint("pipeline_id", "name", name="uq_dataset_per_pipeline"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pipeline_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("pipelines.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False)  # 'source' or 'target'
    location: Mapped[str | None] = mapped_column(String, nullable=True)

    # Relationships
    pipeline: Mapped["Pipeline"] = relationship(back_populates="datasets")  # noqa: F821
    contracts: Mapped[list["Contract"]] = relationship(  # noqa: F821
        back_populates="dataset", cascade="all, delete-orphan"
    )
