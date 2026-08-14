-- Phase 10 Migration: Labelled Synthetic Retrieval Benchmark Set
-- Governed Memory Hub

CREATE TABLE IF NOT EXISTS labelled_retrieval_benchmark (
    benchmark_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    query_text TEXT NOT NULL,
    identity_username VARCHAR(128) NOT NULL,
    expected_barrier_side VARCHAR(32) NOT NULL,
    expected_classification VARCHAR(32) NOT NULL,
    should_allow BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

-- Seed Labelled Synthetic Retrieval Benchmark Queries
INSERT INTO labelled_retrieval_benchmark (query_text, identity_username, expected_barrier_side, expected_classification, should_allow) VALUES
    ('restricted deal information', 'a.okafor@northwind.com', 'SIDE_A', 'RESTRICTED', true),
    ('restricted deal information', 'm.rhee@northwind.com', 'SIDE_B', 'RESTRICTED', false),
    ('unpublished equity research notes', 'diana.sterling@northwind.com', 'SIDE_A', 'CONFIDENTIAL', true),
    ('core architecture guidelines', 'john.doe@northwind.com', 'PUBLIC', 'INTERNAL', true),
    ('personal identity privacy metadata', 'edward.sterling@northwind.com', 'SIDE_B', 'RESTRICTED', false)
ON CONFLICT DO NOTHING;

-- Enable RLS
ALTER TABLE labelled_retrieval_benchmark ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS rls_labelled_retrieval_benchmark_policy ON labelled_retrieval_benchmark;
CREATE POLICY rls_labelled_retrieval_benchmark_policy ON labelled_retrieval_benchmark FOR ALL USING (true);

-- Grant privileges
GRANT SELECT, INSERT, UPDATE, DELETE ON labelled_retrieval_benchmark TO gmh_app_role;
