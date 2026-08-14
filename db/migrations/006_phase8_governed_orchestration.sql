-- Phase 8 Migration: Governed Orchestration & Agent Handoffs
-- Governed Memory Hub

-- 1. Orchestration Task Table (8-Stage Governed Lifecycle)
CREATE TABLE IF NOT EXISTS orchestration_task (
    task_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    current_stage VARCHAR(64) NOT NULL DEFAULT 'INTAKE_CLASSIFICATION',
    status VARCHAR(32) NOT NULL DEFAULT 'RUNNING',
    initiator_identity_id UUID REFERENCES identity(identity_id),
    policy_version VARCHAR(32) NOT NULL DEFAULT 'v1.0.0',
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

-- 2. Governed Handoff Table (Decoupled Agent Handoff Proposals & Approvals)
CREATE TABLE IF NOT EXISTS governed_handoff (
    handoff_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id UUID NOT NULL REFERENCES orchestration_task(task_id) ON DELETE CASCADE,
    stage VARCHAR(64) NOT NULL,
    producer_agent_id UUID NOT NULL REFERENCES identity(identity_id),
    consumer_agent_id UUID REFERENCES identity(identity_id),
    proposal_payload_json JSONB NOT NULL,
    payload_hash VARCHAR(64) NOT NULL CHECK (length(payload_hash) = 64),
    approval_id UUID REFERENCES approval(approval_id),
    status VARCHAR(32) NOT NULL DEFAULT 'PENDING_APPROVAL',
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

-- Enable RLS on Phase 8 tables
ALTER TABLE orchestration_task ENABLE ROW LEVEL SECURITY;
ALTER TABLE governed_handoff ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS rls_orchestration_task_policy ON orchestration_task;
CREATE POLICY rls_orchestration_task_policy ON orchestration_task FOR ALL USING (true);

DROP POLICY IF EXISTS rls_governed_handoff_policy ON governed_handoff;
CREATE POLICY rls_governed_handoff_policy ON governed_handoff FOR ALL USING (true);

-- Grant privileges to gmh_app_role
GRANT SELECT, INSERT, UPDATE, DELETE ON orchestration_task TO gmh_app_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON governed_handoff TO gmh_app_role;
