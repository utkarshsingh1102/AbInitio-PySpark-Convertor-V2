"""Reformat → idiomatic chained PySpark expression.

Code paths:

  - ``config["passthrough"] is True``
        ``df_<id> = df_<src>``  — single alias line.

  - Otherwise, the assignment list is grouped into the smallest number of
    ``withColumns({...})`` batches that respects ``out.X`` self-references
    (a column referencing one defined earlier in the same block forces a
    new batch). Single-column batches use ``.withColumn(name, expr)``.

  - Output is emitted as ONE chained expression:

        df_node_03 = (
            df_node_01
            .withColumns({...})
            .select('a', 'b', 'c')
        )

  - Per-assignment value rendering:
      * ``str``                              → ``F.expr("…")``
      * ``{"__native_expr__": True, ...}``   → the native code verbatim
      * ``{"__typed_null__":  True, ...}``   → ``F.lit(None).cast(<type>)``

  - The final ``.select(*output_cols)`` enforces Reformat semantics
    (output schema = assigned columns), filtering ``__cse_*`` temps that
    came from the CSE rule.
"""
from __future__ import annotations

import re
from typing import Any

from ..ir.models import IRNode
from ._emit_helpers import escape_sql
from .base import ComponentPlugin, EmitContext, register

_BACKTICK_REF_RE = re.compile(r"`([A-Za-z_][A-Za-z0-9_]*)`")
_NATIVE_COL_RE = re.compile(r"F\.col\(['\"]([A-Za-z_][A-Za-z0-9_]*)['\"]\)")


@register
class ReformatPlugin(ComponentPlugin):
    component_type = "Reformat"
    ir_type = "transform"

    def emit_pyspark(self, node: IRNode, ctx: EmitContext) -> str:
        if not node.inputs:
            return f"# [error] reformat {node.name} has no input"
        src = ctx.upstream(node)
        var = ctx.df_var(node.id)

        if node.config.get("passthrough"):
            return f"# transform: {node.name} (passthrough)\n{var} = {src}"

        block = node.config.get("block") or {}
        assignments = block.get("assignments") or []
        default_out = [c for c, _ in assignments if not c.startswith("__cse_")]
        out_cols = [c for c in (node.config.get("output_columns") or default_out)
                    if not c.startswith("__cse_")]

        if not assignments:
            return f"# transform: {node.name} (empty)\n{var} = {src}"

        batches = _group_into_batches(assignments)

        # Build the chained call: src.withColumns({...}).withColumns({...}).select(...)
        chain_steps: list[str] = []
        for batch in batches:
            if len(batch) == 1:
                col, expr = batch[0]
                chain_steps.append(
                    f".withColumn({col!r}, {_render_value(expr)})"
                )
            else:
                items = [f"{col!r}: {_render_value(expr)}" for col, expr in batch]
                if sum(len(i) for i in items) <= 100:
                    chain_steps.append(f".withColumns({{{', '.join(items)}}})")
                else:
                    inner = ",\n        ".join(items)
                    chain_steps.append(f".withColumns({{\n        {inner},\n    }})")
        if out_cols:
            chain_steps.append(
                f".select({', '.join(repr(c) for c in out_cols)})"
            )

        # Render as one chained expression
        steps_str = "\n    ".join(chain_steps)
        return (
            f"# transform: {node.name}\n"
            f"{var} = (\n"
            f"    {src}\n"
            f"    {steps_str}\n"
            f")"
        )


# ── helpers ────────────────────────────────────────────────────────────────


def _render_value(expr: Any) -> str:
    """Render an assignment RHS into a Column expression."""
    if isinstance(expr, dict):
        if expr.get("__native_expr__"):
            return expr["code"]
        if expr.get("__typed_null__"):
            return f"F.lit(None).cast({expr['type_code']})"
    return f'F.expr("{escape_sql(str(expr))}")'


def _refs(expr: Any) -> set[str]:
    """Column names this expression references (used for batch splitting)."""
    if isinstance(expr, str):
        return set(_BACKTICK_REF_RE.findall(expr))
    if isinstance(expr, dict):
        if expr.get("__native_expr__"):
            return set(_NATIVE_COL_RE.findall(expr.get("code", "")))
        # typed null doesn't reference any column
    return set()


def _group_into_batches(
    assignments: list[tuple[str, Any]],
) -> list[list[tuple[str, Any]]]:
    """Split assignments so a column referencing a previously-assigned
    column lives in a later batch (Spark 3.3 ``withColumns`` evaluates
    siblings against the *input* DataFrame).
    """
    batches: list[list[tuple[str, Any]]] = []
    current: list[tuple[str, Any]] = []

    for col, expr in assignments:
        refs = _refs(expr)
        if refs & {c for c, _ in current}:
            batches.append(current)
            current = []
        current.append((col, expr))

    if current:
        batches.append(current)
    return batches
