"""S4 — pick a Join strategy: ``broadcast`` | ``sort_merge`` | ``skew``.

Decision tree (no row-count metadata available → heuristics):

  * If either side is a ``LookupFile`` or its filename contains a
    dimension keyword → BROADCAST that side.
  * Otherwise → SORT_MERGE (Spark's default; we still record it so W4 can
    decide whether to repartition first).
  * Skew detection requires profiling metadata; if a `skew_keys` config
    appears on the join node, emit the SKEW hint.
"""
from __future__ import annotations

from typing import List

from ....ir.models import IRNode
from ..base import OptimizerRule, OptimizationReport, ReportEntry

_DIMENSION_KEYWORDS = ("customer", "product", "lookup", "dim", "ref", "code")


class JoinStrategyAnnotation(OptimizerRule):
    name = "JoinStrategyAnnotation"
    stage = "structural"

    def apply(self, nodes: List[IRNode], report: OptimizationReport) -> List[IRNode]:
        by_id = {n.id: n for n in nodes}
        affected: list[str] = []
        for n in nodes:
            if n.ir_type != "join" or len(n.inputs) < 2:
                continue
            left = by_id.get(_resolve(n, "in_left", 0))
            right = by_id.get(_resolve(n, "in_right", 1))

            cfg = dict(n.config)
            cfg["strategy"] = "sort_merge"

            side = _broadcast_side(left, right)
            if side:
                cfg["strategy"] = "broadcast"
                cfg["broadcast"] = side

            # Skew: only fires if explicitly configured
            if cfg.get("skew_keys"):
                cfg["strategy"] = "skew"

            n.config = cfg
            affected.append(n.id)

        if affected:
            report.add(ReportEntry(
                rule=self.name,
                nodes_affected=affected,
                description=(
                    f"Annotated {len(affected)} join(s) with strategy "
                    f"({', '.join(set(by_id[a].config.get('strategy', '?') for a in affected))})"
                ),
            ))
        return nodes


def _resolve(n: IRNode, port: str, fallback_idx: int) -> str | None:
    if port in n.port_inputs:
        return n.port_inputs[port]
    if 0 <= fallback_idx < len(n.inputs):
        return n.inputs[fallback_idx]
    return None


def _broadcast_side(left: IRNode | None, right: IRNode | None) -> str | None:
    if _is_dim(left) and not _is_dim(right):
        return "left"
    if _is_dim(right) and not _is_dim(left):
        return "right"
    if _is_dim(left) and _is_dim(right):
        return "left"
    return None


def _is_dim(n: IRNode | None) -> bool:
    if n is None:
        return False
    if n.component_type == "LookupFile":
        return True
    if n.ir_type != "read":
        return False
    path = (n.config.get("filename") or n.config.get("path") or "").lower()
    return any(kw in path for kw in _DIMENSION_KEYWORDS)
