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

from app.retrieval_service import project_asset_to_chunks, search_governed_memory, compute_access_attr_hash

@pytest.mark.asyncio
async def test_pgvector_extension_and_chunk_table_exists():
    conn = await asyncpg.connect(
        user=settings.POSTGRES_USER,
        password=settings.POSTGRES_PASSWORD,
        database=settings.POSTGRES_DB,
        host=settings.POSTGRES_HOST,
        port=settings.POSTGRES_PORT,
    )
    try:
        # Check pgvector extension
        ext = await conn.fetchval("SELECT extname FROM pg_extension WHERE extname = 'vector';")
        assert ext == "vector", "pgvector extension is not installed in PostgreSQL."

        # Check knowledge_chunk table
        tbl = await conn.fetchval("SELECT table_name FROM information_schema.tables WHERE table_name = 'knowledge_chunk';")
        assert tbl == "knowledge_chunk", "knowledge_chunk table does not exist."

    finally:
        await conn.close()

@pytest.mark.asyncio
async def test_asset_chunk_projection_with_denormalized_attrs():
    conn = await asyncpg.connect(
        user=settings.POSTGRES_USER,
        password=settings.POSTGRES_PASSWORD,
        database=settings.POSTGRES_DB,
        host=settings.POSTGRES_HOST,
        port=settings.POSTGRES_PORT,
    )
    try:
        # Fetch approved asset
        asset = await conn.fetchrow("SELECT asset_id FROM knowledge_asset WHERE state = 'APPROVED' LIMIT 1;")
        assert asset is not None
        asset_id = str(asset["asset_id"])

        text_content = "Northwind Securities Advisory Division deal analysis report. Confidential financial projections for 2026."
        chunks = await project_asset_to_chunks(conn, asset_id, text_content, chunk_size=10)
        assert len(chunks) > 0
        assert "access_attr_hash" in chunks[0]

        # Verify in DB
        db_chunk = await conn.fetchrow("SELECT * FROM knowledge_chunk WHERE asset_id = $1 LIMIT 1;", uuid.UUID(asset_id))
        assert db_chunk is not None
        assert db_chunk["embedding"] is not None
        assert db_chunk["embedding_model"] == "all-MiniLM-L6-v2"
        assert db_chunk["embedding_version"] == "v1.0"

    finally:
        await conn.close()

@pytest.mark.asyncio
async def test_filter_before_ranking_security():
    conn = await asyncpg.connect(
        user=settings.POSTGRES_USER,
        password=settings.POSTGRES_PASSWORD,
        database=settings.POSTGRES_DB,
        host=settings.POSTGRES_HOST,
        port=settings.POSTGRES_PORT,
    )
    try:
        # 1. Fetch RESTRICTED asset on SIDE_A (MNPI)
        mnpi_asset = await conn.fetchrow("""
            SELECT asset_id FROM knowledge_asset
            WHERE classification = 'RESTRICTED' AND barrier_side = 'SIDE_A' AND state = 'APPROVED'
            LIMIT 1;
        """)
        assert mnpi_asset is not None
        mnpi_asset_id = str(mnpi_asset["asset_id"])

        # Project chunks for MNPI asset
        await project_asset_to_chunks(conn, mnpi_asset_id, "SECRET MNPI DEAL FILE RESTRICTED INFORMATION BARRIER SIDE_A")

        # 2. Fetch User with MEMBER role (no RESTRICTED or SIDE_A entitlement)
        low_user = await conn.fetchrow("""
            SELECT i.identity_id FROM identity i
            WHERE i.role = 'MEMBER' AND i.status = 'ACTIVE'
            AND NOT EXISTS (SELECT 1 FROM entitlement e WHERE e.identity_id = i.identity_id AND e.classification = 'RESTRICTED')
            LIMIT 1;
        """)
        assert low_user is not None
        low_user_id = str(low_user["identity_id"])

        # Execute Search
        results = await search_governed_memory(conn, low_user_id, "SECRET MNPI DEAL FILE", top_k=10)
        returned_asset_ids = [c["asset_id"] for c in results["chunks"]]

        # PROVE Filter BEFORE Ranking: Unauthorized MNPI asset MUST NEVER BE RETURNED
        assert mnpi_asset_id not in returned_asset_ids, "CRITICAL SECURITY VIOLATION: Unauthorized MNPI asset returned to unentitled user!"

    finally:
        await conn.close()

@pytest.mark.asyncio
async def test_stale_access_attribute_fail_closed():
    conn = await asyncpg.connect(
        user=settings.POSTGRES_USER,
        password=settings.POSTGRES_PASSWORD,
        database=settings.POSTGRES_DB,
        host=settings.POSTGRES_HOST,
        port=settings.POSTGRES_PORT,
    )
    try:
        # Corrupt an access_attr_hash on a chunk
        chunk = await conn.fetchrow("SELECT chunk_id FROM knowledge_chunk LIMIT 1;")
        if chunk:
            chunk_id = chunk["chunk_id"]
            bogus_hash = "0000000000000000000000000000000000000000000000000000000000000000"
            await conn.execute("UPDATE knowledge_chunk SET access_attr_hash = $1 WHERE chunk_id = $2;", bogus_hash, chunk_id)

            # Search with admin
            admin = await conn.fetchrow("SELECT identity_id FROM identity WHERE role = 'ADMIN' LIMIT 1;")
            admin_id = str(admin["identity_id"])
            results = await search_governed_memory(conn, admin_id, "Northwind", top_k=50)

            returned_chunk_ids = [c["chunk_id"] for c in results["chunks"]]
            assert str(chunk_id) not in returned_chunk_ids, "Fail-closed check failed: Stale/corrupted chunk was not excluded!"

    finally:
        await conn.close()

@pytest.mark.asyncio
async def test_retrieval_citations_and_embedding_version():
    conn = await asyncpg.connect(
        user=settings.POSTGRES_USER,
        password=settings.POSTGRES_PASSWORD,
        database=settings.POSTGRES_DB,
        host=settings.POSTGRES_HOST,
        port=settings.POSTGRES_PORT,
    )
    try:
        admin = await conn.fetchrow("SELECT identity_id FROM identity WHERE role = 'ADMIN' LIMIT 1;")
        admin_id = str(admin["identity_id"])

        results = await search_governed_memory(conn, admin_id, "Advisory financial", top_k=5)
        if results["chunks"]:
            chunk = results["chunks"][0]
            assert "citation" in chunk
            assert "embedding_version" in chunk
            assert chunk["embedding_version"] == "v1.0"
            assert "Asset:" in chunk["citation"]

    finally:
        await conn.close()

@pytest.mark.asyncio
async def test_retrieval_audit_logging_including_denials():
    conn = await asyncpg.connect(
        user=settings.POSTGRES_USER,
        password=settings.POSTGRES_PASSWORD,
        database=settings.POSTGRES_DB,
        host=settings.POSTGRES_HOST,
        port=settings.POSTGRES_PORT,
    )
    try:
        admin = await conn.fetchrow("SELECT identity_id FROM identity WHERE role = 'ADMIN' LIMIT 1;")
        admin_id = str(admin["identity_id"])

        await search_governed_memory(conn, admin_id, "Policy governance check", top_k=5)

        audit_evt = await conn.fetchrow("""
            SELECT * FROM audit_event
            WHERE action = 'SEARCH_GOVERNED_MEMORY'
            ORDER BY event_id DESC LIMIT 1;
        """)
        assert audit_evt is not None
        assert audit_evt["actor_id"] == str(admin["identity_id"])
        assert audit_evt["decision"] in ("ALLOW", "DENY")

    finally:
        await conn.close()
