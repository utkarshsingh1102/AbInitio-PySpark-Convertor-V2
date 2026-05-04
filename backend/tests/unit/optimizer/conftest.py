"""Shared fixtures for optimizer tests."""
from __future__ import annotations

from backend.codegen.rules.base import OptimizationReport
from backend.ir.models import IRNode


def transform_node(node_id: str, assignments, schema=None, inputs=None,
                   fan_out: int = 0, name: str | None = None):
    return IRNode(
        id=node_id, name=name or node_id,
        component_type="Reformat", ir_type="transform",
        inputs=list(inputs or []),
        outputs=[],
        port_inputs={p: u for p, u in zip(["in"], inputs or [])},
        fan_out=fan_out,
        schema=schema,
        config={"block": {"type": "transform", "assignments": list(assignments)}},
    )


def filter_node(node_id: str, condition: str, inputs=None, fan_out: int = 0):
    return IRNode(
        id=node_id, name=node_id,
        component_type="Filter", ir_type="filter",
        inputs=list(inputs or []),
        outputs=[],
        port_inputs={p: u for p, u in zip(["in"], inputs or [])},
        fan_out=fan_out,
        config={"block": {"type": "filter", "condition": condition}},
    )


def read_node(node_id: str, path: str, schema=None, fan_out: int = 1):
    return IRNode(
        id=node_id, name=node_id,
        component_type="InputFile", ir_type="read",
        outputs=[], inputs=[],
        port_inputs={},
        fan_out=fan_out,
        schema=schema,
        config={"filename": path},
    )


def write_node(node_id: str, path: str, inputs, fmt: str = "parquet",
               mode: str = "overwrite", params=None):
    return IRNode(
        id=node_id, name=node_id,
        component_type="OutputFile", ir_type="write",
        inputs=list(inputs),
        outputs=[],
        port_inputs={"in": inputs[0]} if inputs else {},
        fan_out=0,
        config={"filename": path, "file_format": fmt, "mode": mode},
        params=params or {},
    )


def join_node(node_id: str, left: str, right: str, key: str = "id",
              how: str = "inner"):
    return IRNode(
        id=node_id, name=node_id,
        component_type="Join", ir_type="join",
        inputs=[left, right],
        outputs=[],
        port_inputs={"in_left": left, "in_right": right},
        fan_out=0,
        config={"join_key": key, "join_type": how},
    )


def link(parent, child):
    parent.outputs.append(child.id)


def fresh_report() -> OptimizationReport:
    return OptimizationReport()
