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

-- Seed a Legal-Hold Personal Data Subject Fixture
INSERT INTO data_subject (subject_id, subject_ref, jurisdiction) VALUES
    ('00000000-0000-0000-0000-00000000139e', 'SUBJ-LEGAL-HOLD-99', 'US_NY')
ON CONFLICT (subject_id) DO NOTHING;

-- Enable RLS
ALTER TABLE erasure_receipt ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS rls_erasure_receipt_policy ON erasure_receipt;
CREATE POLICY rls_erasure_receipt_policy ON erasure_receipt FOR ALL USING (true);

-- Grant permissions to app role
GRANT SELECT, INSERT, UPDATE, DELETE ON erasure_receipt TO gmh_app_role;
