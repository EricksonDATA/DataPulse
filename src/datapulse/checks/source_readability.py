"""Check: source readability — can the source data be parsed?"""

from pathlib import Path

from datapulse.models.check_result import CheckStatus
from datapulse.references import DatasetReference, ResolvedData


def _to_resolved(source: Path | ResolvedData | str) -> ResolvedData:
    """Convert any source to ResolvedData.

    Accepts:
    - Path: resolved via local file reader
    - ResolvedData: passed through
    - str: treated as a URI and resolved via DatasetReference
    """
    if isinstance(source, ResolvedData):
        return source
    if isinstance(source, Path):
        ref = DatasetReference.from_legacy_path(str(source))
        return ref.resolve()
    if isinstance(source, str):
        ref = DatasetReference.from_uri(source)
        return ref.resolve()
    return ResolvedData.from_error(str(source), f"Unsupported source type: {type(source)}")


def check_source_readability(source: Path | ResolvedData | str) -> dict:
    """
    Verify that the source data can be parsed.

    Accepts Path, ResolvedData, or URI string.
    Returns dict with status, expected, observed, message.
    """
    resolved = _to_resolved(source)

    if not resolved.is_parseable:
        return {
            "status": CheckStatus.FAILED,
            "expected": {"parseable": True},
            "observed": {"parseable": False, "error": resolved.error},
            "message": f"Source not readable: {resolved.error}",
        }

    if resolved.row_count == 0:
        return {
            "status": CheckStatus.FAILED,
            "expected": {"row_count": "> 0"},
            "observed": {"row_count": 0},
            "message": "Source has 0 rows",
        }

    return {
        "status": CheckStatus.PASSED,
        "expected": {"parseable": True, "row_count": "> 0"},
        "observed": {"parseable": True, "row_count": resolved.row_count, "columns": resolved.column_count},
        "message": f"Source readable: {resolved.row_count} rows, {resolved.column_count} columns",
    }
