"""Check: row count validation — is the row count within expected bounds and are keys unique?"""

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


def check_row_count(
    source: Path | ResolvedData | str,
    quality_rules: dict,
    target: Path | ResolvedData | str | None = None,
) -> dict:
    """
    Verify row count and unique key constraints.

    Accepts Path, ResolvedData, or URI string for source and target.
    """
    min_count = quality_rules.get("min_row_count", 0)
    max_count = quality_rules.get("max_row_count", float("inf"))
    max_diff_pct = quality_rules.get("max_row_count_diff_pct", 100)
    unique_keys = quality_rules.get("unique_keys", [])

    source_resolved = _to_resolved(source)
    if not source_resolved.is_parseable:
        return {
            "status": CheckStatus.FAILED,
            "expected": {"min_row_count": min_count, "max_row_count": max_count},
            "observed": {"source_row_count": 0, "error": source_resolved.error},
            "message": f"Cannot read source for row count: {source_resolved.error}",
        }

    rows = source_resolved.rows
    source_count = source_resolved.row_count
    observed = {
        "source_row_count": source_count,
        "target_row_count": None,
    }

    failures = []

    # 1. Check source count against range
    if not (min_count <= source_count <= max_count):
        failures.append(f"Source row count {source_count} outside range [{min_count}, {max_count}]")

    # 2. Check unique keys for duplicates
    if unique_keys and rows:
        seen = set()
        duplicates = 0
        for row in rows:
            key = tuple(row.get(k, "") for k in unique_keys)
            if key in seen:
                duplicates += 1
            else:
                seen.add(key)

        observed["duplicate_count"] = duplicates
        if duplicates > 0:
            failures.append(f"Found {duplicates} duplicate rows on keys {unique_keys}")

    # 3. Source-to-target reconciliation
    target_count = None
    if target is not None:
        target_resolved = _to_resolved(target)
        if not target_resolved.is_parseable:
            failures.append(f"Target not readable: {target_resolved.error}")
        else:
            target_count = target_resolved.row_count
            observed["target_row_count"] = target_count

            if source_count > 0:
                diff_pct = abs(source_count - target_count) / source_count * 100
            else:
                diff_pct = 0 if target_count == 0 else 100

            if diff_pct > max_diff_pct:
                failures.append(
                    f"Source-target mismatch: {source_count} vs {target_count} "
                    f"({round(diff_pct, 2)}% diff, max {max_diff_pct}%)"
                )

    if failures:
        return {
            "status": CheckStatus.FAILED,
            "expected": {
                "min_row_count": min_count,
                "max_row_count": max_count,
                "unique_keys": unique_keys,
            },
            "observed": observed,
            "message": "; ".join(failures),
        }

    return {
        "status": CheckStatus.PASSED,
        "expected": {
            "min_row_count": min_count,
            "max_row_count": max_count,
            "unique_keys": unique_keys,
        },
        "observed": observed,
        "message": f"Row count {source_count} within range [{min_count}, {max_count}]",
    }
