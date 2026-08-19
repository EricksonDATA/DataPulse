"""Check: schema compatibility — do columns, types, and nullability match the contract?"""

from pathlib import Path

from datapulse.models.check_result import CheckStatus
from datapulse.references import DatasetReference, ResolvedData

# Map contract type names to Python validation functions
TYPE_VALIDATORS = {
    "string": lambda v: isinstance(v, str) and len(v) > 0,
    "integer": lambda v: v.isdigit() if isinstance(v, str) else isinstance(v, int),
    "decimal": lambda v: _is_decimal(v),
    "date": lambda v: _is_date(v),
    "timestamp": lambda v: _is_date(v),  # simplified for Phase 1
}


def _is_decimal(value: str) -> bool:
    """Check if a string represents a decimal number."""
    try:
        float(value)
        return True
    except (ValueError, TypeError):
        return False


def _is_date(value: str) -> bool:
    """Check if a string looks like a date (YYYY-MM-DD)."""
    if not isinstance(value, str):
        return False
    parts = value.split("-")
    if len(parts) != 3:
        return False
    return (
        len(parts[0]) == 4
        and parts[0].isdigit()
        and len(parts[1]) == 2
        and parts[1].isdigit()
        and len(parts[2]) == 2
        and parts[2].isdigit()
    )


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


def check_schema_compatibility(source: Path | ResolvedData | str, schema_definition: dict) -> dict:
    """
    Compare the observed schema with the contract schema.

    Accepts Path, ResolvedData, or URI string.
    Checks:
    - Missing required columns
    - Unexpected extra columns
    - Type mismatches
    - Null values in non-nullable fields
    """
    resolved = _to_resolved(source)

    if not resolved.is_parseable:
        return {
            "status": CheckStatus.FAILED,
            "expected": {"columns": sorted(schema_definition.keys()), "column_count": len(schema_definition)},
            "observed": {"columns": [], "column_count": 0, "error": resolved.error},
            "message": f"Cannot read source for schema check: {resolved.error}",
        }

    observed_columns = resolved.columns
    rows = resolved.rows
    expected_columns = set(schema_definition.keys())
    actual_columns = set(observed_columns)

    failures = []

    # 1. Missing columns
    missing = expected_columns - actual_columns
    if missing:
        failures.append(f"Missing columns: {sorted(missing)}")

    # 2. Unexpected columns
    unexpected = actual_columns - expected_columns
    if unexpected:
        failures.append(f"Unexpected columns: {sorted(unexpected)}")

    # 3. Type and nullability checks (only for columns that exist in both)
    common_columns = expected_columns & actual_columns
    type_errors = []
    null_errors = []

    for col in common_columns:
        col_def = schema_definition[col]
        expected_type = col_def.get("type", "string")
        nullable = col_def.get("nullable", True)

        validator = TYPE_VALIDATORS.get(expected_type)
        if validator is None:
            continue

        for row_idx, row in enumerate(rows):
            value = row.get(col, "")

            # Null check
            if value == "" or value is None:
                if not nullable:
                    null_errors.append(f"Null in non-nullable column '{col}' at row {row_idx + 1}")
                continue

            # Type check
            if not validator(value):
                type_errors.append(
                    f"Type mismatch in '{col}' at row {row_idx + 1}: expected {expected_type}, got '{value}'"
                )

    if null_errors:
        failures.append(f"Null violations ({len(null_errors)}): {null_errors[0]}")
    if type_errors:
        failures.append(f"Type violations ({len(type_errors)}): {type_errors[0]}")

    # Build result
    if failures:
        return {
            "status": CheckStatus.FAILED,
            "expected": {
                "columns": sorted(expected_columns),
                "column_count": len(expected_columns),
            },
            "observed": {
                "columns": sorted(actual_columns),
                "column_count": len(actual_columns),
                "missing": sorted(missing),
                "unexpected": sorted(unexpected),
            },
            "message": "; ".join(failures),
        }

    return {
        "status": CheckStatus.PASSED,
        "expected": {
            "columns": sorted(expected_columns),
            "column_count": len(expected_columns),
        },
        "observed": {
            "columns": sorted(actual_columns),
            "column_count": len(actual_columns),
        },
        "message": f"Schema matches: {len(actual_columns)} columns as expected",
    }
