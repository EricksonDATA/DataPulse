"""Check: freshness validation — is the source data recent enough?"""

import csv
from datetime import datetime, timezone
from pathlib import Path

from datapulse.models.check_result import CheckStatus


def check_freshness(source_path: Path, freshness_rules: dict) -> dict:
    """
    Verify that the latest timestamp in the source is within the freshness window.

    Args:
        source_path: Path to the CSV file.
        freshness_rules: Dict with 'max_age_hours' and 'timestamp_column'.

    Returns:
        dict with status, expected, observed, message.
    """
    max_age_hours = freshness_rules.get("max_age_hours", 24)
    timestamp_column = freshness_rules.get("timestamp_column", "snapshot_date")

    with source_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    if not rows:
        return {
            "status": CheckStatus.FAILED,
            "expected": {"max_age_hours": max_age_hours, "timestamp_column": timestamp_column},
            "observed": {"latest_timestamp": None, "row_count": 0},
            "message": "No rows to evaluate freshness",
        }

    # Find the latest timestamp in the column
    timestamps = []
    for row in rows:
        raw = row.get(timestamp_column, "")
        if raw:
            try:
                # Handle date (YYYY-MM-DD) and datetime formats
                if len(raw) == 10:
                    ts = datetime.strptime(raw, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                else:
                    ts = datetime.fromisoformat(raw).astimezone(timezone.utc)
                timestamps.append(ts)
            except (ValueError, TypeError):
                continue

    if not timestamps:
        return {
            "status": CheckStatus.FAILED,
            "expected": {"max_age_hours": max_age_hours, "timestamp_column": timestamp_column},
            "observed": {"latest_timestamp": None, "parseable_timestamps": 0},
            "message": f"No valid timestamps found in column '{timestamp_column}'",
        }

    latest = max(timestamps)
    now = datetime.now(timezone.utc)
    age_hours = (now - latest).total_seconds() / 3600
    is_fresh = age_hours <= max_age_hours

    if is_fresh:
        return {
            "status": CheckStatus.PASSED,
            "expected": {"max_age_hours": max_age_hours, "timestamp_column": timestamp_column},
            "observed": {
                "latest_timestamp": latest.isoformat(),
                "age_hours": round(age_hours, 2),
            },
            "message": f"Data is fresh: {round(age_hours, 2)}h old (max {max_age_hours}h)",
        }

    return {
        "status": CheckStatus.FAILED,
        "expected": {"max_age_hours": max_age_hours, "timestamp_column": timestamp_column},
        "observed": {
            "latest_timestamp": latest.isoformat(),
            "age_hours": round(age_hours, 2),
        },
        "message": f"Data is stale: {round(age_hours, 2)}h old (max {max_age_hours}h)",
    }
