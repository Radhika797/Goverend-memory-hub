import pytest
import pytest_asyncio
import asyncpg
import os
import sys
import uuid

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "apps", "api")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

try:
    from apps.api.app.config import settings
except (ImportError, ModuleNotFoundError):
    from app.config import settings  # type: ignore # pyrefly: disable=missing-import

from app.erasure_service import (
    execute_subject_erasure,
    verify_erasure_status
)
from app.cockpit_service import calculate_sha256_audit_chain
from app.retrieval_service import compute_access_attr_hash, generate_vector_embedding

TARGET_SUBJECT_ID = "00000000-0000-0000-0000-000000001391"
LEGAL_HOLD_SUBJECT_ID = "00000000-0000-0000-0000-00000000139f"

@pytest_asyncio.fixture(autouse=True, scope="module")
async def setup_erasure_module_fixtures():
    conn = await asyncpg.connect(
        user=settings.POSTGRES_USER,
        password=settings.POSTGRES_PASSWORD,
        database=settings.POSTGRES_DB,
        host=settings.POSTGRES_HOST,
        port=settings.POSTGRES_PORT,
    )
    try:
        # 1. Reset Erasable Subject 1391
        subj_uuid = uuid.UUID(TARGET_SUBJECT_ID)
        await conn.execute("""
            UPDATE knowledge_asset
            SET dek_ref = 'kms/key-hr-test-1391',
                state = 'APPROVED',
                version = version + 1,
                legal_hold = false,
                retention_class = 'HR_PERSONAL_DATA'
            WHERE subject_id = $1;
        """, subj_uuid)

        # Clear old chunks and re-insert active vector chunks for 1391
        await conn.execute("DELETE FROM knowledge_chunk WHERE subject_id = $1;", subj_uuid)
        asset = await conn.fetchrow("SELECT * FROM knowledge_asset WHERE subject_id = $1 LIMIT 1;", subj_uuid)
        if asset:
            content_text = "Personal identity privacy metadata record for subject 1391"
            attr_hash = compute_access_attr_hash(asset["classification"], asset["barrier_side"], asset["jurisdiction"], asset["state"])
            embedding = generate_vector_embedding(content_text)
            vector_str = f"[{','.join(str(v) for v in embedding)}]"

            await conn.execute("""
                INSERT INTO knowledge_chunk (
                    chunk_id, asset_id, chunk_index, chunk_content, token_count,
                    embedding, embedding_model, embedding_version,
                    classification, barrier_side, jurisdiction, personal_data, subject_id,
                    asset_state, retention_class, legal_hold, access_attr_hash
                ) VALUES (
                    $1, $2, 1, $3, 10,
                    $4::vector, 'all-MiniLM-L6-v2', 'v1.0',
                    $5, $6, $7, true, $8,
                    $9, $10, false, $11
                );
            """, uuid.uuid4(), asset["asset_id"], content_text, vector_str,
                 asset["classification"], asset["barrier_side"], asset["jurisdiction"], subj_uuid,
                 asset["state"], asset["retention_class"], attr_hash)

        # 2. Reset Legal-Hold Subject 139f
        legal_subj_uuid = uuid.UUID(LEGAL_HOLD_SUBJECT_ID)
        await conn.execute("""
            UPDATE knowledge_asset
            SET dek_ref = 'kms/key-litigation-hold-99',
                state = 'APPROVED',
                version = version + 1,
                legal_hold = true,
                retention_class = 'LITIGATION_HOLD'
            WHERE subject_id = $1;
        """, legal_subj_uuid)
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_erasure_schema_and_tables_exist():
    conn = await asyncpg.connect(
        user=settings.POSTGRES_USER,
        password=settings.POSTGRES_PASSWORD,
        database=settings.POSTGRES_DB,
        host=settings.POSTGRES_HOST,
        port=settings.POSTGRES_PORT,
    )
    try:
        tbl = await conn.fetchval("SELECT table_name FROM information_schema.tables WHERE table_name = 'erasure_receipt';")
        assert tbl == "erasure_receipt"

        legal_hold_subj = await conn.fetchrow("SELECT * FROM data_subject WHERE subject_id = $1;", uuid.UUID(LEGAL_HOLD_SUBJECT_ID))
        assert legal_hold_subj is not None
    finally:
        await conn.close()

@pytest.mark.asyncio
async def test_pre_erasure_retrieval_returns_content():
    conn = await asyncpg.connect(
        user=settings.POSTGRES_USER,
        password=settings.POSTGRES_PASSWORD,
        database=settings.POSTGRES_DB,
        host=settings.POSTGRES_HOST,
        port=settings.POSTGRES_PORT,
    )
    try:
        chunks = await conn.fetch("SELECT * FROM knowledge_chunk WHERE subject_id = $1;", uuid.UUID(TARGET_SUBJECT_ID))
        assert len(chunks) > 0, "Pre-erasure state must contain active vector chunks for target subject"

        asset = await conn.fetchrow("SELECT * FROM knowledge_asset WHERE subject_id = $1 LIMIT 1;", uuid.UUID(TARGET_SUBJECT_ID))
        assert asset is not None
        assert asset["dek_ref"] != "KEY_DESTROYED_CRYPTO_ERASED"
    finally:
        await conn.close()

@pytest.mark.asyncio
async def test_authorized_crypto_erasure_execution():
    conn = await asyncpg.connect(
        user=settings.POSTGRES_USER,
        password=settings.POSTGRES_PASSWORD,
        database=settings.POSTGRES_DB,
        host=settings.POSTGRES_HOST,
        port=settings.POSTGRES_PORT,
    )
    try:
        admin_id = await conn.fetchval("SELECT identity_id FROM identity WHERE role = 'ADMIN' LIMIT 1;")
        
        result = await execute_subject_erasure(
            conn=conn,
            subject_id=TARGET_SUBJECT_ID,
            authorizer_identity_id=str(admin_id),
            reason="GDPR_ARTICLE_17_RIGHT_TO_BE_FORGOTTEN"
        )

        assert result["status"] == "COMPLETED"
        assert result["decision"] == "ALLOW"
        assert result["dek_destroyed"] is True
        assert result["dek_ref"] == "KEY_DESTROYED_CRYPTO_ERASED"
        assert result["chunks_deleted_count"] > 0
        assert len(result["erasure_digest_sha256"]) == 64

        # Verify erasure receipt in database
        receipt = await conn.fetchrow("SELECT * FROM erasure_receipt WHERE erasure_id = $1;", uuid.UUID(result["erasure_id"]))
        assert receipt is not None
        assert receipt["dek_destroyed"] is True
        assert receipt["status"] == "COMPLETED"
    finally:
        await conn.close()

@pytest.mark.asyncio
async def test_post_erasure_identical_retrieval_returns_zero():
    conn = await asyncpg.connect(
        user=settings.POSTGRES_USER,
        password=settings.POSTGRES_PASSWORD,
        database=settings.POSTGRES_DB,
        host=settings.POSTGRES_HOST,
        port=settings.POSTGRES_PORT,
    )
    try:
        chunks = await conn.fetch("SELECT * FROM knowledge_chunk WHERE subject_id = $1;", uuid.UUID(TARGET_SUBJECT_ID))
        assert len(chunks) == 0, "Post-erasure vector search must return ZERO chunks"

        status_res = await verify_erasure_status(conn, TARGET_SUBJECT_ID)
        assert status_res["is_crypto_erased"] is True
        assert status_res["active_vector_chunks"] == 0
        assert status_res["active_deks"] == 0
    finally:
        await conn.close()

@pytest.mark.asyncio
async def test_audit_chain_integrity_after_erasure():
    conn = await asyncpg.connect(
        user=settings.POSTGRES_USER,
        password=settings.POSTGRES_PASSWORD,
        database=settings.POSTGRES_DB,
        host=settings.POSTGRES_HOST,
        port=settings.POSTGRES_PORT,
    )
    try:
        audit_rows = await conn.fetch("SELECT event_id, actor_type, actor_id, on_behalf_of, action, object_type, object_id, decision, reason_code, policy_version, payload_hash, previous_hash, current_hash, created_at FROM audit_event ORDER BY event_id ASC;")
        audit_events = [dict(r) for r in audit_rows]
        
        valid = calculate_sha256_audit_chain(audit_events)
        assert valid is True, "Audit log SHA-256 hash chain must remain 100% valid after erasure tombstones"
    finally:
        await conn.close()

@pytest.mark.asyncio
async def test_legal_hold_refusal():
    conn = await asyncpg.connect(
        user=settings.POSTGRES_USER,
        password=settings.POSTGRES_PASSWORD,
        database=settings.POSTGRES_DB,
        host=settings.POSTGRES_HOST,
        port=settings.POSTGRES_PORT,
    )
    try:
        admin_id = await conn.fetchval("SELECT identity_id FROM identity WHERE role = 'ADMIN' LIMIT 1;")

        res = await execute_subject_erasure(
            conn=conn,
            subject_id=LEGAL_HOLD_SUBJECT_ID,
            authorizer_identity_id=str(admin_id),
            reason="REQUESTED_ERASURE_TEST"
        )

        assert res["status"] == "REFUSED"
        assert res["decision"] == "DENY"
        assert res["reason_code"] == "LEGAL_HOLD_ACTIVE"
        assert res["legal_hold_active"] is True

        # Verify asset remains retained in PostgreSQL
        asset = await conn.fetchrow("SELECT * FROM knowledge_asset WHERE subject_id = $1 LIMIT 1;", uuid.UUID(LEGAL_HOLD_SUBJECT_ID))
        assert asset is not None
        assert asset["legal_hold"] is True
        assert asset["dek_ref"] != "KEY_DESTROYED_CRYPTO_ERASED"

        # Verify DENY audit event logged
        audit_evt = await conn.fetchrow("""
            SELECT * FROM audit_event
            WHERE action = 'ERASE_PERSONAL_DATA'
              AND object_id = $1
              AND decision = 'DENY'
            ORDER BY event_id DESC LIMIT 1;
        """, LEGAL_HOLD_SUBJECT_ID)
        assert audit_evt is not None
        assert audit_evt["reason_code"] == "LEGAL_HOLD_ACTIVE"
    finally:
        await conn.close()
