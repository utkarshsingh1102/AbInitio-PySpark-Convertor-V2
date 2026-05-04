"""Neo4j ingestion: write a ParsedGraph + DML schemas + xfr blocks.

Idempotent — safe to re-run on the same pipeline_id.

Schema model:

    (:Pipeline {id, name, params})
        -[:HAS_COMPONENT]->
    (:Component {id, name, type, properties, transform_block?})
        -[:USES_SCHEMA]->
    (:Schema {id, name, fields})

    (:Component) -[:FLOWS_TO {from_port, to_port}]-> (:Component)
"""
from __future__ import annotations

import json
from typing import Any

from ..parser.dml_parser import resolve as resolve_schema
from ..parser.types import ParsedGraph
from .client import Neo4jClient


def ingest_pipeline(
    client: Neo4jClient,
    pipeline_id: str,
    parsed: ParsedGraph,
    schemas: dict[str, dict[str, Any]] | None = None,
    transforms: dict[str, Any] | None = None,
) -> str:
    """Write the full pipeline to Neo4j. Returns the pipeline_id.

    Idempotent: if the pipeline_id already exists, its components +
    schemas are deleted first so we never accumulate stale edges from
    a previous ingestion.
    """
    client.ensure_indexes()
    schemas = schemas or {}
    transforms = transforms or {}

    delete_pipeline(client, pipeline_id)
    _ingest_pipeline_node(client, pipeline_id, parsed)
    _ingest_schemas(client, pipeline_id, schemas)
    _ingest_components(client, pipeline_id, parsed, schemas, transforms)
    _ingest_edges(client, parsed, pipeline_id)
    return pipeline_id


def _ingest_pipeline_node(client: Neo4jClient, pipeline_id: str, parsed: ParsedGraph) -> None:
    client.run_write(
        """
        MERGE (p:Pipeline {id: $id})
        SET p.name = $name, p.params = $params
        """,
        id=pipeline_id,
        name=parsed.pipeline_name,
        params=json.dumps(parsed.params),
    )


def _ingest_schemas(client: Neo4jClient, pipeline_id: str, schemas: dict[str, dict[str, Any]]) -> None:
    for name, schema in schemas.items():
        sid = f"{pipeline_id}:{name}"
        client.run_write(
            """
            MERGE (s:Schema {id: $sid})
            SET s.name = $name, s.fields = $fields, s.pipeline_id = $pid
            """,
            sid=sid,
            name=name,
            fields=json.dumps(schema),
            pid=pipeline_id,
        )


def _ingest_components(
    client: Neo4jClient,
    pipeline_id: str,
    parsed: ParsedGraph,
    schemas: dict[str, dict[str, Any]],
    transforms: dict[str, Any],
) -> None:
    for node in parsed.nodes:
        props = dict(node.properties)
        # Embed the named transform/filter block onto the component if present.
        block_name = props.get("transform_file")
        if block_name and block_name in transforms:
            props["__transform_block"] = json.dumps(transforms[block_name])
        elif block_name:
            # also try basename (transform_file may be `customer.xfr` while
            # block name is `customer`).
            base = block_name.rsplit(".", 1)[0]
            if base in transforms:
                props["__transform_block"] = json.dumps(transforms[base])

        client.run_write(
            """
            MATCH (p:Pipeline {id: $pid})
            MERGE (c:Component {id: $cid, pipeline_id: $pid})
            SET c.name = $name,
                c.type = $type,
                c.properties = $properties,
                c.input_ports = $input_ports,
                c.output_ports = $output_ports
            MERGE (p)-[:HAS_COMPONENT]->(c)
            """,
            pid=pipeline_id,
            cid=node.id,
            name=node.name,
            type=node.type,
            properties=json.dumps(props),
            input_ports=json.dumps(
                {k: {"node": up_id, "port": up_port}
                 for k, (up_id, up_port) in node.input_ports.items()}
            ),
            output_ports=json.dumps(node.output_ports),
        )

        # Link to schema (resolved by name from the per-pipeline registry).
        schema_ref = props.get("schema")
        if schema_ref:
            resolved = resolve_schema(schemas, schema_ref)
            if resolved is not None:
                # Map back to the dict key
                schema_name = next(
                    (k for k, v in schemas.items() if v is resolved),
                    schema_ref.replace(".dml", ""),
                )
                sid = f"{pipeline_id}:{schema_name}"
                client.run_write(
                    """
                    MATCH (c:Component {id: $cid, pipeline_id: $pid})
                    MATCH (s:Schema {id: $sid})
                    MERGE (c)-[:USES_SCHEMA]->(s)
                    """,
                    cid=node.id,
                    sid=sid,
                    pid=pipeline_id,
                )


def _ingest_edges(client: Neo4jClient, parsed: ParsedGraph, pipeline_id: str) -> None:
    for e in parsed.edges:
        client.run_write(
            """
            MATCH (a:Component {id: $from, pipeline_id: $pid})
            MATCH (b:Component {id: $to,   pipeline_id: $pid})
            MERGE (a)-[r:FLOWS_TO {from_port: $fp, to_port: $tp}]->(b)
            """,
            **{
                "from": e.from_id,
                "to": e.to_id,
                "fp": e.from_port,
                "tp": e.to_port,
                "pid": pipeline_id,
            },
        )


def delete_pipeline(client: Neo4jClient, pipeline_id: str) -> None:
    """Remove a pipeline and all attached nodes (components, schemas)."""
    client.run_write(
        """
        MATCH (p:Pipeline {id: $pid})-[:HAS_COMPONENT]->(c:Component)
        DETACH DELETE c
        """,
        pid=pipeline_id,
    )
    client.run_write(
        "MATCH (s:Schema {pipeline_id: $pid}) DETACH DELETE s",
        pid=pipeline_id,
    )
    client.run_write(
        "MATCH (p:Pipeline {id: $pid}) DETACH DELETE p",
        pid=pipeline_id,
    )
