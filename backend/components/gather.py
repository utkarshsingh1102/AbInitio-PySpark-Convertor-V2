"""Gather → ``unionByName`` over all inputs (no ordering guarantee).

Concatenate is the same operation but documents that callers care about
preserving order; with parallel Spark execution that's only meaningful
if the inputs are already sorted on a stable key.
"""
from __future__ import annotations

from functools import reduce as _reduce  # noqa: F401  (used in template)

from ..ir.models import IRNode
from .base import ComponentPlugin, EmitContext, register


def _emit_union(node: IRNode, ctx: EmitContext, ordered: bool) -> str:
    if len(node.inputs) < 2:
        return (
            f"# [error] {node.component_type} {node.name} requires ≥2 inputs"
        )
    var = ctx.df_var(node.id)
    inputs = ", ".join(ctx.df_var(i) for i in node.inputs)
    label = "concatenate" if ordered else "gather"
    return (
        f"# {label}: {node.name}\n"
        f"{var} = reduce(lambda a, b: a.unionByName(b, allowMissingColumns=True), [{inputs}])"
    )


@register
class GatherPlugin(ComponentPlugin):
    component_type = "Gather"
    ir_type = "union"

    def emit_pyspark(self, node: IRNode, ctx: EmitContext) -> str:
        return _emit_union(node, ctx, ordered=False)


@register
class ConcatenatePlugin(ComponentPlugin):
    component_type = "Concatenate"
    ir_type = "union"

    def emit_pyspark(self, node: IRNode, ctx: EmitContext) -> str:
        return _emit_union(node, ctx, ordered=True)
