"""Join → ``df_left.join(df_right, on=key, how=type)``."""
from __future__ import annotations

from ..ir.models import IRNode
from ._emit_helpers import csv_to_list
from .base import ComponentPlugin, EmitContext, register

_HOW_MAP = {
    "inner":      "inner",
    "outer":      "outer",
    "full":       "full_outer",
    "full_outer": "full_outer",
    "left":       "left",
    "left_outer": "left",
    "right":      "right",
    "right_outer": "right",
}


@register
class JoinPlugin(ComponentPlugin):
    component_type = "Join"
    ir_type = "join"

    def emit_pyspark(self, node: IRNode, ctx: EmitContext) -> str:
        cfg = node.config
        left_id = node.port_inputs.get("in_left") or (node.inputs[0] if len(node.inputs) >= 1 else None)
        right_id = node.port_inputs.get("in_right") or (node.inputs[1] if len(node.inputs) >= 2 else None)
        if not left_id or not right_id:
            return f"# [error] join {node.name} requires 2 inputs"
        left = ctx.df_var(left_id)
        right = ctx.df_var(right_id)
        var = ctx.df_var(node.id)

        keys = csv_to_list(cfg.get("join_key") or cfg.get("on"))
        how = _HOW_MAP.get((cfg.get("join_type") or cfg.get("how") or "inner").lower(), "inner")
        broadcast_side = cfg.get("broadcast")  # "left" | "right" | None

        left_expr = f"F.broadcast({left})" if broadcast_side == "left" else left
        right_expr = f"F.broadcast({right})" if broadcast_side == "right" else right

        keys_repr = repr(keys) if keys else "[]"
        broadcast_note = f"  # broadcast={broadcast_side}" if broadcast_side else ""
        return (
            f"# join: {node.name} ({how}){broadcast_note}\n"
            f"{var} = {left_expr}.join({right_expr}, on={keys_repr}, how={how!r})"
        )
