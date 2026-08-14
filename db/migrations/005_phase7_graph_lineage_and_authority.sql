-- Phase 7 Migration: Graph / Lineage / Authority Memory
-- Governed Memory Hub

-- 1. Graph Node Table
CREATE TABLE IF NOT EXISTS graph_node (
    node_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    node_type VARCHAR(32) NOT NULL,
    object_ref_id UUID NOT NULL,
    label VARCHAR(255) NOT NULL,
    classification VARCHAR(32) NOT NULL,
    barrier_side VARCHAR(32) NOT NULL,
    jurisdiction VARCHAR(32) NOT NULL,
    asset_state VARCHAR(32) NOT NULL DEFAULT 'APPROVED',
    node_attr_hash VARCHAR(64) NOT NULL CHECK (length(node_attr_hash) = 64),
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT uq_graph_node_object UNIQUE (node_type, object_ref_id)
);

-- 2. Graph Edge Table
CREATE TABLE IF NOT EXISTS graph_edge (
    edge_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_node_id UUID NOT NULL REFERENCES graph_node(node_id) ON DELETE CASCADE,
    target_node_id UUID NOT NULL REFERENCES graph_node(node_id) ON DELETE CASCADE,
    relation_type VARCHAR(32) NOT NULL,
    classification VARCHAR(32) NOT NULL,
    barrier_side VARCHAR(32) NOT NULL,
    jurisdiction VARCHAR(32) NOT NULL,
    edge_attr_hash VARCHAR(64) NOT NULL CHECK (length(edge_attr_hash) = 64),
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT uq_graph_edge_triple UNIQUE (source_node_id, target_node_id, relation_type)
);

-- Indexes for Hop-by-Hop Traversal Performance
CREATE INDEX IF NOT EXISTS idx_graph_edge_source ON graph_edge (source_node_id, relation_type);
CREATE INDEX IF NOT EXISTS idx_graph_edge_target ON graph_edge (target_node_id, relation_type);
CREATE INDEX IF NOT EXISTS idx_graph_node_governance ON graph_node (asset_state, classification, barrier_side, jurisdiction);

-- Enable RLS on Phase 7 tables
ALTER TABLE graph_node ENABLE ROW LEVEL SECURITY;
ALTER TABLE graph_edge ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS rls_graph_node_policy ON graph_node;
CREATE POLICY rls_graph_node_policy ON graph_node FOR ALL USING (true);

DROP POLICY IF EXISTS rls_graph_edge_policy ON graph_edge;
CREATE POLICY rls_graph_edge_policy ON graph_edge FOR ALL USING (true);

-- Grant privileges to gmh_app_role
GRANT SELECT, INSERT, UPDATE, DELETE ON graph_node TO gmh_app_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON graph_edge TO gmh_app_role;
