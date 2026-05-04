"""S3 — tag fan-out nodes for ``.cache()`` / ``.persist(...)`` + ``.unpersist()``.

A node consumed by more than one downstream node would be recomputed once per
consumer without caching. We tag ``config["cache"] = True`` on such nodes;
``StorageLevelSelection`` picks the right ``StorageLevel``; codegen wraps the
node's emit and inserts ``.unpersist()`` after the last consumer.
"""
from __future__ import annotations

from typing import List

from ....ir.models import IRNode
from ..base import OptimizerRule, OptimizationReport, ReportEntry

_SKIP_IR_TYPES = {"read", "checkpoint"}


class FanOutCacheAnnotation(OptimizerRule):
    name = "FanOutCacheAnnotation"
    stage = "structural"

    def apply(self, nodes: List[IRNode], report: OptimizationReport) -> List[IRNode]:
        affected: list[str] = []
        for n in nodes:
            if n.ir_type in _SKIP_IR_TYPES:
                continue
            if n.fan_out > 1:
                cfg = dict(n.config)
                cfg["cache"] = True
                cfg["unpersist_after"] = _last_consumer(n, nodes)
                n.config = cfg
                affected.append(n.id)
        if affected:
            report.add(ReportEntry(
                rule=self.name,
                nodes_affected=affected,
                description=(
                    f"Tagged {len(affected)} node(s) with out-degree > 1 for caching; "
                    "downstream rule W3 picks the StorageLevel"
                ),
            ))
        return nodes


def _last_consumer(node: IRNode, all_nodes: List[IRNode]) -> str | None:
    last: str | None = None
    for n in all_nodes:
        if node.id in n.inputs:
            last = n.id
    return last
