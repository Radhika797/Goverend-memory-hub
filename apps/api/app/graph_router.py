from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

from app.db import get_db_connection
from app.graph_service import project_graph_from_postgres, traverse_governed_graph

router = APIRouter(prefix="/api/v1/graph", tags=["Phase 7 Graph Lineage & Authority Memory"])

class TraverseGraphRequest(BaseModel):
    caller_identity_id: str
    start_object_id: str
    max_depth: Optional[int] = 3
    relation_filter: Optional[List[str]] = None
    policy_version: Optional[str] = "v1.0.0"

@router.post("/project", status_code=status.HTTP_201_CREATED)
async def project_graph_endpoint():
    """Idempotently project PostgreSQL source-of-truth tables into graph nodes and edges."""
    conn = await get_db_connection()
    try:
        counts = await project_graph_from_postgres(conn)
        return {
            "message": "Graph nodes and lineage edges projected successfully from PostgreSQL source of truth",
            "stats": counts
        }
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Graph projection failed: {e}")
    finally:
        await conn.close()

@router.post("/traverse")
async def traverse_graph_endpoint(req: TraverseGraphRequest):
    """
    Perform identity & policy-scoped recursive graph traversal ("HOP-BY-HOP GOVERNANCE FILTER").
    Evaluates clearance level, information barrier, and jurisdiction on EVERY expansion hop.
    """
    conn = await get_db_connection()
    try:
        results = await traverse_governed_graph(
            conn,
            caller_identity_id=req.caller_identity_id,
            start_object_id=req.start_object_id,
            max_depth=req.max_depth or 3,
            relation_filter=req.relation_filter,
            policy_version=req.policy_version or "v1.0.0"
        )
        return results
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Graph traversal engine failure: {e}")
    finally:
        await conn.close()
