import os
import sys
import uuid
import random
import hashlib
import asyncio
import asyncpg
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "apps", "api")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

try:
    from apps.api.app.config import settings
except (ImportError, ModuleNotFoundError):
    from app.config import settings

# Fixed random seed for 100% deterministic generation
SEED_VAL = 42
random.seed(SEED_VAL)

DIVISIONS = ["Advisory", "Markets", "Research", "Operations", "Compliance", "Technology"]
JURISDICTIONS = ["US", "EU", "UK", "GLOBAL"]
ROLES = ["ADMIN", "STEWARD", "ANALYST", "MEMBER", "PUBLIC"]
CLASSIFICATIONS = ["PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED"]
BARRIERS = ["SIDE_A", "SIDE_B", "GENERAL"]

FIRST_NAMES = ["Alexander", "Beatrice", "Charles", "Diana", "Edward", "Fiona", "George", "Hannah", "Ian", "Julia",
               "Kevin", "Laura", "Michael", "Nina", "Oliver", "Penelope", "Quentin", "Rachel", "Samuel", "Tessa"]
LAST_NAMES = ["Sterling", "Vance", "Hawthorne", "Mercer", "Blackwood", "Sinclair", "Kensington", "Montgomery", "Winslow", "Fairfax"]

async def seed_phase3_reference_firm_and_corpus():
    print(f"Connecting to PostgreSQL database '{settings.POSTGRES_DB}' at {settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}...")
    conn = await asyncpg.connect(
        user=settings.POSTGRES_USER,
        password=settings.POSTGRES_PASSWORD,
        database=settings.POSTGRES_DB,
        host=settings.POSTGRES_HOST,
        port=settings.POSTGRES_PORT,
    )

    try:
        async with conn.transaction():
            print("Clearing existing sample data for Phase 3 clean seeding...")
            await conn.execute("TRUNCATE audit_event, knowledge_asset, entitlement, approval, data_subject, identity RESTART IDENTITY CASCADE;")

            # -------------------------------------------------------------
            # 1. Create Exactly 40 Synthetic Identities for Northwind Securities
            # -------------------------------------------------------------
            print("Generating exactly 40 synthetic identities for Northwind Securities...")
            identities = []
            identity_ids = []
            
            # Ensure all 6 divisions are assigned deterministically
            div_cycle = DIVISIONS * 7  # 42 slots, take 40
            
            for i in range(40):
                ident_id = str(uuid.UUID(int=1000 + i))
                identity_ids.append(ident_id)
                fn = FIRST_NAMES[i % len(FIRST_NAMES)]
                ln = LAST_NAMES[(i // len(FIRST_NAMES)) % len(LAST_NAMES)]
                name = f"{fn} {ln}"
                div = div_cycle[i]
                
                # Assign role & type based on division
                if i == 0:
                    role = "ADMIN"
                    itype = "SYSTEM"
                    name = "Northwind Core System"
                elif i == 1:
                    role = "ADMIN"
                    itype = "USER"
                    name = "Victoria Kensington (Global Admin)"
                elif div == "Compliance":
                    role = "STEWARD"
                    itype = "USER"
                elif div == "Research":
                    role = "ANALYST" if i % 2 == 0 else "MEMBER"
                    itype = "USER"
                elif div == "Technology" and i % 5 == 0:
                    role = "ADMIN"
                    itype = "SERVICE_ACCOUNT"
                    name = f"svc_tech_pipeline_{i}"
                else:
                    role = "MEMBER" if i % 3 == 0 else "ANALYST"
                    itype = "USER"

                status = "ACTIVE"
                identities.append((ident_id, name, itype, role, div, status))

            await conn.executemany("""
                INSERT INTO identity (identity_id, name, type, role, department, status)
                VALUES ($1, $2, $3, $4, $5, $6);
            """, identities)

            # -------------------------------------------------------------
            # 2. Create Synthetic Data Subjects (Marked SYNTHETIC)
            # -------------------------------------------------------------
            print("Generating synthetic data subjects (marked SYNTHETIC)...")
            data_subjects = []
            subject_ids = []
            for i in range(100):
                subj_id = str(uuid.UUID(int=5000 + i))
                subject_ids.append(subj_id)
                juris = "US" if i % 3 == 0 else ("EU" if i % 3 == 1 else "UK")
                subj_ref = f"SYNTHETIC-SUBJ-{juris}-{10000 + i}"
                data_subjects.append((subj_id, subj_ref, juris))

            await conn.executemany("""
                INSERT INTO data_subject (subject_id, subject_ref, jurisdiction)
                VALUES ($1, $2, $3);
            """, data_subjects)

            # -------------------------------------------------------------
            # 3. Create Synthetic Approvals
            # -------------------------------------------------------------
            print("Generating synthetic approvals...")
            approvals = []
            approval_ids = []
            compliance_stewards = [id_tuple[0] for id_tuple in identities if id_tuple[4] == "Compliance" or id_tuple[3] == "STEWARD"]
            if not compliance_stewards:
                compliance_stewards = [identities[1][0]]

            for i in range(1500):
                appr_id = str(uuid.UUID(int=10000 + i))
                approval_ids.append(appr_id)
                steward_id = compliance_stewards[i % len(compliance_stewards)]
                appr_type = "INGEST" if i % 3 != 0 else ("PUBLICATION" if i % 3 == 1 else "OVERRIDE")
                obj_type = "knowledge_asset"
                obj_id = str(uuid.UUID(int=50000 + i))
                payload_hash = hashlib.sha256(f"payload_hash_{i}".encode()).hexdigest()
                policy_ver = "v1.2.0"
                status = "APPROVED" if i % 10 != 0 else "REJECTED"
                approvals.append((appr_id, steward_id, appr_type, obj_type, obj_id, payload_hash, policy_ver, status))

            await conn.executemany("""
                INSERT INTO approval (approval_id, approver_id, approval_type, object_type, object_id, approved_payload_hash, policy_version, status)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8);
            """, approvals)

            # -------------------------------------------------------------
            # 4. Create Synthetic Knowledge Assets Corpus (~2,500 assets)
            # -------------------------------------------------------------
            print("Generating 2,500 synthetic corpus assets across Northwind divisions...")
            knowledge_assets = []

            steward_ids = [id_tuple[0] for id_tuple in identities if id_tuple[3] in ["STEWARD", "ADMIN"] or id_tuple[4] in ["Compliance", "Technology"]]
            
            # Helper to generate SHA256 hex
            def make_hash(seed_str):
                return hashlib.sha256(seed_str.encode()).hexdigest()

            # A. Advisory Deal Files (MNPI - Material Non-Public Information) -> 500 assets
            for i in range(500):
                asset_id = str(uuid.UUID(int=50000 + i))
                source = "Northwind Advisory Deal Vault"
                source_ref = f"DEAL-MNPI-2026-{1000 + i}"
                version = 1
                supersession_id = None
                classification = "RESTRICTED"
                barrier_side = "SIDE_A"  # Advisory Information Barrier
                jurisdiction = "US" if i % 2 == 0 else "UK"
                personal_data = False
                subj_id = None
                steward = steward_ids[i % len(steward_ids)]
                appr_id = approval_ids[i % len(approval_ids)]
                state = "APPROVED"
                retention_class = "7_YEARS_MNPI"
                legal_hold = True if i % 10 == 0 else False
                content_ref = f"s3://northwind-vault/advisory/mnpi_deal_{1000+i}.pdf"
                dek_ref = f"kms/key-advisory-{i % 5}"
                chash = make_hash(f"advisory_content_{i}")
                knowledge_assets.append((
                    asset_id, source, source_ref, version, supersession_id, classification,
                    barrier_side, jurisdiction, personal_data, subj_id, steward, appr_id,
                    state, retention_class, legal_hold, content_ref, dek_ref, chash
                ))

            # B. Research Notes (Published & Unpublished) -> 500 assets
            for i in range(500):
                idx = 500 + i
                asset_id = str(uuid.UUID(int=50000 + idx))
                is_published = (i % 2 == 0)
                source = "Northwind Research Hub"
                source_ref = f"RES-NOTE-2026-{'PUB' if is_published else 'UNPUB'}-{2000 + i}"
                version = 1
                supersession_id = None
                classification = "PUBLIC" if is_published else "CONFIDENTIAL"
                barrier_side = "GENERAL" if is_published else "SIDE_B"
                jurisdiction = "GLOBAL" if is_published else ("US" if i % 2 == 0 else "EU")
                personal_data = False
                subj_id = None
                steward = steward_ids[idx % len(steward_ids)]
                appr_id = approval_ids[idx % len(approval_ids)] if is_published else None
                state = "APPROVED" if is_published else ("DRAFT" if i % 4 == 1 else "PENDING_APPROVAL")
                retention_class = "STANDARD_RESEARCH"
                legal_hold = False
                content_ref = f"s3://northwind-vault/research/note_{2000+i}.md"
                dek_ref = f"kms/key-research-{i % 5}"
                chash = make_hash(f"research_content_{i}")
                knowledge_assets.append((
                    asset_id, source, source_ref, version, supersession_id, classification,
                    barrier_side, jurisdiction, personal_data, subj_id, steward, appr_id,
                    state, retention_class, legal_hold, content_ref, dek_ref, chash
                ))

            # C. Engineering Artifacts (Tickets, PRs, ADRs) -> 600 assets
            for i in range(600):
                idx = 1000 + i
                asset_id = str(uuid.UUID(int=50000 + idx))
                artifact_type = "ADR" if i % 10 == 0 else ("PR" if i % 3 == 0 else "TICKET")
                source = f"Northwind Technology {artifact_type} Store"
                source_ref = f"TECH-{artifact_type}-2026-{3000 + i}"
                version = 1
                supersession_id = None
                classification = "INTERNAL"
                barrier_side = "GENERAL"
                jurisdiction = "GLOBAL"
                personal_data = False
                subj_id = None
                steward = steward_ids[idx % len(steward_ids)]
                appr_id = None
                state = "DRAFT" if i % 5 == 0 else ("PENDING_APPROVAL" if i % 5 == 1 else "REJECTED")
                retention_class = "TECH_ARTIFACTS"
                legal_hold = False
                content_ref = f"s3://northwind-vault/tech/{artifact_type.lower()}_{3000+i}.json"
                dek_ref = f"kms/key-tech-{i % 5}"
                chash = make_hash(f"tech_content_{i}")
                knowledge_assets.append((
                    asset_id, source, source_ref, version, supersession_id, classification,
                    barrier_side, jurisdiction, personal_data, subj_id, steward, appr_id,
                    state, retention_class, legal_hold, content_ref, dek_ref, chash
                ))

            # D. Policy & Procedure Documents -> 400 assets
            for i in range(400):
                idx = 1600 + i
                asset_id = str(uuid.UUID(int=50000 + idx))
                source = "Northwind Compliance Policy Library"
                source_ref = f"POL-GOV-2026-{4000 + i}"
                version = 1
                supersession_id = None
                classification = "INTERNAL" if i % 2 == 0 else "CONFIDENTIAL"
                barrier_side = "GENERAL"
                jurisdiction = "US" if i % 3 == 0 else ("EU" if i % 3 == 1 else "UK")
                personal_data = False
                subj_id = None
                steward = steward_ids[idx % len(steward_ids)]
                appr_id = approval_ids[idx % len(approval_ids)]
                state = "APPROVED"
                retention_class = "PERMANENT_POLICY"
                legal_hold = True if i % 5 == 0 else False
                content_ref = f"s3://northwind-vault/policies/policy_{4000+i}.pdf"
                dek_ref = f"kms/key-compliance-{i % 5}"
                chash = make_hash(f"policy_content_{i}")
                knowledge_assets.append((
                    asset_id, source, source_ref, version, supersession_id, classification,
                    barrier_side, jurisdiction, personal_data, subj_id, steward, appr_id,
                    state, retention_class, legal_hold, content_ref, dek_ref, chash
                ))

            # E. Synthetic Personal-Data Onboarding Records -> 492 assets (Marked SYNTHETIC)
            for i in range(492):
                idx = 2000 + i
                asset_id = str(uuid.UUID(int=50000 + idx))
                source = "Northwind Operations HR Onboarding"
                source_ref = f"SYNTHETIC-HR-ONBOARDING-2026-{5000 + i}"
                version = 1
                supersession_id = None
                classification = "CONFIDENTIAL"
                barrier_side = "GENERAL"
                jurisdiction = "EU" if i % 2 == 0 else "UK"
                personal_data = True
                subj_id = subject_ids[i % len(subject_ids)]
                steward = steward_ids[idx % len(steward_ids)]
                appr_id = approval_ids[idx % len(approval_ids)]
                state = "APPROVED"
                retention_class = "HR_PERSONAL_DATA"
                legal_hold = False
                content_ref = f"s3://northwind-vault/hr/synthetic_record_{5000+i}.json"
                dek_ref = f"kms/key-hr-{i % 5}"
                chash = make_hash(f"hr_content_{i}")
                knowledge_assets.append((
                    asset_id, source, source_ref, version, supersession_id, classification,
                    barrier_side, jurisdiction, personal_data, subj_id, steward, appr_id,
                    state, retention_class, legal_hold, content_ref, dek_ref, chash
                ))

            # F. Superseded Document Versions (5 chain pairs -> 5 v1 archived assets + 5 v2 approved assets)
            superseded_v1_ids = []
            for i in range(5):
                idx = 2492 + i
                v1_asset_id = str(uuid.UUID(int=50000 + idx))
                superseded_v1_ids.append(v1_asset_id)
                source = "Northwind Strategy Portal"
                source_ref = f"STRAT-DOC-2026-V1-{6000 + i}"
                version = 1
                supersession_id = None
                classification = "CONFIDENTIAL"
                barrier_side = "GENERAL"
                jurisdiction = "US"
                personal_data = False
                subj_id = None
                steward = steward_ids[idx % len(steward_ids)]
                appr_id = approval_ids[idx % len(approval_ids)]
                state = "ARCHIVED"  # Superseded v1 document is ARCHIVED
                retention_class = "STRATEGY_DOCS"
                legal_hold = False
                content_ref = f"s3://northwind-vault/strat/v1_doc_{6000+i}.pdf"
                dek_ref = f"kms/key-strat-{i}"
                chash = make_hash(f"v1_strat_content_{i}")
                knowledge_assets.append((
                    v1_asset_id, source, source_ref, version, supersession_id, classification,
                    barrier_side, jurisdiction, personal_data, subj_id, steward, appr_id,
                    state, retention_class, legal_hold, content_ref, dek_ref, chash
                ))

            # Add v2 assets referencing v1 as supersession_id
            for i in range(3):  # 3 v2 assets replacing v1 assets (Total assets = 2492 + 5 + 3 = 2500!)
                idx = 2497 + i
                v2_asset_id = str(uuid.UUID(int=50000 + idx))
                v1_ref_id = superseded_v1_ids[i]
                source = "Northwind Strategy Portal"
                source_ref = f"STRAT-DOC-2026-V2-{6000 + i}"
                version = 2
                supersession_id = v1_ref_id  # Linked to v1 asset
                classification = "CONFIDENTIAL"
                barrier_side = "GENERAL"
                jurisdiction = "US"
                personal_data = False
                subj_id = None
                steward = steward_ids[idx % len(steward_ids)]
                appr_id = approval_ids[idx % len(approval_ids)]
                state = "APPROVED"
                retention_class = "STRATEGY_DOCS"
                legal_hold = False
                content_ref = f"s3://northwind-vault/strat/v2_doc_{6000+i}.pdf"
                dek_ref = f"kms/key-strat-{i}"
                chash = make_hash(f"v2_strat_content_{i}")
                knowledge_assets.append((
                    v2_asset_id, source, source_ref, version, supersession_id, classification,
                    barrier_side, jurisdiction, personal_data, subj_id, steward, appr_id,
                    state, retention_class, legal_hold, content_ref, dek_ref, chash
                ))

            # G. EXACTLY THREE Adversarial / Prompt-Injection Documents
            # We explicitly place 3 adversarial documents in the corpus
            adversarial_indices = [105, 750, 1820]
            for adv_idx_pos, adv_target_idx in enumerate(adversarial_indices):
                orig_tuple = knowledge_assets[adv_target_idx]
                adv_id = orig_tuple[0]
                adv_source = f"{orig_tuple[1]} [ADVERSARIAL_CONTAINER]"
                adv_source_ref = f"ADVERSARIAL_PROMPT_INJECTION_0{adv_idx_pos+1}"
                adv_content_ref = f"s3://northwind-vault/adversarial/prompt_injection_payload_0{adv_idx_pos+1}.txt"
                
                # Overwrite original tuple with adversarial content metadata
                knowledge_assets[adv_target_idx] = (
                    adv_id, adv_source, adv_source_ref, orig_tuple[3], orig_tuple[4], orig_tuple[5],
                    orig_tuple[6], orig_tuple[7], orig_tuple[8], orig_tuple[9], orig_tuple[10], orig_tuple[11],
                    orig_tuple[12], orig_tuple[13], orig_tuple[14], adv_content_ref, orig_tuple[16], orig_tuple[17]
                )

            # Insert all 2,500 knowledge assets into PostgreSQL
            await conn.executemany("""
                INSERT INTO knowledge_asset (
                    asset_id, source, source_ref, version, supersession_id, classification,
                    barrier_side, jurisdiction, personal_data, subject_id, steward_id, approval_id,
                    state, retention_class, legal_hold, content_ref, dek_ref, content_hash
                ) VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18
                );
            """, knowledge_assets)

            # -------------------------------------------------------------
            # 5. Populate Entitlements (Identity Authorizations)
            # -------------------------------------------------------------
            print("Generating entitlements for Northwind identities...")
            entitlements = []
            admin_identity_id = identities[0][0]
            for i in range(200):
                ent_id = str(uuid.UUID(int=80000 + i))
                user_id = identity_ids[i % len(identity_ids)]
                classif = CLASSIFICATIONS[i % len(CLASSIFICATIONS)]
                barrier = BARRIERS[i % len(BARRIERS)]
                juris = JURISDICTIONS[i % len(JURISDICTIONS)]
                proj = f"PROJECT_{DIVISIONS[i % len(DIVISIONS)].upper()}"
                entitlements.append((ent_id, user_id, classif, barrier, juris, proj, admin_identity_id))

            await conn.executemany("""
                INSERT INTO entitlement (entitlement_id, identity_id, classification, barrier, jurisdiction, project, grantor_id)
                VALUES ($1, $2, $3, $4, $5, $6, $7);
            """, entitlements)

            # -------------------------------------------------------------
            # 6. Populate Tamper-Evident Audit Log Events
            # -------------------------------------------------------------
            print("Populating initial audit events for corpus bootstrap...")
            audit_events = [
                ("SYSTEM", admin_identity_id, None, "BOOTSTRAP_PHASE3", "system", "northwind_securities", "ALLOW", "PHASE3_INITIALIZATION", "v2.0.0", make_hash("init")),
                ("USER", identities[1][0], None, "BULK_INGEST_CORPUS", "knowledge_asset", "corpus_2500", "ALLOW", "COMPLIANCE_APPROVED", "v2.0.0", make_hash("bulk"))
            ]
            
            for evt in audit_events:
                await conn.execute("""
                    INSERT INTO audit_event (actor_type, actor_id, on_behalf_of, action, object_type, object_id, decision, reason_code, policy_version, payload_hash)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10);
                """, *evt)

        print("[SUCCESS] Phase 3 Synthetic Reference Firm (Northwind Securities) & 2,500 Corpus Assets seeded successfully!")

    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(seed_phase3_reference_firm_and_corpus())
