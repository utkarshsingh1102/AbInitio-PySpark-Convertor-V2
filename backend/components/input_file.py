"""InputFile → ``spark.read.schema(...).format(f).load(path)``."""
from __future__ import annotations

from ..ir.models import IRNode
from ._emit_helpers import schema_dict_to_struct_code
from .base import ComponentPlugin, EmitContext, register


@register
class InputFilePlugin(ComponentPlugin):
    component_type = "InputFile"
    ir_type = "read"

    def emit_pyspark(self, node: IRNode, ctx: EmitContext) -> str:
        var = ctx.df_var(node.id)
        sv = ctx.schema_var(node.id)
        path = node.config.get("filename") or node.config.get("path") or ""
        fmt = node.config.get("file_format") or node.config.get("format") or "parquet"
        delimiter = node.config.get("delimiter")
        has_header = (node.config.get("has_header") or "false").lower() == "true"
        schema_code = schema_dict_to_struct_code(node.schema)

        opts: list[str] = []
        if fmt in ("delimited", "csv", "text") and delimiter:
            opts.append(f'.option("sep", {delimiter!r})')
            fmt = "csv"
        if has_header:
            opts.append('.option("header", "true")')
        opt_str = "".join(f"\n        {o}" for o in opts)

        lines = [
            f"# read: {node.name}",
            f"{sv} = {schema_code}",
            f"{var} = (",
            f"    spark.read",
            f"        .schema({sv}){opt_str}",
            f"        .format({fmt!r})",
            f"        .load({path!r})",
            f")",
        ]
        # ProjectionPruning (S2) — if some downstream column subset is
        # required, drop the rest at scan time.
        select_columns = node.config.get("select_columns")
        if select_columns:
            cols = ", ".join(repr(c) for c in select_columns)
            lines.append(
                f"{var} = {var}.select({cols})  # ProjectionPruning: keep {len(select_columns)}/{len(node.schema.get('fields', [])) if node.schema else '?'} cols"
            )
        # RepartitionBeforeShuffleJoin (W4)
        repart = node.config.get("repartition_on")
        if repart:
            lines.append(
                f"{var} = {var}.repartition(F.col({repart!r}))  # co-partition for sort-merge join"
            )
        return "\n".join(lines)
