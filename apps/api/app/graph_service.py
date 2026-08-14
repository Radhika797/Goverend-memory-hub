import uuid
import hashlib
import json
import asyncpg
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

from app.ingestion_service import record_audit_event, compute_payload_hash
from app.policy_engine import CLEARANCE_LEVELS

def compute_node_attr_hash(node_type: str, object_ref_id: str, classification: str, barrier_side: str, jurisdiction: str, state: str) -> str:
    """Compute SHA-256 hash of core node governance attributes for freshness verification."""
    raw = f"{node_type}|{object_ref_id}|{classification}|{barrier_side}|{jurisdiction}|{state}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

async def project_graph_from_postgres(conn: asyncpg.Connection) -> Dict[str, int]:
    """
    Idempotently project authoritative PostgreSQL tables (identities, assets, chunks, approvals, entitlements, data subjects)
    into graph nodes and relationship edges.
    """
    # 1. Project Identity Nodes
    identities = await conn.fetch("SELECT identity_id, name, department, role FROM identity;")
    for i in identities:
        iid = str(i["identity_id"])
        h = compute_node_attr_hash("IDENTITY", iid, "PUBLIC", "GENERAL", "GLOBAL", "ACTIVE")
        await conn.execute("""
            INSERT INTO graph_node (node_type, object_ref_id, label, classification, barrier_side, jurisdiction, asset_state, node_attr_hash)
            VALUES ('IDENTITY', $1, $2, 'PUBLIC', 'GENERAL', 'GLOBAL', 'ACTIVE', $3)
            ON CONFLICT (node_type, object_ref_id) DO UPDATE SET
                label = EXCLUDED.label, node_attr_hash = EXCLUDED.node_attr_hash;
        """, i["identity_id"], f"{i['name']} ({i['department']})", h)

    # 2. Project Data Subject Nodes
    subjects = await conn.fetch("SELECT subject_id, subject_ref, jurisdiction FROM data_subject;")
    for s in subjects:
        sid = str(s["subject_id"])
        h = compute_node_attr_hash("DATA_SUBJECT", sid, "CONFIDENTIAL", "GENERAL", s["jurisdiction"], "ACTIVE")
        await conn.execute("""
            INSERT INTO graph_node (node_type, object_ref_id, label, classification, barrier_side, jurisdiction, asset_state, node_attr_hash)
            VALUES ('DATA_SUBJECT', $1, $2, 'CONFIDENTIAL', 'GENERAL', $3, 'ACTIVE', $4)
            ON CONFLICT (node_type, object_ref_id) DO UPDATE SET
                label = EXCLUDED.label, jurisdiction = EXCLUDED.jurisdiction, node_attr_hash = EXCLUDED.node_attr_hash;
        """, s["subject_id"], s["subject_ref"], s["jurisdiction"], h)

    # 3. Project Approval Nodes
    approvals = await conn.fetch("SELECT approval_id, approver_id, object_id, status FROM approval;")
    for a in approvals:
        apid = str(a["approval_id"])
        h = compute_node_attr_hash("APPROVAL", apid, "PUBLIC", "GENERAL", "GLOBAL", a["status"])
        await conn.execute("""
            INSERT INTO graph_node (node_type, object_ref_id, label, classification, barrier_side, jurisdiction, asset_state, node_attr_hash)
            VALUES ('APPROVAL', $1, $2, 'PUBLIC', 'GENERAL', 'GLOBAL', $3, $4)
            ON CONFLICT (node_type, object_ref_id) DO UPDATE SET
                label = EXCLUDED.label, asset_state = EXCLUDED.asset_state, node_attr_hash = EXCLUDED.node_attr_hash;
        """, a["approval_id"], f"Approval {apid[:8]} ({a['status']})", a["status"], h)

    # 4. Project Knowledge Asset Nodes
    assets = await conn.fetch("SELECT asset_id, source_ref, classification, barrier_side, jurisdiction, state, supersession_id, steward_id, approval_id, subject_id FROM knowledge_asset;")
    for ka in assets:
        kaid = str(ka["asset_id"])
        h = compute_node_attr_hash("KNOWLEDGE_ASSET", kaid, ka["classification"], ka["barrier_side"], ka["jurisdiction"], ka["state"])
        await conn.execute("""
            INSERT INTO graph_node (node_type, object_ref_id, label, classification, barrier_side, jurisdiction, asset_state, node_attr_hash)
            VALUES ('KNOWLEDGE_ASSET', $1, $2, $3, $4, $5, $6, $7)
            ON CONFLICT (node_type, object_ref_id) DO UPDATE SET
                label = EXCLUDED.label, classification = EXCLUDED.classification, barrier_side = EXCLUDED.barrier_side,
                jurisdiction = EXCLUDED.jurisdiction, asset_state = EXCLUDED.asset_state, node_attr_hash = EXCLUDED.node_attr_hash;
        """, ka["asset_id"], f"Asset {ka['source_ref']}", ka["classification"], ka["barrier_side"], ka["jurisdiction"], ka["state"], h)

    # 5. Project Knowledge Chunk Nodes
    chunks = await conn.fetch("SELECT chunk_id, asset_id, chunk_index, classification, barrier_side, jurisdiction, asset_state, access_attr_hash FROM knowledge_chunk;")
    for ch in chunks:
        chid = str(ch["chunk_id"])
        h = compute_node_attr_hash("KNOWLEDGE_CHUNK", chid, ch["classification"], ch["barrier_side"], ch["jurisdiction"], ch["asset_state"])
        await conn.execute("""
            INSERT INTO graph_node (node_type, object_ref_id, label, classification, barrier_side, jurisdiction, asset_state, node_attr_hash)
            VALUES ('KNOWLEDGE_CHUNK', $1, $2, $3, $4, $5, $6, $7)
            ON CONFLICT (node_type, object_ref_id) DO UPDATE SET
                label = EXCLUDED.label, classification = EXCLUDED.classification, barrier_side = EXCLUDED.barrier_side,
                jurisdiction = EXCLUDED.jurisdiction, asset_state = EXCLUDED.asset_state, node_attr_hash = EXCLUDED.node_attr_hash;
        """, ch["chunk_id"], f"Chunk #{ch['chunk_index']} of Asset {str(ch['asset_id'])[:8]}", ch["classification"], ch["barrier_side"], ch["jurisdiction"], ch["asset_state"], h)

    # 6. Project Edges (Relationships)
    # A. Chunk -> DERIVED_FROM -> Asset
    await conn.execute("""
        INSERT INTO graph_edge (source_node_id, target_node_id, relation_type, classification, barrier_side, jurisdiction, edge_attr_hash)
        SELECT 
            cn.node_id, an.node_id, 'DERIVED_FROM', cn.classification, cn.barrier_side, cn.jurisdiction, cn.node_attr_hash
        FROM knowledge_chunk c
        JOIN graph_node cn ON cn.node_type = 'KNOWLEDGE_CHUNK' AND cn.object_ref_id = c.chunk_id
        JOIN graph_node an ON an.node_type = 'KNOWLEDGE_ASSET' AND an.object_ref_id = c.asset_id
        ON CONFLICT (source_node_id, target_node_id, relation_type) DO UPDATE SET
            classification = EXCLUDED.classification, barrier_side = EXCLUDED.barrier_side, jurisdiction = EXCLUDED.jurisdiction;
    """)

    # B. Asset -> SUPERSEDES -> Asset (Version Chains)
    await conn.execute("""
        INSERT INTO graph_edge (source_node_id, target_node_id, relation_type, classification, barrier_side, jurisdiction, edge_attr_hash)
        SELECT 
            an_curr.node_id, an_prev.node_id, 'SUPERSEDES', an_curr.classification, an_curr.barrier_side, an_curr.jurisdiction, an_curr.node_attr_hash
        FROM knowledge_asset ka
        JOIN graph_node an_curr ON an_curr.node_type = 'KNOWLEDGE_ASSET' AND an_curr.object_ref_id = ka.asset_id
        JOIN graph_node an_prev ON an_prev.node_type = 'KNOWLEDGE_ASSET' AND an_prev.object_ref_id = ka.supersession_id
        WHERE ka.supersession_id IS NOT NULL
        ON CONFLICT (source_node_id, target_node_id, relation_type) DO UPDATE SET
            classification = EXCLUDED.classification, barrier_side = EXCLUDED.barrier_side, jurisdiction = EXCLUDED.jurisdiction;
    """)

    # C. Asset -> STEWARDED_BY -> Identity
    await conn.execute("""
        INSERT INTO graph_edge (source_node_id, target_node_id, relation_type, classification, barrier_side, jurisdiction, edge_attr_hash)
        SELECT 
            an.node_id, idn.node_id, 'STEWARDED_BY', an.classification, an.barrier_side, an.jurisdiction, an.node_attr_hash
        FROM knowledge_asset ka
        JOIN graph_node an ON an.node_type = 'KNOWLEDGE_ASSET' AND an.object_ref_id = ka.asset_id
        JOIN graph_node idn ON idn.node_type = 'IDENTITY' AND idn.object_ref_id = ka.steward_id
        ON CONFLICT (source_node_id, target_node_id, relation_type) DO UPDATE SET
            classification = EXCLUDED.classification, barrier_side = EXCLUDED.barrier_side, jurisdiction = EXCLUDED.jurisdiction;
    """)

    # D. Asset -> APPROVED_BY -> Approval
    await conn.execute("""
        INSERT INTO graph_edge (source_node_id, target_node_id, relation_type, classification, barrier_side, jurisdiction, edge_attr_hash)
        SELECT 
            an.node_id, apn.node_id, 'APPROVED_BY', an.classification, an.barrier_side, an.jurisdiction, an.node_attr_hash
        FROM knowledge_asset ka
        JOIN graph_node an ON an.node_type = 'KNOWLEDGE_ASSET' AND an.object_ref_id = ka.asset_id
        JOIN graph_node apn ON apn.node_type = 'APPROVAL' AND apn.object_ref_id = ka.approval_id
        WHERE ka.approval_id IS NOT NULL
        ON CONFLICT (source_node_id, target_node_id, relation_type) DO UPDATE SET
            classification = EXCLUDED.classification, barrier_side = EXCLUDED.barrier_side, jurisdiction = EXCLUDED.jurisdiction;
    """)

    # E. Asset -> SUBJECT_OF -> Data Subject
    await conn.execute("""
        INSERT INTO graph_edge (source_node_id, target_node_id, relation_type, classification, barrier_side, jurisdiction, edge_attr_hash)
        SELECT 
            an.node_id, sn.node_id, 'SUBJECT_OF', an.classification, an.barrier_side, an.jurisdiction, an.node_attr_hash
        FROM knowledge_asset ka
        JOIN graph_node an ON an.node_type = 'KNOWLEDGE_ASSET' AND an.object_ref_id = ka.asset_id
        JOIN graph_node sn ON sn.node_type = 'DATA_SUBJECT' AND sn.object_ref_id = ka.subject_id
        WHERE ka.subject_id IS NOT NULL
        ON CONFLICT (source_node_id, target_node_id, relation_type) DO UPDATE SET
            classification = EXCLUDED.classification, barrier_side = EXCLUDED.barrier_side, jurisdiction = EXCLUDED.jurisdiction;
    """)

    node_cnt = await conn.fetchval("SELECT COUNT(*) FROM graph_node;")
    edge_cnt = await conn.fetchval("SELECT COUNT(*) FROM graph_edge;")

    return {"nodes": node_cnt, "edges": edge_cnt}


async def traverse_governed_graph(
    conn: asyncpg.Connection,
    caller_identity_id: str,
    start_object_id: str,
    max_depth: int = 3,
    relation_filter: Optional[List[str]] = None,
    policy_version: str = "v1.0.0"
) -> Dict[str, Any]:
    """
    Identity & Policy-Scoped Recursive Graph Traversal Engine ("HOP-BY-HOP GOVERNANCE FILTER").
    Enforces clearance level, information barrier wall, and jurisdiction pre-filtering on EVERY hop step.
    Nodes/edges crossing unauthorized boundaries are NEVER expanded or returned.
    """
    payload_dict = {"caller": caller_identity_id, "start_object": start_object_id, "max_depth": max_depth, "relations": relation_filter}
    payload_hash = compute_payload_hash(payload_dict)

    # 1. Fetch Caller Identity & Entitlements
    try:
        caller_uuid = uuid.UUID(str(caller_identity_id))
    except ValueError:
        await record_audit_event(
            conn, "USER", caller_identity_id, "TRAVERSE_GOVERNED_GRAPH", "graph_node",
            start_object_id, "DENY", "INVALID_CALLER_UUID", policy_version, payload_hash
        )
        raise ValueError("Caller identity ID is not a valid UUID")

    caller = await conn.fetchrow("SELECT * FROM identity WHERE identity_id = $1 AND status = 'ACTIVE';", caller_uuid)
    if not caller:
        await record_audit_event(
            conn, "USER", caller_identity_id, "TRAVERSE_GOVERNED_GRAPH", "graph_node",
            start_object_id, "DENY", "CALLER_INACTIVE_OR_UNMAPPED", policy_version, payload_hash
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
            conn, "USER", str(caller_uuid), "TRAVERSE_GOVERNED_GRAPH", "graph_node",
            start_object_id, "DENY", "ZERO_ENTITLED_NODES", policy_version, payload_hash
        )
        return {
            "start_object_id": start_object_id,
            "max_depth": max_depth,
            "nodes": [],
            "edges": [],
            "nodes_count": 0,
            "edges_count": 0,
            "audit_decision": "DENY",
            "message": "Graph traversal denied: Caller has no active entitlements"
        }

    # 2. Build Governance Pre-Filter Bounds
    if is_admin:
        allowed_classifications = ["PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED"]
        allowed_barriers = ["GENERAL", "SIDE_A", "SIDE_B"]
        allowed_jurisdictions = ["GLOBAL", "US", "EU", "UK"]
    else:
        allowed_classifications = list({e["classification"] for e in entitlements})
        allowed_barriers = list({e["barrier"] for e in entitlements} | {"GENERAL"})
        allowed_jurisdictions = list({e["jurisdiction"] for e in entitlements} | {"GLOBAL"})
        if "GLOBAL" in allowed_jurisdictions:
            allowed_jurisdictions = ["GLOBAL", "US", "EU", "UK"]

    max_clearance = max([CLEARANCE_LEVELS.get(c, 1) for c in allowed_classifications])
    valid_classifications = [c for c, lvl in CLEARANCE_LEVELS.items() if lvl <= max_clearance]

    # Resolve Start Node
    try:
        start_uuid = uuid.UUID(str(start_object_id))
    except ValueError:
        raise ValueError(f"Start object ID '{start_object_id}' is not a valid UUID")

    start_node = await conn.fetchrow("SELECT * FROM graph_node WHERE object_ref_id = $1 OR node_id = $1;", start_uuid)
    if not start_node:
        await record_audit_event(
            conn, "USER", str(caller_uuid), "TRAVERSE_GOVERNED_GRAPH", "graph_node",
            start_object_id, "DENY", "START_NODE_NOT_FOUND", policy_version, payload_hash
        )
        return {
            "start_object_id": start_object_id,
            "max_depth": max_depth,
            "nodes": [],
            "edges": [],
            "nodes_count": 0,
            "edges_count": 0,
            "audit_decision": "DENY",
            "message": f"Start node '{start_object_id}' not found"
        }

    # Verify Start Node Clearance
    start_class_lvl = CLEARANCE_LEVELS.get(start_node["classification"], 4)
    if not is_admin:
        if start_class_lvl > max_clearance or (start_node["barrier_side"] != "GENERAL" and start_node["barrier_side"] not in allowed_barriers):
            await record_audit_event(
                conn, "USER", str(caller_uuid), "TRAVERSE_GOVERNED_GRAPH", "graph_node",
                start_object_id, "DENY", "START_NODE_BARRIER_VIOLATION", policy_version, payload_hash
            )
            return {
                "start_object_id": start_object_id,
                "max_depth": max_depth,
                "nodes": [],
                "edges": [],
                "nodes_count": 0,
                "edges_count": 0,
                "audit_decision": "DENY",
                "message": "Start node violates caller information barrier or clearance level"
            }

    # 3. Recursive Governed Hop-by-Hop Traversal Query
    # SQL WITH RECURSIVE checks governance bounds on EVERY hop
    nodes_rows = await conn.fetch("""
        WITH RECURSIVE governed_path AS (
            -- Base Hop (Start Node)
            SELECT n.node_id, n.node_type, n.object_ref_id, n.label, n.classification, n.barrier_side, n.jurisdiction, n.asset_state, n.node_attr_hash, 1 AS depth
            FROM graph_node n
            WHERE n.node_id = $1
              AND n.classification = ANY($2::varchar[])
              AND n.barrier_side = ANY($3::varchar[])
              AND n.jurisdiction = ANY($4::varchar[])

            UNION DISTINCT

            -- Recursive Hop Step (Enforces Governance Bounds on Target Node)
            SELECT target.node_id, target.node_type, target.object_ref_id, target.label, target.classification, target.barrier_side, target.jurisdiction, target.asset_state, target.node_attr_hash, p.depth + 1
            FROM governed_path p
            JOIN graph_edge e ON p.node_id = e.source_node_id OR p.node_id = e.target_node_id
            JOIN graph_node target ON (target.node_id = e.target_node_id OR target.node_id = e.source_node_id) AND target.node_id != p.node_id
            WHERE p.depth < $5
              AND target.classification = ANY($2::varchar[])
              AND target.barrier_side = ANY($3::varchar[])
              AND target.jurisdiction = ANY($4::varchar[])
        )
        SELECT DISTINCT node_id, node_type, object_ref_id, label, classification, barrier_side, jurisdiction, asset_state, node_attr_hash, depth
        FROM governed_path;
    """, start_node["node_id"], valid_classifications, allowed_barriers, allowed_jurisdictions, max_depth)

    # Fail-Closed Stale Attribute Check on Returned Nodes
    valid_nodes = []
    valid_node_ids = set()
    for n in nodes_rows:
        expected_hash = compute_node_attr_hash(n["node_type"], str(n["object_ref_id"]), n["classification"], n["barrier_side"], n["jurisdiction"], n["asset_state"])
        if n["node_attr_hash"] != expected_hash:
            continue  # Fail-closed: exclude stale node

        valid_nodes.append({
            "node_id": str(n["node_id"]),
            "node_type": n["node_type"],
            "object_ref_id": str(n["object_ref_id"]),
            "label": n["label"],
            "classification": n["classification"],
            "barrier_side": n["barrier_side"],
            "jurisdiction": n["jurisdiction"],
            "depth": n["depth"]
        })
        valid_node_ids.add(n["node_id"])

    # Fetch Edges Connecting Valid Nodes
    edge_rows = await conn.fetch("""
        SELECT e.edge_id, e.source_node_id, e.target_node_id, e.relation_type, e.classification, e.barrier_side, e.jurisdiction
        FROM graph_edge e
        WHERE e.source_node_id = ANY($1::uuid[]) AND e.target_node_id = ANY($1::uuid[])
          AND e.classification = ANY($2::varchar[])
          AND e.barrier_side = ANY($3::varchar[])
          AND e.jurisdiction = ANY($4::varchar[]);
    """, list(valid_node_ids) if valid_node_ids else [uuid.uuid4()], valid_classifications, allowed_barriers, allowed_jurisdictions)

    valid_edges = []
    for e in edge_rows:
        valid_edges.append({
            "edge_id": str(e["edge_id"]),
            "source_node_id": str(e["source_node_id"]),
            "target_node_id": str(e["target_node_id"]),
            "relation_type": e["relation_type"],
            "classification": e["classification"],
            "barrier_side": e["barrier_side"]
        })

    decision = "ALLOW" if valid_nodes else "DENY"
    reason_code = "GRAPH_TRAVERSAL_SUCCESSFUL" if valid_nodes else "GOVERNANCE_BOUNDS_RESTRICTED_GRAPH"

    # Audit Traversal Event
    await record_audit_event(
        conn,
        actor_type="USER",
        actor_id=str(caller_uuid),
        action="TRAVERSE_GOVERNED_GRAPH",
        object_type="graph_node",
        object_id=str(start_node["node_id"]),
        decision=decision,
        reason_code=reason_code,
        policy_version=policy_version,
        payload_hash=payload_hash
    )

    return {
        "start_object_id": start_object_id,
        "max_depth": max_depth,
        "nodes_count": len(valid_nodes),
        "edges_count": len(valid_edges),
        "nodes": valid_nodes,
        "edges": valid_edges,
        "audit_decision": decision,
        "policy_version": policy_version
    }
