"""Shared FastAPI dependencies + job storage helpers."""
from __future__ import annotations

import os
from pathlib import Path

from ..graph.client import Neo4jClient

JOB_ROOT = Path(os.environ.get("JOB_DIR", "/tmp/abinitio-jobs"))
JOB_ROOT.mkdir(parents=True, exist_ok=True)


def get_neo4j() -> Neo4jClient:
    return Neo4jClient.from_env()


def job_dir(job_id: str) -> Path:
    p = JOB_ROOT / job_id
    p.mkdir(parents=True, exist_ok=True)
    return p
