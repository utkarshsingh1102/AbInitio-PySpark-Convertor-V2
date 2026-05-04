"""Graph storage + retrieval endpoints (Neo4j)."""
from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ...graph import queries as Q
from ...graph.client import Neo4jClient
from ...graph.ingestion import ingest_pipeline
from ...parser.mp_parser import parse_mp_string
from ...parser.types import ParsedEdge, ParsedGraph, ParsedNode
from ..deps import get_neo4j, job_dir

router = APIRouter()


class StoreRequest(BaseModel):
    job_id: str


@router.post("/store")
def store(req: StoreRequest, client: Neo4jClient = Depends(get_neo4j)) -> dict[str, Any]:
    d = job_dir(req.job_id)
    ast_path = d / "ast.json"
    if not ast_path.exists():
        raise HTTPException(status_code=400, detail="Run /parse first")
    ast = json.loads(ast_path.read_text())

    # Reconstruct ParsedGraph from the JSON shape
    mp = ast["mp"]
    parsed = ParsedGraph(
        pipeline_name=mp["pipeline"]["name"],
        nodes=[
            ParsedNode(
                id=n["id"], name=n["name"], type=n["type"],
                properties=n.get("properties", {}),
                input_ports={
                    port: (meta["node"], meta["port"])
                    for port, meta in (n.get("input_ports") or {}).items()
                },
                output_ports=n.get("output_ports", []),
            )
            for n in mp["nodes"]
        ],
        edges=[
            ParsedEdge(
                from_id=e["from"], to_id=e["to"],
                from_port=e.get("from_port", "out"),
                to_port=e.get("to_port", "in"),
            )
            for e in mp["edges"]
        ],
        params=mp.get("params", {}),
    )

    pipeline_id = req.job_id
    ingest_pipeline(
        client,
        pipeline_id=pipeline_id,
        parsed=parsed,
        schemas=ast.get("schemas") or {},
        transforms=ast.get("transforms") or {},
    )
    return {"pipeline_id": pipeline_id}


@router.get("/graph/{pipeline_id}")
def get_graph(pipeline_id: str, client: Neo4jClient = Depends(get_neo4j)) -> dict[str, Any]:
    return Q.get_pipeline_dag(client, pipeline_id)


@router.get("/graph/{pipeline_id}/order")
def get_order(pipeline_id: str, client: Neo4jClient = Depends(get_neo4j)) -> dict[str, Any]:
    try:
        ordered = Q.get_execution_order(client, pipeline_id)
    except Q.CyclicGraphError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"order": [{"id": n["id"], "name": n["name"], "type": n["type"]} for n in ordered]}
