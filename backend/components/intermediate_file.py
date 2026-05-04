"""IntermediateFile → write-then-read parquet checkpoint.

Useful for breaking lineage / forcing materialisation between stages.
"""
from __future__ import annotations

from ..ir.models import IRNode
from .base import ComponentPlugin, EmitContext, register


@register
class IntermediateFilePlugin(ComponentPlugin):
    component_type = "IntermediateFile"
    ir_type = "checkpoint"

    def emit_pyspark(self, node: IRNode, ctx: EmitContext) -> str:
        if not node.inputs:
            return f"# [error] intermediate {node.name} has no input"
        src = ctx.upstream(node)
        var = ctx.df_var(node.id)
        path = node.config.get("filename") or f"/tmp/{node.id}.parquet"
        return (
            f"# intermediate: {node.name}\n"
            f"{src}.write.mode('overwrite').parquet({path!r})\n"
            f"{var} = spark.read.parquet({path!r})"
        )
