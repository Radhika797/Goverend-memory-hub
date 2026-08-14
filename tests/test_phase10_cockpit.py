import pytest
import asyncpg
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "apps", "api")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

try:
    from apps.api.app.config import settings
except (ImportError, ModuleNotFoundError):
    from app.config import settings  # type: ignore # pyrefly: disable=missing-import

from app.cockpit_service import (
    get_cockpit_metrics,
    get_metric_drilldown,
    get_reconciliation_report
)

@pytest.mark.asyncio
async def test_cockpit_baseline_schema_and_tables_exist():
    conn = await asyncpg.connect(
        user=settings.POSTGRES_USER,
        password=settings.POSTGRES_PASSWORD,
        database=settings.POSTGRES_DB,
        host=settings.POSTGRES_HOST,
        port=settings.POSTGRES_PORT,
    )
    try:
        tbl = await conn.fetchval("SELECT table_name FROM information_schema.tables WHERE table_name = 'cockpit_baseline';")
        assert tbl == "cockpit_baseline"

        cnt = await conn.fetchval("SELECT COUNT(*) FROM cockpit_baseline;")
        assert cnt >= 10
    finally:
        await conn.close()

@pytest.mark.asyncio
async def test_labelled_retrieval_benchmark_table_exists():
    conn = await asyncpg.connect(
        user=settings.POSTGRES_USER,
        password=settings.POSTGRES_PASSWORD,
        database=settings.POSTGRES_DB,
        host=settings.POSTGRES_HOST,
        port=settings.POSTGRES_PORT,
    )
    try:
        tbl = await conn.fetchval("SELECT table_name FROM information_schema.tables WHERE table_name = 'labelled_retrieval_benchmark';")
        assert tbl == "labelled_retrieval_benchmark"

        cnt = await conn.fetchval("SELECT COUNT(*) FROM labelled_retrieval_benchmark;")
        assert cnt >= 5
    finally:
        await conn.close()

@pytest.mark.asyncio
async def test_cockpit_metrics_endpoint_payload():
    conn = await asyncpg.connect(
        user=settings.POSTGRES_USER,
        password=settings.POSTGRES_PASSWORD,
        database=settings.POSTGRES_DB,
        host=settings.POSTGRES_HOST,
        port=settings.POSTGRES_PORT,
    )
    try:
        metrics = await get_cockpit_metrics(conn)
        assert metrics["audit_chain"]["valid"] is True
        assert metrics["audit_chain"]["status"] == "VALID"
        assert metrics["audit_chain"]["total_events"] > 0

        # Verify Finance Reading View
        fin = metrics["finance_view"]
        assert "spend_vs_budget" in fin
        assert fin["spend_vs_budget"]["budget_usd"] == 1250.0
        assert "tollgate_cycle_time" in fin
        assert fin["tollgate_cycle_time"]["avg_cycle_seconds"] >= 0.0
        assert "human_override_rate" in fin
        assert "exceptions_requiring_attention" in fin

        # Verify Technology Reading View
        tech = metrics["technology_view"]
        assert "agent_first_pass_rate" in tech
        assert "retrieval_accuracy" in tech
        assert tech["retrieval_accuracy"]["labelled_benchmark_queries"] >= 5
        assert "decision_traceability" in tech
        assert "policy_denial_rate" in tech
        assert "trend" in tech["policy_denial_rate"]
        assert "reconciliation_drift" in tech
        assert "embedding_version_coverage" in tech
        assert "token_consumption_per_stage" in tech
    finally:
        await conn.close()

@pytest.mark.asyncio
async def test_relational_vector_graph_reconciliation_drift():
    conn = await asyncpg.connect(
        user=settings.POSTGRES_USER,
        password=settings.POSTGRES_PASSWORD,
        database=settings.POSTGRES_DB,
        host=settings.POSTGRES_HOST,
        port=settings.POSTGRES_PORT,
    )
    try:
        report = await get_reconciliation_report(conn)
        assert report["status"] in ("SYNCHRONIZED", "DRIFT_DETECTED")
        assert report["reconciliation_drift_count"] >= 0
        assert report["relational_store"]["approved_knowledge_assets"] > 0
        assert report["vector_store"]["unique_assets_projected"] >= 0
        assert report["graph_store"]["unique_assets_projected"] > 0
        assert "explanation" in report
    finally:
        await conn.close()

@pytest.mark.asyncio
async def test_cockpit_metric_drilldown():
    conn = await asyncpg.connect(
        user=settings.POSTGRES_USER,
        password=settings.POSTGRES_PASSWORD,
        database=settings.POSTGRES_DB,
        host=settings.POSTGRES_HOST,
        port=settings.POSTGRES_PORT,
    )
    try:
        drilldown = await get_metric_drilldown(conn, "POLICY_DENIAL")
        assert drilldown["metric_id"] == "POLICY_DENIAL"
        assert drilldown["underlying_audit_events_count"] >= 0
        if drilldown["underlying_audit_events_count"] > 0:
            evt = drilldown["audit_events"][0]
            assert evt["event_id"] is not None
            assert len(evt["current_hash"]) == 64
    finally:
        await conn.close()
