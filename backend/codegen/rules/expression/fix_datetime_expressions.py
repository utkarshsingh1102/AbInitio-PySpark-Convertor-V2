"""E2 — rewrite syntactically-valid-but-semantically-wrong expressions on
date/timestamp columns.

Implemented rewrites (column type sourced from upstream schema OR from a
sibling assignment that converts the column to date/timestamp earlier in
the same block):

  ``SUBSTRING(col, 1, 7)``  → ``DATE_FORMAT(col, 'yyyy-MM')``
  ``SUBSTRING(col, 1, 4)``  → ``YEAR(col)`` (cast to string for parity)
  ``SUBSTRING(col, 6, 2)``  → ``MONTH(col)``
  ``SUBSTRING(col, 9, 2)``  → ``DAY(col)``
  ``UPPER(col) / LOWER(col) / TRIM(col)`` on date col → strip the wrap
                                                       (warning emitted)
  ``LENGTH(col)`` on date col → leave alone but emit warning
"""
from __future__ import annotations

import re
from typing import List

from ....ir.models import IRNode
from ..base import OptimizerRule, OptimizationReport, ReportEntry

_DATE_LIKE = ("date", "datetime", "timestamp")

_SUBSTR_RE = re.compile(
    r"SUBSTRING\(\s*`?(\w+)`?\s*,\s*(\d+)\s*,\s*(\d+)\s*\)", re.IGNORECASE
)
_WRAPPED_RE = re.compile(
    r"\b(UPPER|LOWER|TRIM|LTRIM|RTRIM|LENGTH)\s*\(\s*`?(\w+)`?\s*\)", re.IGNORECASE
)


class FixDateTimeExpressions(OptimizerRule):
    name = "FixDateTimeExpressions"
    stage = "expression"

    def apply(self, nodes: List[IRNode], report: OptimizationReport) -> List[IRNode]:
        by_id = {n.id: n for n in nodes}
        affected: list[str] = []
        warnings: list[str] = []

        for n in nodes:
            if n.ir_type != "transform":
                continue
            block = n.config.get("block") or {}
            assignments = block.get("assignments") or []
            if not assignments:
                continue
            upstream_types = _input_types(n, by_id)
            new_assignments: list[tuple[str, object]] = []
            changed = False

            for col, expr in assignments:
                if isinstance(expr, str):
                    new_expr = expr
                    new_expr = _SUBSTR_RE.sub(
                        lambda m: _maybe_substring(m, upstream_types, assignments),
                        new_expr,
                    )
                    new_expr = _WRAPPED_RE.sub(
                        lambda m: _maybe_unwrap(m, upstream_types, assignments, warnings, n.id),
                        new_expr,
                    )
                    if new_expr != expr:
                        changed = True
                    new_assignments.append((col, new_expr))
                else:
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
                description=f"Rewrote date/time expressions on {len(affected)} node(s)",
            ))
        for w in warnings:
            report.add(ReportEntry(
                rule=self.name, severity="warn", description=w,
            ))
        return nodes


def _input_types(node: IRNode, by_id: dict) -> dict[str, str]:
    if not node.inputs:
        return {}
    upstream = by_id.get(node.inputs[0])
    if upstream is None or not upstream.schema:
        return {}
    return {f["name"]: f["type"] for f in upstream.schema.get("fields", [])}


def _self_ref_type(col: str, assignments) -> str | None:
    for c, expr in assignments:
        if c == col and isinstance(expr, str):
            u = expr.upper()
            if "TO_DATE(" in u:
                return "date"
            if "TO_TIMESTAMP(" in u:
                return "datetime"
    return None


def _maybe_substring(m: re.Match, types: dict, assignments) -> str:
    col = m.group(1)
    start = int(m.group(2))
    length = int(m.group(3))
    t = _self_ref_type(col, assignments) or types.get(col)
    if t not in _DATE_LIKE:
        return m.group(0)
    if start == 1 and length == 7:
        return f"DATE_FORMAT(`{col}`, 'yyyy-MM')"
    if start == 1 and length == 4:
        return f"YEAR(`{col}`)"
    if start == 6 and length == 2:
        return f"MONTH(`{col}`)"
    if start == 9 and length == 2:
        return f"DAY(`{col}`)"
    return f"DATE_FORMAT(`{col}`, 'yyyy-MM-dd HH:mm:ss')"


def _maybe_unwrap(m: re.Match, types: dict, assignments, warnings: list, node_id: str) -> str:
    fn = m.group(1).upper()
    col = m.group(2)
    t = _self_ref_type(col, assignments) or types.get(col)
    if t not in _DATE_LIKE:
        return m.group(0)
    if fn in ("UPPER", "LOWER", "TRIM", "LTRIM", "RTRIM"):
        warnings.append(
            f"{fn}(`{col}`) on date column is meaningless on node {node_id}; stripped wrapper"
        )
        return f"`{col}`"
    if fn == "LENGTH":
        warnings.append(
            f"LENGTH(`{col}`) on date column is locale-dependent (node {node_id}); leaving as-is"
        )
        return m.group(0)
    return m.group(0)
