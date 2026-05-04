"""Tests for the realistic-dialect .xfr parser."""
import pytest

from backend.parser.xfr_parser import parse_filter_condition, parse_xfr_string


def _first_assignment(blocks, block_name):
    return blocks[block_name]["assignments"][0]


def test_transform_block():
    src = """\
TRANSFORM t1
BEGIN
    out.x = in.y;
    out.z = in.y + 1;
END
"""
    blocks = parse_xfr_string(src)
    assert "t1" in blocks
    assert blocks["t1"]["type"] == "transform"
    assert blocks["t1"]["assignments"] == [
        ("x", "`y`"),
        ("z", "(`y` + 1)"),
    ]


def test_filter_block_with_condition():
    src = """\
FILTER f1
BEGIN
    CONDITION: in.age > 18 and in.country = "US";
END
"""
    blocks = parse_xfr_string(src)
    assert blocks["f1"]["type"] == "filter"
    assert "AND" in blocks["f1"]["condition"]
    assert "'US'" in blocks["f1"]["condition"]


def test_string_concat_lowering():
    src = "TRANSFORM t BEGIN out.full = in.first + \" \" + in.last; END"
    blocks = parse_xfr_string(src)
    expr = blocks["t"]["assignments"][0][1]
    assert expr.startswith("CONCAT(")


def test_decimal_cast():
    src = 'TRANSFORM t BEGIN out.x = decimal(in.amt * 1.18, 12, 2); END'
    blocks = parse_xfr_string(src)
    expr = blocks["t"]["assignments"][0][1]
    assert "CAST(" in expr and "DECIMAL(12, 2)" in expr


def test_string_to_date_format_translation():
    src = 'TRANSFORM t BEGIN out.d = string_to_date(in.s, "YYYY-MM-DD"); END'
    blocks = parse_xfr_string(src)
    expr = blocks["t"]["assignments"][0][1]
    assert "TO_DATE(" in expr and "'yyyy-MM-dd'" in expr


def test_string_to_datetime_minutes_disambiguation():
    src = 'TRANSFORM t BEGIN out.d = string_to_datetime(in.s, "YYYY-MM-DD HH:MM:SS"); END'
    blocks = parse_xfr_string(src)
    expr = blocks["t"]["assignments"][0][1]
    assert "'yyyy-MM-dd HH:mm:ss'" in expr


def test_else_if_chain():
    src = """\
TRANSFORM t BEGIN
    out.tier = if (in.p >= 5000) "GOLD" else if (in.p >= 1000) "SILVER" else "BRONZE";
END
"""
    blocks = parse_xfr_string(src)
    expr = blocks["t"]["assignments"][0][1]
    # nested CASE WHEN
    assert expr.count("CASE WHEN") == 2


def test_single_eq_equality():
    src = 'TRANSFORM t BEGIN out.b = in.x = 0; END'
    blocks = parse_xfr_string(src)
    expr = blocks["t"]["assignments"][0][1]
    assert "(`x` = 0)" == expr


def test_out_self_reference():
    src = """\
TRANSFORM t BEGIN
    out.a = in.x * 2;
    out.b = out.a + 1;
END
"""
    blocks = parse_xfr_string(src)
    assigns = blocks["t"]["assignments"]
    assert assigns[0] == ("a", "(`x` * 2)")
    assert assigns[1] == ("b", "(`a` + 1)")


def test_null_literal():
    src = 'TRANSFORM t BEGIN out.x = null; END'
    blocks = parse_xfr_string(src)
    assert blocks["t"]["assignments"][0] == ("x", "NULL")


def test_filter_condition_helper():
    assert parse_filter_condition("age > 18") == "(`age` > 18)"
    assert parse_filter_condition("age >= 18 and balance > 0") == "((`age` >= 18) AND (`balance` > 0))"
    assert parse_filter_condition("not is_null(name)") == "(NOT (`name` IS NULL))"


def test_complex_example_parses():
    from pathlib import Path
    from backend.parser.xfr_parser import parse_xfr_file
    p = Path(__file__).resolve().parents[3] / "examples" / "complex_pipeline" / "customer_order_enrichment.xfr"
    blocks = parse_xfr_file(p)
    assert set(blocks.keys()) == {
        "normalize_customer", "normalize_order", "enrich_record",
        "filter_high_value", "filter_standard", "apply_discount",
    }
    # spot-check string concat in normalize_customer
    nc = blocks["normalize_customer"]
    full_name = next(e for c, e in nc["assignments"] if c == "full_name")
    assert "CONCAT(" in full_name
