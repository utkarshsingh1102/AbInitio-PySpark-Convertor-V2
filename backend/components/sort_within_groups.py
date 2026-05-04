"""SortWithinGroups → ``Window.partitionBy(group).orderBy(sort)``.

Adds a ``__row_num`` column (then drops it) so downstream sees rows
ordered within each group.
"""
from __future__ import annotations

from ..ir.models import IRNode
from ._emit_helpers import csv_to_list
from .base import ComponentPlugin, EmitContext, register


@register
class SortWithinGroupsPlugin(ComponentPlugin):
    component_type = "SortWithinGroups"
    ir_type = "sort"

    def emit_pyspark(self, node: IRNode, ctx: EmitContext) -> str:
        if not node.inputs:
            return f"# [error] swg {node.name} has no input"
        src = ctx.upstream(node)
        var = ctx.df_var(node.id)
        group_keys = csv_to_list(node.config.get("group_by") or node.config.get("group"))
        sort_keys = csv_to_list(node.config.get("sort_by") or node.config.get("key"))
        if not (group_keys and sort_keys):
            return f"{var} = {src}  # swg {node.name} (missing group_by or sort_by)"
        partition = ", ".join(f"F.col({k!r})" for k in group_keys)
        order = ", ".join(f"F.col({k!r})" for k in sort_keys)
        return (
            f"# sort_within_groups: {node.name}\n"
            f"_w_{node.id} = Window.partitionBy({partition}).orderBy({order})\n"
            f"{var} = {src}.withColumn('__rn', F.row_number().over(_w_{node.id}))\\\n"
            f"           .orderBy({partition}, {order})\\\n"
            f"           .drop('__rn')"
        )
