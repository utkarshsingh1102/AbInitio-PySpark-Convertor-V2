"""Scan → cumulative aggregation via window functions.

Properties:
  - ``key``: partition columns (group within which to scan)
  - ``sort_by``: ordering within each partition
  - ``aggregates``: e.g. ``sum(amount):running_total``
"""
from __future__ import annotations

from ..ir.models import IRNode
from ._emit_helpers import csv_to_list
from .base import ComponentPlugin, EmitContext, register
from .rollup import _parse_aggregates


@register
class ScanPlugin(ComponentPlugin):
    component_type = "Scan"
    ir_type = "scan"

    def emit_pyspark(self, node: IRNode, ctx: EmitContext) -> str:
        if not node.inputs:
            return f"# [error] scan {node.name} has no input"
        src = ctx.upstream(node)
        var = ctx.df_var(node.id)
        cfg = node.config
        partition = csv_to_list(cfg.get("key") or cfg.get("partition_by"))
        sort_keys = csv_to_list(cfg.get("sort_by"))
        aggs = _parse_aggregates(cfg.get("aggregates") or "")
        partition_expr = ", ".join(f"F.col({k!r})" for k in partition) if partition else ""
        order_expr = ", ".join(f"F.col({k!r})" for k in sort_keys) if sort_keys else ""

        win = f"_w_{node.id}"
        win_def = f"Window"
        if partition:
            win_def += f".partitionBy({partition_expr})"
        if sort_keys:
            win_def += f".orderBy({order_expr})"
        win_def += ".rowsBetween(Window.unboundedPreceding, Window.currentRow)"

        lines = [f"# scan: {node.name}", f"{win} = {win_def}", f"{var} = {src}"]
        for fn, col, alias in aggs:
            lines.append(
                f"{var} = {var}.withColumn({alias!r}, F.{fn}({col!r}).over({win}))"
            )
        return "\n".join(lines)
