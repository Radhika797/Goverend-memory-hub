import uuid
import hashlib
import json
import asyncpg
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

from app.ingestion_service import record_audit_event, compute_payload_hash

PROHIBITED_RETENTION_CLASSES = {"PERMANENT_HOLD", "LITIGATION_HOLD", "REGULATORY_RETAIN_7YR"}

async def execute_subject_erasure(
    conn: asyncpg.Connection,
    subject_id: str,
    authorizer_identity_id: str,
    reason: str = "GDPR_ARTICLE_17_RIGHT_TO_BE_FORGOTTEN",
    asset_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Execute Phase 11 Erasure & Retention Governance.
    Crypto-erases personal data, destroys DEK, hard-deletes vector chunks/graph nodes,
    writes immutable audit tombstone, or refuses erasure if legal_hold=true.
    """
    try:
        subj_uuid = uuid.UUID(str(subject_id))
    except ValueError:
        raise ValueError(f"Subject ID '{subject_id}' is not a valid UUID")

    try:
        auth_uuid = uuid.UUID(str(authorizer_identity_id))
    except ValueError:
        raise ValueError(f"Authorizer Identity ID '{authorizer_identity_id}' is not a valid UUID")

    # Fetch matching assets
    if asset_id:
        try:
            asset_uuid = uuid.UUID(str(asset_id))
            assets = await conn.fetch("SELECT * FROM knowledge_asset WHERE asset_id = $1 AND (subject_id = $2 OR personal_data = true);", asset_uuid, subj_uuid)
        except ValueError:
            raise ValueError(f"Asset ID '{asset_id}' is not a valid UUID")
    else:
        assets = await conn.fetch("SELECT * FROM knowledge_asset WHERE subject_id = $1;", subj_uuid)

    if not assets:
        subj_row = await conn.fetchrow("SELECT * FROM data_subject WHERE subject_id = $1;", subj_uuid)
        if not subj_row:
            raise ValueError(f"Data subject '{subject_id}' not found")

    # 1. Retention & Legal-Hold Decision Gate
    active_legal_holds = [a for a in assets if a["legal_hold"] is True]
    prohibited_retentions = [a for a in assets if a["retention_class"] in PROHIBITED_RETENTION_CLASSES]

    if active_legal_holds or prohibited_retentions:
        refusal_code = "LEGAL_HOLD_ACTIVE" if active_legal_holds else "RETENTION_POLICY_PROHIBITS_ERASURE"
        refusal_msg = f"Erasure refused: {len(active_legal_holds)} active legal hold(s), {len(prohibited_retentions)} prohibited retention class(es)"

        payload = {
            "subject_id": str(subj_uuid),
            "authorizer_identity_id": str(auth_uuid),
            "refusal_reason": refusal_code,
            "legal_hold_count": len(active_legal_holds),
            "prohibited_retention_count": len(prohibited_retentions)
        }
        payload_hash = compute_payload_hash(payload)

        # Record DENY audit event
        audit_event_id = await record_audit_event(
            conn,
            actor_type="USER",
            actor_id=str(auth_uuid),
            action="ERASE_PERSONAL_DATA",
            object_type="data_subject",
            object_id=str(subj_uuid),
            decision="DENY",
            reason_code=refusal_code,
            policy_version="v1.0.0",
            payload_hash=payload_hash
        )

        # Record erasure receipt
        digest_raw = f"{subj_uuid}|{auth_uuid}|REFUSED|{refusal_code}"
        erasure_digest = hashlib.sha256(digest_raw.encode("utf-8")).hexdigest()

        erasure_id = await conn.fetchval("""
            INSERT INTO erasure_receipt (
                subject_id, authorizer_identity_id, status, refusal_reason,
                dek_destroyed, chunks_deleted_count, graph_nodes_deleted_count, erasure_digest_sha256
            ) VALUES ($1, $2, 'REFUSED', $3, false, 0, 0, $4)
            RETURNING erasure_id;
        """, subj_uuid, auth_uuid, refusal_code, erasure_digest)

        return {
            "status": "REFUSED",
            "decision": "DENY",
            "reason_code": refusal_code,
            "refusal_message": refusal_msg,
            "subject_id": str(subj_uuid),
            "legal_hold_active": len(active_legal_holds) > 0,
            "prohibited_retention_active": len(prohibited_retentions) > 0,
            "audit_event_id": audit_event_id,
            "erasure_id": str(erasure_id),
            "erasure_digest_sha256": erasure_digest
        }

    # 2. Authorized Crypto-Erasure Execution
    asset_ids = [a["asset_id"] for a in assets]
    for a_id in asset_ids:
        await conn.execute("""
            UPDATE knowledge_asset
            SET dek_ref = 'KEY_DESTROYED_CRYPTO_ERASED',
                state = 'ARCHIVED',
                updated_at = clock_timestamp()
            WHERE asset_id = $1;
        """, a_id)

    # Hard-Delete Vector Chunks
    deleted_chunks_result = await conn.fetchval("""
        WITH deleted AS (
            DELETE FROM knowledge_chunk
            WHERE subject_id = $1 OR asset_id = ANY($2::uuid[])
            RETURNING chunk_id
        ) SELECT COUNT(*) FROM deleted;
    """, subj_uuid, asset_ids) or 0

    # Hard-Delete Graph Nodes and Edges
    deleted_nodes_result = await conn.fetchval("""
        WITH target_nodes AS (
            SELECT node_id FROM graph_node
            WHERE object_ref_id = $1 OR object_ref_id = ANY($2::uuid[])
        ),
        del_edges AS (
            DELETE FROM graph_edge
            WHERE source_node_id IN (SELECT node_id FROM target_nodes)
               OR target_node_id IN (SELECT node_id FROM target_nodes)
            RETURNING edge_id
        ),
        del_nodes AS (
            DELETE FROM graph_node
            WHERE node_id IN (SELECT node_id FROM target_nodes)
            RETURNING node_id
        ) SELECT COUNT(*) FROM del_nodes;
    """, subj_uuid, asset_ids) or 0

    # Cryptographic Erasure Receipt Digest
    digest_raw = f"{subj_uuid}|{auth_uuid}|ALLOW|KEY_DESTROYED_CRYPTO_ERASED|chunks:{deleted_chunks_result}|nodes:{deleted_nodes_result}"
    erasure_digest = hashlib.sha256(digest_raw.encode("utf-8")).hexdigest()

    # Record Immutable Audit Tombstone
    tombstone_payload = {
        "subject_id": str(subj_uuid),
        "authorizer_identity_id": str(auth_uuid),
        "reason": reason,
        "erased_assets_count": len(asset_ids),
        "dek_status": "KEY_DESTROYED_CRYPTO_ERASED",
        "chunks_deleted_count": deleted_chunks_result,
        "graph_nodes_deleted_count": deleted_nodes_result,
        "erasure_digest_sha256": erasure_digest
    }
    tombstone_payload_hash = compute_payload_hash(tombstone_payload)

    audit_event_id = await record_audit_event(
        conn,
        actor_type="USER",
        actor_id=str(auth_uuid),
        action="ERASE_PERSONAL_DATA",
        object_type="data_subject",
        object_id=str(subj_uuid),
        decision="ALLOW",
        reason_code="CRYPTO_ERASURE_COMPLETED",
        policy_version="v1.0.0",
        payload_hash=tombstone_payload_hash
    )

    # Insert Erasure Receipt
    erasure_id = await conn.fetchval("""
        INSERT INTO erasure_receipt (
            subject_id, authorizer_identity_id, status, refusal_reason,
            dek_destroyed, chunks_deleted_count, graph_nodes_deleted_count, erasure_digest_sha256
        ) VALUES ($1, $2, 'COMPLETED', NULL, true, $3, $4, $5)
        RETURNING erasure_id;
    """, subj_uuid, auth_uuid, deleted_chunks_result, deleted_nodes_result, erasure_digest)

    return {
        "status": "COMPLETED",
        "decision": "ALLOW",
        "reason_code": "CRYPTO_ERASURE_COMPLETED",
        "subject_id": str(subj_uuid),
        "erased_assets_count": len(asset_ids),
        "dek_destroyed": True,
        "dek_ref": "KEY_DESTROYED_CRYPTO_ERASED",
        "chunks_deleted_count": deleted_chunks_result,
        "graph_nodes_deleted_count": deleted_nodes_result,
        "audit_event_id": audit_event_id,
        "erasure_id": str(erasure_id),
        "erasure_digest_sha256": erasure_digest
    }


async def verify_erasure_status(conn: asyncpg.Connection, subject_id: str) -> Dict[str, Any]:
    """Verify data subject erasure status (zero active chunks, destroyed DEKs, audit receipts)."""
    try:
        subj_uuid = uuid.UUID(str(subject_id))
    except ValueError:
        raise ValueError(f"Subject ID '{subject_id}' is not a valid UUID")

    active_chunks = await conn.fetchval("SELECT COUNT(*) FROM knowledge_chunk WHERE subject_id = $1;", subj_uuid) or 0
    active_deks = await conn.fetchval("SELECT COUNT(*) FROM knowledge_asset WHERE subject_id = $1 AND dek_ref != 'KEY_DESTROYED_CRYPTO_ERASED';", subj_uuid) or 0
    receipts = await conn.fetch("SELECT erasure_id, status, refusal_reason, dek_destroyed, chunks_deleted_count, erasure_digest_sha256, created_at FROM erasure_receipt WHERE subject_id = $1 ORDER BY created_at DESC;", subj_uuid)

    receipt_list = [dict(r) for r in receipts]
    for r in receipt_list:
        r["erasure_id"] = str(r["erasure_id"])
        r["created_at"] = r["created_at"].isoformat()

    is_erased = (active_chunks == 0) and (active_deks == 0) and len(receipt_list) > 0 and receipt_list[0]["status"] == "COMPLETED"

    return {
        "subject_id": str(subj_uuid),
        "is_crypto_erased": is_erased,
        "active_vector_chunks": active_chunks,
        "active_deks": active_deks,
        "erasure_receipts_count": len(receipt_list),
        "latest_receipt": receipt_list[0] if receipt_list else None
    }
