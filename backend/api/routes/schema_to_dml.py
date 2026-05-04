"""POST /<fmt>/to-dml — Schema-source → Ab Initio DML translators.

Three format-specific endpoints, all returning the same response shape::

    {"record_name": "...", "dml": "...", "extras": {...}}

The generated DML is guaranteed to round-trip through `parse_dml_string`
(the existing DML parser), so users can paste it straight into the DML
Playground to get a `StructType` + PySpark snippet.
"""
from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ...parser.cobol_to_dml import cobol_copybook_to_dml
from ...parser.hive_to_dml import hive_ddl_to_dml
from ...parser.xml_to_dml import xml_to_dml

router = APIRouter()


# ── shared response model ──────────────────────────────────────────────────


class ToDmlResponse(BaseModel):
    record_name: str
    dml: str
    extras: dict[str, Any] = {}


# ── Hive ───────────────────────────────────────────────────────────────────


class HiveRequest(BaseModel):
    ddl: str


@router.post("/hive/to-dml", response_model=ToDmlResponse)
def hive_to_dml_route(req: HiveRequest) -> ToDmlResponse:
    if not req.ddl or not req.ddl.strip():
        raise HTTPException(status_code=400, detail="Hive DDL is empty")
    try:
        result = hive_ddl_to_dml(req.ddl)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Hive parse error: {exc}") from exc
    return ToDmlResponse(
        record_name=result["table_name"],
        dml=result["dml"],
        extras={"stored_as": result.get("stored_as")},
    )


# ── COBOL ──────────────────────────────────────────────────────────────────


class CobolRequest(BaseModel):
    copybook: str


@router.post("/cobol/to-dml", response_model=ToDmlResponse)
def cobol_to_dml_route(req: CobolRequest) -> ToDmlResponse:
    if not req.copybook or not req.copybook.strip():
        raise HTTPException(status_code=400, detail="Copybook is empty")
    try:
        result = cobol_copybook_to_dml(req.copybook)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"COBOL parse error: {exc}") from exc
    return ToDmlResponse(record_name=result["record_name"], dml=result["dml"])


# ── XML / XSD ──────────────────────────────────────────────────────────────


class XmlRequest(BaseModel):
    xml: str
    mode: Literal["auto", "sample", "xsd"] = "auto"


@router.post("/xml/to-dml", response_model=ToDmlResponse)
def xml_to_dml_route(req: XmlRequest) -> ToDmlResponse:
    if not req.xml or not req.xml.strip():
        raise HTTPException(status_code=400, detail="XML input is empty")
    try:
        result = xml_to_dml(req.xml, mode=req.mode)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"XML parse error: {exc}") from exc
    return ToDmlResponse(
        record_name=result["record_name"],
        dml=result["dml"],
        extras={"detected_mode": result["mode"]},
    )
