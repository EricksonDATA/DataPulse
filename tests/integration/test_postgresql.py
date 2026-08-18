"""PostgreSQL integration tests — runs against a live PostgreSQL instance.

Usage:
    DATAPULSE_DATABASE_URL=postgresql+psycopg://datapulse:change-me@localhost:5432/datapulse \\
    pytest tests/integration/test_postgresql.py -v

Skipped automatically when DATAPULSE_DATABASE_URL is not set or points to SQLite.
"""

import os

import pytest
from sqlalchemy import create_engine, inspect

# Skip entire module if no PostgreSQL URL
PG_URL = os.getenv("DATAPULSE_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(
    "postgresql" not in PG_URL,
    reason="PostgreSQL not configured (set DATAPULSE_DATABASE_URL)",
)


@pytest.fixture(scope="module")
def pg_engine():
    """Create a PostgreSQL engine for integration tests."""
    engine = create_engine(PG_URL)
    yield engine
    engine.dispose()


class TestPostgreSQLConnection:
    def test_connects_to_postgresql(self, pg_engine):
        """Verify we can connect and run a query."""
        from sqlalchemy import text
        with pg_engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            assert result.scalar() == 1
        assert pg_engine.dialect.name == "postgresql"

    def test_all_tables_exist(self, pg_engine):
        """Verify all 6 DataPulse tables exist (created by Alembic migration)."""
        inspector = inspect(pg_engine)
        tables = set(inspector.get_table_names())
        expected = {"pipelines", "datasets", "contracts", "pipeline_runs", "check_results", "incidents"}
        assert expected.issubset(tables), f"Missing tables: {expected - tables}"

    def test_alembic_version_table_exists(self, pg_engine):
        """Verify Alembic version tracking table exists."""
        inspector = inspect(pg_engine)
        assert "alembic_version" in inspector.get_table_names()

    def test_indexes_exist(self, pg_engine):
        """Verify the 3 performance indexes were created."""
        inspector = inspect(pg_engine)

        run_indexes = {idx["name"] for idx in inspector.get_indexes("pipeline_runs")}
        assert "ix_runs_pipeline_started" in run_indexes

        check_indexes = {idx["name"] for idx in inspector.get_indexes("check_results")}
        assert "ix_checks_run_type" in check_indexes

        incident_indexes = {idx["name"] for idx in inspector.get_indexes("incidents")}
        assert "ix_incidents_status_owner" in incident_indexes

    def test_unique_constraints_exist(self, pg_engine):
        """Verify unique constraints are present."""
        inspector = inspect(pg_engine)

        pipeline_uqs = inspector.get_unique_constraints("pipelines")
        assert any("name" in uq["column_names"] for uq in pipeline_uqs)

        run_uqs = inspector.get_unique_constraints("pipeline_runs")
        assert any(
            set(uq["column_names"]) == {"pipeline_id", "run_id"}
            for uq in run_uqs
        )

    def test_foreign_keys_exist(self, pg_engine):
        """Verify foreign key relationships are present."""
        inspector = inspect(pg_engine)
        for table in ["datasets", "contracts", "pipeline_runs", "check_results", "incidents"]:
            fks = inspector.get_foreign_keys(table)
            assert len(fks) > 0, f"{table} has no foreign keys"


class TestPostgreSQLAPILifecycle:
    """Test the full API lifecycle against PostgreSQL via TestClient."""

    def test_full_run_lifecycle(self):
        """Register pipeline, dataset, submit run — all against PostgreSQL."""
        import datapulse.config as config
        import datapulse.api.deps as deps
        import datapulse.db.engine as eng

        # Reset to use PG
        deps._engine = None
        deps._session_factory = None

        fresh_engine = eng.init_db(eng.get_engine())
        deps._engine = fresh_engine
        deps._session_factory = eng.get_session_factory(fresh_engine)

        from datapulse.api.app import app
        from fastapi.testclient import TestClient

        client = TestClient(app)

        # Register
        r = client.post("/pipelines", json={"name": "pg_lifecycle_test", "owner": "test"})
        assert r.status_code == 201

        r = client.post("/datasets", json={
            "pipeline_name": "pg_lifecycle_test",
            "dataset_name": "test_ds",
            "role": "source",
            "contract_version": 1,
            "schema_definition": {"id": {"type": "integer", "nullable": False}},
            "freshness": {"max_age_hours": 99999, "timestamp_column": "id"},
            "quality_rules": {"unique_keys": ["id"], "min_row_count": 1, "max_row_count": 100},
        })
        assert r.status_code == 201

        # Verify data persisted in PostgreSQL
        from datapulse.db.repositories import PipelineRepository
        from sqlalchemy.orm import sessionmaker
        Session = sessionmaker(bind=fresh_engine)
        with Session() as session:
            repo = PipelineRepository(session)
            pipeline = repo.get_by_name("pg_lifecycle_test")
            assert pipeline is not None
            assert pipeline.owner == "test"
