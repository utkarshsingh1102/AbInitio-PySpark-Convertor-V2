"""POST /execute/{id}      — run pipeline.ksh and stream logs over SSE.
GET  /logs/{id}            — read the most recent log file (post-run).
POST /seed-test-data/{id}  — create dummy CSVs at the paths the pipeline reads,
                              so the demo "Run pipeline" button can actually
                              run a generated job inside the container.
"""
from __future__ import annotations

import csv
import io
import json
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException
from sse_starlette.sse import EventSourceResponse

from ...executor.spark_runner import stream_ksh_async
from ..deps import job_dir

router = APIRouter()


@router.post("/execute/{pipeline_id}")
def execute(pipeline_id: str):
    d = job_dir(pipeline_id)

    async def _events():
        async for line in stream_ksh_async(d):
            yield {"event": "log", "data": line}

    return EventSourceResponse(
        _events(),
        # Helps when fronted by Nginx / browser proxies — disables buffering.
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )


@router.get("/logs/{pipeline_id}")
def logs(pipeline_id: str) -> dict[str, object]:
    d = job_dir(pipeline_id)
    log_dir = d / "logs"
    if not log_dir.exists():
        raise HTTPException(status_code=404, detail="No logs yet")
    files = sorted(log_dir.glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        raise HTTPException(status_code=404, detail="No logs yet")
    return {"file": files[0].name, "content": files[0].read_text()}


# ── Demo seeding ──────────────────────────────────────────────────────────


_LOAD_PATH_RE = re.compile(r"\.load\((['\"])([^'\"]+)\1\)")


@router.post("/seed-test-data/{pipeline_id}")
def seed_test_data(pipeline_id: str) -> dict[str, object]:
    """Look at the generated pipeline.py, find every ``.load('PATH')`` call,
    and create a tiny synthetic CSV / parquet at each path.

    Note: only useful for local demos. Real pipelines should mount real data.
    """
    d = job_dir(pipeline_id)
    py = d / "pipeline.py"
    if not py.exists():
        raise HTTPException(status_code=400, detail="Run /generate-code first")

    src = py.read_text()
    paths = sorted(set(_LOAD_PATH_RE.findall(src)))
    # _LOAD_PATH_RE returns (quote, path) tuples
    paths = [p for _, p in paths]

    created: list[str] = []
    for raw in paths:
        target = Path(raw)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.suffix == ".csv" or target.name.endswith(".csv"):
            _write_csv_for(target)
        elif target.suffix == ".parquet":
            # Write CSV next to it as a stand-in (Spark would otherwise
            # need the parquet writer); the demo only loads csv anyway.
            _write_csv_for(target.with_suffix(".csv"))
            target.touch()  # placeholder; codegen typically reads CSV here
        else:
            target.write_text("")
        created.append(str(target))

    return {"pipeline_id": pipeline_id, "created": created, "paths_in_pipeline": paths}


def _write_csv_for(path: Path) -> None:
    """Write a short, schema-flexible CSV. The columns we know about for
    the bundled examples are hard-coded; everything else gets a 1-row
    minimal CSV with the column names the .py expects.
    """
    name = path.name.lower()
    if "customer" in name:
        path.write_text(
            "customer_id,first_name,last_name,email,country,signup_date,loyalty_points\n"
            "1,alice,smith,a@x.com,United States,2020-01-15,5500\n"
            "2,bob,jones,b@x.com,Germany,2022-03-10,800\n"
            "3,charlie,brown,c@x.com,,2021-06-01,2500\n"
        )
    elif "order" in name:
        path.write_text(
            "order_id,customer_id,order_date,product_code,quantity,unit_price,order_amount,status\n"
            "o1,1,2024-01-15 10:00:00,prodA,2,500.00,1200.00,confirmed\n"
            "o2,2,2024-02-20 11:30:00,prodB,1,400.00,400.00,confirmed\n"
            "o3,3,2024-03-05 09:15:00,prodC,4,300.00,,shipped\n"
        )
    else:
        # Generic placeholder — a single header line so empty reads don't crash.
        path.write_text("col1\nvalue\n")
