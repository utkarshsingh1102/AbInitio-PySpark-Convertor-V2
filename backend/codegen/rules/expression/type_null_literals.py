"""E3 — replace ``F.expr("NULL")`` with ``F.lit(None).cast(<target_type>)``.

Patterns matched:
  - bare ``NULL`` / ``null``
  - ``COALESCE(NULL, NULL, ...)``
  - ``IF(false, X, NULL)`` — NOT simplified here (would need a constant
    folder; left for a future rule).
"""
from __future__ import annotations

import re
from typing import List

from ....components._emit_helpers import _primitive_to_code
from ....ir.models import IRNode
from ..base import OptimizerRule, OptimizationReport, ReportEntry

_ALL_NULL_COALESCE_RE = re.compile(
    r"^\s*COALESCE\(\s*(?:NULL\s*,\s*)+NULL\s*\)\s*$", re.IGNORECASE
)


class TypeNullLiterals(OptimizerRule):
    name = "TypeNullLiterals"
    stage = "expression"

    def apply(self, nodes: List[IRNode], report: OptimizationReport) -> List[IRNode]:
        affected: list[str] = []
        for n in nodes:
            if n.ir_type != "transform" or not n.schema:
                continue
            block = n.config.get("block") or {}
            assignments = block.get("assignments") or []
            if not assignments:
                continue
            type_by_col = _types_for(n.schema)
            new_assignments: list[tuple[str, object]] = []
            changed = False
            for col, expr in assignments:
                if isinstance(expr, str) and _is_pure_null(expr):
                    tcode = type_by_col.get(col)
                    if tcode is not None:
                        new_assignments.append(
                            (col, {"__typed_null__": True, "type_code": tcode})
                        )
                        changed = True
                        continue
                new_assignments.append((col, expr))
            if changed:
                new_block = dict(block)
                new_block["assignments"] = new_assignments
                cfg = dict(n.config)
                cfg["block"] = new_block
                n.config = cfg
                affected.append(n.id)
        if affected:
            report.add(ReportEntry(
                rule=self.name,
                nodes_affected=affected,
                description=f"Typed null literals on {len(affected)} node(s) — protects Parquet/Delta writes",
            ))
        return nodes


def _is_pure_null(expr: str) -> bool:
    s = expr.strip()
    if s.upper() == "NULL":
        return True
    return bool(_ALL_NULL_COALESCE_RE.match(s))


def _types_for(schema: dict) -> dict[str, str]:
    out: dict[str, str] = {}
    for f in schema.get("fields", []):
        if f.get("type") == "struct":
            continue
        out[f["name"]] = _primitive_to_code(f["type"], f.get("args", []) or [])
    return out
