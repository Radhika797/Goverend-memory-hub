import pytest
import asyncpg
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "apps", "api")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

try:
    from apps.api.app.config import settings
except (ImportError, ModuleNotFoundError):
    from app.config import settings  # type: ignore # pyrefly: disable=missing-import

@pytest.mark.asyncio
async def test_synthetic_identities_count_and_divisions():
    conn = await asyncpg.connect(
        user=settings.POSTGRES_USER,
        password=settings.POSTGRES_PASSWORD,
        database=settings.POSTGRES_DB,
        host=settings.POSTGRES_HOST,
        port=settings.POSTGRES_PORT,
    )
    try:
        # 1. Exactly 40 synthetic identities
        count = await conn.fetchval("SELECT COUNT(*) FROM identity;")
        assert count == 40, f"Expected exactly 40 synthetic identities, got {count}."

        # 2. Required 6 divisions exist
        expected_divisions = {"Advisory", "Markets", "Research", "Operations", "Compliance", "Technology"}
        records = await conn.fetch("SELECT DISTINCT department FROM identity;")
        actual_divisions = {r["department"] for r in records}
        for div in expected_divisions:
            assert div in actual_divisions, f"Missing required division '{div}' in identity table."

    finally:
        await conn.close()

@pytest.mark.asyncio
async def test_jurisdictions_exist():
    conn = await asyncpg.connect(
        user=settings.POSTGRES_USER,
        password=settings.POSTGRES_PASSWORD,
        database=settings.POSTGRES_DB,
        host=settings.POSTGRES_HOST,
        port=settings.POSTGRES_PORT,
    )
    try:
        # 3. Both US and UK/EU jurisdictions exist
        records = await conn.fetch("SELECT DISTINCT jurisdiction FROM knowledge_asset;")
        jurisdictions = {r["jurisdiction"] for r in records}
        assert "US" in jurisdictions, "Jurisdiction 'US' missing from knowledge assets."
        assert ("EU" in jurisdictions or "UK" in jurisdictions), "Jurisdictions 'EU'/'UK' missing from knowledge assets."

    finally:
        await conn.close()

@pytest.mark.asyncio
async def test_corpus_document_count_range():
    conn = await asyncpg.connect(
        user=settings.POSTGRES_USER,
        password=settings.POSTGRES_PASSWORD,
        database=settings.POSTGRES_DB,
        host=settings.POSTGRES_HOST,
        port=settings.POSTGRES_PORT,
    )
    try:
        # 4. Corpus count is within 2,000–3,000
        count = await conn.fetchval("SELECT COUNT(*) FROM knowledge_asset;")
        assert 2000 <= count <= 3000, f"Expected corpus count between 2,000 and 3,000, got {count}."

    finally:
        await conn.close()

@pytest.mark.asyncio
async def test_mnpi_advisory_documents_exist():
    conn = await asyncpg.connect(
        user=settings.POSTGRES_USER,
        password=settings.POSTGRES_PASSWORD,
        database=settings.POSTGRES_DB,
        host=settings.POSTGRES_HOST,
        port=settings.POSTGRES_PORT,
    )
    try:
        # 5. Advisory deal files marked MNPI
        mnpi_count = await conn.fetchval("""
            SELECT COUNT(*) FROM knowledge_asset
            WHERE source_ref LIKE '%MNPI%' AND classification = 'RESTRICTED' AND barrier_side = 'SIDE_A';
        """)
        assert mnpi_count >= 100, f"Expected MNPI Advisory documents, found {mnpi_count}."

    finally:
        await conn.close()

@pytest.mark.asyncio
async def test_research_published_and_unpublished_exist():
    conn = await asyncpg.connect(
        user=settings.POSTGRES_USER,
        password=settings.POSTGRES_PASSWORD,
        database=settings.POSTGRES_DB,
        host=settings.POSTGRES_HOST,
        port=settings.POSTGRES_PORT,
    )
    try:
        # 6. Published research notes
        published_count = await conn.fetchval("""
            SELECT COUNT(*) FROM knowledge_asset
            WHERE source = 'Northwind Research Hub' AND state = 'APPROVED' AND classification = 'PUBLIC';
        """)
        assert published_count > 0, "No published Research notes found."

        # Unpublished research notes
        unpublished_count = await conn.fetchval("""
            SELECT COUNT(*) FROM knowledge_asset
            WHERE source = 'Northwind Research Hub' AND state IN ('DRAFT', 'PENDING_APPROVAL') AND classification = 'CONFIDENTIAL';
        """)
        assert unpublished_count > 0, "No unpublished Research notes found."

    finally:
        await conn.close()

@pytest.mark.asyncio
async def test_engineering_and_policy_documents_exist():
    conn = await asyncpg.connect(
        user=settings.POSTGRES_USER,
        password=settings.POSTGRES_PASSWORD,
        database=settings.POSTGRES_DB,
        host=settings.POSTGRES_HOST,
        port=settings.POSTGRES_PORT,
    )
    try:
        # 7. Engineering artifacts (tickets, PRs, ADRs)
        tech_count = await conn.fetchval("SELECT COUNT(*) FROM knowledge_asset WHERE source LIKE '%Technology%';")
        assert tech_count >= 100, f"Expected Engineering artifacts, found {tech_count}."

        # Policy & Procedure documents
        policy_count = await conn.fetchval("SELECT COUNT(*) FROM knowledge_asset WHERE source LIKE '%Compliance Policy%';")
        assert policy_count >= 100, f"Expected Policy documents, found {policy_count}."

    finally:
        await conn.close()

@pytest.mark.asyncio
async def test_synthetic_personal_data_marked():
    conn = await asyncpg.connect(
        user=settings.POSTGRES_USER,
        password=settings.POSTGRES_PASSWORD,
        database=settings.POSTGRES_DB,
        host=settings.POSTGRES_HOST,
        port=settings.POSTGRES_PORT,
    )
    try:
        # 8. Synthetic personal-data onboarding records
        personal_data_count = await conn.fetchval("""
            SELECT COUNT(*) FROM knowledge_asset
            WHERE personal_data = TRUE AND subject_id IS NOT NULL AND source_ref LIKE 'SYNTHETIC%';
        """)
        assert personal_data_count >= 100, f"Expected synthetic personal data onboarding records, found {personal_data_count}."

    finally:
        await conn.close()

@pytest.mark.asyncio
async def test_superseded_versions_exist():
    conn = await asyncpg.connect(
        user=settings.POSTGRES_USER,
        password=settings.POSTGRES_PASSWORD,
        database=settings.POSTGRES_DB,
        host=settings.POSTGRES_HOST,
        port=settings.POSTGRES_PORT,
    )
    try:
        # 9. Superseded document versions
        superseded_count = await conn.fetchval("""
            SELECT COUNT(*) FROM knowledge_asset
            WHERE supersession_id IS NOT NULL AND version > 1;
        """)
        assert superseded_count >= 2, f"Expected at least 2 superseded document versions, found {superseded_count}."

    finally:
        await conn.close()

@pytest.mark.asyncio
async def test_exactly_three_adversarial_documents():
    conn = await asyncpg.connect(
        user=settings.POSTGRES_USER,
        password=settings.POSTGRES_PASSWORD,
        database=settings.POSTGRES_DB,
        host=settings.POSTGRES_HOST,
        port=settings.POSTGRES_PORT,
    )
    try:
        # 10. Exactly three adversarial / prompt-injection documents
        adv_count = await conn.fetchval("""
            SELECT COUNT(*) FROM knowledge_asset
            WHERE source_ref LIKE 'ADVERSARIAL_PROMPT_INJECTION%';
        """)
        assert adv_count == 3, f"Expected EXACTLY 3 adversarial documents, found {adv_count}."

    finally:
        await conn.close()

@pytest.mark.asyncio
async def test_governance_metadata_populated():
    conn = await asyncpg.connect(
        user=settings.POSTGRES_USER,
        password=settings.POSTGRES_PASSWORD,
        database=settings.POSTGRES_DB,
        host=settings.POSTGRES_HOST,
        port=settings.POSTGRES_PORT,
    )
    try:
        # 11. Governance metadata fields non-null check
        null_meta_count = await conn.fetchval("""
            SELECT COUNT(*) FROM knowledge_asset
            WHERE classification IS NULL OR barrier_side IS NULL OR jurisdiction IS NULL OR steward_id IS NULL OR state IS NULL;
        """)
        assert null_meta_count == 0, f"Found {null_meta_count} knowledge assets with unpopulated governance metadata."

    finally:
        await conn.close()
