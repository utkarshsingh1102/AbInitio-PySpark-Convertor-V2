"""Filter by Expression → ``df.filter(F.expr(cond))``.

Two ways to specify the condition:
  - ``condition`` property in the .mp (a single boolean expression)
  - a FILTER block in the .xfr file (referenced via ``transform_file``)

If both are present, the ``condition`` property wins (it's already pre-
interpolated by mp_parser).
"""
from __future__ import annotations

import logging

from ..ir.models import IRNode
from ..parser.xfr_parser import parse_filter_condition
from ._emit_helpers import escape_sql
from .base import ComponentPlugin, EmitContext, register

logger = logging.getLogger(__name__)


@register
class FilterPlugin(ComponentPlugin):
    component_type = "Filter"
    ir_type = "filter"

    def parse_props(self, raw, params):
        cfg = dict(raw)
        # Resolve a Spark SQL condition string up-front.
        if "condition" in cfg:
            try:
                cfg["__filter_expr"] = parse_filter_condition(cfg["condition"])
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Could not parse Filter condition %r: %s",
                    cfg.get("condition"), exc,
                )
                cfg["__filter_expr"] = cfg["condition"]
        return cfg

    def emit_pyspark(self, node: IRNode, ctx: EmitContext) -> str:
        if not node.inputs:
            return f"# [error] filter {node.name} has no input"
        src = ctx.upstream(node)
        var = ctx.df_var(node.id)

        # Prefer native PySpark expression if rule E7 produced one.
        block = node.config.get("block") or {}
        native = (
            block.get("native_condition") if block.get("type") == "filter" else None
        )
        native = native or node.config.get("__native_filter")
        if native:
            return (
                f"# filter: {node.name}\n"
                f"{var} = {src}.filter({native})"
            )

        # Fall back to F.expr with the SQL string.
        cond: str | None = None
        if block.get("type") == "filter":
            cond = block.get("condition")
        if not cond:
            cond = node.config.get("__filter_expr")
        cond = cond or "TRUE"
        return (
            f"# filter: {node.name}\n"
            f'{var} = {src}.filter(F.expr("{escape_sql(cond)}"))'
        )
