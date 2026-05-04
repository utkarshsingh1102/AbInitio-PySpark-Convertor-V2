"""Tests for the .xfr function-mapping table + format translation."""
import pytest

from backend.parser.xfr_functions import FN_TABLE, render_fn, translate_format


def test_format_translates_basic_date():
    assert translate_format("YYYY-MM-DD") == "yyyy-MM-dd"


def test_format_translates_datetime():
    assert translate_format("YYYY-MM-DD HH:MM:SS") == "yyyy-MM-dd HH:mm:ss"


def test_format_unchanged_lowercase():
    assert translate_format("yyyy-MM-dd") == "yyyy-MM-dd"


def test_render_known_function():
    out = render_fn("upper", ["`x`"])
    assert out == "UPPER(`x`)"


def test_render_decimal_cast():
    out = render_fn("decimal", ["`x`", "12", "2"])
    assert out == "CAST(`x` AS DECIMAL(12, 2))"


def test_render_string_to_date_translates_format():
    out = render_fn("string_to_date", ["`x`", "'YYYY-MM-DD'"])
    assert out == "TO_DATE(`x`, 'yyyy-MM-dd')"


def test_render_date_diff_3arg():
    out = render_fn("date_diff", ["`a`", "`b`", "'days'"])
    assert out == "DATEDIFF(`a`, `b`)"


def test_render_unknown_returns_none():
    assert render_fn("__unknown__", ["x"]) is None


def test_render_variadic_coalesce():
    out = render_fn("coalesce", ["`a`", "`b`", "`c`"])
    assert out == "COALESCE(`a`, `b`, `c`)"


def test_fn_table_has_all_required():
    required = {
        "upper", "lower", "trim", "string_length",
        "is_null", "coalesce", "decimal",
        "string_to_date", "string_to_datetime", "date_diff",
        "abs", "round", "substring",
    }
    missing = required - set(FN_TABLE)
    assert not missing, f"Missing from FN_TABLE: {missing}"
