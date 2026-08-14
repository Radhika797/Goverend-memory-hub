from fastapi import FastAPI, Response, status
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime, timezone
import asyncio

from app.config import settings
from app.db import check_postgres_health, check_redis_health

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        from db.migrate import run_migrations
        await run_migrations()
    except Exception as e:
        print(f"Auto-migration on startup failed: {e}")
    yield

app = FastAPI(
    title=settings.APP_NAME,
    description="Governed Memory Hub - Phase 2 API with PostgreSQL & Audit Foundation",
    version="2.0.0-phase2",
    lifespan=lifespan
)

# Enable CORS for Next.js Cockpit
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {
        "name": settings.APP_NAME,
        "phase": "Phase 1: Foundation",
        "status": "running",
        "docs": "/docs",
        "health": "/health"
    }

@app.get("/health")
async def health_check(response: Response):
    postgres_task = check_postgres_health()
    redis_task = check_redis_health()

    postgres_res, redis_res = await asyncio.gather(postgres_task, redis_task)

    postgres_ok = postgres_res.get("status") == "healthy"
    redis_ok = redis_res.get("status") == "healthy"

    if postgres_ok and redis_ok:
        overall_status = "healthy"
        response.status_code = status.HTTP_200_OK
    elif postgres_ok or redis_ok:
        overall_status = "degraded"
        response.status_code = status.HTTP_200_OK
    else:
        overall_status = "unhealthy"
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return {
        "status": overall_status,
        "service": settings.APP_NAME,
        "phase": "Phase 1: Foundation",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "dependencies": {
            "postgres": postgres_res,
            "redis": redis_res
        }
    }
