"""Tests for the realistic-dialect .mp parser."""
import pytest

from backend.parser.mp_parser import parse_mp_string

SAMPLE = """\
<graph name="p1">
  <parameters>
    <param name="IN"  value="/data/in.parquet"/>
    <param name="OUT" value="/data/out.parquet"/>
  </parameters>

  <component id="n1" name="In" type="InputFile">
    <property name="filename" value="${IN}"/>
    <port name="out" type="output"/>
  </component>

  <component id="n2" name="Out" type="OutputFile">
    <property name="filename" value="${OUT}"/>
    <port name="in" type="input" source="n1.out"/>
  </component>
</graph>
"""


def test_parses_pipeline_name():
    g = parse_mp_string(SAMPLE)
    assert g.pipeline_name == "p1"


def test_parses_components_without_wrapper():
    g = parse_mp_string(SAMPLE)
    assert [n.id for n in g.nodes] == ["n1", "n2"]
    assert g.nodes[0].type == "InputFile"


def test_interpolates_dollar_var():
    g = parse_mp_string(SAMPLE)
    assert g.nodes[0].properties["filename"] == "/data/in.parquet"
    assert g.nodes[1].properties["filename"] == "/data/out.parquet"


def test_extracts_edges_from_port_source():
    g = parse_mp_string(SAMPLE)
    assert len(g.edges) == 1
    e = g.edges[0]
    assert (e.from_id, e.to_id, e.from_port, e.to_port) == ("n1", "n2", "out", "in")


def test_handles_unescaped_lt_in_attribute():
    """Realistic .mp files put `<=` directly in attribute values."""
    src = """\
<graph name="p">
  <component id="n" name="F" type="Filter">
    <property name="condition" value="x <= 10"/>
    <port name="in" type="input"/>
  </component>
</graph>
"""
    g = parse_mp_string(src)
    assert g.nodes[0].properties["condition"] == "x <= 10"


def test_join_named_ports():
    src = """\
<graph name="p">
  <component id="A" type="InputFile"><port name="out" type="output"/></component>
  <component id="B" type="InputFile"><port name="out" type="output"/></component>
  <component id="J" type="Join">
    <port name="in_left"  type="input" source="A.out"/>
    <port name="in_right" type="input" source="B.out"/>
    <port name="out"      type="output"/>
  </component>
</graph>
"""
    g = parse_mp_string(src)
    join = next(n for n in g.nodes if n.id == "J")
    assert join.input_ports == {
        "in_left":  ("A", "out"),
        "in_right": ("B", "out"),
    }


def test_explicit_connections_block():
    src = """\
<graph name="p">
  <component id="A" type="InputFile"><port name="out" type="output"/></component>
  <component id="B" type="OutputFile"><port name="in" type="input"/></component>
  <connections>
    <edge from="A" to="B"/>
  </connections>
</graph>
"""
    g = parse_mp_string(src)
    assert len(g.edges) == 1
    assert (g.edges[0].from_id, g.edges[0].to_id) == ("A", "B")


def test_complex_example_parses():
    """The full complex_pipeline .mp must parse to 13 nodes / 12 edges."""
    from pathlib import Path
    from backend.parser.mp_parser import parse_mp_file
    p = Path(__file__).resolve().parents[3] / "examples" / "complex_pipeline" / "customer_order_enrichment.mp"
    g = parse_mp_file(p)
    assert len(g.nodes) == 13
    assert len(g.edges) == 12
    join = next(n for n in g.nodes if n.type == "Join")
    assert "in_left" in join.input_ports and "in_right" in join.input_ports
