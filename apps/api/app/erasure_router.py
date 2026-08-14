from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
import asyncpg
import uuid

from app.db import get_db_connection
from app.erasure_service import execute_subject_erasure, verify_erasure_status

router = APIRouter(prefix="/api/v1/erasure", tags=["Erasure & Retention Governance"])

class ErasureRequest(BaseModel):
    subject_id: str = Field(..., description="UUID of data subject to erase")
    authorizer_identity_id: str = Field(..., description="UUID of authorizing admin/steward identity")
    reason: str = Field(default="GDPR_ARTICLE_17_RIGHT_TO_BE_FORGOTTEN", description="Erasure justification code")
    asset_id: Optional[str] = Field(default=None, description="Optional single asset UUID to erase")

@router.post("/execute", status_code=status.HTTP_200_OK)
async def execute_erasure_endpoint(
    req: ErasureRequest,
    conn: asyncpg.Connection = Depends(get_db_connection)
):
    """
    Execute Phase 11 Crypto-Erasure for a Data Subject or Asset.
    Checks legal_hold and retention class; destroys DEK and hard-deletes vector chunks if allowed,
    or returns 403 Forbidden Refusal if legal_hold=true.
    """
    try:
        res = await execute_subject_erasure(
            conn=conn,
            subject_id=req.subject_id,
            authorizer_identity_id=req.authorizer_identity_id,
            reason=req.reason,
            asset_id=req.asset_id
        )
        if res["status"] == "REFUSED":
            return res
        return res
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Erasure execution failed: {str(e)}")

@router.get("/verify/{subject_id}")
async def verify_erasure_endpoint(
    subject_id: str,
    conn: asyncpg.Connection = Depends(get_db_connection)
):
    """Verify data subject erasure status (zero active chunks, destroyed DEKs, audit receipts)."""
    try:
        return await verify_erasure_status(conn, subject_id)
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Erasure verification failed: {str(e)}")

@router.get("/receipt/{erasure_id}")
async def get_erasure_receipt_endpoint(
    erasure_id: str,
    conn: asyncpg.Connection = Depends(get_db_connection)
):
    """Fetch cryptographic erasure receipt by ID."""
    try:
        e_uuid = uuid.UUID(erasure_id)
        row = await conn.fetchrow("SELECT * FROM erasure_receipt WHERE erasure_id = $1;", e_uuid)
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Erasure receipt '{erasure_id}' not found")
        
        receipt = dict(row)
        receipt["erasure_id"] = str(receipt["erasure_id"])
        receipt["subject_id"] = str(receipt["subject_id"]) if receipt["subject_id"] else None
        receipt["asset_id"] = str(receipt["asset_id"]) if receipt["asset_id"] else None
        receipt["authorizer_identity_id"] = str(receipt["authorizer_identity_id"]) if receipt["authorizer_identity_id"] else None
        receipt["created_at"] = receipt["created_at"].isoformat()
        return receipt
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Erasure ID '{erasure_id}' is not a valid UUID")
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Receipt fetch failed: {str(e)}")
