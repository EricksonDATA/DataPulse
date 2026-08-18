"""Check: source readability — can the source file be opened and parsed?"""

import csv
from pathlib import Path

from datapulse.models.check_result import CheckStatus


def check_source_readability(source_path: Path) -> dict:
    """
    Verify that the source file exists and can be parsed as CSV.

    Returns:
        dict with status, expected, observed, message.
    """
    # Can we find the file?
    if not source_path.exists():
        return {
            "status": CheckStatus.FAILED,
            "expected": {"exists": True},
            "observed": {"exists": False},
            "message": f"Source file not found: {source_path}",
        }

    # Can we open and parse it?
    try:
        with source_path.open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            columns = reader.fieldnames or []
    except Exception as e:
        return {
            "status": CheckStatus.FAILED,
            "expected": {"parseable": True},
            "observed": {"parseable": False, "error": str(e)},
            "message": f"Failed to parse source file: {e}",
        }

    # Is it empty?
    if len(rows) == 0:
        return {
            "status": CheckStatus.FAILED,
            "expected": {"row_count": "> 0"},
            "observed": {"row_count": 0},
            "message": "Source file is empty (0 rows)",
        }

    return {
        "status": CheckStatus.PASSED,
        "expected": {"parseable": True, "row_count": "> 0"},
        "observed": {"parseable": True, "row_count": len(rows), "columns": len(columns)},
        "message": f"Source readable: {len(rows)} rows, {len(columns)} columns",
    }
