"""DatasetReference — generic abstraction for data source locations.

Supports multiple storage backends:
- local://path/to/file.csv        — local filesystem
- s3://bucket/key.parquet         — S3 object storage
- table://schema.table_name       — warehouse table
- query://SELECT * FROM table     — arbitrary query
- partition://s3://bucket/dt=2026-08-19/ — partitioned dataset

Each reference resolves to a standard interface that checks can consume
without knowing the underlying storage backend.
"""

from __future__ import annotations

import csv
import enum
import io
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class ReferenceType(str, enum.Enum):
    """Supported dataset reference types."""

    LOCAL = "local"
    S3 = "s3"
    TABLE = "table"
    QUERY = "query"
    PARTITION = "partition"


@dataclass(frozen=True)
class ResolvedData:
    """Standard interface for resolved dataset content.

    All resolvers produce this same shape, regardless of storage backend.
    Checks consume ResolvedData without knowing where it came from.
    """

    rows: list[dict[str, Any]]
    columns: list[str]
    row_count: int
    column_count: int
    source_uri: str
    is_parseable: bool = True
    error: str | None = None

    @classmethod
    def from_error(cls, uri: str, error: str) -> ResolvedData:
        """Create a ResolvedData representing a failed resolution."""
        return cls(
            rows=[],
            columns=[],
            row_count=0,
            column_count=0,
            source_uri=uri,
            is_parseable=False,
            error=error,
        )


@dataclass(frozen=True)
class DatasetReference:
    """A reference to a dataset in any supported storage backend.

    Attributes:
        uri: The full URI (e.g., "local://data/file.csv", "s3://bucket/key")
        ref_type: The type of reference (local, s3, table, query, partition)
        raw_path: The path/key portion after the scheme
    """

    uri: str
    ref_type: ReferenceType
    raw_path: str

    @classmethod
    def from_uri(cls, uri: str) -> DatasetReference:
        """Parse a URI into a DatasetReference.

        Examples:
            >>> DatasetReference.from_uri("local://data/file.csv")
            DatasetReference(uri='local://data/file.csv', ref_type=<ReferenceType.LOCAL: 'local'>, raw_path='data/file.csv')

            >>> DatasetReference.from_uri("s3://bucket/key.parquet")
            DatasetReference(uri='s3://bucket/key.parquet', ref_type=<ReferenceType.S3: 's3'>, raw_path='bucket/key.parquet')

            >>> DatasetReference.from_uri("table://warehouse.fact_orders")
            DatasetReference(uri='table://warehouse.fact_orders', ref_type=<ReferenceType.TABLE: 'table'>, raw_path='warehouse.fact_orders')
        """
        if "://" not in uri:
            # Bare path — treat as local file
            return cls(uri=f"local://{uri}", ref_type=ReferenceType.LOCAL, raw_path=uri)

        scheme, rest = uri.split("://", 1)

        # Map scheme to ReferenceType
        type_map = {
            "local": ReferenceType.LOCAL,
            "s3": ReferenceType.S3,
            "table": ReferenceType.TABLE,
            "query": ReferenceType.QUERY,
            "partition": ReferenceType.PARTITION,
        }

        ref_type = type_map.get(scheme)
        if ref_type is None:
            # Unknown scheme — treat as local path
            return cls(uri=uri, ref_type=ReferenceType.LOCAL, raw_path=uri)

        return cls(uri=uri, ref_type=ref_type, raw_path=rest)

    @classmethod
    def from_legacy_path(cls, path: str | Path) -> DatasetReference:
        """Convert a legacy file path to a DatasetReference.

        This enables backward compatibility with existing adapters
        that pass raw file paths.
        """
        path_str = str(path)
        if "://" in path_str:
            return cls.from_uri(path_str)
        return cls(uri=f"local://{path_str}", ref_type=ReferenceType.LOCAL, raw_path=path_str)

    def resolve(self, s3_client=None, db_session=None) -> ResolvedData:
        """Resolve this reference to actual data.

        Dispatches to the appropriate resolver based on ref_type.
        Each resolver returns a ResolvedData with the same interface.

        Args:
            s3_client: boto3 S3 client (required for S3 references)
            db_session: SQLAlchemy session (required for table/query references)
        """
        if self.ref_type == ReferenceType.LOCAL:
            return self._resolve_local()
        elif self.ref_type == ReferenceType.S3:
            return self._resolve_s3(s3_client)
        elif self.ref_type == ReferenceType.TABLE:
            return self._resolve_table(db_session)
        elif self.ref_type == ReferenceType.QUERY:
            return self._resolve_query(db_session)
        elif self.ref_type == ReferenceType.PARTITION:
            return self._resolve_partition(s3_client)
        else:
            return ResolvedData.from_error(self.uri, f"Unsupported reference type: {self.ref_type}")

    def _resolve_local(self) -> ResolvedData:
        """Resolve a local file reference."""
        path = Path(self.raw_path)
        if not path.exists():
            return ResolvedData.from_error(self.uri, f"File not found: {self.raw_path}")
        if not path.is_file():
            return ResolvedData.from_error(self.uri, f"Not a file: {self.raw_path}")

        try:
            with path.open(newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                rows = list(reader)

            if not rows:
                return ResolvedData.from_error(self.uri, "File is empty")

            columns = list(rows[0].keys())
            return ResolvedData(
                rows=rows,
                columns=columns,
                row_count=len(rows),
                column_count=len(columns),
                source_uri=self.uri,
            )
        except Exception as e:
            return ResolvedData.from_error(self.uri, f"Failed to read file: {e}")

    def _resolve_s3(self, s3_client=None) -> ResolvedData:
        """Resolve an S3 reference.

        If s3_client is None and DATAPULSE_S3_MOCK=true, returns mock data.
        If s3_client is None and mock mode is not enabled, returns an error.
        In production, uses boto3 to download and parse the object.
        """
        import os

        mock_enabled = os.environ.get("DATAPULSE_S3_MOCK", "").lower() == "true"

        if s3_client is None:
            if mock_enabled:
                return self._resolve_s3_mock()
            return ResolvedData.from_error(
                self.uri,
                "S3 client required. Set DATAPULSE_S3_MOCK=true for testing or provide a boto3 client.",
            )

        try:
            # Parse bucket and key from raw_path
            parts = self.raw_path.split("/", 1)
            if len(parts) < 2:
                return ResolvedData.from_error(self.uri, f"Invalid S3 path: {self.raw_path}")

            bucket, key = parts[0], parts[1]

            # Download object
            response = s3_client.get_object(Bucket=bucket, Key=key)
            body = response["Body"].read().decode("utf-8")

            # Parse CSV
            reader = csv.DictReader(io.StringIO(body))
            rows = list(reader)

            if not rows:
                return ResolvedData.from_error(self.uri, "S3 object is empty")

            columns = list(rows[0].keys())
            return ResolvedData(
                rows=rows,
                columns=columns,
                row_count=len(rows),
                column_count=len(columns),
                source_uri=self.uri,
            )
        except Exception as e:
            return ResolvedData.from_error(self.uri, f"Failed to resolve S3 object: {e}")

    def _resolve_s3_mock(self) -> ResolvedData:
        """Mock S3 resolver for testing without AWS credentials.

        Returns synthetic data that exercises the S3 resolution path
        without making actual network calls.
        """
        # Generate synthetic data based on the URI
        mock_rows = [
            {"order_id": f"MOCK-{i:03d}", "amount": str(10.0 * i), "status": "completed"} for i in range(1, 11)
        ]
        columns = list(mock_rows[0].keys())
        return ResolvedData(
            rows=mock_rows,
            columns=columns,
            row_count=len(mock_rows),
            column_count=len(columns),
            source_uri=self.uri,
        )

    def _resolve_table(self, db_session=None) -> ResolvedData:
        """Resolve a warehouse table reference."""
        if db_session is None:
            return ResolvedData.from_error(self.uri, "Database session required for table references")

        try:
            from sqlalchemy import text

            table_name = self.raw_path
            result = db_session.execute(text(f"SELECT * FROM {table_name} LIMIT 10000"))
            columns = list(result.keys())
            rows = [dict(zip(columns, row)) for row in result.fetchall()]

            return ResolvedData(
                rows=rows,
                columns=columns,
                row_count=len(rows),
                column_count=len(columns),
                source_uri=self.uri,
            )
        except Exception as e:
            return ResolvedData.from_error(self.uri, f"Failed to query table: {e}")

    def _resolve_query(self, db_session=None) -> ResolvedData:
        """Resolve a query reference."""
        if db_session is None:
            return ResolvedData.from_error(self.uri, "Database session required for query references")

        try:
            from sqlalchemy import text

            query = self.raw_path
            result = db_session.execute(text(query))
            columns = list(result.keys())
            rows = [dict(zip(columns, row)) for row in result.fetchall()]

            return ResolvedData(
                rows=rows,
                columns=columns,
                row_count=len(rows),
                column_count=len(columns),
                source_uri=self.uri,
            )
        except Exception as e:
            return ResolvedData.from_error(self.uri, f"Failed to execute query: {e}")

    def _resolve_partition(self, s3_client=None) -> ResolvedData:
        """Resolve a partitioned dataset reference.

        For now, delegates to S3 resolver. In production, would
        list partitions and aggregate results.
        """
        # Treat as S3 reference for now
        inner_ref = DatasetReference(
            uri=self.raw_path,
            ref_type=ReferenceType.S3,
            raw_path=self.raw_path.replace("s3://", ""),
        )
        return inner_ref.resolve(s3_client=s3_client)
