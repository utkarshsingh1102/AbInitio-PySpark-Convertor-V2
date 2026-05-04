"""MatchSorted → inner join on sort keys.

Identical to a sorted-merge join semantically; on Spark, plain ``join``
is enough — the planner picks the right physical strategy.
"""
from __future__ import annotations

from ..ir.models import IRNode
from ._emit_helpers import csv_to_list
from .base import ComponentPlugin, EmitContext, register


@register
class MatchSortedPlugin(ComponentPlugin):
    component_type = "MatchSorted"
    ir_type = "join"

    def emit_pyspark(self, node: IRNode, ctx: EmitContext) -> str:
        cfg = node.config
        left_id = node.port_inputs.get("in_left") or (node.inputs[0] if len(node.inputs) >= 1 else None)
        right_id = node.port_inputs.get("in_right") or (node.inputs[1] if len(node.inputs) >= 2 else None)
        if not left_id or not right_id:
            return f"# [error] match_sorted {node.name} requires 2 inputs"
        left = ctx.df_var(left_id)
        right = ctx.df_var(right_id)
        var = ctx.df_var(node.id)
        keys = csv_to_list(cfg.get("key") or cfg.get("on"))
        keys_repr = repr(keys) if keys else "[]"
        return (
            f"# match_sorted: {node.name}\n"
            f"{var} = {left}.join({right}, on={keys_repr}, how='inner')"
        )
