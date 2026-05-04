"""Stage 1 — structural rules."""
from backend.codegen.rules.structural import (
    CollapseConsecutiveTransforms,
    EarlyFilterPushdown,
    EliminatePassthroughNodes,
    FanOutCacheAnnotation,
    JoinStrategyAnnotation,
    ProjectionPruning,
)
from .conftest import (
    filter_node, fresh_report, join_node, link, read_node,
    transform_node, write_node,
)


# ── EarlyFilterPushdown ───────────────────────────────────────────────────


def test_early_filter_pushdown_past_projection_only_reformat():
    schema = {"fields": [
        {"name": "status", "type": "string", "args": [10], "nullable": True, "array": False}
    ]}
    r = read_node("r", "/x.parquet", schema=schema)
    t = transform_node("t", [("status", "`status`")], schema=schema, inputs=["r"], fan_out=1)
    f = filter_node("f", "(`status` = 'ACTIVE')", inputs=["t"], fan_out=1)
    w = write_node("w", "/o", inputs=["f"])
    link(r, t); link(t, f); link(f, w)

    nodes = [r, t, f, w]
    report = fresh_report()
    out = EarlyFilterPushdown()(nodes, report)
    # f should now read from r (pushed past t)
    f_after = next(n for n in out if n.id == "f")
    assert f_after.inputs == ["r"]
    assert any(e.rule == "EarlyFilterPushdown" for e in report.rules_applied)


def test_filter_NOT_pushed_past_reformat_that_redefines_filter_column():
    schema = {"fields": [
        {"name": "x", "type": "integer", "args": [], "nullable": True, "array": False}
    ]}
    r = read_node("r", "/x.parquet", schema=schema)
    t = transform_node("t", [("x", "(`x` * 2)")], schema=schema, inputs=["r"], fan_out=1)
    f = filter_node("f", "(`x` > 100)", inputs=["t"], fan_out=1)
    w = write_node("w", "/o", inputs=["f"])
    link(r, t); link(t, f); link(f, w)
    out = EarlyFilterPushdown()([r, t, f, w], fresh_report())
    f_after = next(n for n in out if n.id == "f")
    assert f_after.inputs == ["t"]  # NOT pushed


# ── ProjectionPruning ─────────────────────────────────────────────────────


def test_projection_pruning_drops_unused_columns():
    schema = {"fields": [
        {"name": "id",     "type": "integer", "args": [], "nullable": False, "array": False},
        {"name": "name",   "type": "string",  "args": [50], "nullable": True, "array": False},
        {"name": "secret", "type": "string",  "args": [50], "nullable": True, "array": False},
    ]}
    r = read_node("r", "/x.parquet", schema=schema)
    t = transform_node("t", [("upper_name", "UPPER(`name`)")], inputs=["r"])
    w = write_node("w", "/o", inputs=["t"])
    r.outputs = ["t"]; t.outputs = ["w"]

    report = fresh_report()
    out = ProjectionPruning()([r, t, w], report)
    r_after = next(n for n in out if n.id == "r")
    # `secret` is never referenced — should be pruned away.
    assert "secret" not in (r_after.config.get("select_columns") or [])
    assert "name" in r_after.config["select_columns"]


# ── FanOutCacheAnnotation ─────────────────────────────────────────────────


def test_fanout_cache_tags_node_with_3_consumers():
    src = transform_node("s", [("x", "(`a` + 1)")], fan_out=3)
    a = filter_node("a", "(`x` > 0)", inputs=["s"])
    b = filter_node("b", "(`x` < 0)", inputs=["s"])
    c = filter_node("c", "(`x` = 0)", inputs=["s"])
    src.outputs = ["a", "b", "c"]
    out = FanOutCacheAnnotation()([src, a, b, c], fresh_report())
    src_after = next(n for n in out if n.id == "s")
    assert src_after.config["cache"] is True
    assert src_after.config["unpersist_after"] == "c"


def test_fanout_cache_skips_pure_reads():
    r = read_node("r", "/x.parquet", fan_out=2)
    out = FanOutCacheAnnotation()([r], fresh_report())
    assert "cache" not in out[0].config


# ── JoinStrategyAnnotation ────────────────────────────────────────────────


def test_join_picks_broadcast_for_dimension_side():
    cust = read_node("c", "/data/customers.csv")
    orders = read_node("o", "/data/orders.csv")
    j = join_node("j", "c", "o")
    out = JoinStrategyAnnotation()([cust, orders, j], fresh_report())
    j_after = next(n for n in out if n.id == "j")
    assert j_after.config["strategy"] == "broadcast"
    assert j_after.config["broadcast"] == "left"


def test_join_falls_back_to_sort_merge():
    a = read_node("a", "/data/transactions.csv")
    b = read_node("b", "/data/events.csv")
    j = join_node("j", "a", "b")
    out = JoinStrategyAnnotation()([a, b, j], fresh_report())
    j_after = next(n for n in out if n.id == "j")
    assert j_after.config["strategy"] == "sort_merge"


# ── CollapseConsecutiveTransforms ─────────────────────────────────────────


def test_two_consecutive_transforms_merge():
    schema = {"fields": [
        {"name": "x", "type": "integer", "args": [], "nullable": True, "array": False}
    ]}
    r = read_node("r", "/x.parquet", schema=schema, fan_out=1)
    t1 = transform_node("t1", [("a", "(`x` + 1)")], schema=schema, inputs=["r"], fan_out=1)
    t2 = transform_node("t2", [("b", "(`a` * 2)")], schema=schema, inputs=["t1"], fan_out=0)
    r.outputs = ["t1"]; t1.outputs = ["t2"]
    out = CollapseConsecutiveTransforms()([r, t1, t2], fresh_report())
    # t1 should be gone; t2 carries both assignments.
    ids = [n.id for n in out]
    assert "t1" not in ids
    t2_after = next(n for n in out if n.id == "t2")
    cols = [c for c, _ in t2_after.config["block"]["assignments"]]
    assert cols == ["a", "b"]


# ── EliminatePassthroughNodes ─────────────────────────────────────────────


def test_eliminate_passthrough_tags_empty_transform():
    n = transform_node("p", [])
    out = EliminatePassthroughNodes()([n], fresh_report())
    assert out[0].config["passthrough"] is True
