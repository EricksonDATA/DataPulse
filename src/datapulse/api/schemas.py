"""Pydantic models — request and response shapes for the API."""

from pydantic import BaseModel


# ── Request models ──────────────────────────────────────────────

class PipelineCreate(BaseModel):
    """Request body for POST /pipelines."""
    name: str
    owner: str


class DatasetCreate(BaseModel):
    """Request body for POST /datasets."""
    pipeline_name: str
    dataset_name: str
    role: str  # 'source' or 'target'
    location: str | None = None
    contract_version: int = 1
    schema_definition: dict
    freshness: dict
    quality_rules: dict


class RunSubmit(BaseModel):
    """Request body for POST /runs."""
    pipeline_name: str
    run_id: str
    source_path: str
    target_path: str | None = None
    dataset_name: str = "inventory_snapshot"
    target_dataset_name: str | None = None
    contract_version: int | None = None


# ── Response models ─────────────────────────────────────────────

class HealthResponse(BaseModel):
    """Response for GET /health."""
    status: str
    version: str


class PipelineResponse(BaseModel):
    """Response after registering a pipeline."""
    id: int
    name: str
    owner: str
    enabled: bool


class DatasetResponse(BaseModel):
    """Response after registering a dataset + contract."""
    dataset_id: int
    dataset_name: str
    contract_id: int
    contract_version: int


class CheckResultResponse(BaseModel):
    """One check result within a run."""
    type: str
    status: str
    expected: dict | None = None
    observed: dict | None = None
    message: str | None = None


class IncidentResponse(BaseModel):
    """One incident within a run."""
    type: str
    severity: str
    owner: str
    status: str
    retryable: bool
    failure_summary: str | None = None


class RunHealthResponse(BaseModel):
    """Response for run health — the main output of DataPulse."""
    run_id: str
    status: str
    started_at: str | None = None
    ended_at: str | None = None
    source_row_count: int | None = None
    target_row_count: int | None = None
    failure_reason: str | None = None
    contract_version: int | None = None
    checks: list[CheckResultResponse] = []
    incidents: list[IncidentResponse] = []
