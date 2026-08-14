import uuid
import hashlib
import json
import asyncpg
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

from app.ingestion_service import record_audit_event, compute_payload_hash
from app.policy_engine import evaluate_access_policy

STAGE_ORDER = [
    "INTAKE_CLASSIFICATION",
    "CLASSIFICATION_REVIEW",
    "REQUIREMENTS_ANALYSIS",
    "REQUIREMENTS_APPROVAL",
    "BUILD_IMPLEMENTATION",
    "BUILD_REVIEW",
    "FINAL_AUDIT_VERIFICATION",
    "COMPLETED"
]

STAGE_AGENT_MAPPING = {
    "INTAKE_CLASSIFICATION": "svc_agent_intake",
    "REQUIREMENTS_ANALYSIS": "svc_agent_requirements",
    "BUILD_IMPLEMENTATION": "svc_agent_build",
    "BUILD_REVIEW": "svc_agent_review"
}

def sanitize_and_frame_as_data(input_text: str) -> str:
    """
    Sanitize input content and frame as DATA ONLY, NEVER INSTRUCTIONS.
    Prevents adversarial prompt injection payloads from overriding agent instructions.
    """
    # Wrap input in explicit data boundary tags
    return f"<DATA_CONTENT_DO_NOT_EXECUTE>\n{input_text}\n</DATA_CONTENT_DO_NOT_EXECUTE>"

async def create_orchestration_task(conn: asyncpg.Connection, initiator_id: str, policy_version: str = "v1.0.0") -> Dict[str, Any]:
    """Initiate a new 8-stage governed orchestration task."""
    try:
        init_uuid = uuid.UUID(str(initiator_id))
    except ValueError:
        raise ValueError(f"Initiator ID '{initiator_id}' is not a valid UUID")

    task_id = uuid.uuid4()
    await conn.execute("""
        INSERT INTO orchestration_task (task_id, current_stage, status, initiator_identity_id, policy_version)
        VALUES ($1, 'INTAKE_CLASSIFICATION', 'RUNNING', $2, $3);
    """, task_id, init_uuid, policy_version)

    payload_hash = compute_payload_hash({"initiator_id": initiator_id, "task_id": str(task_id)})
    await record_audit_event(
        conn,
        actor_type="USER",
        actor_id=str(init_uuid),
        action="CREATE_ORCHESTRATION_TASK",
        object_type="orchestration_task",
        object_id=str(task_id),
        decision="ALLOW",
        reason_code="ORCHESTRATION_TASK_INITIATED",
        policy_version=policy_version,
        payload_hash=payload_hash
    )

    return {
        "task_id": str(task_id),
        "current_stage": "INTAKE_CLASSIFICATION",
        "status": "RUNNING",
        "initiator_identity_id": str(init_uuid),
        "policy_version": policy_version
    }

async def execute_agent_stage(
    conn: asyncpg.Connection,
    task_id: str,
    agent_identity_id: str,
    proposal_content: Dict[str, Any],
    tool_calls: Optional[List[Dict[str, Any]]] = None,
    policy_version: str = "v1.0.0"
) -> Dict[str, Any]:
    """
    Execute an autonomous agent stage with fresh task-scoped context, tool-call policy enforcement,
    and fail-closed handoff creation.
    """
    task_uuid = uuid.UUID(str(task_id))
    task = await conn.fetchrow("SELECT * FROM orchestration_task WHERE task_id = $1;", task_uuid)
    if not task:
        raise ValueError(f"Task '{task_id}' not found")

    if task["status"] == "ESCALATED":
        raise ValueError(f"Task '{task_id}' is ESCALATED and cannot proceed fail-closed")

    if task["status"] == "AWAITING_HUMAN_APPROVAL":
        raise ValueError(f"Task '{task_id}' is awaiting human steward approval before next agent stage can start")

    current_stage = task["current_stage"]
    if current_stage not in STAGE_AGENT_MAPPING:
        raise ValueError(f"Current stage '{current_stage}' requires human review or is in terminal state")

    # 1. Verify Human Approval from Previous Review Stage (if not Stage 1)
    if current_stage != "INTAKE_CLASSIFICATION":
        last_handoff = await conn.fetchrow("""
            SELECT * FROM governed_handoff
            WHERE task_id = $1 AND status = 'APPROVED'
            ORDER BY created_at DESC LIMIT 1;
        """, task_uuid)

        if not last_handoff or not last_handoff["approval_id"]:
            # Fail-Closed: Escalate task due to missing human approval tollgate
            await escalate_task(conn, task_id, "MISSING_HUMAN_APPROVAL_TOLLGATE", policy_version)
            raise ValueError("Execution blocked fail-closed: Previous stage lacks approved human tollgate approval_id")

    # 2. Verify Agent Identity & Entitlements
    agent_uuid = uuid.UUID(str(agent_identity_id))
    agent = await conn.fetchrow("SELECT * FROM identity WHERE identity_id = $1 AND status = 'ACTIVE';", agent_uuid)
    if not agent:
        await escalate_task(conn, task_id, "UNMAPPED_AGENT_IDENTITY", policy_version)
        raise ValueError(f"Agent identity '{agent_identity_id}' is inactive or unmapped")

    # 3. Intercept & Evaluate Tool Calls through Policy Engine
    if tool_calls:
        for tc in tool_calls:
            policy_res = await evaluate_access_policy(
                conn,
                caller_identity_id=str(agent_uuid),
                target_asset_id=tc.get("target_resource_id", str(task_uuid)),
                action=tc.get("action", "READ_KNOWLEDGE_ASSET"),
                policy_version=policy_version
            )
            if policy_res["decision"] == "DENY":
                await escalate_task(conn, task_id, f"TOOL_CALL_POLICY_DENIAL_{tc.get('action')}", policy_version)
                raise ValueError(f"Agent tool call '{tc.get('action')}' denied by policy engine fail-closed")

    # 4. Construct Fresh Context & Sanitize Input
    raw_payload_str = json.dumps(proposal_content, sort_keys=True)
    framed_payload_str = sanitize_and_frame_as_data(raw_payload_str)
    payload_hash = hashlib.sha256(framed_payload_str.encode("utf-8")).hexdigest()

    # 5. Insert Handoff Record in PENDING_APPROVAL status
    handoff_id = uuid.uuid4()
    next_stage_idx = STAGE_ORDER.index(current_stage) + 1
    next_review_stage = STAGE_ORDER[next_stage_idx]

    await conn.execute("""
        INSERT INTO governed_handoff (handoff_id, task_id, stage, producer_agent_id, proposal_payload_json, payload_hash, status)
        VALUES ($1, $2, $3, $4, $5::jsonb, $6, 'PENDING_APPROVAL');
    """, handoff_id, task_uuid, current_stage, agent_uuid, raw_payload_str, payload_hash)

    # Update Task Status to AWAITING_HUMAN_APPROVAL and advance stage to next review stage
    await conn.execute("""
        UPDATE orchestration_task
        SET current_stage = $1, status = 'AWAITING_HUMAN_APPROVAL', updated_at = clock_timestamp()
        WHERE task_id = $2;
    """, next_review_stage, task_uuid)

    # Log Audit Event
    audit_hash = compute_payload_hash({"task_id": str(task_uuid), "handoff_id": str(handoff_id), "stage": current_stage, "payload_hash": payload_hash})
    await record_audit_event(
        conn,
        actor_type="AGENT",
        actor_id=str(agent_uuid),
        action="SUBMIT_AGENT_HANDOFF",
        object_type="governed_handoff",
        object_id=str(handoff_id),
        decision="ALLOW",
        reason_code="HANDOFF_PROPOSAL_SUBMITTED",
        policy_version=policy_version,
        payload_hash=audit_hash
    )

    return {
        "task_id": str(task_uuid),
        "handoff_id": str(handoff_id),
        "stage": current_stage,
        "next_stage": next_review_stage,
        "status": "AWAITING_HUMAN_APPROVAL",
        "payload_hash": payload_hash
    }

async def approve_stage_handoff(
    conn: asyncpg.Connection,
    task_id: str,
    handoff_id: str,
    steward_identity_id: str,
    policy_version: str = "v1.0.0"
) -> Dict[str, Any]:
    """Human Steward Approval Tollgate for Stage Handoffs."""
    task_uuid = uuid.UUID(str(task_id))
    handoff_uuid = uuid.UUID(str(handoff_id))
    steward_uuid = uuid.UUID(str(steward_identity_id))

    steward = await conn.fetchrow("SELECT * FROM identity WHERE identity_id = $1 AND status = 'ACTIVE';", steward_uuid)
    if not steward:
        raise ValueError(f"Steward identity '{steward_identity_id}' is inactive or unmapped")

    handoff = await conn.fetchrow("SELECT * FROM governed_handoff WHERE handoff_id = $1 AND task_id = $2;", handoff_uuid, task_uuid)
    if not handoff:
        raise ValueError(f"Handoff '{handoff_id}' not found for task '{task_id}'")

    if handoff["status"] == "APPROVED":
        return {"message": "Handoff is already approved", "approval_id": str(handoff["approval_id"])}

    # Create Approval Record
    approval_id = uuid.uuid4()
    await conn.execute("""
        INSERT INTO approval (approval_id, approver_id, approval_type, object_type, object_id, approved_payload_hash, policy_version, status)
        VALUES ($1, $2, 'STAGE_HANDOFF', 'governed_handoff', $3, $4, $5, 'APPROVED');
    """, approval_id, steward_uuid, str(handoff_uuid), handoff["payload_hash"], policy_version)

    # Update Handoff Status
    await conn.execute("""
        UPDATE governed_handoff
        SET status = 'APPROVED', approval_id = $1
        WHERE handoff_id = $2;
    """, approval_id, handoff_uuid)

    # Advance Task Stage to next Agent Stage or COMPLETED
    current_stage = handoff["stage"]
    current_stage_idx = STAGE_ORDER.index(current_stage)
    if current_stage == "BUILD_IMPLEMENTATION":
        next_agent_stage = "BUILD_REVIEW"
    elif current_stage in ("BUILD_REVIEW", "FINAL_AUDIT_VERIFICATION"):
        next_agent_stage = "COMPLETED"
    else:
        next_agent_stage = STAGE_ORDER[current_stage_idx + 2] if (current_stage_idx + 2) < len(STAGE_ORDER) else "COMPLETED"
    
    next_task_status = "COMPLETED" if next_agent_stage == "COMPLETED" else "RUNNING"

    await conn.execute("""
        UPDATE orchestration_task
        SET current_stage = $1, status = $2, updated_at = clock_timestamp()
        WHERE task_id = $3;
    """, next_agent_stage, next_task_status, task_uuid)

    # Log Audit Event
    audit_hash = compute_payload_hash({"task_id": str(task_uuid), "handoff_id": str(handoff_uuid), "approval_id": str(approval_id)})
    await record_audit_event(
        conn,
        actor_type="USER",
        actor_id=str(steward_uuid),
        action="APPROVE_STAGE_HANDOFF",
        object_type="governed_handoff",
        object_id=str(handoff_uuid),
        decision="ALLOW",
        reason_code="HUMAN_STEWARD_TOLLGATE_APPROVED",
        policy_version=policy_version,
        payload_hash=audit_hash
    )

    return {
        "task_id": str(task_uuid),
        "handoff_id": str(handoff_uuid),
        "approval_id": str(approval_id),
        "next_stage": next_agent_stage,
        "task_status": next_task_status
    }

async def escalate_task(conn: asyncpg.Connection, task_id: str, reason_code: str, policy_version: str = "v1.0.0") -> Dict[str, Any]:
    """Escalate a task fail-closed due to policy denial, unapproved access, or exception."""
    task_uuid = uuid.UUID(str(task_id))
    await conn.execute("""
        UPDATE orchestration_task
        SET status = 'ESCALATED', updated_at = clock_timestamp()
        WHERE task_id = $1;
    """, task_uuid)

    audit_hash = compute_payload_hash({"task_id": str(task_uuid), "reason_code": reason_code})
    await record_audit_event(
        conn,
        actor_type="SYSTEM",
        actor_id="SYSTEM_ORCHESTRATOR",
        action="ESCALATE_ORCHESTRATION_TASK",
        object_type="orchestration_task",
        object_id=str(task_uuid),
        decision="DENY",
        reason_code=reason_code,
        policy_version=policy_version,
        payload_hash=audit_hash
    )

    return {"task_id": str(task_uuid), "status": "ESCALATED", "reason_code": reason_code}
