"""SQL → native PySpark API translator + the E7 rule wiring."""
from backend.codegen.expr_to_native import to_native
from backend.codegen.rules.expression import RewriteExprToNativeAPI
from .conftest import filter_node, fresh_report, transform_node


# ── translator ────────────────────────────────────────────────────────────


def test_column_ref():
    assert to_native("`name`") == "F.col('name')"


def test_arithmetic_lowered_to_python_operators():
    assert to_native("(`age` + 1)") == "(F.col('age') + F.lit(1))"


def test_function_call_lowered_to_F_dot():
    assert to_native("UPPER(`name`)") == "F.upper(F.col('name'))"


def test_nested_function_calls():
    assert to_native("LOWER(TRIM(`email`))") == "F.lower(F.trim(F.col('email')))"


def test_to_date_format_arg_is_plain_str():
    out = to_native("TO_DATE(`d`, 'yyyy-MM-dd')")
    assert out == "F.to_date(F.col('d'), 'yyyy-MM-dd')"


def test_date_format_format_arg_is_plain_str():
    out = to_native("DATE_FORMAT(`d`, 'yyyy-MM')")
    assert out == "F.date_format(F.col('d'), 'yyyy-MM')"


def test_cast_lowered_to_dot_cast():
    out = to_native("CAST((`a` * 1.18) AS DECIMAL(12, 2))")
    assert out == "(F.col('a') * F.lit(1.18)).cast(DecimalType(12, 2))"


def test_case_when_to_when_otherwise_chain():
    out = to_native(
        "(CASE WHEN (`p` >= 5000) THEN 'GOLD' "
        "ELSE (CASE WHEN (`p` >= 1000) THEN 'SILVER' ELSE 'BRONZE' END) END)"
    )
    # Chained CASE → chained .when().when().otherwise()
    assert out.startswith("F.when(")
    assert out.count(".when(") == 2
    assert out.endswith(".otherwise(F.lit('BRONZE'))")


def test_is_null_to_dot_method():
    assert to_native("(`x` IS NULL)") == "(F.col('x').isNull())"


def test_is_not_null_to_dot_method():
    assert to_native("(`x` IS NOT NULL)") == "(F.col('x').isNotNull())"


def test_and_or_use_bitwise_operators():
    out = to_native("((`a` > 0) AND (`b` < 10))")
    assert "&" in out
    assert "|" not in out


def test_concat_function():
    assert to_native("CONCAT(`a`, ' ', `b`)") == \
        "F.concat(F.col('a'), F.lit(' '), F.col('b'))"


def test_unsupported_returns_none():
    # We don't translate window functions — should fall back.
    assert to_native("SUM(`x`) OVER (PARTITION BY `k`)") is None


def test_empty_returns_none():
    assert to_native("") is None
    assert to_native(None) is None


# ── E7 rule wiring ────────────────────────────────────────────────────────


def test_rule_marks_assignments_as_native():
    n = transform_node("t", [
        ("up", "UPPER(`name`)"),
        ("aged", "(`age` + 1)"),
    ])
    out = RewriteExprToNativeAPI()([n], fresh_report())
    assigns = out[0].config["block"]["assignments"]
    for col, expr in assigns:
        assert isinstance(expr, dict)
        assert expr["__native_expr__"] is True
    code_by_col = {c: e["code"] for c, e in assigns}
    assert "F.upper" in code_by_col["up"]
    assert "F.col('age') + F.lit(1)" in code_by_col["aged"]


def test_rule_skips_unsupported_expressions():
    n = transform_node("t", [
        ("ok", "UPPER(`name`)"),
        ("nope", "ROW_NUMBER() OVER (ORDER BY `x`)"),
    ])
    out = RewriteExprToNativeAPI()([n], fresh_report())
    assigns = dict(out[0].config["block"]["assignments"])
    assert isinstance(assigns["ok"], dict) and assigns["ok"]["__native_expr__"]
    # Unsupported left as plain string — codegen falls back to F.expr
    assert isinstance(assigns["nope"], str)


def test_rule_translates_filter_block_condition():
    f = filter_node("f", "(`age` > 18)")
    out = RewriteExprToNativeAPI()([f], fresh_report())
    block = out[0].config["block"]
    assert "native_condition" in block
    assert "F.col('age')" in block["native_condition"]
