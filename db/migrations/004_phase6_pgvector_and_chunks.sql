-- Phase 6 Migration: Governed Vector Retrieval & Memory
-- Governed Memory Hub

-- 1. Enable pgvector Extension
CREATE EXTENSION IF NOT EXISTS vector;

-- 2. Knowledge Chunk Projection Table
CREATE TABLE IF NOT EXISTS knowledge_chunk (
    chunk_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id UUID NOT NULL REFERENCES knowledge_asset(asset_id) ON DELETE CASCADE,
    chunk_index INT NOT NULL,
    chunk_content TEXT NOT NULL,
    token_count INT NOT NULL DEFAULT 0,
    embedding vector(384),
    embedding_model VARCHAR(64) NOT NULL DEFAULT 'all-MiniLM-L6-v2',
    embedding_version VARCHAR(32) NOT NULL DEFAULT 'v1.0',
    -- Denormalized Governance Access Attributes (Projection from Parent Asset)
    classification VARCHAR(32) NOT NULL,
    barrier_side VARCHAR(32) NOT NULL,
    jurisdiction VARCHAR(32) NOT NULL,
    personal_data BOOLEAN NOT NULL DEFAULT FALSE,
    subject_id UUID REFERENCES data_subject(subject_id),
    asset_state VARCHAR(32) NOT NULL,
    retention_class VARCHAR(64) NOT NULL,
    legal_hold BOOLEAN NOT NULL DEFAULT FALSE,
    access_attr_hash VARCHAR(64) NOT NULL CHECK (length(access_attr_hash) = 64),
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT uq_asset_chunk_index UNIQUE (asset_id, chunk_index)
);

-- 3. HNSW Vector Index for Cosine Distance & GIN Full-Text Index
CREATE INDEX IF NOT EXISTS idx_chunk_embedding_hnsw ON knowledge_chunk USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_chunk_fts ON knowledge_chunk USING gin (to_tsvector('english', chunk_content));
CREATE INDEX IF NOT EXISTS idx_chunk_governance_filter ON knowledge_chunk (asset_state, classification, barrier_side, jurisdiction);

-- Enable RLS on knowledge_chunk
ALTER TABLE knowledge_chunk ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS rls_knowledge_chunk_policy ON knowledge_chunk;
CREATE POLICY rls_knowledge_chunk_policy ON knowledge_chunk FOR ALL USING (true);

-- Grant privileges to gmh_app_role
GRANT SELECT, INSERT, UPDATE, DELETE ON knowledge_chunk TO gmh_app_role;
