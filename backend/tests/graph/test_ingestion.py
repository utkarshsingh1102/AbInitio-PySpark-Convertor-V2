"""Neo4j ingestion + query tests. Skipped if Neo4j is unreachable."""
import pytest

from backend.graph import queries as Q
from backend.graph.ingestion import delete_pipeline, ingest_pipeline
from backend.parser.types import ParsedEdge, ParsedGraph, ParsedNode


def _sample() -> ParsedGraph:
    return ParsedGraph(
        pipeline_name="test_pipe",
        nodes=[
            ParsedNode(id="n1", name="In", type="InputFile",
                       properties={"filename": "/in"}, input_ports={}, output_ports=["out"]),
            ParsedNode(id="n2", name="Tx", type="Reformat",
                       properties={"transform_file": "tx"},
                       input_ports={"in": ("n1", "out")}, output_ports=["out"]),
            ParsedNode(id="n3", name="Ft", type="Filter",
                       properties={"condition": "age > 18"},
                       input_ports={"in": ("n2", "out")}, output_ports=["out"]),
            ParsedNode(id="n4", name="Out", type="OutputFile",
                       properties={"filename": "/out"},
                       input_ports={"in": ("n3", "out")}, output_ports=[]),
        ],
        edges=[
            ParsedEdge("n1", "n2"), ParsedEdge("n2", "n3"), ParsedEdge("n3", "n4"),
        ],
        params={"X": "1"},
    )


def test_ingest_creates_nodes_and_edges(neo4j_client):
    pid = "test_ingest"
    delete_pipeline(neo4j_client, pid)
    try:
        ingest_pipeline(neo4j_client, pid, _sample())
        dag = Q.get_pipeline_dag(neo4j_client, pid)
        assert {n["id"] for n in dag["nodes"]} == {"n1", "n2", "n3", "n4"}
        assert {(e["from"], e["to"]) for e in dag["edges"]} == {
            ("n1", "n2"), ("n2", "n3"), ("n3", "n4"),
        }
        assert dag["params"] == {"X": "1"}
    finally:
        delete_pipeline(neo4j_client, pid)


def test_execution_order_topo_sorted(neo4j_client):
    pid = "test_order"
    delete_pipeline(neo4j_client, pid)
    try:
        ingest_pipeline(neo4j_client, pid, _sample())
        order = Q.get_execution_order(neo4j_client, pid)
        assert [n["id"] for n in order] == ["n1", "n2", "n3", "n4"]
    finally:
        delete_pipeline(neo4j_client, pid)


def test_cycle_detection_raises(neo4j_client):
    pid = "test_cycle"
    delete_pipeline(neo4j_client, pid)
    try:
        cyclic = ParsedGraph(
            pipeline_name="cyc",
            nodes=[
                ParsedNode(id="a", name="A", type="Reformat", properties={}),
                ParsedNode(id="b", name="B", type="Reformat", properties={}),
            ],
            edges=[ParsedEdge("a", "b"), ParsedEdge("b", "a")],
        )
        ingest_pipeline(neo4j_client, pid, cyclic)
        assert Q.detect_cycles(neo4j_client, pid) is True
        with pytest.raises(Q.CyclicGraphError):
            Q.get_execution_order(neo4j_client, pid)
    finally:
        delete_pipeline(neo4j_client, pid)


def test_per_node_schema_attached(neo4j_client):
    pid = "test_schema"
    delete_pipeline(neo4j_client, pid)
    try:
        parsed = _sample()
        # set a schema reference on a component
        parsed.nodes[0].properties["schema"] = "customer"
        schemas = {"customer": {"type": "record", "fields": [
            {"name": "id", "type": "integer", "args": [], "nullable": False, "array": False},
        ]}}
        ingest_pipeline(neo4j_client, pid, parsed, schemas=schemas)
        s = Q.get_schema_for(neo4j_client, "n1")
        assert s is not None
        assert s["fields"][0]["name"] == "id"
    finally:
        delete_pipeline(neo4j_client, pid)
