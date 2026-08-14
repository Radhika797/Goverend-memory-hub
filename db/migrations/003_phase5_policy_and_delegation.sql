-- Phase 5 Migration: Identity & Policy Engine
-- Governed Memory Hub

-- 1. Delegation Token Table (Short-lived delegated authority tracking)
CREATE TABLE IF NOT EXISTS delegation_token (
    token_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    grantor_id UUID NOT NULL REFERENCES identity(identity_id),
    delegate_id UUID NOT NULL REFERENCES identity(identity_id),
    delegated_scopes TEXT[] NOT NULL,
    issued_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    expires_at TIMESTAMPTZ NOT NULL,
    revoked BOOLEAN NOT NULL DEFAULT FALSE,
    signature_hash VARCHAR(64) NOT NULL CHECK (length(signature_hash) = 64),
    CONSTRAINT chk_delegation_expiration CHECK (expires_at > issued_at)
);

-- 2. Policy Definition Table (Versioned policy rules)
CREATE TABLE IF NOT EXISTS policy_definition (
    policy_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    version VARCHAR(32) UNIQUE NOT NULL,
    name VARCHAR(128) NOT NULL,
    rules_json JSONB NOT NULL,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

-- Enable RLS on Phase 5 tables
ALTER TABLE delegation_token ENABLE ROW LEVEL SECURITY;
ALTER TABLE policy_definition ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS rls_delegation_token_policy ON delegation_token;
CREATE POLICY rls_delegation_token_policy ON delegation_token FOR ALL USING (true);

DROP POLICY IF EXISTS rls_policy_definition_policy ON policy_definition;
CREATE POLICY rls_policy_definition_policy ON policy_definition FOR ALL USING (true);

-- Grant privileges to gmh_app_role
GRANT SELECT, INSERT, UPDATE ON delegation_token TO gmh_app_role;
GRANT SELECT, INSERT, UPDATE ON policy_definition TO gmh_app_role;

-- Insert initial versioned policy definition (v1.0.0 & v2.0.0)
INSERT INTO policy_definition (version, name, rules_json, active) VALUES
('v1.0.0', 'Standard Institutional Governance Policy', '{
    "clearance_hierarchy": {"PUBLIC": 1, "INTERNAL": 2, "CONFIDENTIAL": 3, "RESTRICTED": 4},
    "default_fail_closed": true,
    "require_steward_for_approval": true
}'::jsonb, true),
('v2.0.0', 'Strict Multi-Jurisdictional Barrier Policy', '{
    "clearance_hierarchy": {"PUBLIC": 1, "INTERNAL": 2, "CONFIDENTIAL": 3, "RESTRICTED": 4},
    "default_fail_closed": true,
    "require_steward_for_approval": true,
    "strict_barrier_enforcement": true
}'::jsonb, true)
ON CONFLICT (version) DO NOTHING;
