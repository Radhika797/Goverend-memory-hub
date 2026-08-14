import os
import sys
import hashlib
import pytest
import asyncpg

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "apps", "api")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.config import settings

@pytest.mark.asyncio
async def test_audit_event_hash_chaining():
    conn = await asyncpg.connect(
        user=settings.POSTGRES_USER,
        password=settings.POSTGRES_PASSWORD,
        database=settings.POSTGRES_DB,
        host=settings.POSTGRES_HOST,
        port=settings.POSTGRES_PORT,
    )
    try:
        # Insert test audit event
        row = await conn.fetchrow("""
            INSERT INTO audit_event (
                actor_type, actor_id, on_behalf_of, action, object_type, object_id,
                decision, reason_code, policy_version, payload_hash
            ) VALUES (
                'TEST_USER', 'actor_test_001', 'agent_sub', 'TEST_ACTION', 'test_object',
                'obj_100', 'ALLOW', 'POLICY_PASS', 'v1.0.0', 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'
            ) RETURNING event_id, previous_hash, current_hash;
        """)

        assert row is not None
        event_id = row["event_id"]
        prev_hash = row["previous_hash"]
        curr_hash = row["current_hash"]

        # Recalculate canonical hash locally to verify DB trigger computation
        canonical_str = (
            f"{prev_hash}|TEST_USER|actor_test_001|agent_sub|TEST_ACTION|"
            f"test_object|obj_100|ALLOW|POLICY_PASS|v1.0.0|e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        )
        expected_hash = hashlib.sha256(canonical_str.encode("utf-8")).hexdigest()

        assert curr_hash == expected_hash, f"Hash mismatch: expected {expected_hash}, got {curr_hash}"

    finally:
        await conn.close()

@pytest.mark.asyncio
async def test_audit_event_update_rejected():
    conn = await asyncpg.connect(
        user=settings.POSTGRES_USER,
        password=settings.POSTGRES_PASSWORD,
        database=settings.POSTGRES_DB,
        host=settings.POSTGRES_HOST,
        port=settings.POSTGRES_PORT,
    )
    try:
        event = await conn.fetchrow("SELECT event_id FROM audit_event LIMIT 1;")
        if not event:
            event = await conn.fetchrow("""
                INSERT INTO audit_event (
                    actor_type, actor_id, action, object_type, object_id,
                    decision, reason_code, policy_version, payload_hash
                ) VALUES (
                    'SYSTEM', 'sys_01', 'INIT', 'sys', '0', 'ALLOW', 'OK', 'v1.0', 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'
                ) RETURNING event_id;
            """)

        event_id = event["event_id"]

        with pytest.raises(asyncpg.RaiseError) as exc_info:
            await conn.execute(
                "UPDATE audit_event SET action = 'TAMPERED' WHERE event_id = $1;", event_id
            )

        assert "Audit events are immutable and append-only" in str(exc_info.value)

    finally:
        await conn.close()

@pytest.mark.asyncio
async def test_audit_event_delete_rejected():
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
            with pytest.raises(asyncpg.RaiseError) as exc_info:
                await conn.execute("DELETE FROM audit_event WHERE event_id = $1;", event_id)

            assert "Audit events are immutable and append-only" in str(exc_info.value)

    finally:
        await conn.close()
