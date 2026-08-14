import os
import sys
import uuid
import pytest
import asyncpg

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "apps", "api")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.config import settings

@pytest.mark.asyncio
async def test_approval_integrity_constraint():
    conn = await asyncpg.connect(
        user=settings.POSTGRES_USER,
        password=settings.POSTGRES_PASSWORD,
        database=settings.POSTGRES_DB,
        host=settings.POSTGRES_HOST,
        port=settings.POSTGRES_PORT,
    )
    try:
        steward = await conn.fetchrow("SELECT identity_id FROM identity WHERE role = 'STEWARD' LIMIT 1;")
        if not steward:
            steward_id = str(uuid.uuid4())
            await conn.execute("""
                INSERT INTO identity (identity_id, name, type, role, department)
                VALUES ($1, 'Test Steward', 'USER', 'STEWARD', 'Engineering');
            """, steward_id)
        else:
            steward_id = str(steward["identity_id"])

        # Attempt to insert an APPROVED asset without approval_id
        with pytest.raises(asyncpg.CheckViolationError) as exc_info:
            await conn.execute("""
                INSERT INTO knowledge_asset (
                    source, source_ref, classification, barrier_side, jurisdiction,
                    steward_id, state, retention_class, content_ref, dek_ref, content_hash, approval_id
                ) VALUES (
                    'Test Source', 'REF-001', 'INTERNAL', 'SIDE_A', 'EU',
                    $1, 'APPROVED', '5_YEARS', 's3://test', 'key-01',
                    'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855', NULL
                );
            """, steward_id)

        assert "chk_approval_integrity" in str(exc_info.value)

    finally:
        await conn.close()

@pytest.mark.asyncio
async def test_personal_data_subject_required_constraint():
    conn = await asyncpg.connect(
        user=settings.POSTGRES_USER,
        password=settings.POSTGRES_PASSWORD,
        database=settings.POSTGRES_DB,
        host=settings.POSTGRES_HOST,
        port=settings.POSTGRES_PORT,
    )
    try:
        steward = await conn.fetchrow("SELECT identity_id FROM identity LIMIT 1;")
        steward_id = str(steward["identity_id"])

        # Attempt to insert personal_data = TRUE without subject_id
        with pytest.raises(asyncpg.CheckViolationError) as exc_info:
            await conn.execute("""
                INSERT INTO knowledge_asset (
                    source, source_ref, classification, barrier_side, jurisdiction,
                    personal_data, subject_id, steward_id, state, retention_class,
                    content_ref, dek_ref, content_hash
                ) VALUES (
                    'Test Source', 'REF-002', 'INTERNAL', 'SIDE_A', 'EU',
                    TRUE, NULL, $1, 'DRAFT', '5_YEARS',
                    's3://test', 'key-01', 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'
                );
            """, steward_id)

        assert "chk_personal_data_subject" in str(exc_info.value)

    finally:
        await conn.close()

@pytest.mark.asyncio
async def test_invalid_state_rejected():
    conn = await asyncpg.connect(
        user=settings.POSTGRES_USER,
        password=settings.POSTGRES_PASSWORD,
        database=settings.POSTGRES_DB,
        host=settings.POSTGRES_HOST,
        port=settings.POSTGRES_PORT,
    )
    try:
        steward = await conn.fetchrow("SELECT identity_id FROM identity LIMIT 1;")
        steward_id = str(steward["identity_id"])

        with pytest.raises(asyncpg.CheckViolationError):
            await conn.execute("""
                INSERT INTO knowledge_asset (
                    source, source_ref, classification, barrier_side, jurisdiction,
                    steward_id, state, retention_class, content_ref, dek_ref, content_hash
                ) VALUES (
                    'Test Source', 'REF-003', 'INTERNAL', 'SIDE_A', 'EU',
                    $1, 'INVALID_GOVERNANCE_STATE', '5_YEARS', 's3://test', 'key-01',
                    'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'
                );
            """, steward_id)

    finally:
        await conn.close()
