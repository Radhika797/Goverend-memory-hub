from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

from app.db import get_db_connection
from app.orchestration_service import (
    create_orchestration_task,
    execute_agent_stage,
    approve_stage_handoff,
    escalate_task
)

router = APIRouter(prefix="/api/v1/orchestration", tags=["Phase 8 Governed Orchestration & Agent Handoffs"])

class CreateTaskRequest(BaseModel):
    initiator_identity_id: str
    policy_version: Optional[str] = "v1.0.0"

class ExecuteStageRequest(BaseModel):
    agent_identity_id: str
    proposal_content: Dict[str, Any]
    tool_calls: Optional[List[Dict[str, Any]]] = None
    policy_version: Optional[str] = "v1.0.0"

class ApproveStageRequest(BaseModel):
    handoff_id: str
    steward_identity_id: str
    policy_version: Optional[str] = "v1.0.0"

@router.post("/tasks", status_code=status.HTTP_201_CREATED)
async def create_task_endpoint(req: CreateTaskRequest):
    """Initiate a new 8-stage governed orchestration task."""
    conn = await get_db_connection()
    try:
        res = await create_orchestration_task(conn, req.initiator_identity_id, req.policy_version or "v1.0.0")
        return res
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Task creation failed: {e}")
    finally:
        await conn.close()

@router.post("/tasks/{task_id}/execute-stage")
async def execute_stage_endpoint(task_id: str, req: ExecuteStageRequest):
    """Execute an autonomous agent stage with fresh task-scoped context and tool-call policy enforcement."""
    conn = await get_db_connection()
    try:
        res = await execute_agent_stage(
            conn,
            task_id=task_id,
            agent_identity_id=req.agent_identity_id,
            proposal_content=req.proposal_content,
            tool_calls=req.tool_calls,
            policy_version=req.policy_version or "v1.0.0"
        )
        return res
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Stage execution failed: {e}")
    finally:
        await conn.close()

@router.post("/tasks/{task_id}/approve-stage")
async def approve_stage_endpoint(task_id: str, req: ApproveStageRequest):
    """Human Steward Approval Tollgate for Stage Handoffs."""
    conn = await get_db_connection()
    try:
        res = await approve_stage_handoff(
            conn,
            task_id=task_id,
            handoff_id=req.handoff_id,
            steward_identity_id=req.steward_identity_id,
            policy_version=req.policy_version or "v1.0.0"
        )
        return res
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Stage approval failed: {e}")
    finally:
        await conn.close()

@router.get("/tasks/{task_id}")
async def get_task_endpoint(task_id: str):
    """Get orchestration task details and handoff history."""
    conn = await get_db_connection()
    try:
        import uuid
        task_uuid = uuid.UUID(str(task_id))
        task = await conn.fetchrow("SELECT * FROM orchestration_task WHERE task_id = $1;", task_uuid)
        if not task:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Task '{task_id}' not found")
        
        handoffs = await conn.fetch("SELECT * FROM governed_handoff WHERE task_id = $1 ORDER BY created_at ASC;", task_uuid)

        return {
            "task_id": str(task["task_id"]),
            "current_stage": task["current_stage"],
            "status": task["status"],
            "initiator_identity_id": str(task["initiator_identity_id"]),
            "policy_version": task["policy_version"],
            "handoffs": [dict(h) for h in handoffs]
        }
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid task UUID format")
    finally:
        await conn.close()
