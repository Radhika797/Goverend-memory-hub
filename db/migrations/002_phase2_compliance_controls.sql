-- Phase 2 Migration 002: Strict Compliance Controls & RLS
-- Governed Memory Hub

-- 1. Enable Row-Level Security (RLS) on all governed knowledge and audit tables
ALTER TABLE knowledge_asset ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_event ENABLE ROW LEVEL SECURITY;
ALTER TABLE entitlement ENABLE ROW LEVEL SECURITY;
ALTER TABLE approval ENABLE ROW LEVEL SECURITY;
ALTER TABLE identity ENABLE ROW LEVEL SECURITY;
ALTER TABLE data_subject ENABLE ROW LEVEL SECURITY;

-- 2. Define RLS Policies for governed tables
DROP POLICY IF EXISTS rls_knowledge_asset_policy ON knowledge_asset;
CREATE POLICY rls_knowledge_asset_policy ON knowledge_asset FOR ALL USING (true);

DROP POLICY IF EXISTS rls_audit_event_select_policy ON audit_event;
CREATE POLICY rls_audit_event_select_policy ON audit_event FOR SELECT USING (true);

DROP POLICY IF EXISTS rls_audit_event_insert_policy ON audit_event;
CREATE POLICY rls_audit_event_insert_policy ON audit_event FOR INSERT WITH CHECK (true);

DROP POLICY IF EXISTS rls_entitlement_policy ON entitlement;
CREATE POLICY rls_entitlement_policy ON entitlement FOR ALL USING (true);

DROP POLICY IF EXISTS rls_approval_policy ON approval;
CREATE POLICY rls_approval_policy ON approval FOR ALL USING (true);

DROP POLICY IF EXISTS rls_identity_policy ON identity;
CREATE POLICY rls_identity_policy ON identity FOR ALL USING (true);

DROP POLICY IF EXISTS rls_data_subject_policy ON data_subject;
CREATE POLICY rls_data_subject_policy ON data_subject FOR ALL USING (true);

-- 3. Application Role Creation & Database Privileges
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'gmh_app_role') THEN
        CREATE ROLE gmh_app_role NOLOGIN;
    END IF;
END
$$;

-- Grant SELECT, INSERT on audit_event to gmh_app_role and explicitly REVOKE UPDATE, DELETE
GRANT SELECT, INSERT ON audit_event TO gmh_app_role;
REVOKE UPDATE, DELETE ON audit_event FROM gmh_app_role;
GRANT USAGE, SELECT ON SEQUENCE audit_event_event_id_seq TO gmh_app_role;

-- Grant standard operational privileges to gmh_app_role on asset & governance tables
GRANT SELECT, INSERT, UPDATE, DELETE ON knowledge_asset, entitlement, approval, identity, data_subject TO gmh_app_role;

-- 4. Enhanced Knowledge Asset State Transition Validation Trigger
CREATE OR REPLACE FUNCTION validate_knowledge_asset_transition()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'UPDATE' THEN
        -- No state change is always valid (e.g. updating non-state columns)
        IF OLD.state = NEW.state THEN
            RETURN NEW;
        END IF;

        -- DRAFT transitions
        IF OLD.state = 'DRAFT' AND NEW.state NOT IN ('PENDING_APPROVAL', 'ARCHIVED') THEN
            RAISE EXCEPTION 'Invalid state transition from % to %.', OLD.state, NEW.state;
        END IF;

        -- PENDING_APPROVAL transitions
        IF OLD.state = 'PENDING_APPROVAL' AND NEW.state NOT IN ('APPROVED', 'REJECTED', 'DRAFT', 'ARCHIVED') THEN
            RAISE EXCEPTION 'Invalid state transition from % to %.', OLD.state, NEW.state;
        END IF;

        -- APPROVED transitions (Can only be retired to ARCHIVED)
        IF OLD.state = 'APPROVED' AND NEW.state NOT IN ('ARCHIVED') THEN
            RAISE EXCEPTION 'Invalid state transition from APPROVED to %. Approved assets must be ARCHIVED for retirement.', NEW.state;
        END IF;

        -- REJECTED transitions
        IF OLD.state = 'REJECTED' AND NEW.state NOT IN ('DRAFT', 'ARCHIVED') THEN
            RAISE EXCEPTION 'Invalid state transition from % to %.', OLD.state, NEW.state;
        END IF;

        -- ARCHIVED transitions (Cannot reactivate without version increment)
        IF OLD.state = 'ARCHIVED' AND NEW.version <= OLD.version THEN
            RAISE EXCEPTION 'Invalid state transition from ARCHIVED to % without incrementing version.', NEW.state;
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_knowledge_asset_transition ON knowledge_asset;
CREATE TRIGGER trg_knowledge_asset_transition
BEFORE UPDATE ON knowledge_asset
FOR EACH ROW EXECUTE FUNCTION validate_knowledge_asset_transition();

-- 5. Asset Retirement Protection Trigger (Prevent physical deletion of approved/archived or legal hold assets)
CREATE OR REPLACE FUNCTION prevent_physical_delete_on_retired_assets()
RETURNS TRIGGER AS $$
BEGIN
    IF OLD.state IN ('APPROVED', 'ARCHIVED') OR OLD.legal_hold = TRUE THEN
        RAISE EXCEPTION 'Physical deletion of approved, archived, or legal-hold assets is prohibited. Assets must be retained for compliance.';
    END IF;
    RETURN OLD;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_prevent_asset_delete ON knowledge_asset;
CREATE TRIGGER trg_prevent_asset_delete
BEFORE DELETE ON knowledge_asset
FOR EACH ROW EXECUTE FUNCTION prevent_physical_delete_on_retired_assets();
