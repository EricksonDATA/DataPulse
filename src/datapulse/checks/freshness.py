"""Check: freshness validation — is the source data recent enough?"""

from datetime import datetime, timezone
from pathlib import Path

from datapulse.models.check_result import CheckStatus
from datapulse.references import DatasetReference, ResolvedData


def _to_resolved(source: Path | ResolvedData | str) -> ResolvedData:
    """Convert any source to ResolvedData."""
    if isinstance(source, ResolvedData):
        return source
    if isinstance(source, Path):
        ref = DatasetReference.from_legacy_path(str(source))
        return ref.resolve()
    if isinstance(source, str):
        ref = DatasetReference.from_uri(source)
        return ref.resolve()
    return ResolvedData.from_error(str(source), f"Unsupported source type: {type(source)}")


def check_freshness(source: Path | ResolvedData | str, freshness_rules: dict) -> dict:
    """
    Verify that the latest timestamp in the source is within the freshness window.

    Accepts Path, ResolvedData, or URI string.
    """
    max_age_hours = freshness_rules.get("max_age_hours", 24)
    timestamp_column = freshness_rules.get("timestamp_column", "snapshot_date")

    resolved = _to_resolved(source)
    if not resolved.is_parseable:
        return {
            "status": CheckStatus.FAILED,
            "expected": {"max_age_hours": max_age_hours, "timestamp_column": timestamp_column},
            "observed": {"latest_timestamp": None, "error": resolved.error},
            "message": f"Cannot read source for freshness: {resolved.error}",
        }

    rows = resolved.rows
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
