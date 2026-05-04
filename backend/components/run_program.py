"""RunProgram → shell-out via ``subprocess.run`` from inside the script.

For most ETL the program runs *outside* spark; we shell out before the
next stage. The component contributes zero data flow: it's a side effect.
"""
from __future__ import annotations

from ..ir.models import IRNode
from .base import ComponentPlugin, EmitContext, register


@register
class RunProgramPlugin(ComponentPlugin):
    component_type = "RunProgram"
    ir_type = "side_effect"

    def emit_pyspark(self, node: IRNode, ctx: EmitContext) -> str:
        cmd = node.config.get("command") or node.config.get("program") or "echo noop"
        return (
            f"# run_program: {node.name}\n"
            f"import subprocess as _sp\n"
            f"_sp.run({cmd!r}, shell=True, check=True)"
        )

    def emit_ksh_hint(self, node, ctx):
        cmd = node.config.get("command") or node.config.get("program")
        return cmd
