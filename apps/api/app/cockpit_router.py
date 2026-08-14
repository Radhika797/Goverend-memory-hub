from fastapi import APIRouter, HTTPException, status
from typing import Optional, Dict, Any

from app.db import get_db_connection
from app.cockpit_service import (
    get_cockpit_metrics,
    get_metric_drilldown,
    get_reconciliation_report
)

router = APIRouter(prefix="/api/v1/cockpit", tags=["Phase 10 Control Cockpit & Observability"])

@router.get("/metrics")
async def cockpit_metrics_endpoint():
    """
    Get Control Cockpit Metrics Payload (ONE Screen with TWO Readings: Finance View & Technology View).
    Returns real aggregated metrics, week-one baselines, live SHA-256 audit hash chain status,
    and relational/vector/graph reconciliation drift.
    """
    conn = await get_db_connection()
    try:
        metrics = await get_cockpit_metrics(conn)
        return metrics
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to fetch cockpit metrics: {e}")
    finally:
        await conn.close()

@router.get("/drilldown/{metric_id}")
async def cockpit_drilldown_endpoint(metric_id: str):
    """Drill down to real underlying audit events backing a specific cockpit metric."""
    conn = await get_db_connection()
    try:
        drilldown = await get_metric_drilldown(conn, metric_id)
        return drilldown
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to fetch metric drilldown: {e}")
    finally:
        await conn.close()

@router.get("/reconciliation")
async def cockpit_reconciliation_endpoint():
    """Get relational/vector/graph reconciliation report and drift status."""
    conn = await get_db_connection()
    try:
        report = await get_reconciliation_report(conn)
        return report
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to fetch reconciliation report: {e}")
    finally:
        await conn.close()
