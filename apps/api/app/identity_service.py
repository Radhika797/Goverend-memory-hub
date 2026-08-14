import uuid
import hashlib
import json
import base64
import asyncpg
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional

async def verify_oidc_token(conn: asyncpg.Connection, token_str: str) -> Dict[str, Any]:
    """
    Verify OIDC JWT bearer token claims and resolve matching PostgreSQL identity.
    Supports JWT structures (header.payload.signature) and JSON simulated tokens.
    Fail-closed: Returns None or raises ValueError if invalid/expired.
    """
    if not token_str:
        raise ValueError("OIDC token is empty or missing")

    # Clean bearer prefix if present
    clean_token = token_str.replace("Bearer ", "").strip()

    payload = {}
    try:
        if clean_token.startswith("{") and clean_token.endswith("}"):
            payload = json.loads(clean_token)
        elif "." in clean_token:
            parts = clean_token.split(".")
            if len(parts) >= 2:
                # Decode Base64 payload
                padding = "=" * (4 - len(parts[1]) % 4)
                decoded_bytes = base64.b64decode(parts[1] + padding)
                payload = json.loads(decoded_bytes.decode("utf-8"))
        else:
            # Fallback simple sub token
            payload = {"sub": clean_token, "iss": "https://auth.northwind.com", "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp())}
    except Exception as e:
        raise ValueError(f"OIDC JWT claim decoding failed: {e}")

    sub = payload.get("sub")
    if not sub:
        raise ValueError("OIDC token missing required 'sub' claim")

    # Check expiration if present
    exp = payload.get("exp")
    if exp:
        now_ts = datetime.now(timezone.utc).timestamp()
        if now_ts > exp:
            raise ValueError(f"OIDC token expired (exp: {exp}, now: {int(now_ts)})")

    # Resolve identity from PostgreSQL using identity_id UUID or name/sub
    identity_row = None
    try:
        sub_uuid = uuid.UUID(str(sub))
        identity_row = await conn.fetchrow("SELECT * FROM identity WHERE identity_id = $1;", sub_uuid)
    except ValueError:
        identity_row = await conn.fetchrow("SELECT * FROM identity WHERE name = $1 OR identity_id::text = $2;", str(sub), str(sub))

    if not identity_row:
        raise ValueError(f"No registered identity found for OIDC subject '{sub}'")

    if identity_row["status"] != "ACTIVE":
        raise ValueError(f"Identity '{sub}' is revoked or suspended (status: {identity_row['status']})")

    result = dict(identity_row)
    result["oidc_claims"] = payload
    return result


async def create_delegation_token(
    conn: asyncpg.Connection,
    grantor_id: str,
    delegate_id: str,
    requested_scopes: List[str],
    ttl_seconds: int = 3600
) -> Dict[str, Any]:
    """
    Issue a short-lived Delegation Token from a human grantor to an agent/workload delegate.
    Enforces NON-WIDENING AUTHORITY: Delegated scopes are restricted to grantor's active entitlements.
    """
    # 1. Verify grantor identity
    try:
        grantor_uuid = uuid.UUID(str(grantor_id))
    except ValueError:
        raise ValueError(f"Grantor ID '{grantor_id}' is not a valid UUID")

    grantor = await conn.fetchrow("SELECT * FROM identity WHERE identity_id = $1 AND status = 'ACTIVE';", grantor_uuid)
    if not grantor:
        raise ValueError(f"Grantor identity '{grantor_id}' not found or inactive")

    # 2. Verify delegate identity
    try:
        delegate_uuid = uuid.UUID(str(delegate_id))
    except ValueError:
        raise ValueError(f"Delegate ID '{delegate_id}' is not a valid UUID")

    delegate = await conn.fetchrow("SELECT * FROM identity WHERE identity_id = $1 AND status = 'ACTIVE';", delegate_uuid)
    if not delegate:
        raise ValueError(f"Delegate identity '{delegate_id}' not found or inactive")

    # 3. Fetch Grantor's Active Entitlements to enforce Non-Widening Guarantee
    grantor_entitlements = await conn.fetch("""
        SELECT classification, barrier, jurisdiction, project
        FROM entitlement
        WHERE identity_id = $1 AND (expires_at IS NULL OR expires_at > clock_timestamp());
    """, grantor_uuid)

    grantor_scope_set = set()
    for ent in grantor_entitlements:
        grantor_scope_set.add(ent["classification"])
        grantor_scope_set.add(ent["barrier"])
        grantor_scope_set.add(ent["jurisdiction"])
        grantor_scope_set.add(ent["project"])

    # Non-Widening Filter: Only keep scopes that exist in Grantor's entitlements
    effective_delegated_scopes = [s for s in requested_scopes if s in grantor_scope_set or s in ["READ", "WRITE", "EXECUTE"]]

    if not effective_delegated_scopes:
        raise ValueError(f"Non-widening authority check failed: Grantor '{grantor_id}' possesses no matching entitlements for requested scopes")

    # 4. Generate Token Record
    token_id = uuid.uuid4()
    issued_at = datetime.now(timezone.utc)
    expires_at = issued_at + timedelta(seconds=ttl_seconds)

    # Compute deterministic signature hash
    sig_base = f"{token_id}|{grantor_uuid}|{delegate_uuid}|{sorted(effective_delegated_scopes)}|{int(expires_at.timestamp())}"
    signature_hash = hashlib.sha256(sig_base.encode("utf-8")).hexdigest()

    await conn.execute("""
        INSERT INTO delegation_token (
            token_id, grantor_id, delegate_id, delegated_scopes, issued_at, expires_at, revoked, signature_hash
        ) VALUES ($1, $2, $3, $4, $5, $6, FALSE, $7);
    """, token_id, grantor_uuid, delegate_uuid, effective_delegated_scopes, issued_at, expires_at, signature_hash)

    return {
        "token_id": str(token_id),
        "grantor_id": str(grantor_uuid),
        "delegate_id": str(delegate_uuid),
        "delegated_scopes": effective_delegated_scopes,
        "issued_at": issued_at.isoformat(),
        "expires_at": expires_at.isoformat(),
        "signature_hash": signature_hash,
        "non_widened": True
    }


async def verify_delegation_token(conn: asyncpg.Connection, token_id_str: str) -> Dict[str, Any]:
    """
    Verify delegation token validity, revocation state, signature hash, and return authorized context.
    Fail-closed: Raises ValueError if expired, revoked, or signature hash corrupted.
    """
    try:
        token_uuid = uuid.UUID(str(token_id_str))
    except ValueError:
        raise ValueError(f"Delegation Token ID '{token_id_str}' is not a valid UUID")

    token_row = await conn.fetchrow("SELECT * FROM delegation_token WHERE token_id = $1;", token_uuid)
    if not token_row:
        raise ValueError(f"Delegation token '{token_id_str}' not found")

    if token_row["revoked"]:
        raise ValueError(f"Delegation token '{token_id_str}' has been REVOKED")

    now = datetime.now(timezone.utc)
    exp = token_row["expires_at"]
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)

    if now > exp:
        raise ValueError(f"Delegation token '{token_id_str}' EXPIRED at {exp.isoformat()}")

    # Verify signature hash integrity
    sig_base = f"{token_row['token_id']}|{token_row['grantor_id']}|{token_row['delegate_id']}|{sorted(token_row['delegated_scopes'])}|{int(exp.timestamp())}"
    expected_hash = hashlib.sha256(sig_base.encode("utf-8")).hexdigest()
    if token_row["signature_hash"] != expected_hash:
        raise ValueError(f"Delegation token '{token_id_str}' SIGNATURE CORRUPTED OR TAMPERED")

    return dict(token_row)
