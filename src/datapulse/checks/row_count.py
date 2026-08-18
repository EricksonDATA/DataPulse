"""Check: row count validation — is the row count within expected bounds and are keys unique?"""

import csv
from pathlib import Path

from datapulse.models.check_result import CheckStatus


def check_row_count(
    source_path: Path,
    quality_rules: dict,
    target_path: Path | None = None,
) -> dict:
    """
    Verify row count and unique key constraints.

    Checks:
    - Row count within configured range
    - Unique keys have no duplicates
    - Source-to-target reconciliation (if target provided)

    Args:
        source_path: Path to the source CSV file.
        quality_rules: Dict with 'min_row_count', 'max_row_count',
                       'unique_keys', and optional 'max_row_count_diff_pct'.
        target_path: Optional path to the target CSV file.

    Returns:
        dict with status, expected, observed, message.
    """
    min_count = quality_rules.get("min_row_count", 0)
    max_count = quality_rules.get("max_row_count", float("inf"))
    max_diff_pct = quality_rules.get("max_row_count_diff_pct", 100)
    unique_keys = quality_rules.get("unique_keys", [])

    with source_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        source_count = len(rows)

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
    if target_path is not None:
        if not target_path.exists():
            failures.append(f"Target file not found: {target_path}")
        else:
            with target_path.open(newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                target_count = sum(1 for _ in reader)
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
