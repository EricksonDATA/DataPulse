"""Notification service — webhook delivery for DataPulse alerts."""

import logging
from datetime import datetime, timezone

import httpx

logger = logging.getLogger("datapulse.notifications")


def send_webhook(
    webhook_url: str,
    pipeline_name: str,
    run_id: str,
    status: str,
    failed_checks: list[dict],
    incident_owner: str | None = None,
    retryable: bool = False,
    grafana_url: str | None = None,
    max_retries: int = 3,
) -> dict:
    """
    Send a webhook notification for a pipeline run event.

    Includes bounded retries with exponential backoff for transient failures.
    Does NOT fail the pipeline run if the notification fails — records the failure separately.
    """
    payload = {
        "pipeline": pipeline_name,
        "run_id": run_id,
        "status": status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "failed_checks": failed_checks,
        "incident": {
            "owner": incident_owner,
            "retryable": retryable,
        },
        "links": {
            "run": f"http://localhost:8000/pipelines/{pipeline_name}/runs/{run_id}",
            "grafana": grafana_url or "http://localhost:3000/d/datapulse-health",
        },
    }

    for attempt in range(max_retries):
        try:
            response = httpx.post(webhook_url, json=payload, timeout=10.0)
            if response.status_code < 400:
                logger.info("webhook_sent", extra={
                    "url": webhook_url, "status_code": response.status_code, "attempt": attempt + 1,
                })
                return {"status": "sent", "status_code": response.status_code, "attempt": attempt + 1}
        except httpx.HTTPError as e:
            logger.warning("webhook_retry", extra={
                "url": webhook_url, "error": str(e), "attempt": attempt + 1,
            })
            if attempt < max_retries - 1:
                import time
                time.sleep(2 ** attempt)

    logger.error("webhook_failed", extra={"url": webhook_url, "max_retries": max_retries})
    return {"status": "failed", "error": "max retries exceeded", "attempts": max_retries}
