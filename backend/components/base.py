"""Plugin registry for Ab Initio component types.

A `ComponentPlugin` knows how to:
  - read a component's properties out of the parsed `.mp` (parse_props)
  - lower it into an IRNode (to_ir)
  - emit the PySpark code block for it (emit_pyspark)

Plugins self-register by being decorated with ``@register``. Importing the
``backend.components`` package triggers discovery, so listing this module
is enough — call sites just do ``from backend.components import REGISTRY``.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from ..ir.models import IRNode

REGISTRY: dict[str, "ComponentPlugin"] = {}


def register(plugin_cls):
    """Class decorator: instantiate and register under ``component_type``."""
    instance = plugin_cls()
    if instance.component_type in REGISTRY:
        raise ValueError(
            f"Duplicate component plugin for {instance.component_type!r}"
        )
    REGISTRY[instance.component_type] = instance
    return plugin_cls


@dataclass
class EmitContext:
    """State threaded through code emission for one pipeline."""

    pipeline_id: str
    params: dict[str, str] = field(default_factory=dict)
    # node_id → variable name in the generated script
    df_vars: dict[str, str] = field(default_factory=dict)
    # node_id → schema variable name (e.g. SCHEMA_node_01)
    schema_vars: dict[str, str] = field(default_factory=dict)
    # node_id → list of (port_name, upstream_node_id)
    inputs_by_port: dict[str, dict[str, str]] = field(default_factory=dict)
    # node_id → fan-out count (number of outgoing edges)
    fan_out: dict[str, int] = field(default_factory=dict)

    def df_var(self, node_id: str) -> str:
        """Return (and lazily allocate) the df variable name for a node."""
        if node_id not in self.df_vars:
            safe = node_id.replace("-", "_").replace(".", "_")
            self.df_vars[node_id] = f"df_{safe}"
        return self.df_vars[node_id]

    def schema_var(self, node_id: str) -> str:
        if node_id not in self.schema_vars:
            safe = node_id.replace("-", "_").replace(".", "_")
            self.schema_vars[node_id] = f"SCHEMA_{safe}"
        return self.schema_vars[node_id]

    def upstream(self, node: IRNode, port: str | None = None) -> str:
        """Return the df-var for a node's input.

        If ``port`` is given, look it up by port name; otherwise use the first
        entry in ``IRNode.inputs``.
        """
        if port is not None:
            ports = self.inputs_by_port.get(node.id, {})
            up_id = ports.get(port)
            if up_id is None:
                raise ValueError(
                    f"Node {node.id!r} has no input on port {port!r}"
                )
            return self.df_var(up_id)
        if not node.inputs:
            raise ValueError(f"Node {node.id!r} has no inputs")
        return self.df_var(node.inputs[0])


class ComponentPlugin(ABC):
    """Abstract base class for an Ab Initio component handler."""

    #: Ab Initio component type as it appears in the `.mp` `type=` attribute.
    component_type: str = ""
    #: Logical IR type (read | transform | filter | join | aggregate | write | ...).
    ir_type: str = ""

    def parse_props(self, raw: dict[str, Any], params: dict[str, str]) -> dict[str, Any]:
        """Normalize component properties into IRNode.config form.

        Default implementation passes raw through unchanged. Override to
        do component-specific massaging (e.g. parse a ``join_key`` CSV).
        """
        return dict(raw)

    @abstractmethod
    def emit_pyspark(self, node: IRNode, ctx: EmitContext) -> str:
        """Return the PySpark code block for this node (no leading indent)."""
        raise NotImplementedError

    # Optional hook: subclasses can override to inject spark-submit flags
    # or pre/post-run shell commands into the generated .ksh wrapper.
    def emit_ksh_hint(self, node: IRNode, ctx: EmitContext) -> str | None:
        return None
