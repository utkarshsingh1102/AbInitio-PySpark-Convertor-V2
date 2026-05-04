"""E7 — translate ``F.expr("…")`` strings into native PySpark API calls.

Runs LAST in stage 2 so all upstream expression rewrites have settled.
For each transform-block assignment whose value is a SQL string, attempts
to translate via :mod:`backend.codegen.expr_to_native`. On success the
value is replaced with a marker dict ``{"__native_expr__": True, "code":
"<python expression>"}`` that the Reformat plugin renders directly. On
failure the original string is left in place — the codegen falls back
to ``F.expr(...)`` and nothing breaks.

Also rewrites Filter conditions: those produce ``df.filter(<col_expr>)``
instead of ``df.filter(F.expr("..."))``.
"""
from __future__ import annotations

from typing import List

from ....ir.models import IRNode
from ...expr_to_native import to_native
from ..base import OptimizationReport, OptimizerRule, ReportEntry


class RewriteExprToNativeAPI(OptimizerRule):
    name = "RewriteExprToNativeAPI"
    stage = "expression"

    def apply(self, nodes: List[IRNode], report: OptimizationReport) -> List[IRNode]:
        affected: list[str] = []
        translated_count = 0
        skipped_count = 0

        for n in nodes:
            if n.ir_type == "transform":
                t, s = self._rewrite_transform(n)
                translated_count += t
                skipped_count += s
                if t > 0:
                    affected.append(n.id)
            elif n.ir_type == "filter":
                if self._rewrite_filter(n):
                    translated_count += 1
                    affected.append(n.id)
                else:
                    skipped_count += 1

        if affected:
            report.add(ReportEntry(
                rule=self.name,
                nodes_affected=sorted(set(affected)),
                description=(
                    f"Replaced {translated_count} F.expr(\"…\") call(s) with native "
                    f"PySpark API across {len(set(affected))} node(s); "
                    f"{skipped_count} expression(s) too complex — left as F.expr"
                ),
            ))
        return nodes

    def _rewrite_transform(self, n: IRNode) -> tuple[int, int]:
        block = n.config.get("block") or {}
        assignments = block.get("assignments") or []
        if not assignments:
            return (0, 0)
        translated, skipped = 0, 0
        new_assignments: list[tuple[str, object]] = []
        for col, expr in assignments:
            if isinstance(expr, str):
                native = to_native(expr)
                if native is not None:
                    new_assignments.append(
                        (col, {"__native_expr__": True, "code": native})
                    )
                    translated += 1
                    continue
                skipped += 1
            new_assignments.append((col, expr))

        if translated:
            new_block = dict(block)
            new_block["assignments"] = new_assignments
            cfg = dict(n.config)
            cfg["block"] = new_block
            n.config = cfg
        return translated, skipped

    def _rewrite_filter(self, n: IRNode) -> bool:
        block = n.config.get("block") or {}
        if block.get("type") != "filter":
            cond = n.config.get("__filter_expr") or n.config.get("condition")
            if not cond:
                return False
            native = to_native(cond)
            if native is None:
                return False
            cfg = dict(n.config)
            cfg["__native_filter"] = native
            n.config = cfg
            return True
        cond = block.get("condition") or ""
        native = to_native(cond)
        if native is None:
            return False
        new_block = dict(block)
        new_block["native_condition"] = native
        cfg = dict(n.config)
        cfg["block"] = new_block
        n.config = cfg
        return True
