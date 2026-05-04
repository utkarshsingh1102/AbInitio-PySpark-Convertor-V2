"""DenormalizeSorted → ``df.groupBy(group).agg(F.collect_list(...))``."""
from __future__ import annotations

from ..ir.models import IRNode
from ._emit_helpers import csv_to_list
from .base import ComponentPlugin, EmitContext, register


@register
class DenormalizeSortedPlugin(ComponentPlugin):
    component_type = "DenormalizeSorted"
    ir_type = "denormalize"

    def emit_pyspark(self, node: IRNode, ctx: EmitContext) -> str:
        if not node.inputs:
            return f"# [error] denormalize {node.name} has no input"
        src = ctx.upstream(node)
        var = ctx.df_var(node.id)
        group_keys = csv_to_list(node.config.get("group_by") or node.config.get("key"))
        list_cols = csv_to_list(node.config.get("collect"))
        if not (group_keys and list_cols):
            return f"{var} = {src}  # denormalize {node.name} (missing keys)"
        agg_exprs = ", ".join(
            f'F.collect_list({c!r}).alias({(c + "_list")!r})' for c in list_cols
        )
        return (
            f"# denormalize: {node.name}\n"
            f"{var} = {src}.groupBy({group_keys!r}).agg({agg_exprs})"
        )
