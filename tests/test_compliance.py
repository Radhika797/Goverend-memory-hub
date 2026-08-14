import os
import sys
import uuid
import pytest
import asyncpg

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "apps", "api")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# pyrefly: ignore [missing-import]
from app.config import settings

@pytest.mark.asyncio
async def test_check1_row_level_security_enabled():
    conn = await asyncpg.connect(
        user=settings.POSTGRES_USER,
        password=settings.POSTGRES_PASSWORD,
        database=settings.POSTGRES_DB,
        host=settings.POSTGRES_HOST,
        port=settings.POSTGRES_PORT,
    )
    try:
        tables = ['knowledge_asset', 'audit_event', 'entitlement', 'approval', 'identity', 'data_subject']
        for table in tables:
            rls_enabled = await conn.fetchval("""
                SELECT c.relrowsecurity
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE c.relname = $1 AND n.nspname = 'public';
            """, table)
            assert rls_enabled is True, f"Row Level Security (RLS) is not enabled on table '{table}'."

        policies = await conn.fetch("SELECT tablename, policyname FROM pg_policies WHERE schemaname = 'public';")
        policy_tables = {p['tablename'] for p in policies}
        for table in tables:
            assert table in policy_tables, f"No RLS policy defined for table '{table}'."

    finally:
        await conn.close()

@pytest.mark.asyncio
async def test_check2_audit_database_role_permissions():
    conn = await asyncpg.connect(
        user=settings.POSTGRES_USER,
        password=settings.POSTGRES_PASSWORD,
        database=settings.POSTGRES_DB,
        host=settings.POSTGRES_HOST,
        port=settings.POSTGRES_PORT,
    )
    try:
        has_select = await conn.fetchval("SELECT has_table_privilege('gmh_app_role', 'audit_event', 'SELECT');")
        has_insert = await conn.fetchval("SELECT has_table_privilege('gmh_app_role', 'audit_event', 'INSERT');")
        has_update = await conn.fetchval("SELECT has_table_privilege('gmh_app_role', 'audit_event', 'UPDATE');")
        has_delete = await conn.fetchval("SELECT has_table_privilege('gmh_app_role', 'audit_event', 'DELETE');")

        assert has_select is True, "gmh_app_role must have SELECT privilege on audit_event."
        assert has_insert is True, "gmh_app_role must have INSERT privilege on audit_event."
        assert has_update is False, "gmh_app_role MUST NOT have UPDATE privilege on audit_event."
        assert has_delete is False, "gmh_app_role MUST NOT have DELETE privilege on audit_event."

    finally:
        await conn.close()

@pytest.mark.asyncio
async def test_check3_audit_immutability_trigger_and_permission():
    conn = await asyncpg.connect(
        user=settings.POSTGRES_USER,
        password=settings.POSTGRES_PASSWORD,
        database=settings.POSTGRES_DB,
        host=settings.POSTGRES_HOST,
        port=settings.POSTGRES_PORT,
    )
    try:
        event = await conn.fetchrow("SELECT event_id FROM audit_event LIMIT 1;")
        if event:
            event_id = event["event_id"]

            with pytest.raises(asyncpg.RaiseError) as exc_up:
                await conn.execute("UPDATE audit_event SET action = 'MODIFIED' WHERE event_id = $1;", event_id)
            assert "Audit events are immutable and append-only" in str(exc_up.value)

            with pytest.raises(asyncpg.RaiseError) as exc_del:
                await conn.execute("DELETE FROM audit_event WHERE event_id = $1;", event_id)
            assert "Audit events are immutable and append-only" in str(exc_del.value)

    finally:
        await conn.close()

@pytest.mark.asyncio
async def test_check4_audit_schema_columns():
    conn = await asyncpg.connect(
        user=settings.POSTGRES_USER,
        password=settings.POSTGRES_PASSWORD,
        database=settings.POSTGRES_DB,
        host=settings.POSTGRES_HOST,
        port=settings.POSTGRES_PORT,
    )
    try:
        expected_columns = {
            'actor_type', 'actor_id', 'on_behalf_of', 'action',
            'object_type', 'object_id', 'decision', 'reason_code',
            'policy_version', 'payload_hash', 'previous_hash', 'current_hash', 'created_at'
        }
        cols = await conn.fetch("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'audit_event';
        """)
        actual_cols = {c['column_name'] for c in cols}
        for col in expected_columns:
            assert col in actual_cols, f"Column '{col}' missing from audit_event schema."

    finally:
        await conn.close()

@pytest.mark.asyncio
async def test_check5_db_trigger_state_transitions():
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

        # Insert asset in APPROVED state (with approval)
        appr_id = str(uuid.uuid4())
        await conn.execute("""
            INSERT INTO approval (approval_id, approver_id, approval_type, object_type, object_id, approved_payload_hash, policy_version, status)
            VALUES ($1, $2, 'INGEST', 'knowledge_asset', 'obj_trg', 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855', 'v1.0', 'APPROVED');
        """, appr_id, steward_id)

        asset_id = str(uuid.uuid4())
        await conn.execute("""
            INSERT INTO knowledge_asset (
                asset_id, source, source_ref, classification, barrier_side, jurisdiction,
                steward_id, approval_id, state, retention_class, content_ref, dek_ref, content_hash
            ) VALUES (
                $1, 'Test', 'REF-TRG', 'INTERNAL', 'SIDE_A', 'EU',
                $2, $3, 'APPROVED', '5_YEARS', 's3://test', 'key-01', 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'
            );
        """, asset_id, steward_id, appr_id)

        # Try invalid transition APPROVED -> DRAFT (Must raise trigger exception)
        with pytest.raises(asyncpg.RaiseError) as exc_info:
            await conn.execute("UPDATE knowledge_asset SET state = 'DRAFT' WHERE asset_id = $1;", asset_id)
        assert "Invalid state transition" in str(exc_info.value)

    finally:
        await conn.close()

@pytest.mark.asyncio
async def test_check6_retired_assets_protection_and_audit_preservation():
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

        appr_id = str(uuid.uuid4())
        await conn.execute("""
            INSERT INTO approval (approval_id, approver_id, approval_type, object_type, object_id, approved_payload_hash, policy_version, status)
            VALUES ($1, $2, 'RETIREMENT', 'knowledge_asset', 'obj_ret', 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855', 'v1.0', 'APPROVED');
        """, appr_id, steward_id)

        asset_id = str(uuid.uuid4())
        await conn.execute("""
            INSERT INTO knowledge_asset (
                asset_id, source, source_ref, classification, barrier_side, jurisdiction,
                steward_id, approval_id, state, retention_class, content_ref, dek_ref, content_hash
            ) VALUES (
                $1, 'Test', 'REF-RET', 'INTERNAL', 'SIDE_A', 'EU',
                $2, $3, 'APPROVED', '5_YEARS', 's3://test', 'key-01', 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'
            );
        """, asset_id, steward_id, appr_id)

        # Transition to ARCHIVED (retirement)
        await conn.execute("UPDATE knowledge_asset SET state = 'ARCHIVED' WHERE asset_id = $1;", asset_id)
        archived_state = await conn.fetchval("SELECT state FROM knowledge_asset WHERE asset_id = $1;", asset_id)
        assert archived_state == 'ARCHIVED'

        # Attempt physical DELETE on archived asset -> MUST BE REJECTED BY TRIGGER
        with pytest.raises(asyncpg.RaiseError) as exc_info:
            await conn.execute("DELETE FROM knowledge_asset WHERE asset_id = $1;", asset_id)
        assert "Physical deletion of approved, archived, or legal-hold assets is prohibited" in str(exc_info.value)

    finally:
        await conn.close()
