-- Phase 9 Migration: Evidence Package & Verification Suite
-- Governed Memory Hub

-- 1. Evidence Package Table
CREATE TABLE IF NOT EXISTS evidence_package (
    package_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    scope_type VARCHAR(32) NOT NULL, -- TASK, ASSET, GLOBAL
    scope_ref_id UUID NOT NULL,
    package_json JSONB NOT NULL,
    package_digest_sha256 VARCHAR(64) NOT NULL CHECK (length(package_digest_sha256) = 64),
    generated_by UUID REFERENCES identity(identity_id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

-- Enable RLS on Phase 9 table
ALTER TABLE evidence_package ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS rls_evidence_package_policy ON evidence_package;
CREATE POLICY rls_evidence_package_policy ON evidence_package FOR ALL USING (true);

-- Grant privileges to gmh_app_role
GRANT SELECT, INSERT, UPDATE, DELETE ON evidence_package TO gmh_app_role;
