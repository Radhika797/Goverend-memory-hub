-- Phase 10 Migration: Control Cockpit & Observability Baselines
-- Governed Memory Hub

-- 1. Cockpit Baseline Table (Week-One Governance Baselines)
CREATE TABLE IF NOT EXISTS cockpit_baseline (
    baseline_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    metric_name VARCHAR(128) NOT NULL UNIQUE,
    baseline_value NUMERIC NOT NULL,
    unit VARCHAR(32) NOT NULL,
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

-- Seed Week-One Governance Baselines
INSERT INTO cockpit_baseline (metric_name, baseline_value, unit, description) VALUES
    ('spend_vs_budget_usd', 1250.00, 'USD', 'Initial week-one budget allocation'),
    ('tollgate_cycle_time_sec', 45.0, 'SECONDS', 'Baseline human steward tollgate approval cycle time'),
    ('human_override_rate_pct', 2.5, 'PERCENT', 'Baseline human steward rejection/override rate'),
    ('exceptions_count', 0.0, 'COUNT', 'Baseline unresolved escalated exceptions'),
    ('agent_first_pass_rate_pct', 95.0, 'PERCENT', 'Baseline agent first-pass task completion rate'),
    ('retrieval_accuracy_pct', 98.5, 'PERCENT', 'Baseline retrieval precision against labelled set'),
    ('decision_traceability_pct', 100.0, 'PERCENT', 'Baseline audit log decision traceability coverage'),
    ('policy_denial_rate_pct', 4.2, 'PERCENT', 'Baseline policy evaluation denial rate'),
    ('reconciliation_drift_count', 0.0, 'COUNT', 'Baseline relational/vector/graph entity drift count'),
    ('embedding_version_coverage_pct', 100.0, 'PERCENT', 'Baseline coverage of bge-small-en-v1.5 embeddings'),
    ('avg_stage_token_consumption', 1200.0, 'TOKENS', 'Baseline average token spend per stage')
ON CONFLICT (metric_name) DO UPDATE SET
    baseline_value = EXCLUDED.baseline_value,
    unit = EXCLUDED.unit;

-- Enable RLS on Phase 10 table
ALTER TABLE cockpit_baseline ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS rls_cockpit_baseline_policy ON cockpit_baseline;
CREATE POLICY rls_cockpit_baseline_policy ON cockpit_baseline FOR ALL USING (true);

-- Grant privileges to gmh_app_role
GRANT SELECT, INSERT, UPDATE, DELETE ON cockpit_baseline TO gmh_app_role;
