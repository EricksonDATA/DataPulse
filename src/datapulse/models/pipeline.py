"""Pipeline model — a registered data pipeline."""

from sqlalchemy import Integer, String, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship

from datapulse.db.base import Base


class Pipeline(Base):
    """
    A registered pipeline that DataPulse monitors.

    Example: 'ecommerce_inventory' owned by 'data-platform'.
    Each pipeline can have many datasets and many runs.
    """

    __tablename__ = "pipelines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    owner: Mapped[str] = mapped_column(String, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships — access pipeline.datasets, pipeline.runs
    datasets: Mapped[list["Dataset"]] = relationship(  # noqa: F821
        back_populates="pipeline", cascade="all, delete-orphan"
    )
    runs: Mapped[list["PipelineRun"]] = relationship(  # noqa: F821
        back_populates="pipeline", cascade="all, delete-orphan"
    )
