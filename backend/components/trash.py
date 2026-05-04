"""Trash → ``df.write.format('noop').mode('overwrite').save()`` (data sink → /dev/null).

Useful as a sink for branches you want to validate (run the lineage)
without persisting output.
"""
from __future__ import annotations

from ..ir.models import IRNode
from .base import ComponentPlugin, EmitContext, register


@register
class TrashPlugin(ComponentPlugin):
    component_type = "Trash"
    ir_type = "write"

    def emit_pyspark(self, node: IRNode, ctx: EmitContext) -> str:
        if not node.inputs:
            return f"# [error] trash {node.name} has no input"
        src = ctx.upstream(node)
        return (
            f"# trash: {node.name}\n"
            f"({src}.write.format('noop').mode('overwrite').save())"
        )
