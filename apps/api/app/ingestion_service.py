import uuid
import hashlib
import json
import asyncpg
from typing import Dict, Any, List, Optional

VALID_CLASSIFICATIONS = {"PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED"}
VALID_BARRIER_SIDES = {"SIDE_A", "SIDE_B", "GENERAL"}
VALID_STEWARD_ROLES = {"STEWARD", "ADMIN"}

def compute_payload_hash(data: dict) -> str:
    """Compute deterministic SHA-256 payload hash."""
    canonical_bytes = json.dumps(data, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(canonical_bytes).hexdigest()

async def record_audit_event(
    conn: asyncpg.Connection,
    actor_type: str,
    actor_id: str,
    action: str,
    object_type: str,
    object_id: str,
    decision: str,
    reason_code: str,
    policy_version: str,
    payload_hash: str,
    on_behalf_of: Optional[str] = None
):
    """Insert audit log event into immutable, hash-chained audit_event table."""
    safe_reason_code = str(reason_code)[:64] if reason_code else "REASON_UNSPECIFIED"
    await conn.execute("""
        INSERT INTO audit_event (
            actor_type, actor_id, on_behalf_of, action, object_type, object_id,
            decision, reason_code, policy_version, payload_hash
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10);
    """, actor_type, str(actor_id), on_behalf_of, action, object_type, str(object_id),
       decision, safe_reason_code, policy_version, payload_hash)


async def validate_governance_metadata(conn: asyncpg.Connection, payload: dict) -> List[str]:
    """Validate required governance metadata. Returns list of error strings."""
    errors = []

    # Required fields
    required_fields = ["source", "source_ref", "classification", "barrier_side", "jurisdiction", "steward_id", "retention_class", "content_ref", "dek_ref", "content_hash"]
    for field in required_fields:
        if not payload.get(field):
            errors.append(f"Missing required metadata field: '{field}'")

    if errors:
        return errors

    # Enum checks
    classification = payload.get("classification")
    if classification not in VALID_CLASSIFICATIONS:
        errors.append(f"Invalid classification '{classification}'. Allowed: {sorted(list(VALID_CLASSIFICATIONS))}")

    barrier_side = payload.get("barrier_side")
    if barrier_side not in VALID_BARRIER_SIDES:
        errors.append(f"Invalid barrier_side '{barrier_side}'. Allowed: {sorted(list(VALID_BARRIER_SIDES))}")

    # Content hash length check
    chash = payload.get("content_hash", "")
    if len(chash) != 64 or not all(c in "0123456789abcdefABCDEF" for c in chash):
        errors.append("Invalid content_hash format. Must be a 64-character hexadecimal SHA-256 string.")

    # Steward identity check
    steward_id_str = str(payload.get("steward_id"))
    try:
        steward_uuid = uuid.UUID(steward_id_str)
        steward_role = await conn.fetchval("SELECT role FROM identity WHERE identity_id = $1;", steward_uuid)
        if not steward_role:
            errors.append(f"Steward identity '{steward_id_str}' does not exist.")
        elif steward_role not in VALID_STEWARD_ROLES:
            errors.append(f"Identity '{steward_id_str}' with role '{steward_role}' is not authorized as a steward.")
    except ValueError:
        errors.append(f"Steward ID '{steward_id_str}' is not a valid UUID.")

    # Personal data subject check
    personal_data = bool(payload.get("personal_data", False))
    subject_id = payload.get("subject_id")
    if personal_data:
        if not subject_id:
            errors.append("subject_id is mandatory when personal_data is True.")
        else:
            try:
                subj_uuid = uuid.UUID(str(subject_id))
                subj_exists = await conn.fetchval("SELECT subject_id FROM data_subject WHERE subject_id = $1;", subj_uuid)
                if not subj_exists:
                    errors.append(f"Data subject '{subject_id}' does not exist in data_subject table.")
            except ValueError:
                errors.append(f"subject_id '{subject_id}' is not a valid UUID.")

    # Direct APPROVED state ingestion check
    requested_state = payload.get("state")
    if requested_state == "APPROVED":
        errors.append("Uploaded knowledge assets cannot be ingested directly into APPROVED state without steward approval.")

    return errors

async def ingest_knowledge_asset(conn: asyncpg.Connection, payload: dict) -> Dict[str, Any]:
    """Ingest a new knowledge asset into PENDING_APPROVAL / DRAFT state with governance checks."""
    errors = await validate_governance_metadata(conn, payload)
    if errors:
        actor_id = str(payload.get("steward_id", "anonymous"))
        payload_hash = payload.get("content_hash") or compute_payload_hash(payload)
        await record_audit_event(
            conn,
            actor_type="USER",
            actor_id=actor_id,
            action="INGEST_KNOWLEDGE_ASSET",
            object_type="knowledge_asset",
            object_id=str(payload.get("source_ref", "unknown")),
            decision="DENY",
            reason_code="GOVERNANCE_VALIDATION_FAILED",
            policy_version="v1.0.0",
            payload_hash=payload_hash
        )
        raise ValueError(f"Governance validation failed: {'; '.join(errors)}")

    asset_id = str(uuid.uuid4())
    state = payload.get("state", "PENDING_APPROVAL")
    if state not in ("DRAFT", "PENDING_APPROVAL"):
        state = "PENDING_APPROVAL"

    version = int(payload.get("version", 1))
    supersession_id = payload.get("supersession_id")
    if supersession_id:
        supersession_id = str(uuid.UUID(str(supersession_id)))

    subject_id = payload.get("subject_id")
    if subject_id:
        subject_id = str(uuid.UUID(str(subject_id)))

    steward_id = str(uuid.UUID(str(payload["steward_id"])))

    await conn.execute("""
        INSERT INTO knowledge_asset (
            asset_id, source, source_ref, version, supersession_id, classification,
            barrier_side, jurisdiction, personal_data, subject_id, steward_id, approval_id,
            state, retention_class, legal_hold, content_ref, dek_ref, content_hash
        ) VALUES (
            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, NULL, $12, $13, $14, $15, $16, $17
        );
    """,
        uuid.UUID(asset_id),
        payload["source"],
        payload["source_ref"],
        version,
        uuid.UUID(supersession_id) if supersession_id else None,
        payload["classification"],
        payload["barrier_side"],
        payload["jurisdiction"],
        bool(payload.get("personal_data", False)),
        uuid.UUID(subject_id) if subject_id else None,
        uuid.UUID(steward_id),
        state,
        payload["retention_class"],
        bool(payload.get("legal_hold", False)),
        payload["content_ref"],
        payload["dek_ref"],
        payload["content_hash"]
    )

    await record_audit_event(
        conn,
        actor_type="USER",
        actor_id=steward_id,
        action="INGEST_KNOWLEDGE_ASSET",
        object_type="knowledge_asset",
        object_id=asset_id,
        decision="ALLOW",
        reason_code="GOVERNANCE_METADATA_VALIDATED",
        policy_version="v1.0.0",
        payload_hash=payload["content_hash"]
    )

    row = await conn.fetchrow("SELECT * FROM knowledge_asset WHERE asset_id = $1;", uuid.UUID(asset_id))
    return dict(row)

async def approve_knowledge_asset(
    conn: asyncpg.Connection,
    asset_id: str,
    approver_id: str,
    policy_version: str = "v1.0.0"
) -> Dict[str, Any]:
    """Approve a pending knowledge asset via human steward approval tollgate."""
    # Verify approver identity
    try:
        approver_uuid = uuid.UUID(str(approver_id))
    except ValueError:
        raise ValueError(f"Approver ID '{approver_id}' is not a valid UUID.")

    approver_role = await conn.fetchval("SELECT role FROM identity WHERE identity_id = $1;", approver_uuid)
    if not approver_role:
        raise ValueError(f"Approver identity '{approver_id}' does not exist.")
    if approver_role not in VALID_STEWARD_ROLES:
        raise ValueError(f"Approver '{approver_id}' with role '{approver_role}' is not authorized to approve assets.")

    # Fetch asset
    try:
        asset_uuid = uuid.UUID(str(asset_id))
    except ValueError:
        raise ValueError(f"Asset ID '{asset_id}' is not a valid UUID.")

    asset = await conn.fetchrow("SELECT * FROM knowledge_asset WHERE asset_id = $1;", asset_uuid)
    if not asset:
        raise ValueError(f"Knowledge asset '{asset_id}' not found.")

    if asset["state"] == "APPROVED":
        raise ValueError(f"Knowledge asset '{asset_id}' is already APPROVED.")

    if asset["state"] not in ("PENDING_APPROVAL", "DRAFT"):
        raise ValueError(f"Knowledge asset '{asset_id}' in state '{asset['state']}' cannot be approved.")

    # Generate approval record
    approval_id = uuid.uuid4()
    payload_hash = asset["content_hash"]

    await conn.execute("""
        INSERT INTO approval (
            approval_id, approver_id, approval_type, object_type, object_id,
            approved_payload_hash, policy_version, status
        ) VALUES ($1, $2, 'INGEST_APPROVAL', 'knowledge_asset', $3, $4, $5, 'APPROVED');
    """, approval_id, approver_uuid, str(asset_uuid), payload_hash, policy_version)

    # Transition asset state to APPROVED with approval_id attached
    await conn.execute("""
        UPDATE knowledge_asset
        SET approval_id = $1, state = 'APPROVED', updated_at = clock_timestamp()
        WHERE asset_id = $2;
    """, approval_id, asset_uuid)

    # Record audit event
    await record_audit_event(
        conn,
        actor_type="USER",
        actor_id=str(approver_uuid),
        action="APPROVE_KNOWLEDGE_ASSET",
        object_type="knowledge_asset",
        object_id=str(asset_uuid),
        decision="ALLOW",
        reason_code="HUMAN_STEWARD_APPROVAL",
        policy_version=policy_version,
        payload_hash=payload_hash
    )

    updated_asset = await conn.fetchrow("SELECT * FROM knowledge_asset WHERE asset_id = $1;", asset_uuid)
    return dict(updated_asset)

async def reject_knowledge_asset(
    conn: asyncpg.Connection,
    asset_id: str,
    approver_id: str,
    reason: str = "Steward rejected asset",
    policy_version: str = "v1.0.0"
) -> Dict[str, Any]:
    """Reject a pending knowledge asset via human steward approval tollgate."""
    try:
        approver_uuid = uuid.UUID(str(approver_id))
    except ValueError:
        raise ValueError(f"Approver ID '{approver_id}' is not a valid UUID.")

    approver_role = await conn.fetchval("SELECT role FROM identity WHERE identity_id = $1;", approver_uuid)
    if not approver_role:
        raise ValueError(f"Approver identity '{approver_id}' does not exist.")
    if approver_role not in VALID_STEWARD_ROLES:
        raise ValueError(f"Approver '{approver_id}' with role '{approver_role}' is not authorized to reject assets.")

    try:
        asset_uuid = uuid.UUID(str(asset_id))
    except ValueError:
        raise ValueError(f"Asset ID '{asset_id}' is not a valid UUID.")

    asset = await conn.fetchrow("SELECT * FROM knowledge_asset WHERE asset_id = $1;", asset_uuid)
    if not asset:
        raise ValueError(f"Knowledge asset '{asset_id}' not found.")

    if asset["state"] in ("APPROVED", "ARCHIVED"):
        raise ValueError(f"Knowledge asset '{asset_id}' in state '{asset['state']}' cannot be rejected.")

    approval_id = uuid.uuid4()
    payload_hash = asset["content_hash"]

    await conn.execute("""
        INSERT INTO approval (
            approval_id, approver_id, approval_type, object_type, object_id,
            approved_payload_hash, policy_version, status
        ) VALUES ($1, $2, 'INGEST_REJECTION', 'knowledge_asset', $3, $4, $5, 'REJECTED');
    """, approval_id, approver_uuid, str(asset_uuid), payload_hash, policy_version)

    await conn.execute("""
        UPDATE knowledge_asset
        SET state = 'REJECTED', updated_at = clock_timestamp()
        WHERE asset_id = $1;
    """, asset_uuid)


    await record_audit_event(
        conn,
        actor_type="USER",
        actor_id=str(approver_uuid),
        action="REJECT_KNOWLEDGE_ASSET",
        object_type="knowledge_asset",
        object_id=str(asset_uuid),
        decision="DENY",
        reason_code=f"HUMAN_STEWARD_REJECTION: {reason}",
        policy_version=policy_version,
        payload_hash=payload_hash
    )

    updated_asset = await conn.fetchrow("SELECT * FROM knowledge_asset WHERE asset_id = $1;", asset_uuid)
    return dict(updated_asset)

async def list_pending_assets(conn: asyncpg.Connection, limit: int = 50) -> List[Dict[str, Any]]:
    """Fetch assets pending steward approval."""
    rows = await conn.fetch("""
        SELECT * FROM knowledge_asset
        WHERE state = 'PENDING_APPROVAL'
        ORDER BY created_at DESC
        LIMIT $1;
    """, limit)
    return [dict(r) for r in rows]

async def get_asset_by_id(conn: asyncpg.Connection, asset_id: str) -> Optional[Dict[str, Any]]:
    """Get single knowledge asset by asset_id."""
    try:
        asset_uuid = uuid.UUID(str(asset_id))
    except ValueError:
        return None
    row = await conn.fetchrow("SELECT * FROM knowledge_asset WHERE asset_id = $1;", asset_uuid)
    return dict(row) if row else None
