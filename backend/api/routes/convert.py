"""POST /generate-code      — build IR from Neo4j, run optimizer, emit code.
GET  /optimize-report/{id} — return the most recent optimizer report.
"""
from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ...codegen.ksh_gen import generate_ksh
from ...codegen.pyspark_gen import generate_pyspark
from ...graph import queries as Q
from ...graph.client import Neo4jClient
from ...ir.builder import build_ir
from ..deps import get_neo4j, job_dir

router = APIRouter()


class GenerateRequest(BaseModel):
    pipeline_id: str


@router.post("/generate-code")
def generate(
    req: GenerateRequest, client: Neo4jClient = Depends(get_neo4j)
) -> dict[str, Any]:
    try:
        ir_nodes = build_ir(client, req.pipeline_id)
    except Q.CyclicGraphError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not ir_nodes:
        raise HTTPException(status_code=404, detail="Pipeline not found or empty")

    py_src, report = generate_pyspark(
        ir_nodes, app_name=req.pipeline_id, return_report=True
    )
    ksh_src = generate_ksh(ir_nodes, pipeline_name=req.pipeline_id)

    out = job_dir(req.pipeline_id)
    (out / "pipeline.py").write_text(py_src)
    (out / "pipeline.ksh").write_text(ksh_src)
    (out / "optimization_report.json").write_text(
        json.dumps(report.to_dict(), indent=2)
    )

    return {
        "pipeline_id": req.pipeline_id,
        "pyspark": py_src,
        "ksh": ksh_src,
        "report": report.to_dict(),
    }


@router.get("/optimize-report/{pipeline_id}")
def get_report(pipeline_id: str) -> dict[str, Any]:
    path = job_dir(pipeline_id) / "optimization_report.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Run /generate-code first")
    return json.loads(path.read_text())
