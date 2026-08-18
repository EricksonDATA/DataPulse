"""Repository layer — database operations for runs, check results, and incidents."""

from datetime import datetime

from sqlalchemy.orm import Session

from datapulse.models.check_result import CheckResult, CheckStatus, CheckType
from datapulse.models.incident import Incident, IncidentSeverity, IncidentStatus
from datapulse.models.run import PipelineRun, RunStatus


class RunRepository:
    """CRUD operations for pipeline runs."""

    def __init__(self, session: Session):
        self.session = session

    def find_by_pipeline_and_run_id(self, pipeline_id: int, run_id: str) -> PipelineRun | None:
        """Find an existing run by pipeline + run_id (idempotency check)."""
        return self.session.query(PipelineRun).filter_by(pipeline_id=pipeline_id, run_id=run_id).first()

    def create(self, pipeline_id: int, run_id: str, contract_version: int | None = None) -> PipelineRun:
        """Create a new run in REGISTERED status."""
        run = PipelineRun(
            pipeline_id=pipeline_id,
            run_id=run_id,
            status=RunStatus.REGISTERED,
            contract_version=contract_version,
            started_at=datetime.utcnow(),
        )
        self.session.add(run)
        self.session.flush()
        return run

    def update_status(self, run: PipelineRun, status: RunStatus) -> None:
        """Update the run's status."""
        run.status = status
        self.session.flush()

    def finalize(
        self,
        run: PipelineRun,
        status: RunStatus,
        source_row_count: int | None = None,
        target_row_count: int | None = None,
        failure_reason: str | None = None,
    ) -> None:
        """Record final run status, counts, and failure reason."""
        run.status = status
        run.source_row_count = source_row_count
        run.target_row_count = target_row_count
        run.failure_reason = failure_reason
        run.ended_at = datetime.utcnow()
        self.session.flush()

    def get_latest_for_pipeline(self, pipeline_id: int) -> PipelineRun | None:
        """Get the most recent run for a pipeline."""
        return (
            self.session.query(PipelineRun)
            .filter_by(pipeline_id=pipeline_id)
            .order_by(PipelineRun.started_at.desc())
            .first()
        )

    def get_runs_for_pipeline(
        self,
        pipeline_id: int,
        status: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[PipelineRun]:
        """List runs for a pipeline with optional status filter and pagination."""
        q = self.session.query(PipelineRun).filter_by(pipeline_id=pipeline_id)
        if status:
            q = q.filter_by(status=RunStatus(status))
        return q.order_by(PipelineRun.started_at.desc()).offset(offset).limit(limit).all()

    def find_by_run_id(self, run_id: str) -> PipelineRun | None:
        """Find a run by its run_id across all pipelines."""
        return self.session.query(PipelineRun).filter_by(run_id=run_id).first()


class CheckResultRepository:
    """CRUD operations for check results."""

    def __init__(self, session: Session):
        self.session = session

    def create(
        self,
        pipeline_run_id: int,
        check_type: CheckType,
        status: CheckStatus,
        expected: dict | None = None,
        observed: dict | None = None,
        message: str | None = None,
    ) -> CheckResult:
        """Persist one check result."""
        result = CheckResult(
            pipeline_run_id=pipeline_run_id,
            check_type=check_type,
            status=status,
            expected=expected,
            observed=observed,
            message=message,
        )
        self.session.add(result)
        self.session.flush()
        return result

    def get_for_run(self, pipeline_run_id: int) -> list[CheckResult]:
        """Get all check results for a run."""
        return self.session.query(CheckResult).filter_by(pipeline_run_id=pipeline_run_id).all()


class IncidentRepository:
    """CRUD operations for incidents."""

    def __init__(self, session: Session):
        self.session = session

    def create(
        self,
        pipeline_run_id: int,
        incident_type: str,
        severity: IncidentSeverity,
        owner: str,
        retryable: bool = False,
        failure_summary: str | None = None,
    ) -> Incident:
        """Create an incident for a failed or late run."""
        incident = Incident(
            pipeline_run_id=pipeline_run_id,
            incident_type=incident_type,
            severity=severity,
            owner=owner,
            status=IncidentStatus.OPEN,
            retryable=retryable,
            failure_summary=failure_summary,
            first_observed_at=datetime.utcnow(),
        )
        self.session.add(incident)
        self.session.flush()
        return incident

    def get_for_run(self, pipeline_run_id: int) -> list[Incident]:
        """Get all incidents for a run."""
        return self.session.query(Incident).filter_by(pipeline_run_id=pipeline_run_id).all()

    def get_open_for_pipeline(self, pipeline_id: int, limit: int = 20) -> list[Incident]:
        """Get open incidents for a pipeline, newest first."""
        return (
            self.session.query(Incident)
            .join(Incident.pipeline_run)
            .filter(PipelineRun.pipeline_id == pipeline_id)
            .filter(Incident.status == IncidentStatus.OPEN)
            .order_by(Incident.first_observed_at.desc())
            .limit(limit)
            .all()
        )
