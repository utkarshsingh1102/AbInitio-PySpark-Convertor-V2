"""E1 — strip identity ``out.col = in.col`` (or ``out.col = `col` ``) assignments."""
from __future__ import annotations

import re
from typing import List

from ....ir.models import IRNode
from ..base import OptimizerRule, OptimizationReport, ReportEntry

_IDENTITY_RE = re.compile(r"^\s*`?(\w+)`?\s*$")


class StripIdentityAssignments(OptimizerRule):
    name = "StripIdentityAssignments"
    stage = "expression"

    def apply(self, nodes: List[IRNode], report: OptimizationReport) -> List[IRNode]:
        affected: list[str] = []
        total_stripped = 0
        for n in nodes:
            if n.ir_type != "transform":
                continue
            block = n.config.get("block") or {}
            assignments = block.get("assignments") or []
            if not assignments:
                continue
            cleaned: list[tuple[str, object]] = []
            for col, expr in assignments:
                if isinstance(expr, str):
                    m = _IDENTITY_RE.match(expr)
                    if m and m.group(1) == col:
                        total_stripped += 1
                        continue
                cleaned.append((col, expr))
            if len(cleaned) != len(assignments):
                new_block = dict(block)
                new_block["assignments"] = cleaned
                cfg = dict(n.config)
                cfg["block"] = new_block
                cfg.setdefault("output_columns", [c for c, _ in assignments])
                n.config = cfg
                affected.append(n.id)
        if affected:
            report.add(ReportEntry(
                rule=self.name,
                nodes_affected=affected,
                description=f"Removed {total_stripped} identity assignment(s) across {len(affected)} node(s)",
            ))
        return nodes
