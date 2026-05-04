"""W3 — pick a ``StorageLevel`` for each ``.cache()``-tagged node.

Decision table:

  * narrow schema (≤ 5 cols, all primitives)            → ``MEMORY_ONLY``
  * wide schema (> 20 cols) or has nested struct/array  → ``MEMORY_AND_DISK_SER``
  * only consumers are ``write`` nodes                  → ``DISK_ONLY``
  * 5+ consumers                                        → ``MEMORY_AND_DISK``
  * default                                             → ``MEMORY_AND_DISK``
"""
from __future__ import annotations

from typing import List

from ....ir.models import IRNode
from ..base import OptimizerRule, OptimizationReport, ReportEntry


class StorageLevelSelection(OptimizerRule):
    name = "StorageLevelSelection"
    stage = "write"

    def apply(self, nodes: List[IRNode], report: OptimizationReport) -> List[IRNode]:
        by_id = {n.id: n for n in nodes}
        affected: list[str] = []
        for n in nodes:
            if not n.config.get("cache"):
                continue
            level = _decide(n, by_id)
            cfg = dict(n.config)
            cfg["storage_level"] = level
            n.config = cfg
            affected.append(n.id)
        if affected:
            report.add(ReportEntry(
                rule=self.name,
                nodes_affected=affected,
                description=f"Assigned StorageLevel to {len(affected)} cached node(s)",
            ))
        return nodes


def _decide(n: IRNode, by_id: dict) -> str:
    consumers = [by_id[c] for c in n.outputs if c in by_id]
    if consumers and all(c.ir_type == "write" for c in consumers):
        return "DISK_ONLY"
    width, has_nested = _schema_shape(n.schema)
    if width > 20 or has_nested:
        return "MEMORY_AND_DISK_SER"
    if width <= 5 and not has_nested:
        return "MEMORY_ONLY"
    if len(consumers) >= 5:
        return "MEMORY_AND_DISK"
    return "MEMORY_AND_DISK"


def _schema_shape(schema) -> tuple[int, bool]:
    if not schema:
        return 0, False
    fields = schema.get("fields", []) or []
    width = len(fields)
    has_nested = any(
        f.get("type") in ("struct", "array") or f.get("array") for f in fields
    )
    return width, has_nested
