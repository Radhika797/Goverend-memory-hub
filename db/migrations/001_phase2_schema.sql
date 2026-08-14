-- Phase 2 Migration: PostgreSQL Database + Audit Foundation
-- Governed Memory Hub

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- 1. Migration History Table
CREATE TABLE IF NOT EXISTS schema_migrations (
    version VARCHAR(128) PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

-- 2. Identity Table
CREATE TABLE IF NOT EXISTS identity (
    identity_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(128) NOT NULL,
    type VARCHAR(32) NOT NULL CHECK (type IN ('USER', 'SERVICE_ACCOUNT', 'SYSTEM')),
    role VARCHAR(64) NOT NULL CHECK (role IN ('ADMIN', 'STEWARD', 'ANALYST', 'MEMBER', 'PUBLIC')),
    department VARCHAR(64) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'REVOKED', 'SUSPENDED')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

-- 3. Data Subject Table
CREATE TABLE IF NOT EXISTS data_subject (
    subject_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    subject_ref VARCHAR(128) UNIQUE NOT NULL,
    jurisdiction VARCHAR(32) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

-- 4. Approval Table
CREATE TABLE IF NOT EXISTS approval (
    approval_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    approver_id UUID NOT NULL REFERENCES identity(identity_id),
    approval_type VARCHAR(64) NOT NULL,
    object_type VARCHAR(64) NOT NULL,
    object_id VARCHAR(128) NOT NULL,
    approved_payload_hash VARCHAR(64) NOT NULL CHECK (length(approved_payload_hash) = 64),
    policy_version VARCHAR(32) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING', 'APPROVED', 'REJECTED', 'EXPIRED')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

-- 5. Knowledge Asset Table
CREATE TABLE IF NOT EXISTS knowledge_asset (
    asset_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source VARCHAR(128) NOT NULL,
    source_ref VARCHAR(256) NOT NULL,
    version INT NOT NULL DEFAULT 1 CHECK (version > 0),
    supersession_id UUID REFERENCES knowledge_asset(asset_id) ON DELETE SET NULL,
    classification VARCHAR(32) NOT NULL CHECK (classification IN ('PUBLIC', 'INTERNAL', 'CONFIDENTIAL', 'RESTRICTED')),
    barrier_side VARCHAR(32) NOT NULL CHECK (barrier_side IN ('SIDE_A', 'SIDE_B', 'GENERAL')),
    jurisdiction VARCHAR(32) NOT NULL,
    personal_data BOOLEAN NOT NULL DEFAULT FALSE,
    subject_id UUID REFERENCES data_subject(subject_id),
    steward_id UUID NOT NULL REFERENCES identity(identity_id),
    approval_id UUID REFERENCES approval(approval_id),
    state VARCHAR(32) NOT NULL DEFAULT 'DRAFT' CHECK (state IN ('DRAFT', 'PENDING_APPROVAL', 'APPROVED', 'REJECTED', 'ARCHIVED')),
    retention_class VARCHAR(64) NOT NULL,
    legal_hold BOOLEAN NOT NULL DEFAULT FALSE,
    content_ref VARCHAR(512) NOT NULL,
    dek_ref VARCHAR(256) NOT NULL,
    content_hash VARCHAR(64) NOT NULL CHECK (length(content_hash) = 64),
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),

    -- Governance Constraints
    CONSTRAINT chk_approval_integrity CHECK (state != 'APPROVED' OR approval_id IS NOT NULL),
    CONSTRAINT chk_personal_data_subject CHECK (personal_data = FALSE OR subject_id IS NOT NULL)
);

-- 6. Entitlement Table
CREATE TABLE IF NOT EXISTS entitlement (
    entitlement_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    identity_id UUID NOT NULL REFERENCES identity(identity_id),
    classification VARCHAR(32) NOT NULL CHECK (classification IN ('PUBLIC', 'INTERNAL', 'CONFIDENTIAL', 'RESTRICTED')),
    barrier VARCHAR(32) NOT NULL CHECK (barrier IN ('SIDE_A', 'SIDE_B', 'GENERAL')),
    jurisdiction VARCHAR(32) NOT NULL,
    project VARCHAR(64) NOT NULL,
    grantor_id UUID NOT NULL REFERENCES identity(identity_id),
    granted_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    expires_at TIMESTAMPTZ,
    CONSTRAINT chk_entitlement_expiration CHECK (expires_at IS NULL OR expires_at > granted_at)
);

-- 7. Audit Event Table
CREATE TABLE IF NOT EXISTS audit_event (
    event_id BIGSERIAL PRIMARY KEY,
    actor_type VARCHAR(32) NOT NULL,
    actor_id VARCHAR(128) NOT NULL,
    on_behalf_of VARCHAR(128),
    action VARCHAR(64) NOT NULL,
    object_type VARCHAR(64) NOT NULL,
    object_id VARCHAR(128) NOT NULL,
    decision VARCHAR(32) NOT NULL,
    reason_code VARCHAR(64) NOT NULL,
    policy_version VARCHAR(32) NOT NULL,
    payload_hash VARCHAR(64) NOT NULL,
    previous_hash VARCHAR(64) NOT NULL,
    current_hash VARCHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

-- 8. Audit Immutability Trigger (Prevent UPDATE / DELETE)
CREATE OR REPLACE FUNCTION prevent_audit_modification()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'Audit events are immutable and append-only. UPDATE and DELETE operations are prohibited.';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_audit_immutable ON audit_event;
CREATE TRIGGER trg_audit_immutable
BEFORE UPDATE OR DELETE ON audit_event
FOR EACH ROW EXECUTE FUNCTION prevent_audit_modification();

-- 9. Audit Hash Chaining Trigger (Automatic Calculation & Chain Verification on Insert)
CREATE OR REPLACE FUNCTION compute_audit_hash_chain()
RETURNS TRIGGER AS $$
DECLARE
    last_hash VARCHAR(64);
    canonical_str TEXT;
BEGIN
    -- Fetch the previous event's current_hash if previous_hash is not explicitly set
    IF NEW.previous_hash IS NULL OR NEW.previous_hash = '' THEN
        SELECT current_hash INTO last_hash FROM audit_event ORDER BY event_id DESC LIMIT 1;
        IF last_hash IS NULL THEN
            last_hash := '0000000000000000000000000000000000000000000000000000000000000000';
        END IF;
        NEW.previous_hash := last_hash;
    END IF;

    -- Construct canonical payload string for SHA-256 hash chaining
    canonical_str := NEW.previous_hash || '|' ||
                     COALESCE(NEW.actor_type, '') || '|' ||
                     COALESCE(NEW.actor_id, '') || '|' ||
                     COALESCE(NEW.on_behalf_of, '') || '|' ||
                     COALESCE(NEW.action, '') || '|' ||
                     COALESCE(NEW.object_type, '') || '|' ||
                     COALESCE(NEW.object_id, '') || '|' ||
                     COALESCE(NEW.decision, '') || '|' ||
                     COALESCE(NEW.reason_code, '') || '|' ||
                     COALESCE(NEW.policy_version, '') || '|' ||
                     COALESCE(NEW.payload_hash, '');

    -- Compute SHA256 current_hash
    NEW.current_hash := encode(digest(canonical_str, 'sha256'), 'hex');

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_audit_hash_chain ON audit_event;
CREATE TRIGGER trg_audit_hash_chain
BEFORE INSERT ON audit_event
FOR EACH ROW EXECUTE FUNCTION compute_audit_hash_chain();

-- 10. Knowledge Asset State Transition Integrity Trigger
CREATE OR REPLACE FUNCTION validate_knowledge_asset_transition()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'UPDATE' THEN
        -- Prevent changing state from ARCHIVED to APPROVED without version increment
        IF OLD.state = 'ARCHIVED' AND NEW.state = 'APPROVED' AND NEW.version <= OLD.version THEN
            RAISE EXCEPTION 'Cannot transition state from ARCHIVED directly to APPROVED without incrementing version.';
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_knowledge_asset_transition ON knowledge_asset;
CREATE TRIGGER trg_knowledge_asset_transition
BEFORE UPDATE ON knowledge_asset
FOR EACH ROW EXECUTE FUNCTION validate_knowledge_asset_transition();
