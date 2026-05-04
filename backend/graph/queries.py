"""Cypher query library — all graph intelligence lives here."""
from __future__ import annotations

import json
from typing import Any

from .client import Neo4jClient


class CyclicGraphError(Exception):
    """Raised when a pipeline DAG has at least one cycle."""


# ── DAG retrieval ──────────────────────────────────────────────────────────


def get_pipeline_dag(client: Neo4jClient, pipeline_id: str) -> dict[str, Any]:
    """Return ``{nodes: [...], edges: [...], params: {...}}``."""
    nodes_raw = client.run(
        """
        MATCH (p:Pipeline {id: $pid})-[:HAS_COMPONENT]->(c:Component)
        OPTIONAL MATCH (c)-[:USES_SCHEMA]->(s:Schema)
        RETURN c.id AS id, c.name AS name, c.type AS type,
               c.properties AS properties,
               c.input_ports AS input_ports,
               c.output_ports AS output_ports,
               s.fields AS schema_json,
               s.name AS schema_name
        """,
        pid=pipeline_id,
    )
    edges_raw = client.run(
        """
        MATCH (p:Pipeline {id: $pid})-[:HAS_COMPONENT]->(a:Component)
        MATCH (a)-[r:FLOWS_TO]->(b:Component)
        WHERE (p)-[:HAS_COMPONENT]->(b)
        RETURN a.id AS from_id, b.id AS to_id,
               r.from_port AS from_port, r.to_port AS to_port
        """,
        pid=pipeline_id,
    )
    params_rows = client.run(
        "MATCH (p:Pipeline {id: $pid}) RETURN p.params AS params, p.name AS name",
        pid=pipeline_id,
    )
    params = json.loads(params_rows[0]["params"]) if params_rows and params_rows[0].get("params") else {}
    pipeline_name = params_rows[0]["name"] if params_rows else pipeline_id

    nodes: list[dict[str, Any]] = []
    for n in nodes_raw:
        nodes.append({
            "id": n["id"],
            "name": n["name"],
            "type": n["type"],
            "properties": json.loads(n["properties"]) if n["properties"] else {},
            "input_ports": json.loads(n["input_ports"]) if n["input_ports"] else {},
            "output_ports": json.loads(n["output_ports"]) if n["output_ports"] else [],
            "schema": json.loads(n["schema_json"]) if n["schema_json"] else None,
            "schema_name": n.get("schema_name"),
        })

    edges = [
        {
            "from": e["from_id"],
            "to": e["to_id"],
            "from_port": e["from_port"] or "out",
            "to_port": e["to_port"] or "in",
        }
        for e in edges_raw
    ]
    return {"nodes": nodes, "edges": edges, "params": params, "pipeline_name": pipeline_name}


# ── ordering / validation ──────────────────────────────────────────────────


def get_execution_order(client: Neo4jClient, pipeline_id: str) -> list[dict[str, Any]]:
    if detect_cycles(client, pipeline_id):
        raise CyclicGraphError(f"Pipeline {pipeline_id} contains a cycle")

    dag = get_pipeline_dag(client, pipeline_id)
    nodes_by_id = {n["id"]: n for n in dag["nodes"]}
    indeg = {nid: 0 for nid in nodes_by_id}
    adj: dict[str, list[str]] = {nid: [] for nid in nodes_by_id}
    for e in dag["edges"]:
        if e["from"] in nodes_by_id and e["to"] in nodes_by_id:
            adj[e["from"]].append(e["to"])
            indeg[e["to"]] += 1

    queue = [nid for nid, d in indeg.items() if d == 0]
    ordered: list[dict[str, Any]] = []
    while queue:
        queue.sort()
        nid = queue.pop(0)
        ordered.append(nodes_by_id[nid])
        for nxt in adj[nid]:
            indeg[nxt] -= 1
            if indeg[nxt] == 0:
                queue.append(nxt)
    if len(ordered) != len(nodes_by_id):
        raise CyclicGraphError(f"Pipeline {pipeline_id} contains a cycle")
    return ordered


def get_root_nodes(client: Neo4jClient, pipeline_id: str) -> list[dict[str, Any]]:
    return client.run(
        """
        MATCH (p:Pipeline {id: $pid})-[:HAS_COMPONENT]->(c:Component)
        WHERE NOT EXISTS { MATCH (other:Component)-[:FLOWS_TO]->(c) }
        RETURN c.id AS id, c.name AS name, c.type AS type
        """,
        pid=pipeline_id,
    )


def get_leaf_nodes(client: Neo4jClient, pipeline_id: str) -> list[dict[str, Any]]:
    return client.run(
        """
        MATCH (p:Pipeline {id: $pid})-[:HAS_COMPONENT]->(c:Component)
        WHERE NOT EXISTS { MATCH (c)-[:FLOWS_TO]->(other:Component) }
        RETURN c.id AS id, c.name AS name, c.type AS type
        """,
        pid=pipeline_id,
    )


def get_downstream(client: Neo4jClient, pipeline_id: str, component_name: str) -> list[dict[str, Any]]:
    return client.run(
        """
        MATCH (p:Pipeline {id: $pid})-[:HAS_COMPONENT]->(start:Component {name: $name})
        MATCH (start)-[:FLOWS_TO*]->(n:Component)
        RETURN DISTINCT n.id AS id, n.name AS name, n.type AS type
        """,
        pid=pipeline_id,
        name=component_name,
    )


def detect_cycles(client: Neo4jClient, pipeline_id: str) -> bool:
    rows = client.run(
        """
        MATCH (p:Pipeline {id: $pid})-[:HAS_COMPONENT]->(c:Component)
        WHERE EXISTS { MATCH (c)-[:FLOWS_TO*1..]->(c) }
        RETURN count(c) AS cnt
        """,
        pid=pipeline_id,
    )
    return bool(rows and rows[0]["cnt"] > 0)


def get_schema_for(client: Neo4jClient, component_id: str) -> dict[str, Any] | None:
    rows = client.run(
        """
        MATCH (c:Component {id: $cid})-[:USES_SCHEMA]->(s:Schema)
        RETURN s.fields AS fields LIMIT 1
        """,
        cid=component_id,
    )
    if not rows or rows[0]["fields"] is None:
        return None
    return json.loads(rows[0]["fields"])
