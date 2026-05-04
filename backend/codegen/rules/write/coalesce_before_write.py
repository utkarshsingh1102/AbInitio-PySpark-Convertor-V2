"""W1 — emit ``.coalesce(n)`` / ``.repartition(n)`` before every Write.

Decision tree (file-format aware, mode-aware, size-class-aware):

  * Append mode  → always ``coalesce`` (avoid full shuffle on appends)
  * Parquet/ORC/Delta  → coalesce(dop) by default; repartition only on
    ``size_class = 'large'`` if explicitly tagged.
  * CSV/text  → coalesce(dop)

Tags ``config["coalesce"] = N`` (or ``config["repartition"] = N``) which
the OutputFile plugin honours.
"""
from __future__ import annotations

from typing import List

from ....ir.models import IRNode
from ..base import OptimizerRule, OptimizationReport, ReportEntry

_COLUMNAR = {"parquet", "orc", "delta"}


class CoalesceBeforeWrite(OptimizerRule):
    name = "CoalesceBeforeWrite"
    stage = "write"

    def apply(self, nodes: List[IRNode], report: OptimizationReport) -> List[IRNode]:
        affected: list[str] = []
        for n in nodes:
            if n.ir_type != "write":
                continue
            cfg = dict(n.config)
            mode = (cfg.get("mode") or "overwrite").lower()
            fmt = (cfg.get("file_format") or cfg.get("format") or "parquet").lower()
            dop = _read_dop(n.params)
            size_class = (cfg.get("size_class") or "medium").lower()

            if mode == "append":
                cfg["coalesce"] = dop or 1
            elif fmt in _COLUMNAR:
                if size_class == "small":
                    cfg["coalesce"] = 1
                elif size_class == "large":
                    cfg["repartition"] = dop or 200
                else:
                    cfg["coalesce"] = dop or 4
            else:
                cfg["coalesce"] = dop or 4

            n.config = cfg
            affected.append(n.id)

        if affected:
            report.add(ReportEntry(
                rule=self.name,
                nodes_affected=affected,
                description=f"Bounded output partition count on {len(affected)} write(s)",
            ))
        return nodes


def _read_dop(params: dict) -> int | None:
    raw = params.get("DOP")
    if raw is None:
        return None
    try:
        n = int(raw)
        return n if n > 0 else None
    except (TypeError, ValueError):
        return None
