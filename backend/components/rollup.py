"""Rollup / Aggregate → ``df.groupBy(...).agg(...)``.

The ``aggregates`` property is a comma-separated list:
``sum(order_amount):monthly_spend, count(order_id):order_count``.
"""
from __future__ import annotations

import re

from ..ir.models import IRNode
from ._emit_helpers import csv_to_list
from .base import ComponentPlugin, EmitContext, register

_AGG_RE = re.compile(r"\s*(\w+)\s*\(\s*([^)]+?)\s*\)\s*(?::\s*(\w+))?\s*")


def _parse_aggregates(spec: str) -> list[tuple[str, str, str]]:
    """`sum(x):total, count(y):n` → [(fn, col, alias), ...]."""
    out: list[tuple[str, str, str]] = []
    for piece in spec.split(","):
        piece = piece.strip()
        if not piece:
            continue
        m = _AGG_RE.fullmatch(piece)
        if not m:
            continue
        fn, col, alias = m.group(1), m.group(2), m.group(3)
        out.append((fn.lower(), col, alias or f"{fn}_{col}"))
    return out


class _BaseRollup(ComponentPlugin):
    ir_type = "aggregate"

    def emit_pyspark(self, node: IRNode, ctx: EmitContext) -> str:
        if not node.inputs:
            return f"# [error] rollup {node.name} has no input"
        src = ctx.upstream(node)
        var = ctx.df_var(node.id)
        cfg = node.config
        group_by = csv_to_list(cfg.get("group_by") or cfg.get("key"))
        aggs = _parse_aggregates(cfg.get("aggregates") or "")
        if not aggs:
            agg_exprs = 'F.count(F.lit(1)).alias("count")'
        else:
            agg_exprs = ", ".join(
                f'F.{fn}({col!r}).alias({alias!r})' for fn, col, alias in aggs
            )
        return (
            f"# rollup: {node.name}\n"
            f"{var} = {src}.groupBy({group_by!r}).agg({agg_exprs})"
        )


@register
class RollupPlugin(_BaseRollup):
    component_type = "Rollup"


@register
class AggregatePlugin(_BaseRollup):
    component_type = "Aggregate"
