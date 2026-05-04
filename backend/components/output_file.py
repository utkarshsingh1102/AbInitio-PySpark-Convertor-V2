"""OutputFile → ``df.write.mode(m).format(f).save(path)``.

Honors annotations from the optimizer:
  * ``config["coalesce"] = N``       — wraps with ``.coalesce(N)``
  * ``config["repartition"] = N``    — wraps with ``.repartition(N)``
  * ``config["partition_columns"]``  — emits ``.partitionBy(...)``
"""
from __future__ import annotations

from ..ir.models import IRNode
from .base import ComponentPlugin, EmitContext, register


@register
class OutputFilePlugin(ComponentPlugin):
    component_type = "OutputFile"
    ir_type = "write"

    def emit_pyspark(self, node: IRNode, ctx: EmitContext) -> str:
        if not node.inputs:
            return f"# [error] write {node.name} has no input"
        src = ctx.upstream(node)
        cfg = node.config
        path = cfg.get("filename") or cfg.get("path") or ""
        fmt = cfg.get("file_format") or cfg.get("format") or "parquet"
        mode = cfg.get("mode", "overwrite")

        coalesce_n = cfg.get("coalesce")
        repart_n = cfg.get("repartition")
        if coalesce_n:
            target = f"{src}.coalesce({int(coalesce_n)})"
        elif repart_n:
            target = f"{src}.repartition({int(repart_n)})"
        else:
            target = src

        partition_cols = cfg.get("partition_columns") or []
        partition_line = ""
        if partition_cols:
            partition_line = f"    .partitionBy({', '.join(repr(c) for c in partition_cols)})\n"

        return (
            f"# write: {node.name}\n"
            f"({target}.write\n"
            f"    .mode({mode!r})\n"
            f"{partition_line}"
            f"    .format({fmt!r})\n"
            f"    .save({path!r}))"
        )
