"""Normalize → ``F.explode`` (flatten an array into multiple rows)."""
from __future__ import annotations

from ..ir.models import IRNode
from .base import ComponentPlugin, EmitContext, register


@register
class NormalizePlugin(ComponentPlugin):
    component_type = "Normalize"
    ir_type = "normalize"

    def emit_pyspark(self, node: IRNode, ctx: EmitContext) -> str:
        if not node.inputs:
            return f"# [error] normalize {node.name} has no input"
        src = ctx.upstream(node)
        var = ctx.df_var(node.id)
        array_col = node.config.get("array_field") or node.config.get("explode") or ""
        item_alias = node.config.get("item_alias") or array_col or "item"
        if not array_col:
            return f"{var} = {src}  # normalize {node.name} (no array_field)"
        return (
            f"# normalize: {node.name}\n"
            f"{var} = {src}.withColumn({item_alias!r}, F.explode(F.col({array_col!r}))).drop({array_col!r})"
        )
