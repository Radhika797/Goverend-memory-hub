import uuid
import hashlib
import json
import asyncpg
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from app.ingestion_service import record_audit_event, compute_payload_hash
from app.identity_service import verify_delegation_token

CLEARANCE_LEVELS = {
    "PUBLIC": 1,
    "INTERNAL": 2,
    "CONFIDENTIAL": 3,
    "RESTRICTED": 4
}

async def evaluate_access_policy(
    conn: asyncpg.Connection,
    caller_identity_id: str,
    target_asset_id: str,
    action: str = "READ_KNOWLEDGE_ASSET",
    on_behalf_of_id: Optional[str] = None,
    delegation_token_id: Optional[str] = None,
    policy_version: str = "v1.0.0"
) -> Dict[str, Any]:
    """
    Deterministic Policy Engine for Governed Memory Hub.
    Evaluates 4-Way Governance Bounds:
      1. Classification Clearance Level
      2. Information Barrier Wall (SIDE_A / SIDE_B / GENERAL)
      3. Jurisdiction Scope (US / EU / UK / GLOBAL)
      4. Active Entitlement Scope & Expiration
    
    Outcomes:
      - PERMIT: All checks passed.
      - DENY: Clearance mismatch, barrier violation, or expired entitlement.
      - PERMIT_WITH_CONSTRAINTS: Access granted subject to runtime obligations (e.g. redact PII).
    
    Fail-Closed Principle: Any error or unhandled condition defaults to DENY.
    """
    payload_dict = {
        "caller_identity_id": caller_identity_id,
        "target_asset_id": target_asset_id,
        "action": action,
        "on_behalf_of_id": on_behalf_of_id,
        "delegation_token_id": delegation_token_id,
        "policy_version": policy_version
    }
    payload_hash = compute_payload_hash(payload_dict)

    # FAIL-CLOSED WRAPPER
    try:
        # 1. Fetch Target Asset
        try:
            asset_uuid = uuid.UUID(str(target_asset_id))
        except ValueError:
            await record_audit_event(
                conn, "USER", caller_identity_id, action, "knowledge_asset",
                target_asset_id, "DENY", "INVALID_ASSET_UUID", policy_version, payload_hash, on_behalf_of_id
            )
            return _build_decision("DENY", "INVALID_ASSET_UUID", "Target asset ID is not a valid UUID", policy_version)

        asset = await conn.fetchrow("SELECT * FROM knowledge_asset WHERE asset_id = $1;", asset_uuid)
        if not asset:
            await record_audit_event(
                conn, "USER", caller_identity_id, action, "knowledge_asset",
                target_asset_id, "DENY", "ASSET_NOT_FOUND", policy_version, payload_hash, on_behalf_of_id
            )
            return _build_decision("DENY", "ASSET_NOT_FOUND", f"Target asset '{target_asset_id}' not found", policy_version)

        # 2. Fetch Caller Identity
        try:
            caller_uuid = uuid.UUID(str(caller_identity_id))
        except ValueError:
            await record_audit_event(
                conn, "USER", caller_identity_id, action, "knowledge_asset",
                target_asset_id, "DENY", "INVALID_CALLER_UUID", policy_version, payload_hash, on_behalf_of_id
            )
            return _build_decision("DENY", "INVALID_CALLER_UUID", "Caller identity ID is not a valid UUID", policy_version)

        caller = await conn.fetchrow("SELECT * FROM identity WHERE identity_id = $1 AND status = 'ACTIVE';", caller_uuid)
        if not caller:
            await record_audit_event(
                conn, "USER", caller_identity_id, action, "knowledge_asset",
                target_asset_id, "DENY", "CALLER_INACTIVE_OR_UNMAPPED", policy_version, payload_hash, on_behalf_of_id
            )
            return _build_decision("DENY", "CALLER_INACTIVE_OR_UNMAPPED", f"Caller identity '{caller_identity_id}' inactive or unmapped", policy_version)

        effective_actor_id = str(caller_uuid)
        effective_on_behalf_of = on_behalf_of_id

        # 3. Process Delegation Token if provided
        delegated_scopes = None
        if delegation_token_id:
            try:
                del_info = await verify_delegation_token(conn, delegation_token_id)
                # Verify delegation is linked to caller as delegate
                if str(del_info["delegate_id"]) != effective_actor_id:
                    await record_audit_event(
                        conn, "AGENT", effective_actor_id, action, "knowledge_asset",
                        target_asset_id, "DENY", "DELEGATION_DELEGATE_MISMATCH", policy_version, payload_hash, effective_on_behalf_of
                    )
                    return _build_decision("DENY", "DELEGATION_DELEGATE_MISMATCH", "Delegation token delegate does not match caller identity", policy_version)

                effective_on_behalf_of = str(del_info["grantor_id"])
                delegated_scopes = set(del_info["delegated_scopes"])
            except ValueError as del_err:
                await record_audit_event(
                    conn, "AGENT", effective_actor_id, action, "knowledge_asset",
                    target_asset_id, "DENY", "DELEGATION_TOKEN_INVALID", policy_version, payload_hash, effective_on_behalf_of
                )
                return _build_decision("DENY", "DELEGATION_TOKEN_INVALID", str(del_err), policy_version)

        # 4. Fetch Active Entitlements for effective actor (grantor if on_behalf_of, else caller)
        eval_identity_id = uuid.UUID(effective_on_behalf_of) if effective_on_behalf_of else caller_uuid
        entitlements = await conn.fetch("""
            SELECT classification, barrier, jurisdiction, project
            FROM entitlement
            WHERE identity_id = $1 AND (expires_at IS NULL OR expires_at > clock_timestamp());
        """, eval_identity_id)

        # Admin override check
        if caller["role"] == "ADMIN":
            constraints = []
            if asset["personal_data"]:
                constraints.append({"type": "REDACT_PERSONAL_DATA", "subject_id": str(asset["subject_id"]) if asset["subject_id"] else None})
            if asset["legal_hold"]:
                constraints.append({"type": "ENFORCE_LEGAL_HOLD_LOCK"})

            decision = "PERMIT_WITH_CONSTRAINTS" if constraints else "PERMIT"
            await record_audit_event(
                conn, "USER", effective_actor_id, action, "knowledge_asset",
                target_asset_id, decision, "ADMIN_OVERRIDE_PERMIT", policy_version, payload_hash, effective_on_behalf_of
            )
            return _build_decision(decision, "ADMIN_OVERRIDE_PERMIT", "Access permitted under Admin role", policy_version, constraints)

        if not entitlements:
            await record_audit_event(
                conn, "USER", effective_actor_id, action, "knowledge_asset",
                target_asset_id, "DENY", "NO_ACTIVE_ENTITLEMENTS", policy_version, payload_hash, effective_on_behalf_of
            )
            return _build_decision("DENY", "NO_ACTIVE_ENTITLEMENTS", f"Identity '{eval_identity_id}' has no active entitlements", policy_version)

        # 5. Evaluate Governance Controls
        asset_classification = asset["classification"]
        asset_barrier = asset["barrier_side"]
        asset_jurisdiction = asset["jurisdiction"]

        asset_class_level = CLEARANCE_LEVELS.get(asset_classification, 4)

        matched_entitlement = False
        for ent in entitlements:
            ent_class_level = CLEARANCE_LEVELS.get(ent["classification"], 1)
            # Check 1: Classification Clearance Level
            if ent_class_level < asset_class_level:
                continue

            # Check 2: Information Barrier Wall
            if asset_barrier != "GENERAL" and ent["barrier"] != "GENERAL" and ent["barrier"] != asset_barrier:
                continue

            # Check 3: Jurisdiction Scope
            if asset_jurisdiction != "GLOBAL" and ent["jurisdiction"] != "GLOBAL" and ent["jurisdiction"] != asset_jurisdiction:
                continue

            matched_entitlement = True
            break

        if not matched_entitlement:
            await record_audit_event(
                conn, "USER", effective_actor_id, action, "knowledge_asset",
                target_asset_id, "DENY", "GOVERNANCE_BOUNDS_VIOLATED", policy_version, payload_hash, effective_on_behalf_of
            )
            return _build_decision("DENY", "GOVERNANCE_BOUNDS_VIOLATED", "Request violates clearance level, information barrier, or jurisdiction bounds", policy_version)

        # Check 4: Non-Widening Delegation Scopes if token present
        if delegated_scopes is not None:
            if asset_classification not in delegated_scopes and asset_barrier not in delegated_scopes and asset_jurisdiction not in delegated_scopes:
                # Check if general action permitted
                if "READ" not in delegated_scopes and "ALL" not in delegated_scopes:
                    await record_audit_event(
                        conn, "AGENT", effective_actor_id, action, "knowledge_asset",
                        target_asset_id, "DENY", "DELEGATED_SCOPE_EXCEEDED", policy_version, payload_hash, effective_on_behalf_of
                    )
                    return _build_decision("DENY", "DELEGATED_SCOPE_EXCEEDED", "Delegation token scope does not authorize access to asset", policy_version)

        # 6. Determine Constraints
        constraints = []
        if asset["personal_data"]:
            constraints.append({"type": "REDACT_PERSONAL_DATA", "subject_id": str(asset["subject_id"]) if asset["subject_id"] else None})
        if asset["legal_hold"]:
            constraints.append({"type": "ENFORCE_LEGAL_HOLD_LOCK"})

        decision = "PERMIT_WITH_CONSTRAINTS" if constraints else "PERMIT"
        reason_code = "POLICY_EVALUATION_PASSED" if decision == "PERMIT" else "PERMITTED_WITH_MANDATORY_CONSTRAINTS"

        await record_audit_event(
            conn, "USER" if not delegation_token_id else "AGENT", effective_actor_id, action, "knowledge_asset",
            target_asset_id, decision, reason_code, policy_version, payload_hash, effective_on_behalf_of
        )

        return _build_decision(decision, reason_code, "Policy evaluation passed governance bounds", policy_version, constraints)

    except Exception as err:
        # FAIL-CLOSED DEFAULT
        await record_audit_event(
            conn, "SYSTEM", caller_identity_id, action, "knowledge_asset",
            target_asset_id, "DENY", "FAIL_CLOSED_EXCEPTION", policy_version, payload_hash, on_behalf_of_id
        )
        return _build_decision("DENY", "FAIL_CLOSED_EXCEPTION", f"Internal policy evaluation error (fail-closed): {err}", policy_version)


def _build_decision(decision: str, reason_code: str, message: str, policy_version: str, constraints: Optional[List[dict]] = None) -> Dict[str, Any]:
    return {
        "decision": decision,
        "reason_code": reason_code,
        "message": message,
        "policy_version": policy_version,
        "constraints": constraints or [],
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
