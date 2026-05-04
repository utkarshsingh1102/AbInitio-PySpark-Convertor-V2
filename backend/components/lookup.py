"""Lookup → broadcast join.

Resolves the lookup dataset via the ``in_lookup`` port (preferred) or the
second positional input.
"""
from __future__ import annotations

from ..ir.models import IRNode
from ._emit_helpers import csv_to_list
from .base import ComponentPlugin, EmitContext, register


@register
class LookupPlugin(ComponentPlugin):
    component_type = "Lookup"
    ir_type = "lookup"

    def emit_pyspark(self, node: IRNode, ctx: EmitContext) -> str:
        cfg = node.config
        main_id = node.port_inputs.get("in") or (node.inputs[0] if node.inputs else None)
        lkp_id = node.port_inputs.get("in_lookup") or node.port_inputs.get("lookup")
        if lkp_id is None and len(node.inputs) >= 2:
            lkp_id = node.inputs[1]
        if not main_id or not lkp_id:
            return f"# [error] lookup {node.name} requires main + lookup inputs"
        main = ctx.df_var(main_id)
        lkp = ctx.df_var(lkp_id)
        var = ctx.df_var(node.id)
        keys = csv_to_list(cfg.get("key"))
        keys_repr = repr(keys) if keys else "[]"
        return (
            f"# lookup: {node.name}\n"
            f"{var} = {main}.join(F.broadcast({lkp}), on={keys_repr}, how='left')"
        )
