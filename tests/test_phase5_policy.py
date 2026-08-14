import pytest
import asyncpg
import uuid
import json
import base64
import os
import sys
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "apps", "api")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

try:
    from apps.api.app.config import settings
except (ImportError, ModuleNotFoundError):
    from app.config import settings  # type: ignore # pyrefly: disable=missing-import

from app.identity_service import verify_oidc_token, create_delegation_token, verify_delegation_token
from app.policy_engine import evaluate_access_policy

@pytest.mark.asyncio
async def test_oidc_identity_verification():
    conn = await asyncpg.connect(
        user=settings.POSTGRES_USER,
        password=settings.POSTGRES_PASSWORD,
        database=settings.POSTGRES_DB,
        host=settings.POSTGRES_HOST,
        port=settings.POSTGRES_PORT,
    )
    try:
        user_row = await conn.fetchrow("SELECT identity_id, name FROM identity WHERE type = 'USER' AND status = 'ACTIVE' LIMIT 1;")
        assert user_row is not None
        user_id = str(user_row["identity_id"])

        # Construct simulated OIDC JWT payload
        claims = {
            "sub": user_id,
            "iss": "https://auth.northwind.com",
            "aud": "governed-memory-hub",
            "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()),
            "email": "user@northwind.com"
        }
        claims_b64 = base64.b64encode(json.dumps(claims).encode("utf-8")).decode("utf-8").rstrip("=")
        jwt_token = f"eyJhbGciOiJIUzI1NiJ9.{claims_b64}.signature"

        verified = await verify_oidc_token(conn, jwt_token)
        assert verified["identity_id"] == user_row["identity_id"]
        assert verified["status"] == "ACTIVE"

    finally:
        await conn.close()

@pytest.mark.asyncio
async def test_delegation_token_non_widening():
    conn = await asyncpg.connect(
        user=settings.POSTGRES_USER,
        password=settings.POSTGRES_PASSWORD,
        database=settings.POSTGRES_DB,
        host=settings.POSTGRES_HOST,
        port=settings.POSTGRES_PORT,
    )
    try:
        # Fetch Grantor (User) and Delegate (Agent)
        grantor = await conn.fetchrow("SELECT identity_id FROM identity WHERE role = 'ANALYST' AND status = 'ACTIVE' LIMIT 1;")
        delegate = await conn.fetchrow("SELECT identity_id FROM identity WHERE type IN ('SERVICE_ACCOUNT', 'SYSTEM') AND status = 'ACTIVE' LIMIT 1;")
        assert grantor and delegate

        grantor_id = str(grantor["identity_id"])
        delegate_id = str(delegate["identity_id"])

        # Request scopes (some valid for grantor, some invalid/unauthorized)
        requested_scopes = ["INTERNAL", "SIDE_A", "UNAUTHORIZED_RESTRICTED_SCOPE", "READ"]

        token_info = await create_delegation_token(conn, grantor_id, delegate_id, requested_scopes)
        assert token_info["non_widened"] is True
        # Verify unauthorized scope was stripped out by non-widening check
        assert "UNAUTHORIZED_RESTRICTED_SCOPE" not in token_info["delegated_scopes"]

        # Verify token in DB
        ver = await verify_delegation_token(conn, token_info["token_id"])
        assert str(ver["grantor_id"]) == grantor_id
        assert str(ver["delegate_id"]) == delegate_id

    finally:
        await conn.close()

@pytest.mark.asyncio
async def test_policy_permit_decision():
    conn = await asyncpg.connect(
        user=settings.POSTGRES_USER,
        password=settings.POSTGRES_PASSWORD,
        database=settings.POSTGRES_DB,
        host=settings.POSTGRES_HOST,
        port=settings.POSTGRES_PORT,
    )
    try:
        # Fetch asset with classification INTERNAL, barrier GENERAL, personal_data FALSE
        asset = await conn.fetchrow("""
            SELECT asset_id, classification, barrier_side, jurisdiction
            FROM knowledge_asset
            WHERE classification = 'INTERNAL' AND barrier_side = 'GENERAL' AND personal_data = FALSE AND legal_hold = FALSE
            LIMIT 1;
        """)
        assert asset is not None
        asset_id = str(asset["asset_id"])

        # Fetch entitlement for INTERNAL
        ent = await conn.fetchrow("SELECT identity_id FROM entitlement WHERE classification = 'INTERNAL' LIMIT 1;")
        assert ent is not None
        caller_id = str(ent["identity_id"])

        decision = await evaluate_access_policy(conn, caller_id, asset_id, action="READ_KNOWLEDGE_ASSET")
        assert decision["decision"] in ("PERMIT", "PERMIT_WITH_CONSTRAINTS")
        assert decision["policy_version"] == "v1.0.0"

    finally:
        await conn.close()

@pytest.mark.asyncio
async def test_policy_deny_decision():
    conn = await asyncpg.connect(
        user=settings.POSTGRES_USER,
        password=settings.POSTGRES_PASSWORD,
        database=settings.POSTGRES_DB,
        host=settings.POSTGRES_HOST,
        port=settings.POSTGRES_PORT,
    )
    try:
        # Fetch RESTRICTED asset on SIDE_A
        asset = await conn.fetchrow("""
            SELECT asset_id FROM knowledge_asset
            WHERE classification = 'RESTRICTED' AND barrier_side = 'SIDE_A'
            LIMIT 1;
        """)
        assert asset is not None
        asset_id = str(asset["asset_id"])

        # Fetch identity with low clearance or SIDE_B barrier
        low_user = await conn.fetchrow("""
            SELECT i.identity_id FROM identity i
            WHERE i.role = 'MEMBER' AND i.status = 'ACTIVE'
            AND NOT EXISTS (SELECT 1 FROM entitlement e WHERE e.identity_id = i.identity_id AND e.classification = 'RESTRICTED')
            LIMIT 1;
        """)
        if not low_user:
            low_user = await conn.fetchrow("SELECT identity_id FROM identity WHERE role = 'MEMBER' LIMIT 1;")

        caller_id = str(low_user["identity_id"])

        decision = await evaluate_access_policy(conn, caller_id, asset_id, action="READ_KNOWLEDGE_ASSET")
        assert decision["decision"] == "DENY"
        assert decision["reason_code"] in ("GOVERNANCE_BOUNDS_VIOLATED", "NO_ACTIVE_ENTITLEMENTS")

    finally:
        await conn.close()

@pytest.mark.asyncio
async def test_policy_permit_with_constraints():
    conn = await asyncpg.connect(
        user=settings.POSTGRES_USER,
        password=settings.POSTGRES_PASSWORD,
        database=settings.POSTGRES_DB,
        host=settings.POSTGRES_HOST,
        port=settings.POSTGRES_PORT,
    )
    try:
        # Fetch asset with personal_data = TRUE or legal_hold = TRUE
        asset = await conn.fetchrow("""
            SELECT asset_id, personal_data, legal_hold FROM knowledge_asset
            WHERE personal_data = TRUE OR legal_hold = TRUE
            LIMIT 1;
        """)
        assert asset is not None
        asset_id = str(asset["asset_id"])

        admin_user = await conn.fetchrow("SELECT identity_id FROM identity WHERE role = 'ADMIN' LIMIT 1;")
        assert admin_user is not None
        caller_id = str(admin_user["identity_id"])

        decision = await evaluate_access_policy(conn, caller_id, asset_id, action="READ_KNOWLEDGE_ASSET")
        assert decision["decision"] == "PERMIT_WITH_CONSTRAINTS"
        assert len(decision["constraints"]) > 0

    finally:
        await conn.close()

@pytest.mark.asyncio
async def test_fail_closed_on_corrupt_token_or_unmapped_identity():
    conn = await asyncpg.connect(
        user=settings.POSTGRES_USER,
        password=settings.POSTGRES_PASSWORD,
        database=settings.POSTGRES_DB,
        host=settings.POSTGRES_HOST,
        port=settings.POSTGRES_PORT,
    )
    try:
        asset = await conn.fetchrow("SELECT asset_id FROM knowledge_asset LIMIT 1;")
        asset_id = str(asset["asset_id"])

        # Fake unmapped UUID
        unmapped_caller_id = str(uuid.uuid4())

        decision = await evaluate_access_policy(conn, unmapped_caller_id, asset_id)
        assert decision["decision"] == "DENY"
        assert decision["reason_code"] == "CALLER_INACTIVE_OR_UNMAPPED"

    finally:
        await conn.close()
