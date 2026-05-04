"""LookupFile → like InputFile but tagged for broadcast usage downstream.

Code-gen wise, identical to InputFile (we read the file). The Lookup
component wraps it with ``F.broadcast(...)`` at join time.
"""
from __future__ import annotations

from ..ir.models import IRNode
from ._emit_helpers import schema_dict_to_struct_code
from .base import ComponentPlugin, EmitContext, register


@register
class LookupFilePlugin(ComponentPlugin):
    component_type = "LookupFile"
    ir_type = "read"

    def emit_pyspark(self, node: IRNode, ctx: EmitContext) -> str:
        var = ctx.df_var(node.id)
        sv = ctx.schema_var(node.id)
        path = node.config.get("filename") or node.config.get("path") or ""
        fmt = node.config.get("file_format") or node.config.get("format") or "parquet"
        schema_code = schema_dict_to_struct_code(node.schema)
        return (
            f"# lookup_file: {node.name}\n"
            f"{sv} = {schema_code}\n"
            f"{var} = (\n"
            f"    spark.read\n"
            f"        .schema({sv})\n"
            f"        .format({fmt!r})\n"
            f"        .load({path!r})\n"
            f")  # broadcast applied at lookup site"
        )
