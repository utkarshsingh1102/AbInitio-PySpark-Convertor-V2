"""DedupSorted → ``df.dropDuplicates([keys])``.

``which`` selects between first / last / unique within each key group.
``last`` requires a sort key (most recent row).
"""
from __future__ import annotations

from ..ir.models import IRNode
from ._emit_helpers import csv_to_list
from .base import ComponentPlugin, EmitContext, register


@register
class DedupSortedPlugin(ComponentPlugin):
    component_type = "DedupSorted"
    ir_type = "dedup"

    def emit_pyspark(self, node: IRNode, ctx: EmitContext) -> str:
        if not node.inputs:
            return f"# [error] dedup {node.name} has no input"
        src = ctx.upstream(node)
        var = ctx.df_var(node.id)
        keys = csv_to_list(node.config.get("key") or node.config.get("dedup_key"))
        which = (node.config.get("which") or "first").lower()
        if not keys:
            return f"{var} = {src}.dropDuplicates()  # dedup {node.name}"
        if which == "unique":
            # rows that are unique on the key
            return (
                f"# dedup ({which}): {node.name}\n"
                f"{var} = {src}.groupBy({keys!r}).count().filter('count = 1').drop('count')\\\n"
                f"           .join({src}, on={keys!r}, how='left')"
            )
        return (
            f"# dedup ({which}): {node.name}\n"
            f"{var} = {src}.dropDuplicates({keys!r})"
        )
