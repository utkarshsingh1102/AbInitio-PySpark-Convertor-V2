"""Sort → ``df.orderBy(*keys)``.

``key`` (CSV) lists the sort columns; ``order=desc`` reverses direction.
"""
from __future__ import annotations

from ..ir.models import IRNode
from ._emit_helpers import csv_to_list
from .base import ComponentPlugin, EmitContext, register


@register
class SortPlugin(ComponentPlugin):
    component_type = "Sort"
    ir_type = "sort"

    def emit_pyspark(self, node: IRNode, ctx: EmitContext) -> str:
        if not node.inputs:
            return f"# [error] sort {node.name} has no input"
        src = ctx.upstream(node)
        var = ctx.df_var(node.id)
        keys = csv_to_list(node.config.get("key"))
        desc = (node.config.get("order") or "asc").lower() == "desc"
        if not keys:
            return f"{var} = {src}  # sort {node.name} (no keys)"
        cols = ", ".join(
            f"F.col({k!r}).{'desc' if desc else 'asc'}()" for k in keys
        )
        return (
            f"# sort: {node.name}\n"
            f"{var} = {src}.orderBy({cols})"
        )
