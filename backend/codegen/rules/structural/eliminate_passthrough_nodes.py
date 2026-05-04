"""S6 — tag transform nodes whose body is fully identity as passthrough.

Run after ``StripIdentityAssignments``. If the assignment list is empty
post-strip, the Reformat is pure passthrough and codegen emits a single
alias line.
"""
from __future__ import annotations

from typing import List

from ....ir.models import IRNode
from ..base import OptimizerRule, OptimizationReport, ReportEntry


class EliminatePassthroughNodes(OptimizerRule):
    name = "EliminatePassthroughNodes"
    stage = "structural"

    def apply(self, nodes: List[IRNode], report: OptimizationReport) -> List[IRNode]:
        affected: list[str] = []
        for n in nodes:
            if n.ir_type != "transform":
                continue
            block = n.config.get("block") or {}
            assignments = block.get("assignments") or []
            if not assignments:
                cfg = dict(n.config)
                cfg["passthrough"] = True
                n.config = cfg
                affected.append(n.id)
        if affected:
            report.add(ReportEntry(
                rule=self.name,
                nodes_affected=affected,
                description=f"{len(affected)} transform(s) had no real assignments — emitting alias",
            ))
        return nodes
