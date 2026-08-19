"""API routes — DataPulse endpoints."""

import logging

from fastapi import Depends, FastAPI, HTTPException, Request
from sqlalchemy.orm import Session

from datapulse.api.auth import get_api_key
from datapulse.api.deps import get_db
from datapulse.api.schemas import (
    ContractSummary,
    DatasetCreate,
    DatasetResponse,
    HealthResponse,
    IncidentListItem,
    PipelineCreate,
    PipelineResponse,
    ReadyResponse,
    RunHealthResponse,
    RunListItem,
    RunSubmit,
)
from datapulse.db.repositories import ContractRepository, DatasetRepository, PipelineRepository
from datapulse.db.run_repositories import IncidentRepository, RunRepository
from datapulse.logging_config import setup_logging
from datapulse.services.run_service import RunService

app = FastAPI(
    title="DataPulse",
    description="Data contract and pipeline observability platform",
    version="0.1.0",
)

# Initialize structured logging
setup_logging()
logger = logging.getLogger("datapulse.api")


# ── GET /health ─────────────────────────────────────────────────


@app.get("/health", response_model=HealthResponse)
def health():
    """Confirm the API is available."""
    return HealthResponse(status="ok", version="0.1.0")


# ── POST /pipelines ─────────────────────────────────────────────


@app.post("/pipelines", response_model=PipelineResponse, status_code=201)
def register_pipeline(data: PipelineCreate, db: Session = Depends(get_db), api_key: str = Depends(get_api_key)):
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
def register_dataset(data: DatasetCreate, db: Session = Depends(get_db), api_key: str = Depends(get_api_key)):
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
def submit_run(data: RunSubmit, db: Session = Depends(get_db), api_key: str = Depends(get_api_key)):
    """Submit a pipeline run. Idempotent — same run_id returns existing result."""
    from pathlib import Path

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
def get_run_health(name: str, run_id: str, db: Session = Depends(get_db), api_key: str = Depends(get_api_key)):
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
def get_pipeline_health(name: str, db: Session = Depends(get_db), api_key: str = Depends(get_api_key)):
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


# ── GET /pipelines/{name}/runs ─────────────────────────────────


@app.get("/pipelines/{name}/runs", response_model=list[RunListItem])
def list_pipeline_runs(
    name: str,
    status: str | None = None,
    limit: int = 20,
    offset: int = 0,
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key),
):
    """List recent runs for a pipeline with optional status filter."""
    pipeline_repo = PipelineRepository(db)
    pipeline = pipeline_repo.get_by_name(name)
    if pipeline is None:
        raise HTTPException(status_code=404, detail=f"Pipeline '{name}' not found.")

    run_repo = RunRepository(db)
    runs = run_repo.get_runs_for_pipeline(
        pipeline_id=pipeline.id,
        status=status,
        limit=min(limit, 100),
        offset=offset,
    )

    result = []
    for run in runs:
        duration_ms = None
        if run.started_at and run.ended_at:
            duration_ms = int((run.ended_at - run.started_at).total_seconds() * 1000)
        result.append(
            RunListItem(
                run_id=run.run_id,
                status=run.status.value,
                started_at=run.started_at.isoformat() if run.started_at else None,
                ended_at=run.ended_at.isoformat() if run.ended_at else None,
                duration_ms=duration_ms,
                source_row_count=run.source_row_count,
                target_row_count=run.target_row_count,
                failure_reason=run.failure_reason,
                contract_version=run.contract_version,
            )
        )
    return result


# ── GET /pipelines/{name}/incidents ────────────────────────────


@app.get("/pipelines/{name}/incidents", response_model=list[IncidentListItem])
def list_pipeline_incidents(
    name: str,
    limit: int = 20,
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key),
):
    """List open incidents for a pipeline."""
    pipeline_repo = PipelineRepository(db)
    pipeline = pipeline_repo.get_by_name(name)
    if pipeline is None:
        raise HTTPException(status_code=404, detail=f"Pipeline '{name}' not found.")

    incident_repo = IncidentRepository(db)
    incidents = incident_repo.get_open_for_pipeline(
        pipeline_id=pipeline.id,
        limit=min(limit, 100),
    )

    return [
        IncidentListItem(
            id=inc.id,
            run_id=inc.pipeline_run.run_id,
            incident_type=inc.incident_type,
            severity=inc.severity.value,
            status=inc.status.value,
            owner=inc.owner,
            retryable=inc.retryable,
            failure_summary=inc.failure_summary,
            first_observed_at=inc.first_observed_at.isoformat() if inc.first_observed_at else None,
        )
        for inc in incidents
    ]


# ── GET /datasets/{name}/contract ──────────────────────────────


@app.get("/datasets/{name}/contract", response_model=ContractSummary)
def get_dataset_contract(
    name: str,
    pipeline_name: str | None = None,
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key),
):
    """Retrieve the active contract summary for a dataset."""
    dataset_repo = DatasetRepository(db)
    contract_repo = ContractRepository(db)

    dataset = None
    if pipeline_name:
        pipeline = PipelineRepository(db).get_by_name(pipeline_name)
        if pipeline:
            dataset = dataset_repo.get_by_name(pipeline.id, name)
    else:
        from datapulse.models.dataset import Dataset as DatasetModel

        dataset = db.query(DatasetModel).filter_by(name=name).first()

    if dataset is None:
        raise HTTPException(status_code=404, detail=f"Dataset '{name}' not found.")

    contract = contract_repo.get_latest(dataset.id)
    if contract is None:
        raise HTTPException(status_code=404, detail=f"No contract found for dataset '{name}'.")

    freshness = contract.freshness or {}
    return ContractSummary(
        dataset_name=dataset.name,
        role=dataset.role,
        contract_version=contract.version,
        schema_columns=list((contract.schema_definition or {}).keys()),
        freshness_max_age_hours=freshness.get("max_age_hours"),
        quality_rules=contract.quality_rules,
    )


# ── GET /ready ─────────────────────────────────────────────────


@app.get("/ready", response_model=ReadyResponse)
def readiness(db: Session = Depends(get_db)):
    """Confirm the API and database are ready."""
    try:
        from sqlalchemy import text

        db.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception:
        db_status = "unavailable"
    return ReadyResponse(
        status="ok" if db_status == "ok" else "degraded",
        database=db_status,
        version="0.2.0",
    )


# ── POST /runs/{run_id}/acknowledge ────────────────────────────


@app.post("/runs/{run_id}/acknowledge")
def acknowledge_run(run_id: str, db: Session = Depends(get_db), api_key: str = Depends(get_api_key)):
    """Acknowledge a run's incidents — marks them as acknowledged."""
    run_repo = RunRepository(db)
    run = run_repo.find_by_run_id(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found.")

    incident_repo = IncidentRepository(db)
    incidents = incident_repo.get_for_run(run.id)
    acknowledged = 0
    for inc in incidents:
        from datapulse.models.incident import IncidentStatus

        if inc.status == IncidentStatus.OPEN:
            inc.status = IncidentStatus.ACKNOWLEDGED
            acknowledged += 1
    db.commit()

    return {"run_id": run_id, "acknowledged": acknowledged}


# ── POST /webhook/receiver ─────────────────────────────────────


@app.post("/webhook/receiver")
def webhook_receiver(payload: dict, request: Request, db: Session = Depends(get_db)):
    """Receive and log webhook notifications from Grafana alerts.

    Security: If DATAPULSE_WEBHOOK_SECRET is set, the request must include
    an X-Webhook-Secret header matching the configured value.
    If not set, the endpoint is open (development mode).
    """
    import os

    from datapulse.models.notification import Notification

    # Validate webhook secret if configured
    webhook_secret = os.environ.get("DATAPULSE_WEBHOOK_SECRET", "")
    if webhook_secret:
        provided_secret = request.headers.get("X-Webhook-Secret", "")
        if provided_secret != webhook_secret:
            raise HTTPException(status_code=403, detail="Invalid webhook secret")

    # Extract alert name from payload if present
    alert_name = None
    alerts = payload.get("alerts", [])
    if alerts:
        alert_name = alerts[0].get("labels", {}).get("alertname")

    notification = Notification(
        alert_name=alert_name,
        status=payload.get("status", "unknown"),
        payload=payload,
    )
    db.add(notification)
    db.commit()

    logger.info("webhook_received", extra={"alert_name": alert_name})
    return {"status": "received"}


@app.get("/webhook/log")
def get_webhook_log(limit: int = 20, db: Session = Depends(get_db), api_key: str = Depends(get_api_key)):
    """View recent webhook notifications from the database."""
    from datapulse.models.notification import Notification

    notifications = db.query(Notification).order_by(Notification.created_at.desc()).limit(min(limit, 100)).all()

    return [
        {
            "id": n.id,
            "alert_name": n.alert_name,
            "status": n.status,
            "payload": n.payload,
            "created_at": n.created_at.isoformat(),
        }
        for n in notifications
    ]


# ── GET /metrics ───────────────────────────────────────────────


@app.get("/metrics")
def get_metrics(db: Session = Depends(get_db), api_key: str = Depends(get_api_key)):
    """Operational metrics for DataPulse self-monitoring."""
    from datapulse.metrics import get_operational_metrics

    return get_operational_metrics(db)
