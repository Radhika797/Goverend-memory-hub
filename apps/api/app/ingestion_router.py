from fastapi import APIRouter, HTTPException, status, Query
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

from app.db import get_db_connection
from app.ingestion_service import (
    ingest_knowledge_asset,
    approve_knowledge_asset,
    reject_knowledge_asset,
    list_pending_assets,
    get_asset_by_id
)

router = APIRouter(prefix="/api/v1/assets", tags=["Governed Ingestion & Approval Tollgate"])

class IngestAssetRequest(BaseModel):
    source: str
    source_ref: str
    classification: str
    barrier_side: str
    jurisdiction: str
    steward_id: str
    retention_class: str
    content_ref: str
    dek_ref: str
    content_hash: str
    personal_data: bool = False
    subject_id: Optional[str] = None
    version: int = 1
    supersession_id: Optional[str] = None
    legal_hold: bool = False
    state: Optional[str] = "PENDING_APPROVAL"

class ApproveAssetRequest(BaseModel):
    approver_id: str
    policy_version: Optional[str] = "v1.0.0"

class RejectAssetRequest(BaseModel):
    approver_id: str
    reason: Optional[str] = "Steward rejected asset"
    policy_version: Optional[str] = "v1.0.0"

@router.post("/ingest", status_code=status.HTTP_201_CREATED)
async def ingest_asset_endpoint(req: IngestAssetRequest):
    """Ingest new knowledge asset into PENDING_APPROVAL / DRAFT state."""
    conn = await get_db_connection()
    try:
        payload = req.model_dump()
        asset = await ingest_knowledge_asset(conn, payload)
        return {
            "message": "Knowledge asset successfully ingested into pending state",
            "asset": asset
        }
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    finally:
        await conn.close()

@router.get("/pending")
async def get_pending_assets_endpoint(limit: int = Query(50, ge=1, le=500)):
    """List knowledge assets currently pending human steward approval."""
    conn = await get_db_connection()
    try:
        assets = await list_pending_assets(conn, limit=limit)
        return {
            "count": len(assets),
            "pending_assets": assets
        }
    finally:
        await conn.close()

@router.get("/{asset_id}")
async def get_asset_endpoint(asset_id: str):
    """Get single knowledge asset details and governance status."""
    conn = await get_db_connection()
    try:
        asset = await get_asset_by_id(conn, asset_id)
        if not asset:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Knowledge asset '{asset_id}' not found.")
        return {"asset": asset}
    finally:
        await conn.close()

@router.post("/{asset_id}/approve")
async def approve_asset_endpoint(asset_id: str, req: ApproveAssetRequest):
    """Approve a pending knowledge asset via human steward approval tollgate."""
    conn = await get_db_connection()
    try:
        asset = await approve_knowledge_asset(conn, asset_id, req.approver_id, req.policy_version)
        return {
            "message": f"Knowledge asset '{asset_id}' successfully approved",
            "asset": asset
        }
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    finally:
        await conn.close()

@router.post("/{asset_id}/reject")
async def reject_asset_endpoint(asset_id: str, req: RejectAssetRequest):
    """Reject a pending knowledge asset via human steward approval tollgate."""
    conn = await get_db_connection()
    try:
        asset = await reject_knowledge_asset(conn, asset_id, req.approver_id, req.reason, req.policy_version)
        return {
            "message": f"Knowledge asset '{asset_id}' successfully rejected",
            "asset": asset
        }
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    finally:
        await conn.close()
