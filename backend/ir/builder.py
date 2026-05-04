"""IR builder — turn a Neo4j pipeline into ``list[IRNode]`` in execution order.

Uses the plugin REGISTRY (under ``backend.components``) to look up the
correct ``ir_type`` for each component and to call ``parse_props`` for any
component-specific config normalisation.
"""
from __future__ import annotations

import json
import logging

from ..components import REGISTRY  # triggers plugin discovery on import
from ..graph import queries as Q
from ..graph.client import Neo4jClient
from .models import IRNode

logger = logging.getLogger(__name__)


def build_ir(client: Neo4jClient, pipeline_id: str) -> list[IRNode]:
    if Q.detect_cycles(client, pipeline_id):
        raise Q.CyclicGraphError(f"Pipeline {pipeline_id} contains a cycle")

    dag = Q.get_pipeline_dag(client, pipeline_id)
    ordered = Q.get_execution_order(client, pipeline_id)
    nodes_by_id = {n["id"]: n for n in dag["nodes"]}
    # Surface the pipeline name to codegen via params (used as Spark appName)
    params = dict(dag.get("params") or {})
    if dag.get("pipeline_name"):
        params.setdefault("PIPELINE_NAME", dag["pipeline_name"])

    incoming: dict[str, list[str]] = {n["id"]: [] for n in dag["nodes"]}
    outgoing: dict[str, list[str]] = {n["id"]: [] for n in dag["nodes"]}
    for e in dag["edges"]:
        outgoing.setdefault(e["from"], []).append(e["to"])
        incoming.setdefault(e["to"], []).append(e["from"])

    ir_nodes: list[IRNode] = []
    for node in ordered:
        cid = node["id"]
        comp_type = node["type"]
        plugin = REGISTRY.get(comp_type)
        if plugin is None:
            logger.warning(
                "No plugin registered for component type %r (node %s); "
                "emitting as 'unknown'", comp_type, cid,
            )
            ir_type = "unknown"
            cfg = dict(node.get("properties") or {})
        else:
            ir_type = plugin.ir_type
            cfg = plugin.parse_props(node.get("properties") or {}, dag.get("params") or {})

        # Pull the parsed transform/filter block onto the node config.
        block_json = cfg.pop("__transform_block", None)
        if block_json:
            try:
                block = json.loads(block_json)
                cfg["block"] = block
            except Exception:  # noqa: BLE001
                pass

        full = nodes_by_id[cid]
        port_inputs = {
            port: meta["node"] for port, meta in (full.get("input_ports") or {}).items()
        }

        ir_nodes.append(
            IRNode(
                id=cid,
                name=full["name"],
                component_type=comp_type,
                ir_type=ir_type,
                inputs=incoming.get(cid, []),
                outputs=outgoing.get(cid, []),
                port_inputs=port_inputs,
                fan_out=len(outgoing.get(cid, [])),
                schema=full.get("schema"),
                config=cfg,
                params=params,
            )
        )

    return ir_nodes
