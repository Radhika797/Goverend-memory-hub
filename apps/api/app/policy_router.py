from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

from app.db import get_db_connection
from app.identity_service import verify_oidc_token, create_delegation_token, verify_delegation_token
from app.policy_engine import evaluate_access_policy

router = APIRouter(prefix="/api/v1", tags=["Phase 5 Identity & Policy Engine"])

class VerifyOIDCTokenRequest(BaseModel):
    token: str

class CreateDelegationTokenRequest(BaseModel):
    grantor_id: str
    delegate_id: str
    requested_scopes: List[str]
    ttl_seconds: Optional[int] = 3600

class EvaluatePolicyRequest(BaseModel):
    caller_identity_id: str
    target_asset_id: str
    action: Optional[str] = "READ_KNOWLEDGE_ASSET"
    on_behalf_of_id: Optional[str] = None
    delegation_token_id: Optional[str] = None
    policy_version: Optional[str] = "v1.0.0"

@router.post("/identity/verify-oidc")
async def verify_oidc_endpoint(req: VerifyOIDCTokenRequest):
    """Verify OIDC JWT bearer token claims and return identity profile."""
    conn = await get_db_connection()
    try:
        identity = await verify_oidc_token(conn, req.token)
        return {
            "message": "OIDC identity verification successful",
            "identity": identity
        }
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))
    finally:
        await conn.close()

@router.post("/identity/delegation-token", status_code=status.HTTP_201_CREATED)
async def create_delegation_token_endpoint(req: CreateDelegationTokenRequest):
    """Issue a non-widening delegation token from human grantor to workload/agent delegate."""
    conn = await get_db_connection()
    try:
        token_info = await create_delegation_token(
            conn, req.grantor_id, req.delegate_id, req.requested_scopes, req.ttl_seconds
        )
        return {
            "message": "Non-widening delegation token created successfully",
            "delegation_token": token_info
        }
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    finally:
        await conn.close()

@router.post("/policy/evaluate")
async def evaluate_policy_endpoint(req: EvaluatePolicyRequest):
    """
    Evaluate 4-way governance access policy (Clearance, Barrier, Jurisdiction, Scope).
    Returns versioned decision: PERMIT, DENY, or PERMIT_WITH_CONSTRAINTS.
    """
    conn = await get_db_connection()
    try:
        decision = await evaluate_access_policy(
            conn,
            caller_identity_id=req.caller_identity_id,
            target_asset_id=req.target_asset_id,
            action=req.action or "READ_KNOWLEDGE_ASSET",
            on_behalf_of_id=req.on_behalf_of_id,
            delegation_token_id=req.delegation_token_id,
            policy_version=req.policy_version or "v1.0.0"
        )
        return decision
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Policy evaluation failed: {e}")
    finally:
        await conn.close()
