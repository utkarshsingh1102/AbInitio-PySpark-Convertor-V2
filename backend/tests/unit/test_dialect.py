"""Cross-cutting dialect feature tests."""
from backend.parser.params import extract_params, interpolate, interpolate_all
import xml.etree.ElementTree as ET


def test_param_interpolate_basic():
    assert interpolate("hello ${X}", {"X": "world"}) == "hello world"


def test_param_interpolate_recursive_two_levels():
    # ${A} → ${B}, ${B} → final
    assert interpolate("${A}", {"A": "${B}", "B": "leaf"}) == "leaf"


def test_param_interpolate_unknown_var_left_alone():
    assert interpolate("got ${UNKNOWN}", {}) == "got ${UNKNOWN}"


def test_extract_params_attribute_form():
    root = ET.fromstring(
        '<graph><parameters><param name="X" value="1"/><param name="Y" value="2"/></parameters></graph>'
    )
    assert extract_params(root) == {"X": "1", "Y": "2"}


def test_interpolate_all_walks_dict():
    out = interpolate_all({"a": "${X}", "b": ["${X}", 1]}, {"X": "v"})
    assert out == {"a": "v", "b": ["v", 1]}


def test_dml_dash_comment_in_xfr_is_stripped():
    from backend.parser.xfr_parser import parse_xfr_string
    src = """\
-- top comment
TRANSFORM t BEGIN
    -- field comment
    out.x = in.y;  -- trailing
END
"""
    blocks = parse_xfr_string(src)
    assert blocks["t"]["assignments"] == [("x", "`y`")]


def test_mp_lt_in_attribute_value():
    from backend.parser.mp_parser import parse_mp_string
    src = """\
<graph name="g">
  <component id="n" type="Filter">
    <property name="condition" value="x <= 5"/>
    <port name="in" type="input"/>
  </component>
</graph>"""
    g = parse_mp_string(src)
    assert g.nodes[0].properties["condition"] == "x <= 5"
