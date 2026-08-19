"""Streaming CSV reader — process large files without loading entirely into memory.

Used by checks that need to validate large datasets (1GB+).
Reads CSV in chunks and yields rows one at a time.
"""

import csv
from pathlib import Path
from typing import Iterator

from datapulse.references import DatasetReference, ResolvedData


def stream_csv_rows(source: Path | ResolvedData | str, chunk_size: int = 8192) -> Iterator[dict]:
    """Stream CSV rows one at a time without loading the entire file.

    Args:
        source: Path, ResolvedData, or URI string
        chunk_size: Number of bytes to read at a time (for file-based sources)

    Yields:
        dict: One row per yield, with column names as keys
    """
    if isinstance(source, ResolvedData):
        # Already resolved — yield from memory
        for row in source.rows:
            yield row
        return

    if isinstance(source, Path):
        with source.open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                yield row
        return

    if isinstance(source, str):
        # Check if it's a local file path
        path = Path(source)
        if path.exists() and path.is_file():
            with path.open(newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    yield row
            return

        # For S3/remote URIs, resolve first then stream
        ref = DatasetReference.from_uri(source)
        resolved = ref.resolve()
        if resolved.is_parseable:
            for row in resolved.rows:
                yield row
        return


def count_rows_streaming(source: Path | ResolvedData | str) -> int:
    """Count rows without loading all data into memory.

    Returns:
        int: Number of data rows (excluding header)
    """
    count = 0
    for _ in stream_csv_rows(source):
        count += 1
    return count


def check_unique_keys_streaming(
    source: Path | ResolvedData | str,
    unique_keys: list[str],
) -> tuple[int, int]:
    """Check for duplicate keys without loading all data into memory.

    Returns:
        tuple: (total_rows, duplicate_count)
    """
    seen = set()
    duplicates = 0
    total = 0

    for row in stream_csv_rows(source):
        total += 1
        key = tuple(row.get(k, "") for k in unique_keys)
        if key in seen:
            duplicates += 1
        else:
            seen.add(key)

    return total, duplicates


def get_columns_from_source(source: Path | ResolvedData | str) -> list[str]:
    """Get column names from the first row without loading all data.

    Returns:
        list: Column names
    """
    for row in stream_csv_rows(source):
        return list(row.keys())
    return []
