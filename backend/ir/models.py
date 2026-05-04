"""IR (Intermediate Representation) data models.

Built from Neo4j queries — never from the parser directly. Plugins (under
``backend.components``) own the type→IR mapping; this module just defines
the shape.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class IRNode:
    id: str
    name: str
    component_type: str           # Ab Initio name: "Reformat", "Join", etc.
    ir_type: str                  # plugin-supplied logical type
    inputs: list[str] = field(default_factory=list)        # ordered upstream ids
    outputs: list[str] = field(default_factory=list)       # downstream ids
    port_inputs: dict[str, str] = field(default_factory=dict)  # port → upstream id
    fan_out: int = 0
    schema: Any = None            # resolved DML schema dict for this node
    config: dict[str, Any] = field(default_factory=dict)
    params: dict[str, str] = field(default_factory=dict)   # pipeline-level params (interpolated)


class CyclicGraphError(Exception):
    """Raised when a pipeline DAG contains at least one cycle."""
