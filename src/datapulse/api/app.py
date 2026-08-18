"""API routes — the 6 DataPulse endpoints."""

from pathlib import Path

from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session

from datapulse.api.deps import get_db
from datapulse.logging_config import setup_logging
from datapulse.api.schemas import (
    PipelineCreate,
    DatasetCreate,
    RunSubmit,
    HealthResponse,
    PipelineResponse,
    DatasetResponse,
    RunHealthResponse,
)
from datapulse.db.repositories import PipelineRepository, DatasetRepository, ContractRepository
from datapulse.db.run_repositories import RunRepository, IncidentRepository, CheckResultRepository
from datapulse.services.run_service import RunService

app = FastAPI(
    title="DataPulse",
    description="Data contract and pipeline observability platform",
    version="0.1.0",
)

# Initialize structured logging
setup_logging()


# ── GET /health ─────────────────────────────────────────────────

@app.get("/health", response_model=HealthResponse)
def health():
    """Confirm the API is available."""
    return HealthResponse(status="ok", version="0.1.0")


# ── POST /pipelines ─────────────────────────────────────────────

@app.post("/pipelines", response_model=PipelineResponse, status_code=201)
def register_pipeline(data: PipelineCreate, db: Session = Depends(get_db)):
    """Register a new pipeline."""
    repo = PipelineRepository(db)
    pipeline = repo.get_or_create(name=data.name, owner=data.owner)
    return PipelineResponse(
        id=pipeline.id,
        name=pipeline.name,
        owner=pipeline.owner,
        enabled=pipeline.enabled,
    )


# ── POST /datasets ──────────────────────────────────────────────

@app.post("/datasets", response_model=DatasetResponse, status_code=201)
def register_dataset(data: DatasetCreate, db: Session = Depends(get_db)):
    """Register a dataset and its contract for a pipeline."""
    pipeline_repo = PipelineRepository(db)
    pipeline = pipeline_repo.get_by_name(data.pipeline_name)
    if pipeline is None:
        raise HTTPException(status_code=404, detail=f"Pipeline '{data.pipeline_name}' not found. Register it first.")

    dataset_repo = DatasetRepository(db)
    dataset = dataset_repo.get_or_create(
        pipeline_id=pipeline.id,
        name=data.dataset_name,
        role=data.role,
        location=data.location,
    )

    contract_repo = ContractRepository(db)
    contract = contract_repo.get_or_create(
        dataset_id=dataset.id,
        version=data.contract_version,
        schema_definition=data.schema_definition,
        freshness=data.freshness,
        quality_rules=data.quality_rules,
    )

    return DatasetResponse(
        dataset_id=dataset.id,
        dataset_name=dataset.name,
        contract_id=contract.id,
        contract_version=contract.version,
    )


# ── POST /runs ──────────────────────────────────────────────────

@app.post("/runs", response_model=RunHealthResponse, status_code=201)
def submit_run(data: RunSubmit, db: Session = Depends(get_db)):
    """Submit a pipeline run. Idempotent — same run_id returns existing result."""
    source_path = Path(data.source_path)
    target_path = Path(data.target_path) if data.target_path else None
    service = RunService(db)

    try:
        result = service.submit_run(
            pipeline_name=data.pipeline_name,
            run_id=data.run_id,
            source_path=source_path,
            target_path=target_path,
            dataset_name=data.dataset_name,
            target_dataset_name=data.target_dataset_name,
            contract_version=data.contract_version,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return RunHealthResponse(**result)


# ── GET /pipelines/{name}/runs/{run_id} ─────────────────────────

@app.get("/pipelines/{name}/runs/{run_id}", response_model=RunHealthResponse)
def get_run_health(name: str, run_id: str, db: Session = Depends(get_db)):
    """Retrieve one run's health summary."""
    pipeline_repo = PipelineRepository(db)
    pipeline = pipeline_repo.get_by_name(name)
    if pipeline is None:
        raise HTTPException(status_code=404, detail=f"Pipeline '{name}' not found.")

    run_repo = RunRepository(db)
    run = run_repo.find_by_pipeline_and_run_id(pipeline.id, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found for pipeline '{name}'.")

    service = RunService(db)
    return RunHealthResponse(**service._build_health_summary(run))


# ── GET /pipelines/{name}/health ────────────────────────────────

@app.get("/pipelines/{name}/health", response_model=RunHealthResponse)
def get_pipeline_health(name: str, db: Session = Depends(get_db)):
    """Retrieve the latest health for a pipeline."""
    pipeline_repo = PipelineRepository(db)
    pipeline = pipeline_repo.get_by_name(name)
    if pipeline is None:
        raise HTTPException(status_code=404, detail=f"Pipeline '{name}' not found.")

    run_repo = RunRepository(db)
    run = run_repo.get_latest_for_pipeline(pipeline.id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"No runs found for pipeline '{name}'.")

    service = RunService(db)
    return RunHealthResponse(**service._build_health_summary(run))
