import pytest
import asyncpg
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "apps", "api")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.config import settings

@pytest.mark.asyncio
async def test_database_tables_exist():
    conn = await asyncpg.connect(
        user=settings.POSTGRES_USER,
        password=settings.POSTGRES_PASSWORD,
        database=settings.POSTGRES_DB,
        host=settings.POSTGRES_HOST,
        port=settings.POSTGRES_PORT,
    )
    try:
        expected_tables = {
            "schema_migrations",
            "identity",
            "data_subject",
            "approval",
            "knowledge_asset",
            "entitlement",
            "audit_event"
        }

        records = await conn.fetch("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public';
        """)
        existing_tables = {r["table_name"] for r in records}

        for table in expected_tables:
            assert table in existing_tables, f"Table '{table}' does not exist in PostgreSQL schema."

    finally:
        await conn.close()
