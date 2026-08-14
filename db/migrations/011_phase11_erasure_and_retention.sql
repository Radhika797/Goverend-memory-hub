-- Phase 11 Migration: Erasure & Retention Governance
-- Governed Memory Hub

CREATE TABLE IF NOT EXISTS erasure_receipt (
    erasure_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    subject_id UUID REFERENCES data_subject(subject_id) ON DELETE SET NULL,
    asset_id UUID REFERENCES knowledge_asset(asset_id) ON DELETE SET NULL,
    authorizer_identity_id UUID REFERENCES identity(identity_id) ON DELETE SET NULL,
    status VARCHAR(32) NOT NULL, -- 'COMPLETED', 'REFUSED'
    refusal_reason VARCHAR(128),
    dek_destroyed BOOLEAN NOT NULL DEFAULT false,
    chunks_deleted_count INTEGER NOT NULL DEFAULT 0,
    graph_nodes_deleted_count INTEGER NOT NULL DEFAULT 0,
    erasure_digest_sha256 VARCHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

-- Seed a Legal-Hold Personal Data Subject Fixture for Legal-Hold Refusal Verification
INSERT INTO data_subject (subject_id, subject_ref, jurisdiction) VALUES
    ('00000000-0000-0000-0000-00000000139e', 'SUBJ-LEGAL-HOLD-99', 'US_NY')
ON CONFLICT (subject_id) DO NOTHING;

-- Seed an Asset for the Legal-Hold Subject with legal_hold = true
INSERT INTO knowledge_asset (
    asset_id, source, source_ref, version, classification, barrier_side, jurisdiction,
    personal_data, subject_id, steward_id, approval_id, state, retention_class, legal_hold,
    content_ref, dek_ref, content_hash
) VALUES (
    '00000000-0000-0000-0000-00000000c999', 'HR_PORTAL', 'ref/litigation_subject_record.doc', 1,
    'CONFIDENTIAL', 'GENERAL', 'US_NY', true, '00000000-0000-0000-0000-00000000139e',
    '00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000100',
    'APPROVED', 'LITIGATION_HOLD', true, 's3://vault/litigation_99.enc', 'kms/key-litigation-hold-99',
    'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'
) ON CONFLICT (asset_id) DO NOTHING;

-- Enable RLS
ALTER TABLE erasure_receipt ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS rls_erasure_receipt_policy ON erasure_receipt;
CREATE POLICY rls_erasure_receipt_policy ON erasure_receipt FOR ALL USING (true);

-- Grant permissions to app role
GRANT SELECT, INSERT, UPDATE, DELETE ON erasure_receipt TO gmh_app_role;
