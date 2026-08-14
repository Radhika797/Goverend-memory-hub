import time
import asyncpg
import redis.asyncio as aioredis
from typing import Dict, Any
from app.config import settings

async def check_postgres_health() -> Dict[str, Any]:
    start_time = time.perf_counter()
    try:
        conn = await asyncpg.connect(
            user=settings.POSTGRES_USER,
            password=settings.POSTGRES_PASSWORD,
            database=settings.POSTGRES_DB,
            host=settings.POSTGRES_HOST,
            port=settings.POSTGRES_PORT,
            timeout=3.0
        )
        val = await conn.fetchval("SELECT 1")
        await conn.close()
        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
        if val == 1:
            return {
                "status": "healthy",
                "latency_ms": latency_ms,
                "message": "PostgreSQL 16 connection successful"
            }
        else:
            return {
                "status": "unhealthy",
                "latency_ms": latency_ms,
                "message": f"Unexpected validation result: {val}"
            }
    except Exception as e:
        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
        return {
            "status": "unhealthy",
            "latency_ms": latency_ms,
            "error": str(e)
        }

async def check_redis_health() -> Dict[str, Any]:
    start_time = time.perf_counter()
    try:
        r = aioredis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            password=settings.REDIS_PASSWORD if settings.REDIS_PASSWORD else None,
            socket_timeout=3.0
        )
        pong = await r.ping()
        await r.aclose()
        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
        if pong:
            return {
                "status": "healthy",
                "latency_ms": latency_ms,
                "message": "Redis connection successful"
            }
        else:
            return {
                "status": "unhealthy",
                "latency_ms": latency_ms,
                "message": "Redis ping returned False"
            }
    except Exception as e:
        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
        return {
            "status": "unhealthy",
            "latency_ms": latency_ms,
            "error": str(e)
        }
