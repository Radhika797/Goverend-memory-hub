import pytest
import asyncpg
import uuid
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "apps", "api")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

try:
    from apps.api.app.config import settings
except (ImportError, ModuleNotFoundError):
    from app.config import settings  # type: ignore # pyrefly: disable=missing-import

from app.graph_service import project_graph_from_postgres, traverse_governed_graph, compute_node_attr_hash

@pytest.mark.asyncio
async def test_graph_schema_and_tables_exist():
    conn = await asyncpg.connect(
        user=settings.POSTGRES_USER,
        password=settings.POSTGRES_PASSWORD,
        database=settings.POSTGRES_DB,
        host=settings.POSTGRES_HOST,
        port=settings.POSTGRES_PORT,
    )
    try:
        nodes_tbl = await conn.fetchval("SELECT table_name FROM information_schema.tables WHERE table_name = 'graph_node';")
        assert nodes_tbl == "graph_node", "graph_node table does not exist."

        edges_tbl = await conn.fetchval("SELECT table_name FROM information_schema.tables WHERE table_name = 'graph_edge';")
        assert edges_tbl == "graph_edge", "graph_edge table does not exist."

    finally:
        await conn.close()

@pytest.mark.asyncio
async def test_idempotent_graph_projection():
    conn = await asyncpg.connect(
        user=settings.POSTGRES_USER,
        password=settings.POSTGRES_PASSWORD,
        database=settings.POSTGRES_DB,
        host=settings.POSTGRES_HOST,
        port=settings.POSTGRES_PORT,
    )
    try:
        # Run projection twice
        stats1 = await project_graph_from_postgres(conn)
        stats2 = await project_graph_from_postgres(conn)

        assert stats1["nodes"] > 0
        assert stats1["edges"] > 0
        assert stats1["nodes"] == stats2["nodes"], "Graph projection is not idempotent (node count changed)."
        assert stats1["edges"] == stats2["edges"], "Graph projection is not idempotent (edge count changed)."

    finally:
        await conn.close()

@pytest.mark.asyncio
async def test_authorized_vs_unauthorized_graph_traversal():
    conn = await asyncpg.connect(
        user=settings.POSTGRES_USER,
        password=settings.POSTGRES_PASSWORD,
        database=settings.POSTGRES_DB,
        host=settings.POSTGRES_HOST,
        port=settings.POSTGRES_PORT,
    )
    try:
        # Project graph
        await project_graph_from_postgres(conn)

        # 1. Fetch RESTRICTED asset on SIDE_A (MNPI)
        mnpi_asset = await conn.fetchrow("""
            SELECT asset_id, classification, barrier_side, jurisdiction FROM knowledge_asset
            WHERE classification = 'RESTRICTED' AND barrier_side = 'SIDE_A' AND state = 'APPROVED'
            LIMIT 1;
        """)
        assert mnpi_asset is not None
        mnpi_asset_id = str(mnpi_asset["asset_id"])

        # Fetch Advisory Identity (SIDE_A, RESTRICTED, matching jurisdiction cleared)
        advisory_user = await conn.fetchrow("""
            SELECT i.identity_id FROM identity i
            JOIN entitlement e ON i.identity_id = e.identity_id
            WHERE e.barrier = $1 AND e.classification = $2 AND e.jurisdiction IN ($3, 'GLOBAL')
            LIMIT 1;
        """, mnpi_asset["barrier_side"], mnpi_asset["classification"], mnpi_asset["jurisdiction"])
        if not advisory_user:
            advisory_user = await conn.fetchrow("SELECT identity_id FROM identity WHERE role = 'ADMIN' LIMIT 1;")
        assert advisory_user is not None
        advisory_user_id = str(advisory_user["identity_id"])

        # Fetch Markets Identity (SIDE_B cleared - NOT SIDE_A)
        markets_user = await conn.fetchrow("""
            SELECT i.identity_id FROM identity i
            JOIN entitlement e ON i.identity_id = e.identity_id
            WHERE e.barrier = 'SIDE_B' AND i.role != 'ADMIN'
            LIMIT 1;
        """)
        assert markets_user is not None
        markets_user_id = str(markets_user["identity_id"])

        # Advisory User Traversal (Authorized)
        res_advisory = await traverse_governed_graph(conn, advisory_user_id, mnpi_asset_id, max_depth=3)
        assert res_advisory["audit_decision"] == "ALLOW"
        assert res_advisory["nodes_count"] > 0

        # Markets User Traversal (Unauthorized - Hostile Barrier Expansion Attempt)
        res_markets = await traverse_governed_graph(conn, markets_user_id, mnpi_asset_id, max_depth=3)
        assert res_markets["audit_decision"] == "DENY"
        assert res_markets["nodes_count"] == 0, "CRITICAL SECURITY VIOLATION: Unauthorized SIDE_A graph nodes returned to SIDE_B caller!"

    finally:
        await conn.close()

@pytest.mark.asyncio
async def test_stale_node_attribute_fail_closed():
    conn = await asyncpg.connect(
        user=settings.POSTGRES_USER,
        password=settings.POSTGRES_PASSWORD,
        database=settings.POSTGRES_DB,
        host=settings.POSTGRES_HOST,
        port=settings.POSTGRES_PORT,
    )
    try:
        await project_graph_from_postgres(conn)

        # Corrupt node_attr_hash on a graph node
        node = await conn.fetchrow("SELECT node_id, object_ref_id FROM graph_node WHERE classification = 'PUBLIC' LIMIT 1;")
        if node:
            node_id = node["node_id"]
            bogus_hash = "0000000000000000000000000000000000000000000000000000000000000000"
            await conn.execute("UPDATE graph_node SET node_attr_hash = $1 WHERE node_id = $2;", bogus_hash, node_id)

            admin = await conn.fetchrow("SELECT identity_id FROM identity WHERE role = 'ADMIN' LIMIT 1;")
            admin_id = str(admin["identity_id"])

            res = await traverse_governed_graph(conn, admin_id, str(node["object_ref_id"]), max_depth=2)
            returned_node_ids = [n["node_id"] for n in res["nodes"]]

            assert str(node_id) not in returned_node_ids, "Fail-closed check failed: Stale/corrupted graph node was not excluded!"

    finally:
        await conn.close()

@pytest.mark.asyncio
async def test_graph_traversal_audit_logging():
    conn = await asyncpg.connect(
        user=settings.POSTGRES_USER,
        password=settings.POSTGRES_PASSWORD,
        database=settings.POSTGRES_DB,
        host=settings.POSTGRES_HOST,
        port=settings.POSTGRES_PORT,
    )
    try:
        await project_graph_from_postgres(conn)
        admin = await conn.fetchrow("SELECT identity_id FROM identity WHERE role = 'ADMIN' LIMIT 1;")
        admin_id = str(admin["identity_id"])

        asset = await conn.fetchrow("SELECT asset_id FROM knowledge_asset LIMIT 1;")
        asset_id = str(asset["asset_id"])

        await traverse_governed_graph(conn, admin_id, asset_id, max_depth=2)

        audit_evt = await conn.fetchrow("""
            SELECT * FROM audit_event
            WHERE action = 'TRAVERSE_GOVERNED_GRAPH'
            ORDER BY event_id DESC LIMIT 1;
        """)
        assert audit_evt is not None
        assert audit_evt["actor_id"] == admin_id
        assert audit_evt["decision"] in ("ALLOW", "DENY")

    finally:
        await conn.close()
