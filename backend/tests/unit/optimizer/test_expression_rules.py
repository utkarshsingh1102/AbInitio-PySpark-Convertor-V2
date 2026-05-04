"""Stage 2 — expression-level rules."""
from backend.codegen.rules.expression import (
    DeduplicateCommonSubexpressions,
    FixDateTimeExpressions,
    NullSafeComparisonRewrite,
    RewriteUDFsToNativeFunctions,
    StripIdentityAssignments,
    TypeNullLiterals,
)
from .conftest import filter_node, fresh_report, read_node, transform_node


# ── StripIdentityAssignments ──────────────────────────────────────────────


def test_strip_identity_removes_passthrough_columns():
    n = transform_node("t", [
        ("id",   "`id`"),
        ("name", "UPPER(`name`)"),
    ])
    out = StripIdentityAssignments()([n], fresh_report())
    cols = [c for c, _ in out[0].config["block"]["assignments"]]
    assert cols == ["name"]
    assert out[0].config["output_columns"] == ["id", "name"]


# ── FixDateTimeExpressions ────────────────────────────────────────────────


def test_substring_1_7_on_timestamp_becomes_date_format():
    schema = {"fields": [
        {"name": "ts", "type": "datetime", "args": [], "nullable": True, "array": False}
    ]}
    r = read_node("r", "/x.parquet", schema=schema)
    n = transform_node("t", [("month", "SUBSTRING(`ts`, 1, 7)")], inputs=["r"])
    out = FixDateTimeExpressions()([r, n], fresh_report())
    expr = next(c for c in out if c.id == "t").config["block"]["assignments"][0][1]
    assert "DATE_FORMAT" in expr


def test_substring_1_4_on_date_becomes_year():
    schema = {"fields": [
        {"name": "d", "type": "date", "args": [], "nullable": True, "array": False}
    ]}
    r = read_node("r", "/x.parquet", schema=schema)
    n = transform_node("t", [("yr", "SUBSTRING(`d`, 1, 4)")], inputs=["r"])
    out = FixDateTimeExpressions()([r, n], fresh_report())
    expr = next(c for c in out if c.id == "t").config["block"]["assignments"][0][1]
    assert expr == "YEAR(`d`)"


def test_strip_meaningless_upper_on_date():
    schema = {"fields": [
        {"name": "d", "type": "date", "args": [], "nullable": True, "array": False}
    ]}
    r = read_node("r", "/x.parquet", schema=schema)
    n = transform_node("t", [("d2", "UPPER(`d`)")], inputs=["r"])
    report = fresh_report()
    out = FixDateTimeExpressions()([r, n], report)
    expr = next(c for c in out if c.id == "t").config["block"]["assignments"][0][1]
    assert expr == "`d`"
    assert any(e.severity == "warn" for e in report.warnings)


# ── TypeNullLiterals ──────────────────────────────────────────────────────


def test_typed_null_uses_decimal_type_from_schema():
    schema = {"fields": [
        {"name": "amt", "type": "decimal", "args": [10, 2], "nullable": True, "array": False}
    ]}
    n = transform_node("t", [("amt", "NULL")], schema=schema)
    out = TypeNullLiterals()([n], fresh_report())
    expr = out[0].config["block"]["assignments"][0][1]
    assert isinstance(expr, dict)
    assert expr["__typed_null__"] is True
    assert expr["type_code"] == "DecimalType(10, 2)"


def test_typed_null_for_all_null_coalesce():
    schema = {"fields": [
        {"name": "x", "type": "integer", "args": [], "nullable": True, "array": False}
    ]}
    n = transform_node("t", [("x", "COALESCE(NULL, NULL, NULL)")], schema=schema)
    out = TypeNullLiterals()([n], fresh_report())
    expr = out[0].config["block"]["assignments"][0][1]
    assert isinstance(expr, dict)
    assert expr["__typed_null__"] is True


# ── RewriteUDFsToNativeFunctions ──────────────────────────────────────────


def test_rewrite_string_length_to_length():
    n = transform_node("t", [("L", "string_length(`name`)")])
    out = RewriteUDFsToNativeFunctions()([n], fresh_report())
    expr = out[0].config["block"]["assignments"][0][1]
    assert expr == "LENGTH(`name`)"


def test_rewrite_unknown_udf_warns():
    n = transform_node("t", [("h", "custom_hash_fn(`x`)")])
    report = fresh_report()
    out = RewriteUDFsToNativeFunctions()([n], report)
    expr = out[0].config["block"]["assignments"][0][1]
    assert expr == "custom_hash_fn(`x`)"
    assert any(e.severity == "warn" and "custom_hash_fn" in e.description for e in report.warnings)


# ── NullSafeComparisonRewrite ─────────────────────────────────────────────


def test_null_safe_rewrite_on_nullable_column():
    schema = {"fields": [
        {"name": "country", "type": "string", "args": [50], "nullable": True, "array": False}
    ]}
    r = read_node("r", "/x.parquet", schema=schema)
    f = filter_node("f", "`country` = 'US'", inputs=["r"])
    out = NullSafeComparisonRewrite()([r, f], fresh_report())
    cond = next(n for n in out if n.id == "f").config["block"]["condition"]
    assert "IS NOT NULL" in cond


def test_null_safe_skips_non_nullable_column():
    schema = {"fields": [
        {"name": "id", "type": "integer", "args": [], "nullable": False, "array": False}
    ]}
    r = read_node("r", "/x.parquet", schema=schema)
    f = filter_node("f", "`id` = 5", inputs=["r"])
    out = NullSafeComparisonRewrite()([r, f], fresh_report())
    cond = next(n for n in out if n.id == "f").config["block"]["condition"]
    assert "IS NOT NULL" not in cond


# ── DeduplicateCommonSubexpressions ───────────────────────────────────────


def test_cse_extracts_repeated_subexpression():
    n = transform_node("t", [
        ("tax_amount", "(`order_amount` * 0.18)"),
        ("total",      "(`order_amount` + (`order_amount` * 0.18))"),
    ])
    out = DeduplicateCommonSubexpressions()([n], fresh_report())
    assigns = out[0].config["block"]["assignments"]
    cse_cols = [c for c, _ in assigns if c.startswith("__cse_")]
    assert len(cse_cols) == 1
    # Both original columns should now reference the cse column
    rewritten = {c: e for c, e in assigns}
    assert any("__cse_" in str(rewritten[c]) for c in ("tax_amount", "total"))


def test_cse_skips_when_only_one_occurrence():
    n = transform_node("t", [("tax", "(`x` * 0.18)")])
    out = DeduplicateCommonSubexpressions()([n], fresh_report())
    cols = [c for c, _ in out[0].config["block"]["assignments"]]
    assert all(not c.startswith("__cse_") for c in cols)
