import os
import sys
import asyncio
import asyncpg

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "apps", "api")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.config import settings

async def seed_synthetic_data():
    print(f"Seeding synthetic Phase 2 data in '{settings.POSTGRES_DB}'...")
    conn = await asyncpg.connect(
        user=settings.POSTGRES_USER,
        password=settings.POSTGRES_PASSWORD,
        database=settings.POSTGRES_DB,
        host=settings.POSTGRES_HOST,
        port=settings.POSTGRES_PORT,
    )

    try:
        async with conn.transaction():
            # 1. Identities
            admin_id = "11111111-1111-1111-1111-111111111111"
            steward_id = "22222222-2222-2222-2222-222222222222"
            analyst_id = "33333333-3333-3333-3333-333333333333"

            await conn.execute("""
                INSERT INTO identity (identity_id, name, type, role, department, status) VALUES
                ($1, 'Admin System', 'SYSTEM', 'ADMIN', 'Security', 'ACTIVE'),
                ($2, 'Sarah Steward', 'USER', 'STEWARD', 'Engineering', 'ACTIVE'),
                ($3, 'Alex Analyst', 'USER', 'ANALYST', 'Finance', 'ACTIVE')
                ON CONFLICT (identity_id) DO NOTHING;
            """, admin_id, steward_id, analyst_id)

            # 2. Data Subjects
            subj_1 = "44444444-4444-4444-4444-444444444444"
            subj_2 = "55555555-5555-5555-5555-555555555555"

            await conn.execute("""
                INSERT INTO data_subject (subject_id, subject_ref, jurisdiction) VALUES
                ($1, 'SUBJ-EU-8921', 'EU'),
                ($2, 'SUBJ-US-1042', 'US')
                ON CONFLICT (subject_id) DO NOTHING;
            """, subj_1, subj_2)

            # 3. Approvals
            appr_1 = "66666666-6666-6666-6666-666666666666"
            appr_2 = "88888888-8888-8888-8888-888888888888"

            await conn.execute("""
                INSERT INTO approval (approval_id, approver_id, approval_type, object_type, object_id, approved_payload_hash, policy_version, status) VALUES
                ($1, $2, 'INGEST', 'knowledge_asset', '77777777-7777-7777-7777-777777777777', 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855', 'v1.0.0', 'APPROVED'),
                ($3, $2, 'POLICY_OVERRIDE', 'knowledge_asset', '99999999-9999-9999-9999-999999999999', 'a591a6d40bf420404a011733cfb7b190d62c65bf0bcda32b57b277d9ad9f146e', 'v1.0.0', 'APPROVED')
                ON CONFLICT (approval_id) DO NOTHING;
            """, appr_1, steward_id, appr_2)

            # 4. Knowledge Assets
            asset_1 = "77777777-7777-7777-7777-777777777777"
            asset_2 = "99999999-9999-9999-9999-999999999999"
            asset_3 = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"

            await conn.execute("""
                INSERT INTO knowledge_asset (
                    asset_id, source, source_ref, version, classification, barrier_side, jurisdiction,
                    personal_data, subject_id, steward_id, approval_id, state, retention_class,
                    legal_hold, content_ref, dek_ref, content_hash
                ) VALUES
                ($1, 'Engineering Portal', 'DOC-2026-ENG-01', 1, 'INTERNAL', 'SIDE_A', 'EU', TRUE, $4, $5, $6, 'APPROVED', '5_YEARS', FALSE, 's3://vault/eng-01.txt', 'kms/key-001', 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'),
                ($2, 'Finance Portal', 'DOC-2026-FIN-02', 1, 'RESTRICTED', 'SIDE_B', 'US', FALSE, NULL, $5, $7, 'APPROVED', '7_YEARS', TRUE, 's3://vault/fin-02.txt', 'kms/key-002', 'a591a6d40bf420404a011733cfb7b190d62c65bf0bcda32b57b277d9ad9f146e'),
                ($3, 'Drafting Queue', 'DOC-2026-DFT-03', 1, 'CONFIDENTIAL', 'GENERAL', 'GLOBAL', FALSE, NULL, $5, NULL, 'DRAFT', 'STANDARD', FALSE, 's3://vault/dft-03.txt', 'kms/key-003', 'b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9')
                ON CONFLICT (asset_id) DO NOTHING;
            """, asset_1, asset_2, asset_3, subj_1, steward_id, appr_1, appr_2)

            # 5. Entitlements
            ent_1 = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
            ent_2 = "cccccccc-cccc-cccc-cccc-cccccccccccc"

            await conn.execute("""
                INSERT INTO entitlement (entitlement_id, identity_id, classification, barrier, jurisdiction, project, grantor_id) VALUES
                ($1, $2, 'INTERNAL', 'SIDE_A', 'EU', 'PROJECT_ALPHA', $4),
                ($3, $5, 'RESTRICTED', 'SIDE_B', 'US', 'PROJECT_BETA', $4)
                ON CONFLICT (entitlement_id) DO NOTHING;
            """, ent_1, analyst_id, ent_2, admin_id, steward_id)

            # 6. Audit Events (Tamper-evident chain automatically populated via triggers)
            # Clear synthetic test events if already present to ensure clean chain demo
            count = await conn.fetchval("SELECT COUNT(*) FROM audit_event;")
            if count == 0:
                await conn.execute("""
                    INSERT INTO audit_event (actor_type, actor_id, on_behalf_of, action, object_type, object_id, decision, reason_code, policy_version, payload_hash, previous_hash, current_hash) VALUES
                    ('SYSTEM', $1, NULL, 'BOOTSTRAP', 'system', 'gmh_core', 'ALLOW', 'SYSTEM_INITIALIZATION', 'v1.0.0', 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855', '', ''),
                    ('USER', $2, NULL, 'INGEST_KNOWLEDGE_ASSET', 'knowledge_asset', $3, 'ALLOW', 'APPROVED_BY_STEWARD', 'v1.0.0', 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855', '', '');
                """, admin_id, steward_id, asset_1)

        print("[SUCCESS] Synthetic Phase 2 seed data populated successfully.")

    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(seed_synthetic_data())
