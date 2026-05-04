"""E5 — make equality comparisons null-safe inside Filter conditions on
nullable columns.

Spark's ``=`` returns NULL (not FALSE) when an operand is NULL; for a
``WHERE`` clause this means rows with NULL in the comparison column are
silently dropped. That's typically *not* what an Ab Initio Filter
expects (Ab Initio's filter is row-wise boolean, NULL excluded too). So
this is a semantic policy: for equality on a nullable column, rewrite
``col = literal`` to ``(col IS NOT NULL AND col = literal)``.

Scope: filter blocks only. Skips join keys (Spark joins handle NULLs
correctly for equi-joins). Skips assignments inside Reformats (those
preserve NULL semantics intentionally).
"""
from __future__ import annotations

import re
from typing import List

from ....ir.models import IRNode
from ..base import OptimizerRule, OptimizationReport, ReportEntry

# Match `col = <literal>` and `<literal> = col` outside parentheses.
# Conservative: only catches ``backticked_col = LITERAL`` form.
_EQ_RE = re.compile(
    r"`(?P<col>\w+)`\s*=\s*(?P<lit>'[^']*'|-?\d+(?:\.\d+)?|TRUE|FALSE|NULL)",
)


class NullSafeComparisonRewrite(OptimizerRule):
    name = "NullSafeComparisonRewrite"
    stage = "expression"

    def apply(self, nodes: List[IRNode], report: OptimizationReport) -> List[IRNode]:
        by_id = {n.id: n for n in nodes}
        affected: list[str] = []
        for n in nodes:
            if n.ir_type != "filter":
                continue
            cond = _condition(n)
            if not cond:
                continue
            schema = _input_schema(n, by_id)
            new_cond, changed = _rewrite(cond, schema)
            if changed:
                _set_condition(n, new_cond)
                affected.append(n.id)
        if affected:
            report.add(ReportEntry(
                rule=self.name,
                nodes_affected=affected,
                description=f"Hardened {len(affected)} filter(s) against nullable equality NULL-drop",
            ))
        return nodes


def _condition(n: IRNode) -> str:
    block = n.config.get("block") or {}
    if block.get("type") == "filter":
        return block.get("condition") or ""
    return n.config.get("__filter_expr") or n.config.get("condition") or ""


def _set_condition(n: IRNode, cond: str) -> None:
    block = n.config.get("block") or {}
    if block.get("type") == "filter":
        new_block = dict(block)
        new_block["condition"] = cond
        cfg = dict(n.config)
        cfg["block"] = new_block
        n.config = cfg
    else:
        cfg = dict(n.config)
        cfg["__filter_expr"] = cond
        n.config = cfg


def _input_schema(n: IRNode, by_id: dict) -> dict[str, dict]:
    if not n.inputs:
        return {}
    upstream = by_id.get(n.inputs[0])
    if upstream is None or not upstream.schema:
        return {}
    return {f["name"]: f for f in upstream.schema.get("fields", [])}


def _rewrite(cond: str, schema: dict) -> tuple[str, bool]:
    changed = False

    def _sub(m: re.Match) -> str:
        nonlocal changed
        col = m.group("col")
        lit = m.group("lit")
        if lit.upper() == "NULL":
            return m.group(0)
        f = schema.get(col)
        if not f or f.get("nullable") is False:
            return m.group(0)
        changed = True
        return f"(`{col}` IS NOT NULL AND `{col}` = {lit})"

    return _EQ_RE.sub(_sub, cond), changed
