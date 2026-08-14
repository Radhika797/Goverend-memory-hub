import pytest
import pytest_asyncio
import asyncpg
import uuid
import hashlib
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "apps", "api")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.config import settings

SAMPLE_HASH = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"

@pytest_asyncio.fixture(loop_scope="function")
async def db_steward_id():
    conn = await asyncpg.connect(
        user=settings.POSTGRES_USER,
        password=settings.POSTGRES_PASSWORD,
        database=settings.POSTGRES_DB,
        host=settings.POSTGRES_HOST,
        port=settings.POSTGRES_PORT,
    )
    try:
        row = await conn.fetchrow("SELECT identity_id FROM identity WHERE role IN ('STEWARD', 'ADMIN') LIMIT 1;")
        assert row is not None, "No STEWARD or ADMIN identity found in database."
        return str(row["identity_id"])
    finally:
        await conn.close()

@pytest_asyncio.fixture(loop_scope="function")
async def db_subject_id():
    conn = await asyncpg.connect(
        user=settings.POSTGRES_USER,
        password=settings.POSTGRES_PASSWORD,
        database=settings.POSTGRES_DB,
        host=settings.POSTGRES_HOST,
        port=settings.POSTGRES_PORT,
    )
    try:
        row = await conn.fetchrow("SELECT subject_id FROM data_subject LIMIT 1;")
        assert row is not None, "No data_subject found in database."
        return str(row["subject_id"])
    finally:
        await conn.close()

@pytest.fixture
def valid_ingest_payload(db_steward_id):
    return {
        "source": "Engineering Vault",
        "source_ref": f"INGEST-TEST-{uuid.uuid4().hex[:8]}",
        "classification": "INTERNAL",
        "barrier_side": "SIDE_A",
        "jurisdiction": "EU",
        "steward_id": db_steward_id,
        "retention_class": "5_YEARS",
        "content_ref": "s3://vault/test.pdf",
        "dek_ref": "kms/key-001",
        "content_hash": SAMPLE_HASH,
        "personal_data": False
    }

@pytest.mark.asyncio
async def test_ingest_asset_starts_pending(async_client, valid_ingest_payload):
    response = await async_client.post("/api/v1/assets/ingest", json=valid_ingest_payload)
    assert response.status_code == 201
    data = response.json()
    assert "asset" in data
    asset = data["asset"]
    assert asset["state"] == "PENDING_APPROVAL"
    assert asset["approval_id"] is None
    assert asset["source_ref"] == valid_ingest_payload["source_ref"]

@pytest.mark.asyncio
async def test_direct_approved_ingestion_rejected(async_client, valid_ingest_payload):
    payload = valid_ingest_payload.copy()
    payload["state"] = "APPROVED"
    response = await async_client.post("/api/v1/assets/ingest", json=payload)
    assert response.status_code == 400
    assert "cannot be ingested directly into APPROVED state" in response.json()["detail"]

@pytest.mark.asyncio
async def test_validation_fail_closed_invalid_classification(async_client, valid_ingest_payload):
    payload = valid_ingest_payload.copy()
    payload["classification"] = "TOP_SECRET_INVALID"
    response = await async_client.post("/api/v1/assets/ingest", json=payload)
    assert response.status_code == 400
    assert "Invalid classification" in response.json()["detail"]

@pytest.mark.asyncio
async def test_validation_fail_closed_missing_subject_id_for_personal_data(async_client, valid_ingest_payload):
    payload = valid_ingest_payload.copy()
    payload["personal_data"] = True
    payload["subject_id"] = None
    response = await async_client.post("/api/v1/assets/ingest", json=payload)
    assert response.status_code == 400
    assert "subject_id is mandatory when personal_data is True" in response.json()["detail"]

@pytest.mark.asyncio
async def test_validation_fail_closed_invalid_steward(async_client, valid_ingest_payload):
    payload = valid_ingest_payload.copy()
    payload["steward_id"] = str(uuid.uuid4())
    response = await async_client.post("/api/v1/assets/ingest", json=payload)
    assert response.status_code == 400
    assert "does not exist" in response.json()["detail"]

@pytest.mark.asyncio
async def test_human_approval_workflow(async_client, valid_ingest_payload, db_steward_id):
    # 1. Ingest asset -> PENDING_APPROVAL
    ingest_resp = await async_client.post("/api/v1/assets/ingest", json=valid_ingest_payload)
    assert ingest_resp.status_code == 201
    asset_id = ingest_resp.json()["asset"]["asset_id"]

    # 2. Steward approves asset
    approve_payload = {
        "approver_id": db_steward_id,
        "policy_version": "v1.0.0"
    }
    approve_resp = await async_client.post(f"/api/v1/assets/{asset_id}/approve", json=approve_payload)
    assert approve_resp.status_code == 200
    approved_asset = approve_resp.json()["asset"]
    assert approved_asset["state"] == "APPROVED"
    assert approved_asset["approval_id"] is not None

    # 3. Verify PostgreSQL database records
    conn = await asyncpg.connect(
        user=settings.POSTGRES_USER,
        password=settings.POSTGRES_PASSWORD,
        database=settings.POSTGRES_DB,
        host=settings.POSTGRES_HOST,
        port=settings.POSTGRES_PORT,
    )
    try:
        appr_row = await conn.fetchrow("SELECT * FROM approval WHERE approval_id = $1;", uuid.UUID(approved_asset["approval_id"]))
        assert appr_row is not None
        assert appr_row["status"] == "APPROVED"
        assert str(appr_row["approver_id"]) == db_steward_id

        audit_row = await conn.fetchrow("""
            SELECT * FROM audit_event
            WHERE object_id = $1 AND action = 'APPROVE_KNOWLEDGE_ASSET'
            ORDER BY event_id DESC LIMIT 1;
        """, asset_id)
        assert audit_row is not None
        assert audit_row["decision"] == "ALLOW"
    finally:
        await conn.close()

@pytest.mark.asyncio
async def test_human_rejection_workflow(async_client, valid_ingest_payload, db_steward_id):
    # 1. Ingest asset -> PENDING_APPROVAL
    ingest_resp = await async_client.post("/api/v1/assets/ingest", json=valid_ingest_payload)
    assert ingest_resp.status_code == 201
    asset_id = ingest_resp.json()["asset"]["asset_id"]

    # 2. Steward rejects asset
    reject_payload = {
        "approver_id": db_steward_id,
        "reason": "Policy compliance rejection: insufficient classification metadata",
        "policy_version": "v1.0.0"
    }
    reject_resp = await async_client.post(f"/api/v1/assets/{asset_id}/reject", json=reject_payload)
    assert reject_resp.status_code == 200
    rejected_asset = reject_resp.json()["asset"]
    assert rejected_asset["state"] == "REJECTED"

    # 3. Verify PostgreSQL database records
    conn = await asyncpg.connect(
        user=settings.POSTGRES_USER,
        password=settings.POSTGRES_PASSWORD,
        database=settings.POSTGRES_DB,
        host=settings.POSTGRES_HOST,
        port=settings.POSTGRES_PORT,
    )
    try:
        appr_row = await conn.fetchrow("SELECT * FROM approval WHERE object_id = $1 AND status = 'REJECTED';", asset_id)
        assert appr_row is not None

        audit_row = await conn.fetchrow("""
            SELECT * FROM audit_event
            WHERE object_id = $1 AND action = 'REJECT_KNOWLEDGE_ASSET'
            ORDER BY event_id DESC LIMIT 1;
        """, asset_id)
        assert audit_row is not None
        assert audit_row["decision"] == "DENY"
    finally:
        await conn.close()

@pytest.mark.asyncio
async def test_pending_assets_listing(async_client, valid_ingest_payload):
    ingest_resp = await async_client.post("/api/v1/assets/ingest", json=valid_ingest_payload)
    assert ingest_resp.status_code == 201

    pending_resp = await async_client.get("/api/v1/assets/pending")
    assert pending_resp.status_code == 200
    data = pending_resp.json()
    assert data["count"] > 0
    assert any(a["source_ref"] == valid_ingest_payload["source_ref"] for a in data["pending_assets"])

@pytest.mark.asyncio
async def test_audit_chain_integrity_after_ingest_and_approve(async_client, valid_ingest_payload):
    conn = await asyncpg.connect(
        user=settings.POSTGRES_USER,
        password=settings.POSTGRES_PASSWORD,
        database=settings.POSTGRES_DB,
        host=settings.POSTGRES_HOST,
        port=settings.POSTGRES_PORT,
    )
    try:
        events = await conn.fetch("SELECT * FROM audit_event ORDER BY event_id ASC;")
        assert len(events) > 0

        # Verify hash chaining
        for i in range(1, len(events)):
            prev_event = events[i - 1]
            curr_event = events[i]
            assert curr_event["previous_hash"] == prev_event["current_hash"]

            canonical_str = (
                f"{curr_event['previous_hash']}|"
                f"{curr_event['actor_type'] or ''}|"
                f"{curr_event['actor_id'] or ''}|"
                f"{curr_event['on_behalf_of'] or ''}|"
                f"{curr_event['action'] or ''}|"
                f"{curr_event['object_type'] or ''}|"
                f"{curr_event['object_id'] or ''}|"
                f"{curr_event['decision'] or ''}|"
                f"{curr_event['reason_code'] or ''}|"
                f"{curr_event['policy_version'] or ''}|"
                f"{curr_event['payload_hash'] or ''}"
            )
            expected_hash = hashlib.sha256(canonical_str.encode("utf-8")).hexdigest()
            assert curr_event["current_hash"] == expected_hash
    finally:
        await conn.close()
