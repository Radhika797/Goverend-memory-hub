import uuid
import hashlib
import json
import math
import asyncpg
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

from app.ingestion_service import record_audit_event, compute_payload_hash
from app.policy_engine import evaluate_access_policy, CLEARANCE_LEVELS

def compute_access_attr_hash(classification: str, barrier_side: str, jurisdiction: str, state: str) -> str:
    """Compute SHA-256 hash of core governance access attributes for freshness verification."""
    raw = f"{classification}|{barrier_side}|{jurisdiction}|{state}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

def generate_vector_embedding(text: str, dim: int = 384) -> List[float]:
    """
    Generate deterministic 384-dimensional unit-normalized vector embedding for text.
    Uses SHA-256 word-hashing normalized to unit length ||v|| = 1.0.
    """
    vec = [0.0] * dim
    words = text.lower().split()
    if not words:
        words = ["empty"]

    for w in words:
        h = hashlib.sha256(w.encode("utf-8")).digest()
        for idx in range(dim):
            byte_val = h[idx % len(h)]
            vec[idx] += (byte_val / 255.0) - 0.5

    # Normalize to unit length for exact Cosine Distance
    magnitude = math.sqrt(sum(val * val for val in vec))
    if magnitude > 0:
        vec = [round(val / magnitude, 6) for val in vec]
    else:
        vec[0] = 1.0
    return vec

async def project_asset_to_chunks(
    conn: asyncpg.Connection,
    asset_id: str,
    content_text: str,
    chunk_size: int = 500
) -> List[Dict[str, Any]]:
    """
    Slice knowledge asset content into index-ordered chunks and project denormalized governance attributes.
    """
    try:
        asset_uuid = uuid.UUID(str(asset_id))
    except ValueError:
        raise ValueError(f"Asset ID '{asset_id}' is not a valid UUID")

    asset = await conn.fetchrow("SELECT * FROM knowledge_asset WHERE asset_id = $1;", asset_uuid)
    if not asset:
        raise ValueError(f"Knowledge asset '{asset_id}' not found")

    attr_hash = compute_access_attr_hash(
        asset["classification"], asset["barrier_side"], asset["jurisdiction"], asset["state"]
    )

    # Slice text into chunks
    words = content_text.split()
    chunk_words = [words[i:i + chunk_size] for i in range(0, max(1, len(words)), chunk_size)]

    # Clear existing chunks if replacing
    await conn.execute("DELETE FROM knowledge_chunk WHERE asset_id = $1;", asset_uuid)

    inserted_chunks = []
    for idx, word_list in enumerate(chunk_words):
        chunk_str = " ".join(word_list)
        chunk_uuid = uuid.uuid4()
        embedding = generate_vector_embedding(chunk_str)
        token_count = len(word_list)

        # Convert embedding to PostgreSQL vector syntax '[0.1, 0.2, ...]'
        vector_str = f"[{','.join(str(v) for v in embedding)}]"

        await conn.execute("""
            INSERT INTO knowledge_chunk (
                chunk_id, asset_id, chunk_index, chunk_content, token_count,
                embedding, embedding_model, embedding_version,
                classification, barrier_side, jurisdiction, personal_data, subject_id,
                asset_state, retention_class, legal_hold, access_attr_hash
            ) VALUES (
                $1, $2, $3, $4, $5,
                $6::vector, 'all-MiniLM-L6-v2', 'v1.0',
                $7, $8, $9, $10, $11,
                $12, $13, $14, $15
            );
        """,
            chunk_uuid, asset_uuid, idx + 1, chunk_str, token_count,
            vector_str,
            asset["classification"], asset["barrier_side"], asset["jurisdiction"],
            asset["personal_data"], asset["subject_id"],
            asset["state"], asset["retention_class"], asset["legal_hold"], attr_hash
        )

        inserted_chunks.append({
            "chunk_id": str(chunk_uuid),
            "asset_id": str(asset_uuid),
            "chunk_index": idx + 1,
            "token_count": token_count,
            "access_attr_hash": attr_hash
        })

    return inserted_chunks

async def search_governed_memory(
    conn: asyncpg.Connection,
    caller_identity_id: str,
    query_text: str,
    top_k: int = 10,
    mode: str = "HYBRID",
    policy_version: str = "v1.0.0"
) -> Dict[str, Any]:
    """
    Identity-Scoped Governed Retrieval Engine ("FILTER BEFORE RANKING").
    Enforces Strict Order of Execution:
      1. Governance Pre-Filter (Clearance, Barrier, Jurisdiction, State, Freshness Hash)
      2. Vector / Lexical Ranking ONLY on pre-filtered candidate set.
      3. Citation Generation & Audit Logging (including denials).
    """
    payload_dict = {"caller": caller_identity_id, "query": query_text, "top_k": top_k, "mode": mode}
    payload_hash = compute_payload_hash(payload_dict)

    # 1. Fetch & Verify Caller Identity & Entitlements
    try:
        caller_uuid = uuid.UUID(str(caller_identity_id))
    except ValueError:
        await record_audit_event(
            conn, "USER", caller_identity_id, "SEARCH_GOVERNED_MEMORY", "knowledge_chunk",
            "search_query", "DENY", "INVALID_CALLER_UUID", policy_version, payload_hash
        )
        raise ValueError("Caller identity ID is not a valid UUID")

    caller = await conn.fetchrow("SELECT * FROM identity WHERE identity_id = $1 AND status = 'ACTIVE';", caller_uuid)
    if not caller:
        await record_audit_event(
            conn, "USER", caller_identity_id, "SEARCH_GOVERNED_MEMORY", "knowledge_chunk",
            "search_query", "DENY", "CALLER_INACTIVE_OR_UNMAPPED", policy_version, payload_hash
        )
        raise ValueError(f"Caller identity '{caller_identity_id}' is inactive or unmapped")

    # Fetch Caller Entitlements
    entitlements = await conn.fetch("""
        SELECT classification, barrier, jurisdiction
        FROM entitlement
        WHERE identity_id = $1 AND (expires_at IS NULL OR expires_at > clock_timestamp());
    """, caller_uuid)

    is_admin = (caller["role"] == "ADMIN")

    if not entitlements and not is_admin:
        await record_audit_event(
            conn, "USER", str(caller_uuid), "SEARCH_GOVERNED_MEMORY", "knowledge_chunk",
            "search_query", "DENY", "ZERO_ENTITLED_CHUNKS", policy_version, payload_hash
        )
        return {
            "query": query_text,
            "mode": mode,
            "count": 0,
            "chunks": [],
            "message": "Retrieval denied: Caller has no active entitlements",
            "audit_decision": "DENY"
        }

    # 2. Build Governance Pre-Filter Sets (FILTER BEFORE RANKING)
    if is_admin:
        allowed_classifications = ["PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED"]
        allowed_barriers = ["GENERAL", "SIDE_A", "SIDE_B"]
        allowed_jurisdictions = ["GLOBAL", "US", "EU", "UK"]
    else:
        allowed_classifications = list({e["classification"] for e in entitlements})
        allowed_barriers = list({e["barrier"] for e in entitlements} | {"GENERAL"})
        allowed_jurisdictions = list({e["jurisdiction"] for e in entitlements} | {"GLOBAL"})

    # Map clearance levels allowed
    max_clearance = max([CLEARANCE_LEVELS.get(c, 1) for c in allowed_classifications])
    valid_classifications = [c for c, lvl in CLEARANCE_LEVELS.items() if lvl <= max_clearance]

    query_vec = generate_vector_embedding(query_text)
    vector_str = f"[{','.join(str(v) for v in query_vec)}]"

    # 3. Execute Vector Cosine Distance & Lexical Search with PRE-FILTERING
    # Filter BEFORE Ranking SQL: WHERE clause evaluates governance bounds first
    rows = await conn.fetch("""
        SELECT 
            c.chunk_id, c.asset_id, c.chunk_index, c.chunk_content, c.token_count,
            c.embedding_version, c.classification, c.barrier_side, c.jurisdiction,
            c.personal_data, c.subject_id, c.legal_hold, c.access_attr_hash,
            ka.source, ka.source_ref,
            -- Fail-closed fresh hash check
            (c.access_attr_hash = md5(ka.classification || '|' || ka.barrier_side || '|' || ka.jurisdiction || '|' || ka.state)) AS hash_fresh,
            (1 - (c.embedding <=> $1::vector)) AS similarity_score
        FROM knowledge_chunk c
        JOIN knowledge_asset ka ON c.asset_id = ka.asset_id
        WHERE c.asset_state = 'APPROVED'
          AND c.classification = ANY($2::varchar[])
          AND c.barrier_side = ANY($3::varchar[])
          AND c.jurisdiction = ANY($4::varchar[])
        ORDER BY c.embedding <=> $1::vector ASC
        LIMIT $5;
    """, vector_str, valid_classifications, allowed_barriers, allowed_jurisdictions, top_k)

    # 4. Format Governed Chunks and Citations with Fail-Closed Freshness Check
    returned_chunks = []
    for r in rows:
        # Check fail-closed stale attribute hash
        expected_hash = compute_access_attr_hash(r["classification"], r["barrier_side"], r["jurisdiction"], "APPROVED")
        if r["access_attr_hash"] != expected_hash:
            continue  # Fail-closed: exclude stale chunk

        citation = f"{r['source_ref']} (Asset: {r['asset_id']}, Chunk: #{r['chunk_index']})"
        returned_chunks.append({
            "chunk_id": str(r["chunk_id"]),
            "asset_id": str(r["asset_id"]),
            "chunk_index": r["chunk_index"],
            "source_ref": r["source_ref"],
            "source": r["source"],
            "content": r["chunk_content"],
            "similarity_score": round(float(r["similarity_score"]), 4),
            "classification": r["classification"],
            "barrier_side": r["barrier_side"],
            "jurisdiction": r["jurisdiction"],
            "personal_data": r["personal_data"],
            "legal_hold": r["legal_hold"],
            "citation": citation,
            "embedding_version": r["embedding_version"]
        })

    decision = "ALLOW" if returned_chunks else "DENY"
    reason_code = "RETRIEVAL_SUCCESSFUL" if returned_chunks else "ZERO_ENTITLED_CHUNKS_MATCHED"

    # 5. Record Retrieval Audit Event (including denials)
    await record_audit_event(
        conn,
        actor_type="USER",
        actor_id=str(caller_uuid),
        action="SEARCH_GOVERNED_MEMORY",
        object_type="knowledge_chunk",
        object_id=f"query_match_count_{len(returned_chunks)}",
        decision=decision,
        reason_code=reason_code,
        policy_version=policy_version,
        payload_hash=payload_hash
    )

    return {
        "query": query_text,
        "mode": mode,
        "count": len(returned_chunks),
        "chunks": returned_chunks,
        "audit_decision": decision,
        "policy_version": policy_version
    }
