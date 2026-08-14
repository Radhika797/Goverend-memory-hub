from fastapi import APIRouter, HTTPException, status, Query
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

from app.db import get_db_connection
from app.retrieval_service import project_asset_to_chunks, search_governed_memory

router = APIRouter(prefix="/api/v1/memory", tags=["Phase 6 Governed Memory & Vector Retrieval"])

class ProjectChunksRequest(BaseModel):
    asset_id: str
    content_text: str
    chunk_size: Optional[int] = 500

class SearchMemoryRequest(BaseModel):
    caller_identity_id: str
    query_text: str
    top_k: Optional[int] = 10
    mode: Optional[str] = "HYBRID"
    policy_version: Optional[str] = "v1.0.0"

@router.post("/project-chunks", status_code=status.HTTP_201_CREATED)
async def project_chunks_endpoint(req: ProjectChunksRequest):
    """Slice knowledge asset content into index-ordered chunks with denormalized governance projections."""
    conn = await get_db_connection()
    try:
        chunks = await project_asset_to_chunks(conn, req.asset_id, req.content_text, req.chunk_size or 500)
        return {
            "message": f"Knowledge asset '{req.asset_id}' successfully projected into {len(chunks)} governed chunks",
            "chunks": chunks
        }
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    finally:
        await conn.close()

@router.post("/search")
async def search_memory_endpoint(req: SearchMemoryRequest):
    """
    Perform identity & policy-scoped vector retrieval with 'FILTER BEFORE RANKING' guarantee.
    Enforces pre-filtering on clearance, barrier, jurisdiction, and asset state before scoring.
    """
    conn = await get_db_connection()
    try:
        results = await search_governed_memory(
            conn,
            caller_identity_id=req.caller_identity_id,
            query_text=req.query_text,
            top_k=req.top_k or 10,
            mode=req.mode or "HYBRID",
            policy_version=req.policy_version or "v1.0.0"
        )
        return results
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Retrieval engine failure: {e}")
    finally:
        await conn.close()
