import urllib.request
import urllib.error
import json
import asyncio
import asyncpg
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "apps", "api")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.config import settings

async def run_smoke_test():
    conn = await asyncpg.connect(
        user=settings.POSTGRES_USER,
        password=settings.POSTGRES_PASSWORD,
        database=settings.POSTGRES_DB,
        host=settings.POSTGRES_HOST,
        port=settings.POSTGRES_PORT,
    )
    
    steward_id = str(await conn.fetchval("SELECT identity_id FROM identity WHERE role IN ('STEWARD', 'ADMIN') LIMIT 1;"))
    print(f"Using Steward Identity ID: {steward_id}")

    # =========================================================================
    # TEST 1: Valid ingest -> PENDING_APPROVAL
    # =========================================================================
    print("\n" + "="*80)
    print("TEST 1: Valid Ingest -> PENDING_APPROVAL")
    print("="*80)
    
    payload_1 = {
        "source": "Smoke Test Vault",
        "source_ref": "SMOKE-TEST-001",
        "classification": "INTERNAL",
        "barrier_side": "SIDE_A",
        "jurisdiction": "US",
        "steward_id": steward_id,
        "retention_class": "5_YEARS",
        "content_ref": "s3://smoke-vault/test1.pdf",
        "dek_ref": "kms/key-smoke-1",
        "content_hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        "personal_data": False
    }

    req1 = urllib.request.Request(
        "http://127.0.0.1:8000/api/v1/assets/ingest",
        data=json.dumps(payload_1).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    
    with urllib.request.urlopen(req1) as resp:
        resp_status_1 = resp.status
        resp_body_1 = json.loads(resp.read().decode("utf-8"))

    asset_id_1 = resp_body_1["asset"]["asset_id"]
    state_1 = resp_body_1["asset"]["state"]
    
    audit_1 = await conn.fetchrow("""
        SELECT event_id, actor_id, action, decision, reason_code, current_hash
        FROM audit_event WHERE object_id = $1 ORDER BY event_id DESC LIMIT 1;
    """, asset_id_1)

    print("Request Body:")
    print(json.dumps(payload_1, indent=2))
    print(f"\nResponse Status Code: {resp_status_1}")
    print("Response Body:")
    print(json.dumps(resp_body_1, indent=2))
    print(f"Asset ID: {asset_id_1}")
    print(f"Asset State: {state_1}")
    print("Audit Result:")
    print(json.dumps(dict(audit_1) if audit_1 else {}, indent=2, default=str))

    # =========================================================================
    # TEST 2: Pending asset appears in pending list
    # =========================================================================
    print("\n" + "="*80)
    print("TEST 2: Pending Asset Appears in Pending List")
    print("="*80)
    
    req2 = urllib.request.Request("http://127.0.0.1:8000/api/v1/assets/pending")
    with urllib.request.urlopen(req2) as resp:
        resp_status_2 = resp.status
        resp_body_2 = json.loads(resp.read().decode("utf-8"))

    matching_pending = [a for a in resp_body_2.get("pending_assets", []) if a["asset_id"] == asset_id_1]

    print("GET Request URL: http://127.0.0.1:8000/api/v1/assets/pending")
    print(f"Response Status Code: {resp_status_2}")
    print(f"Total Pending Assets Count: {resp_body_2.get('count')}")
    print(f"Target Asset ({asset_id_1}) Found in Pending List: {len(matching_pending) > 0}")
    if matching_pending:
        print("Matching Pending Asset Details:")
        print(json.dumps(matching_pending[0], indent=2, default=str))

    # =========================================================================
    # TEST 3: Approve -> APPROVED + approval_id
    # =========================================================================
    print("\n" + "="*80)
    print("TEST 3: Approve Asset -> APPROVED + approval_id")
    print("="*80)
    
    payload_3 = {
        "approver_id": steward_id,
        "policy_version": "v1.0.0"
    }

    req3 = urllib.request.Request(
        f"http://127.0.0.1:8000/api/v1/assets/{asset_id_1}/approve",
        data=json.dumps(payload_3).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    
    with urllib.request.urlopen(req3) as resp:
        resp_status_3 = resp.status
        resp_body_3 = json.loads(resp.read().decode("utf-8"))

    state_3 = resp_body_3["asset"]["state"]
    approval_id_3 = resp_body_3["asset"]["approval_id"]

    audit_3 = await conn.fetchrow("""
        SELECT event_id, actor_id, action, decision, reason_code, current_hash
        FROM audit_event WHERE object_id = $1 AND action = 'APPROVE_KNOWLEDGE_ASSET' ORDER BY event_id DESC LIMIT 1;
    """, asset_id_1)

    print(f"Request URL: http://127.0.0.1:8000/api/v1/assets/{asset_id_1}/approve")
    print("Request Body:")
    print(json.dumps(payload_3, indent=2))
    print(f"\nResponse Status Code: {resp_status_3}")
    print("Response Body:")
    print(json.dumps(resp_body_3, indent=2))
    print(f"Asset ID: {asset_id_1}")
    print(f"Asset State: {state_3}")
    print(f"Attached Approval ID: {approval_id_3}")
    print("Audit Result:")
    print(json.dumps(dict(audit_3) if audit_3 else {}, indent=2, default=str))

    # =========================================================================
    # TEST 4: Second asset reject -> REJECTED
    # =========================================================================
    print("\n" + "="*80)
    print("TEST 4: Ingest Second Asset & Reject -> REJECTED")
    print("="*80)
    
    payload_4_ingest = {
        "source": "Smoke Test Vault",
        "source_ref": "SMOKE-TEST-002",
        "classification": "CONFIDENTIAL",
        "barrier_side": "SIDE_B",
        "jurisdiction": "UK",
        "steward_id": steward_id,
        "retention_class": "STANDARD",
        "content_ref": "s3://smoke-vault/test2.pdf",
        "dek_ref": "kms/key-smoke-2",
        "content_hash": "a591a6d40bf420404a011733cfb7b190d62c65bf0bcda32b57b277d9ad9f146e",
        "personal_data": False
    }

    req4_ingest = urllib.request.Request(
        "http://127.0.0.1:8000/api/v1/assets/ingest",
        data=json.dumps(payload_4_ingest).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req4_ingest) as resp:
        resp_body_4_ingest = json.loads(resp.read().decode("utf-8"))

    asset_id_2 = resp_body_4_ingest["asset"]["asset_id"]

    payload_4_reject = {
        "approver_id": steward_id,
        "reason": "Smoke test rejection trigger",
        "policy_version": "v1.0.0"
    }

    req4_reject = urllib.request.Request(
        f"http://127.0.0.1:8000/api/v1/assets/{asset_id_2}/reject",
        data=json.dumps(payload_4_reject).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )

    with urllib.request.urlopen(req4_reject) as resp:
        resp_status_4 = resp.status
        resp_body_4 = json.loads(resp.read().decode("utf-8"))

    state_4 = resp_body_4["asset"]["state"]

    audit_4 = await conn.fetchrow("""
        SELECT event_id, actor_id, action, decision, reason_code, current_hash
        FROM audit_event WHERE object_id = $1 AND action = 'REJECT_KNOWLEDGE_ASSET' ORDER BY event_id DESC LIMIT 1;
    """, asset_id_2)

    print(f"Ingested Second Asset ID: {asset_id_2}")
    print(f"Rejection Request URL: http://127.0.0.1:8000/api/v1/assets/{asset_id_2}/reject")
    print("Rejection Request Body:")
    print(json.dumps(payload_4_reject, indent=2))
    print(f"\nResponse Status Code: {resp_status_4}")
    print("Response Body:")
    print(json.dumps(resp_body_4, indent=2))
    print(f"Asset ID: {asset_id_2}")
    print(f"Asset State: {state_4}")
    print("Audit Result:")
    print(json.dumps(dict(audit_4) if audit_4 else {}, indent=2, default=str))

    # =========================================================================
    # TEST 5: Invalid personal_data=true without subject_id -> HTTP 400 + DENY audit
    # =========================================================================
    print("\n" + "="*80)
    print("TEST 5: Invalid personal_data=true without subject_id -> HTTP 400 + DENY audit")
    print("="*80)
    
    payload_5 = {
        "source": "Smoke Test Vault",
        "source_ref": "SMOKE-TEST-003-INVALID",
        "classification": "CONFIDENTIAL",
        "barrier_side": "GENERAL",
        "jurisdiction": "EU",
        "steward_id": steward_id,
        "retention_class": "HR_PERSONAL_DATA",
        "content_ref": "s3://smoke-vault/invalid_hr.json",
        "dek_ref": "kms/key-smoke-3",
        "content_hash": "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9",
        "personal_data": True,
        "subject_id": None
    }

    req5 = urllib.request.Request(
        "http://127.0.0.1:8000/api/v1/assets/ingest",
        data=json.dumps(payload_5).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )

    try:
        with urllib.request.urlopen(req5) as resp:
            resp_status_5 = resp.status
            resp_body_5 = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        resp_status_5 = e.code
        resp_body_5 = json.loads(e.read().decode("utf-8"))

    audit_5 = await conn.fetchrow("""
        SELECT event_id, actor_id, action, object_id, decision, reason_code, current_hash
        FROM audit_event WHERE object_id = 'SMOKE-TEST-003-INVALID' ORDER BY event_id DESC LIMIT 1;
    """)

    print("Request Body:")
    print(json.dumps(payload_5, indent=2))
    print(f"\nResponse Status Code: {resp_status_5}")
    print("Response Body:")
    print(json.dumps(resp_body_5, indent=2))
    print(f"Asset ID: None (Ingestion Denied)")
    print(f"Asset State: None (Not Created)")
    print("Audit Result:")
    print(json.dumps(dict(audit_5) if audit_5 else {}, indent=2, default=str))

    await conn.close()

if __name__ == "__main__":
    asyncio.run(run_smoke_test())
