"""Operational metrics — DataPulse self-monitoring."""

from datetime import datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from datapulse.models.check_result import CheckResult, CheckStatus
from datapulse.models.incident import Incident, IncidentStatus
from datapulse.models.notification import Notification
from datapulse.models.pipeline import Pipeline
from datapulse.models.run import PipelineRun


def get_operational_metrics(db: Session) -> dict:
    """Collect operational metrics for DataPulse self-monitoring.

    Returns metrics about:
    - Pipeline counts
    - Run status distribution
    - Check performance
    - Stuck runs
    - Incident summary
    - Notification delivery
    """
    now = datetime.utcnow()
    one_hour_ago = now - timedelta(hours=1)
    one_day_ago = now - timedelta(days=1)

    # Pipeline counts
    total_pipelines = db.query(func.count(Pipeline.id)).scalar() or 0
    active_pipelines = db.query(func.count(Pipeline.id)).filter(Pipeline.enabled.is_(True)).scalar() or 0

    # Run status distribution (last 24h)
    runs_24h = (
        db.query(PipelineRun.status, func.count(PipelineRun.id))
        .filter(PipelineRun.started_at >= one_day_ago)
        .group_by(PipelineRun.status)
        .all()
    )
    run_status_dist = {status.value: count for status, count in runs_24h}

    # Average check duration (last 24h)
    avg_duration = (
        db.query(func.avg(PipelineRun.ended_at - PipelineRun.started_at))
        .filter(PipelineRun.ended_at.isnot(None))
        .filter(PipelineRun.started_at >= one_day_ago)
        .scalar()
    )
    avg_duration_ms = int(avg_duration.total_seconds() * 1000) if avg_duration else 0

    # Stuck runs (started but not ended, older than 1 hour)
    stuck_runs = (
        db.query(func.count(PipelineRun.id))
        .filter(PipelineRun.ended_at.is_(None))
        .filter(PipelineRun.started_at < one_hour_ago)
        .scalar()
    ) or 0

    # Failed checks by type (last 24h)
    failed_checks = (
        db.query(CheckResult.check_type, func.count(CheckResult.id))
        .filter(CheckResult.status == CheckStatus.FAILED)
        .join(PipelineRun)
        .filter(PipelineRun.started_at >= one_day_ago)
        .group_by(CheckResult.check_type)
        .all()
    )
    failed_checks_dist = {check_type.value: count for check_type, count in failed_checks}

    # Open incidents
    open_incidents = (
        db.query(func.count(Incident.id))
        .filter(Incident.status == IncidentStatus.OPEN)
        .scalar()
    ) or 0

    # Notification delivery (last 24h)
    notifications_24h = (
        db.query(Notification.status, func.count(Notification.id))
        .filter(Notification.created_at >= one_day_ago)
        .group_by(Notification.status)
        .all()
    )
    notification_dist = {status: count for status, count in notifications_24h}

    return {
        "timestamp": now.isoformat(),
        "pipelines": {
            "total": total_pipelines,
            "active": active_pipelines,
        },
        "runs_24h": {
            "total": sum(run_status_dist.values()),
            "by_status": run_status_dist,
            "avg_duration_ms": avg_duration_ms,
            "stuck": stuck_runs,
        },
        "checks_24h": {
            "failed_by_type": failed_checks_dist,
            "total_failed": sum(failed_checks_dist.values()),
        },
        "incidents": {
            "open": open_incidents,
        },
        "notifications_24h": {
            "total": sum(notification_dist.values()),
            "by_status": notification_dist,
        },
    }
