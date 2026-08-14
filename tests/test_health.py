import pytest
from unittest.mock import patch

@pytest.mark.asyncio
async def test_root_endpoint(async_client):
    response = await async_client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Governed Memory Hub"
    assert data["phase"] == "Phase 1: Foundation"

@pytest.mark.asyncio
async def test_health_endpoint_structure(async_client):
    response = await async_client.get("/health")
    assert response.status_code in [200, 503]
    data = response.json()

    assert "status" in data
    assert data["status"] in ["healthy", "degraded", "unhealthy"]
    assert data["phase"] == "Phase 1: Foundation"
    assert "timestamp" in data
    assert "dependencies" in data
    assert "postgres" in data["dependencies"]
    assert "redis" in data["dependencies"]

@pytest.mark.asyncio
async def test_health_endpoint_mock_healthy(async_client):
    with patch("app.main.check_postgres_health") as mock_pg, \
         patch("app.main.check_redis_health") as mock_redis:

        mock_pg.return_value = {
            "status": "healthy",
            "latency_ms": 1.2,
            "message": "PostgreSQL 16 connection successful"
        }
        mock_redis.return_value = {
            "status": "healthy",
            "latency_ms": 0.8,
            "message": "Redis connection successful"
        }

        response = await async_client.get("/health")
        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "healthy"
        assert data["dependencies"]["postgres"]["status"] == "healthy"
        assert data["dependencies"]["redis"]["status"] == "healthy"

@pytest.mark.asyncio
async def test_health_endpoint_mock_unhealthy(async_client):
    with patch("app.main.check_postgres_health") as mock_pg, \
         patch("app.main.check_redis_health") as mock_redis:

        mock_pg.return_value = {
            "status": "unhealthy",
            "latency_ms": 5.0,
            "error": "Connection refused"
        }
        mock_redis.return_value = {
            "status": "unhealthy",
            "latency_ms": 5.0,
            "error": "Connection timeout"
        }

        response = await async_client.get("/health")
        assert response.status_code in [500, 503, 530]
        data = response.json()

        assert data["status"] == "unhealthy"
        assert data["dependencies"]["postgres"]["status"] == "unhealthy"
        assert data["dependencies"]["redis"]["status"] == "unhealthy"
