"""Shared parser data shapes."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ParsedNode:
    """One Ab Initio component as it comes out of the .mp parser."""

    id: str
    name: str
    type: str
    properties: dict[str, Any] = field(default_factory=dict)
    # port name → (upstream_node_id, upstream_port_name)
    input_ports: dict[str, tuple[str, str]] = field(default_factory=dict)
    # port name → "output" (we only model the existence of named outputs)
    output_ports: list[str] = field(default_factory=list)


@dataclass
class ParsedEdge:
    from_id: str
    to_id: str
    from_port: str = "out"
    to_port: str = "in"


@dataclass
class ParsedGraph:
    """The result of ``mp_parser.parse_mp_*``."""

    pipeline_name: str
    nodes: list[ParsedNode] = field(default_factory=list)
    edges: list[ParsedEdge] = field(default_factory=list)
    params: dict[str, str] = field(default_factory=dict)
    # filename or DEFINE name → schema dict (filled by the caller from .dml)
    schemas_by_name: dict[str, Any] = field(default_factory=dict)
    # transform/filter block name → list of (col, expr) or (None, condition)
    transforms_by_name: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """JSON-serialisable form (used by API + Neo4j ingestion)."""
        return {
            "pipeline": {"name": self.pipeline_name},
            "params": self.params,
            "nodes": [
                {
                    "id": n.id,
                    "name": n.name,
                    "type": n.type,
                    "properties": n.properties,
                    "input_ports": {
                        port: {"node": up_id, "port": up_port}
                        for port, (up_id, up_port) in n.input_ports.items()
                    },
                    "output_ports": list(n.output_ports),
                }
                for n in self.nodes
            ],
            "edges": [
                {
                    "from": e.from_id,
                    "to": e.to_id,
                    "from_port": e.from_port,
                    "to_port": e.to_port,
                }
                for e in self.edges
            ],
            "schemas": self.schemas_by_name,
            "transforms": self.transforms_by_name,
        }
