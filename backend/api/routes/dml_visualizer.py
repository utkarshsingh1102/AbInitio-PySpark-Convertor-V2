"""POST /dml/visualize — return the intermediate output of every parser stage.

Used by the front-end Visualizer page to animate how a DML source goes
from raw text → tokens → AST → layout → PySpark StructType.

The endpoint is purely diagnostic; the regular /dml/convert endpoint runs
the same pipeline end-to-end without exposing the intermediates.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ...components._emit_helpers import schema_dict_to_struct_code
from ...parser import dml_parser as DP
from ...parser.preprocess import (
    expand_c_macros,
    strip_sql_comments,
    strip_unresolved_vars,
)

router = APIRouter()


# ── request / response models ─────────────────────────────────────────────


class VisualizeRequest(BaseModel):
    dml: str
    params: dict[str, str] | None = None


class StageNote(BaseModel):
    label: str
    detail: str


class TokenView(BaseModel):
    kind: str
    value: str


class SchemaView(BaseModel):
    name: str
    fields: list[dict[str, Any]]
    layout: str | None = None
    record_length: int | None = None
    struct_code: str


class VisualizeResponse(BaseModel):
    # Stage 1 — preprocessing
    source_raw: str
    after_comments: str
    after_macros: str
    after_interpolate: str
    stage1_notes: list[StageNote]

    # Stage 2 — tokenization
    tokens: list[TokenView]

    # Stage 3 — parsing
    schemas: list[SchemaView]

    # Stage 4 / 5 are folded into SchemaView (layout + struct_code per schema)


# ── route ─────────────────────────────────────────────────────────────────


@router.post("/dml/visualize", response_model=VisualizeResponse)
def visualize(req: VisualizeRequest) -> VisualizeResponse:
    if not req.dml or not req.dml.strip():
        raise HTTPException(status_code=400, detail="DML text is empty")

    raw = req.dml
    notes: list[StageNote] = []

    # ── Stage 1: comments → macros → interpolate → strip-unresolved ──────
    after_comments = strip_sql_comments(raw)
    if after_comments != raw:
        notes.append(StageNote(
            label="Comments stripped",
            detail="Removed `--`, `//`, and `/* … */` comments.",
        ))

    after_macros = expand_c_macros(after_comments)
    if after_macros != after_comments:
        notes.append(StageNote(
            label="C-macros expanded",
            detail="Resolved `#define NAME value` substitutions.",
        ))

    after_interpolate = after_macros
    if req.params:
        from ...parser.params import interpolate
        after_interpolate = interpolate(after_macros, req.params)
        if after_interpolate != after_macros:
            notes.append(StageNote(
                label="${VAR} interpolated",
                detail=f"Substituted {len(req.params)} parameter(s).",
            ))

    after_strip = strip_unresolved_vars(after_interpolate)
    if after_strip != after_interpolate:
        notes.append(StageNote(
            label="Unresolved ${VAR} stripped",
            detail="Lenient mode: silently dropped variables we couldn't resolve.",
        ))

    # ── Stage 2: tokenize ─────────────────────────────────────────────────
    try:
        toks = DP._tokenize(after_strip)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Tokenizer error: {exc}") from exc

    tokens = [TokenView(kind=k, value=v) for (k, v) in toks]

    # ── Stage 3 + 4 + 5: parse → layout → convert ────────────────────────
    try:
        parser = DP._Parser(toks)
        schemas_dict = parser.parse_file()
        for sch in schemas_dict.values():
            DP._attach_layout(sch)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Parser error: {exc}") from exc

    schema_views: list[SchemaView] = []
    for name, schema in schemas_dict.items():
        schema_views.append(SchemaView(
            name=name,
            fields=schema.get("fields", []),
            layout=schema.get("layout"),
            record_length=schema.get("record_length"),
            struct_code=schema_dict_to_struct_code(schema),
        ))

    return VisualizeResponse(
        source_raw=raw,
        after_comments=after_comments,
        after_macros=after_macros,
        after_interpolate=after_interpolate,
        stage1_notes=notes,
        tokens=tokens,
        schemas=schema_views,
    )
