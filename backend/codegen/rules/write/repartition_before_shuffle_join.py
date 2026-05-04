"""W4 — explicit co-partitioning before SORT_MERGE joins.

For joins annotated by S4 with ``strategy = sort_merge`` and a single
join key, we tag each input with ``repartition_on`` so the codegen wraps
both sides in ``.repartition(spark.sql.shuffle.partitions, key)``. This
collapses two independent shuffles into one deterministic co-partitioning
shuffle.

Skipped for broadcast/skew/bucketed joins.
"""
from __future__ import annotations

from typing import List

from ....ir.models import IRNode
from ..base import OptimizerRule, OptimizationReport, ReportEntry


class RepartitionBeforeShuffleJoin(OptimizerRule):
    name = "RepartitionBeforeShuffleJoin"
    stage = "write"

    def apply(self, nodes: List[IRNode], report: OptimizationReport) -> List[IRNode]:
        by_id = {n.id: n for n in nodes}
        affected: list[str] = []
        for n in nodes:
            if n.ir_type != "join":
                continue
            if n.config.get("strategy") != "sort_merge":
                continue
            keys = n.config.get("join_key") or n.config.get("on") or ""
            if isinstance(keys, str):
                keys = [k.strip() for k in keys.split(",") if k.strip()]
            if len(keys) != 1:
                # Multi-key joins: skip — Spark handles them with a single shuffle anyway
                continue
            key = keys[0]
            for input_id in n.inputs:
                up = by_id.get(input_id)
                if up is None:
                    continue
                cfg = dict(up.config)
                cfg["repartition_on"] = key
                up.config = cfg
            cfg = dict(n.config)
            cfg["co_partitioned_on"] = key
            n.config = cfg
            affected.append(n.id)

        if affected:
            report.add(ReportEntry(
                rule=self.name,
                nodes_affected=affected,
                description=f"Co-partitioned inputs to {len(affected)} sort-merge join(s) on the join key",
            ))
        return nodes
