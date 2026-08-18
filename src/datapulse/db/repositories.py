"""Repository layer — database operations for pipelines, datasets, and contracts."""

from sqlalchemy.orm import Session

from datapulse.models.pipeline import Pipeline
from datapulse.models.dataset import Dataset
from datapulse.models.contract import Contract


class PipelineRepository:
    """CRUD operations for pipelines."""

    def __init__(self, session: Session):
        self.session = session

    def get_or_create(self, name: str, owner: str) -> Pipeline:
        """Get an existing pipeline or create a new one."""
        pipeline = self.session.query(Pipeline).filter_by(name=name).first()
        if pipeline is None:
            pipeline = Pipeline(name=name, owner=owner)
            self.session.add(pipeline)
            self.session.flush()
        return pipeline

    def get_by_name(self, name: str) -> Pipeline | None:
        """Find a pipeline by name."""
        return self.session.query(Pipeline).filter_by(name=name).first()


class DatasetRepository:
    """CRUD operations for datasets."""

    def __init__(self, session: Session):
        self.session = session

    def get_or_create(
        self, pipeline_id: int, name: str, role: str, location: str | None = None
    ) -> Dataset:
        """Get an existing dataset or create a new one."""
        dataset = (
            self.session.query(Dataset)
            .filter_by(pipeline_id=pipeline_id, name=name)
            .first()
        )
        if dataset is None:
            dataset = Dataset(
                pipeline_id=pipeline_id, name=name, role=role, location=location
            )
            self.session.add(dataset)
            self.session.flush()
        return dataset

    def get_by_name(self, pipeline_id: int, name: str) -> Dataset | None:
        """Find a dataset by pipeline and name."""
        return (
            self.session.query(Dataset)
            .filter_by(pipeline_id=pipeline_id, name=name)
            .first()
        )


class ContractRepository:
    """CRUD operations for contracts."""

    def __init__(self, session: Session):
        self.session = session

    def get_or_create(
        self,
        dataset_id: int,
        version: int,
        schema_definition: dict,
        freshness: dict,
        quality_rules: dict,
    ) -> Contract:
        """Get an existing contract version or create a new one."""
        contract = (
            self.session.query(Contract)
            .filter_by(dataset_id=dataset_id, version=version)
            .first()
        )
        if contract is not None:
            return contract

        contract = Contract(
            dataset_id=dataset_id,
            version=version,
            schema_definition=schema_definition,
            freshness=freshness,
            quality_rules=quality_rules,
        )
        self.session.add(contract)
        self.session.flush()
        return contract

    def get_latest(self, dataset_id: int) -> Contract | None:
        """Get the most recent contract version for a dataset."""
        return (
            self.session.query(Contract)
            .filter_by(dataset_id=dataset_id)
            .order_by(Contract.version.desc())
            .first()
        )

    def get_by_version(self, dataset_id: int, version: int) -> Contract | None:
        """Get a specific contract version for a dataset."""
        return (
            self.session.query(Contract)
            .filter_by(dataset_id=dataset_id, version=version)
            .first()
        )
