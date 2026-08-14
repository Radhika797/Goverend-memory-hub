from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from typing import Optional, Dict, Any

from app.db import get_db_connection
from app.evidence_service import (
    generate_evidence_package,
    verify_evidence_package,
    execute_deliberate_failure
)

router = APIRouter(prefix="/api/v1/evidence", tags=["Phase 9 Evidence & Demonstration Proof"])

class GeneratePackRequest(BaseModel):
    scope_type: str = "GLOBAL"
    scope_ref_id: str
    generator_identity_id: str
    policy_version: Optional[str] = "v1.0.0"

class VerifyPackRequest(BaseModel):
    package_data: Dict[str, Any]

class DeliberateFailureRequest(BaseModel):
    failure_type: str  # PROMPT_INJECTION, ENTITLEMENT_ESCALATION, RUNAWAY_SPEND, DEPENDENCY_FAILURE
    caller_identity_id: str
    payload: Optional[Dict[str, Any]] = None
    policy_version: Optional[str] = "v1.0.0"

@router.post("/generate-pack", status_code=status.HTTP_201_CREATED)
async def generate_pack_endpoint(req: GeneratePackRequest):
    """Generate a non-rewriteable Evidence Package (JSON & ZIP) containing real Phase 1-8 records."""
    conn = await get_db_connection()
    try:
        res = await generate_evidence_package(
            conn,
            scope_type=req.scope_type,
            scope_ref_id=req.scope_ref_id,
            generator_identity_id=req.generator_identity_id,
            policy_version=req.policy_version or "v1.0.0"
        )
        return res
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Evidence package generation failed: {e}")
    finally:
        await conn.close()

@router.post("/verify-pack")
async def verify_pack_endpoint(req: VerifyPackRequest):
    """Automated cryptographic verification engine for evidence packages."""
    conn = await get_db_connection()
    try:
        res = await verify_evidence_package(conn, req.package_data)
        return res
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Evidence package verification failed: {e}")
    finally:
        await conn.close()

@router.get("/audit-summary")
async def audit_summary_endpoint():
    """Export audit log hash chain summary and governance compliance attestation."""
    conn = await get_db_connection()
    try:
        import hashlib
        events = await conn.fetch("SELECT event_id, actor_type, actor_id, action, object_type, object_id, decision, reason_code, policy_version, payload_hash, previous_hash, current_hash, created_at FROM audit_event ORDER BY event_id ASC;")
        
        all_events = [dict(e) for e in events]
        chain_valid = True
        for r in all_events:
            prev_h = r.get("previous_hash", "")
            curr_h = r.get("current_hash", "")
            canonical_str = (
                f"{prev_h}|"
                f"{r.get('actor_type') or ''}|"
                f"{r.get('actor_id') or ''}|"
                f"{r.get('on_behalf_of') or ''}|"
                f"{r.get('action') or ''}|"
                f"{r.get('object_type') or ''}|"
                f"{r.get('object_id') or ''}|"
                f"{r.get('decision') or ''}|"
                f"{r.get('reason_code') or ''}|"
                f"{r.get('policy_version') or ''}|"
                f"{r.get('payload_hash') or ''}"
            )
            expected_hash = hashlib.sha256(canonical_str.encode("utf-8")).hexdigest()
            if curr_h != expected_hash:
                chain_valid = False
                break

        return {
            "total_audit_events": len(all_events),
            "hash_chain_integrity": chain_valid,
            "root_hash": all_events[0]["current_hash"] if all_events else None,
            "latest_hash": all_events[-1]["current_hash"] if all_events else None,
            "requirement_evidence_summary": "Evidence supporting the requirement for SEC/FINRA/GDPR governed memory controls."
        }
    finally:
        await conn.close()

@router.post("/deliberate-failure")
async def deliberate_failure_endpoint(req: DeliberateFailureRequest):
    """Execute and audit one of the 4 PDF-mandated deliberate failure scenarios."""
    conn = await get_db_connection()
    try:
        res = await execute_deliberate_failure(
            conn,
            failure_type=req.failure_type,
            caller_identity_id=req.caller_identity_id,
            payload=req.payload,
            policy_version=req.policy_version or "v1.0.0"
        )
        return res
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Deliberate failure execution failed: {e}")
    finally:
        await conn.close()
