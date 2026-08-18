"""Run service — orchestrates the full pipeline run lifecycle."""

import logging
import time
from pathlib import Path

from sqlalchemy.orm import Session

from datapulse.db.repositories import ContractRepository, DatasetRepository, PipelineRepository
from datapulse.db.run_repositories import CheckResultRepository, IncidentRepository, RunRepository
from datapulse.models.check_result import CheckStatus, CheckType
from datapulse.models.incident import IncidentSeverity
from datapulse.models.run import RunStatus

logger = logging.getLogger("datapulse.run_service")


class RunService:
    """
    Orchestrates a pipeline run from submission to final status.

    Lifecycle:
        1. Idempotency check — same run_id returns existing run
        2. Status → RUNNING
        3. Execute checks in order
        4. Determine final status from check results
        5. Create incident if failed/late
        6. Return health summary
    """

    CHECK_ORDER = [
        CheckType.SOURCE_READABILITY,
        CheckType.SCHEMA_COMPATIBILITY,
        CheckType.TARGET_SCHEMA_COMPATIBILITY,
        CheckType.ROW_COUNT,
        CheckType.FRESHNESS,
    ]

    def __init__(self, session: Session):
        self.session = session
        self.pipeline_repo = PipelineRepository(session)
        self.dataset_repo = DatasetRepository(session)
        self.contract_repo = ContractRepository(session)
        self.run_repo = RunRepository(session)
        self.check_repo = CheckResultRepository(session)
        self.incident_repo = IncidentRepository(session)

    def submit_run(
        self,
        pipeline_name: str,
        run_id: str,
        source_path: Path,
        target_path: Path | None = None,
        dataset_name: str = "inventory_snapshot",
        target_dataset_name: str | None = None,
        contract_version: int | None = None,
    ) -> dict:
        """
        Submit a pipeline run. Returns a health summary dict.

        This is the main entry point — handles the full lifecycle.
        Idempotent: submitting the same run_id twice returns the same result.
        """
        # 1. Ensure pipeline and dataset exist
        pipeline = self.pipeline_repo.get_by_name(pipeline_name)
        if pipeline is None:
            raise ValueError(f"Pipeline '{pipeline_name}' not registered. Register it first.")

        # 2. Idempotency check
        existing_run = self.run_repo.find_by_pipeline_and_run_id(pipeline.id, run_id)
        if existing_run is not None:
            logger.info("run_exists — returning cached result", extra={"run_id": run_id, "pipeline": pipeline_name})
            return self._build_health_summary(existing_run)

        # 3. Get contract (specific version if requested, otherwise latest)
        dataset = None
        for d in pipeline.datasets:
            if d.name == dataset_name:
                dataset = d
                break
        if dataset is None:
            raise ValueError(f"Dataset '{dataset_name}' not found in pipeline '{pipeline_name}'.")

        if contract_version is not None:
            contract = self.contract_repo.get_by_version(dataset.id, contract_version)
            if contract is None:
                raise ValueError(f"Contract version {contract_version} not found for dataset '{dataset_name}'.")
        else:
            contract = self.contract_repo.get_latest(dataset.id)
            if contract is None:
                raise ValueError(f"No contract found for dataset '{dataset_name}'.")

        effective_version = contract.version

        # 3b. Load target contract if target dataset specified
        target_contract = None
        if target_dataset_name and target_path:
            target_dataset = None
            for d in pipeline.datasets:
                if d.name == target_dataset_name:
                    target_dataset = d
                    break
            if target_dataset is not None:
                target_contract = self.contract_repo.get_latest(target_dataset.id)

        # 4. Create run → status = RUNNING
        run = self.run_repo.create(pipeline.id, run_id, effective_version)
        self.run_repo.update_status(run, RunStatus.RUNNING)
        self.session.commit()
        run_start = time.monotonic()
        logger.info(
            "run_started",
            extra={
                "run_id": run_id,
                "pipeline": pipeline_name,
                "dataset": dataset_name,
                "contract_version": effective_version,
            },
        )

        # 5. Execute checks in deterministic order
        all_passed = True
        is_late = False
        failure_reasons = []
        source_row_count = None
        target_row_count = None

        for check_type in self.CHECK_ORDER:
            result = self._execute_check(
                check_type=check_type,
                run_id=run.id,
                source_path=source_path,
                contract=contract,
                target_path=target_path,
                target_contract=target_contract,
            )

            # Persist each check result immediately
            self.check_repo.create(
                pipeline_run_id=run.id,
                check_type=check_type,
                status=result["status"],
                expected=result.get("expected"),
                observed=result.get("observed"),
                message=result.get("message"),
            )
            self.session.commit()
            logger.info(
                "check_completed",
                extra={
                    "run_id": run_id,
                    "pipeline": pipeline_name,
                    "dataset": dataset_name,
                    "check_type": check_type.value,
                    "status": result["status"].value,
                },
            )

            if result["status"] == CheckStatus.FAILED:
                all_passed = False
                failure_reasons.append(result.get("message", f"{check_type.value} failed"))

                if check_type == CheckType.FRESHNESS:
                    is_late = True

                # Short-circuit: if source readability fails, skip remaining checks
                if check_type == CheckType.SOURCE_READABILITY:
                    break

            # Capture row counts from the row_count check
            if check_type == CheckType.ROW_COUNT and result.get("observed"):
                source_row_count = result["observed"].get("source_row_count")
                target_row_count = result["observed"].get("target_row_count")

        # 6. Determine final status
        # Priority: PASSED > FAILED > LATE
        # LATE only when freshness is the ONLY failure
        if all_passed:
            final_status = RunStatus.PASSED
        elif is_late and len(failure_reasons) == 1:
            final_status = RunStatus.LATE
        else:
            final_status = RunStatus.FAILED

        # 7. Finalize run
        failure_reason = "; ".join(failure_reasons) if failure_reasons else None
        self.run_repo.finalize(
            run=run,
            status=final_status,
            source_row_count=source_row_count,
            target_row_count=target_row_count,
            failure_reason=failure_reason,
        )

        # 8. Create incident if failed or late
        if final_status in (RunStatus.FAILED, RunStatus.LATE):
            severity = IncidentSeverity.HIGH if final_status == RunStatus.LATE else IncidentSeverity.MEDIUM
            self.incident_repo.create(
                pipeline_run_id=run.id,
                incident_type="contract_violation" if final_status == RunStatus.FAILED else "late_arrival",
                severity=severity,
                owner=pipeline.owner,
                retryable=True,
                failure_summary=failure_reason,
            )
            logger.warning(
                "incident_created",
                extra={
                    "run_id": run_id,
                    "pipeline": pipeline_name,
                    "status": final_status.value,
                    "error_type": "contract_violation" if final_status == RunStatus.FAILED else "late_arrival",
                },
            )

        self.session.commit()
        duration_ms = int((time.monotonic() - run_start) * 1000)
        logger.info(
            "run_completed",
            extra={
                "run_id": run_id,
                "pipeline": pipeline_name,
                "dataset": dataset_name,
                "contract_version": effective_version,
                "status": final_status.value,
                "duration_ms": duration_ms,
                "source_row_count": source_row_count,
                "target_row_count": target_row_count,
            },
        )

        return self._build_health_summary(run)

    def _execute_check(
        self,
        check_type: CheckType,
        run_id: int,
        source_path: Path,
        contract,
        target_path: Path | None = None,
        target_contract=None,
    ) -> dict:
        """Execute a single check and return the result dict."""
        from datapulse.checks.freshness import check_freshness
        from datapulse.checks.row_count import check_row_count
        from datapulse.checks.schema_compatibility import check_schema_compatibility
        from datapulse.checks.source_readability import check_source_readability

        if check_type == CheckType.SOURCE_READABILITY:
            return check_source_readability(source_path)
        elif check_type == CheckType.SCHEMA_COMPATIBILITY:
            return check_schema_compatibility(source_path, contract.schema_definition)
        elif check_type == CheckType.TARGET_SCHEMA_COMPATIBILITY:
            if target_path and target_contract:
                return check_schema_compatibility(target_path, target_contract.schema_definition)
            return {"status": CheckStatus.SKIPPED, "message": "No target to validate"}
        elif check_type == CheckType.ROW_COUNT:
            return check_row_count(source_path, contract.quality_rules, target_path)
        elif check_type == CheckType.FRESHNESS:
            return check_freshness(source_path, contract.freshness)
        else:
            raise ValueError(f"Unknown check type: {check_type}")

    def _build_health_summary(self, run) -> dict:
        """Build a health summary dict from a run."""
        check_results = self.check_repo.get_for_run(run.id)
        incidents = self.incident_repo.get_for_run(run.id)

        return {
            "run_id": run.run_id,
            "status": run.status.value,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "ended_at": run.ended_at.isoformat() if run.ended_at else None,
            "source_row_count": run.source_row_count,
            "target_row_count": run.target_row_count,
            "failure_reason": run.failure_reason,
            "contract_version": run.contract_version,
            "checks": [
                {
                    "type": cr.check_type.value,
                    "status": cr.status.value,
                    "expected": cr.expected,
                    "observed": cr.observed,
                    "message": cr.message,
                }
                for cr in check_results
            ],
            "incidents": [
                {
                    "type": inc.incident_type,
                    "severity": inc.severity.value,
                    "owner": inc.owner,
                    "status": inc.status.value,
                    "retryable": inc.retryable,
                    "failure_summary": inc.failure_summary,
                }
                for inc in incidents
            ],
        }
