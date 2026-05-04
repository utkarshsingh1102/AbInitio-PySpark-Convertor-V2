"""Replicate → pure aliasing.

Spark DataFrames are lazy and immutable, so multiple downstream consumers
of the same ``df_<id>`` "fan out" automatically. The Replicate plugin just
materialises that as ``df_<replicate_id> = df_<src>``.
"""
from __future__ import annotations

from ..ir.models import IRNode
from .base import ComponentPlugin, EmitContext, register


@register
class ReplicatePlugin(ComponentPlugin):
    component_type = "Replicate"
    ir_type = "replicate"

    def emit_pyspark(self, node: IRNode, ctx: EmitContext) -> str:
        if not node.inputs:
            return f"# [error] replicate {node.name} has no input"
        src = ctx.upstream(node)
        var = ctx.df_var(node.id)
        return f"# replicate: {node.name}\n{var} = {src}"
