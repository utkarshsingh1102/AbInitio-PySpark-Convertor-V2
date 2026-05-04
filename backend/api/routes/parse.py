"""POST /parse — parse uploaded .mp/.dml/.xfr files into a structured AST."""
from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ...parser.dml_parser import parse_dml_file
from ...parser.mp_parser import parse_mp_file
from ...parser.xfr_parser import parse_xfr_file
from ..deps import job_dir

router = APIRouter()


class ParseRequest(BaseModel):
    job_id: str


@router.post("/parse")
def parse(req: ParseRequest) -> dict[str, Any]:
    d = job_dir(req.job_id)
    mp_files = list(d.glob("*.mp"))
    dml_files = list(d.glob("*.dml"))
    xfr_files = list(d.glob("*.xfr"))

    if not mp_files:
        raise HTTPException(status_code=400, detail="No .mp file in job")

    parsed_mp = parse_mp_file(mp_files[0])

    # Use parameters from the .mp so DML can reference ${VAR} too.
    params = getattr(parsed_mp, "params", {}) or {}
    schemas: dict[str, Any] = {}
    for f in dml_files:
        schemas.update(parse_dml_file(f, params=params))

    transforms: dict[str, Any] = {}
    for f in xfr_files:
        transforms.update(parse_xfr_file(f))

    out = {
        "job_id": req.job_id,
        "mp": parsed_mp.to_dict(),
        "schemas": schemas,
        "transforms": transforms,
    }
    (d / "ast.json").write_text(json.dumps(out, indent=2, default=str))
    return out
