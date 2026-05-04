"""W2 — emit ``.partitionBy(...)`` for time-bucketed outputs.

Triggers when:
  * the .mp explicitly sets ``partitionBy="col"`` on the OutputFile, OR
  * the upstream schema contains a column named after a known time bucket
    (``order_month``, ``year``, ``month``, ``day``, ``date``, ``order_date``)
    AND the output format is columnar.

Skipped (avoids the small-files-explosion trap) when the partitioning
column is high-cardinality. Without profiling stats we approximate with
type — date / month / year columns are low-cardinality so they pass.
"""
from __future__ import annotations

from typing import List

from ....ir.models import IRNode
from ..base import OptimizerRule, OptimizationReport, ReportEntry

_TIME_KEYWORDS = ("month", "year", "day", "date", "_dt")
_COLUMNAR = {"parquet", "orc", "delta"}


class PartitionByAnnotation(OptimizerRule):
    name = "PartitionByAnnotation"
    stage = "write"

    def apply(self, nodes: List[IRNode], report: OptimizationReport) -> List[IRNode]:
        by_id = {n.id: n for n in nodes}
        affected: list[str] = []
        for n in nodes:
            if n.ir_type != "write":
                continue
            cfg = dict(n.config)
            fmt = (cfg.get("file_format") or cfg.get("format") or "parquet").lower()
            if fmt not in _COLUMNAR:
                continue

            # Explicit override takes priority
            explicit = cfg.get("partitionBy") or cfg.get("partition_by")
            if explicit:
                cfg["partition_columns"] = _split(explicit)
                n.config = cfg
                affected.append(n.id)
                continue

            # Heuristic: pick a time-bucket column from the upstream schema
            up = by_id.get(n.inputs[0]) if n.inputs else None
            if up is None or not up.schema:
                continue
            for f in up.schema.get("fields", []):
                col = f["name"]
                if any(kw in col.lower() for kw in _TIME_KEYWORDS):
                    if f.get("type") in ("date", "datetime", "timestamp", "string", "integer"):
                        cfg["partition_columns"] = [col]
                        n.config = cfg
                        affected.append(n.id)
                    break

        if affected:
            report.add(ReportEntry(
                rule=self.name,
                nodes_affected=affected,
                description=f"Auto-partitioned {len(affected)} write(s) by detected time-bucket column",
            ))
        return nodes


def _split(value) -> list[str]:
    if isinstance(value, list):
        return [str(v).strip() for v in value]
    return [c.strip() for c in str(value).split(",") if c.strip()]
