"""Stage 3 — write/runtime rules."""
from backend.codegen.rules.write import (
    CoalesceBeforeWrite,
    PartitionByAnnotation,
    RepartitionBeforeShuffleJoin,
    StorageLevelSelection,
)
from backend.ir.models import IRNode

from .conftest import fresh_report, join_node, read_node, transform_node, write_node


# ── CoalesceBeforeWrite ───────────────────────────────────────────────────


def test_coalesce_for_overwrite_parquet_uses_dop():
    w = write_node("w", "/o", inputs=["t"], params={"DOP": "8"})
    out = CoalesceBeforeWrite()([w], fresh_report())
    assert out[0].config["coalesce"] == 8


def test_coalesce_for_append_uses_dop_not_repartition():
    w = write_node("w", "/o", inputs=["t"], mode="append", params={"DOP": "4"})
    out = CoalesceBeforeWrite()([w], fresh_report())
    assert out[0].config["coalesce"] == 4
    assert "repartition" not in out[0].config


def test_repartition_for_large_overwrite():
    w = write_node("w", "/o", inputs=["t"], params={"DOP": "16"})
    w.config["size_class"] = "large"
    out = CoalesceBeforeWrite()([w], fresh_report())
    assert out[0].config.get("repartition") == 16


# ── PartitionByAnnotation ─────────────────────────────────────────────────


def test_partition_by_explicit_property():
    src = transform_node("t", [("x", "`x`")])
    w = write_node("w", "/o", inputs=["t"])
    w.config["partitionBy"] = "country, year"
    out = PartitionByAnnotation()([src, w], fresh_report())
    w_after = next(n for n in out if n.id == "w")
    assert w_after.config["partition_columns"] == ["country", "year"]


def test_partition_by_detects_time_bucket_column():
    schema = {"fields": [
        {"name": "id",          "type": "integer", "args": [], "nullable": False, "array": False},
        {"name": "order_month", "type": "string",  "args": [7], "nullable": True, "array": False},
    ]}
    src = transform_node("t", [], schema=schema)
    w = write_node("w", "/o", inputs=["t"])
    src.outputs = ["w"]
    out = PartitionByAnnotation()([src, w], fresh_report())
    w_after = next(n for n in out if n.id == "w")
    assert w_after.config.get("partition_columns") == ["order_month"]


# ── StorageLevelSelection ─────────────────────────────────────────────────


def test_storage_level_disk_only_when_only_consumers_are_writes():
    src = transform_node("s", [("x", "(`a` + 1)")], fan_out=2)
    src.config["cache"] = True
    src.outputs = ["w1", "w2"]
    w1 = write_node("w1", "/a", inputs=["s"])
    w2 = write_node("w2", "/b", inputs=["s"])
    out = StorageLevelSelection()([src, w1, w2], fresh_report())
    assert next(n for n in out if n.id == "s").config["storage_level"] == "DISK_ONLY"


def test_storage_level_memory_only_for_narrow_schema():
    schema = {"fields": [
        {"name": "k", "type": "integer", "args": [], "nullable": False, "array": False}
    ]}
    src = transform_node("s", [("k", "`k`")], schema=schema, fan_out=2)
    src.config["cache"] = True
    src.outputs = ["c1", "c2"]
    c1 = transform_node("c1", [("y", "(`k` * 2)")], inputs=["s"])
    c2 = transform_node("c2", [("y", "(`k` * 3)")], inputs=["s"])
    out = StorageLevelSelection()([src, c1, c2], fresh_report())
    assert next(n for n in out if n.id == "s").config["storage_level"] == "MEMORY_ONLY"


# ── RepartitionBeforeShuffleJoin ──────────────────────────────────────────


def test_repartition_tags_inputs_for_sort_merge_join():
    a = read_node("a", "/data/transactions.csv")
    b = read_node("b", "/data/events.csv")
    j = join_node("j", "a", "b", key="id")
    j.config["strategy"] = "sort_merge"
    out = RepartitionBeforeShuffleJoin()([a, b, j], fresh_report())
    a_after = next(n for n in out if n.id == "a")
    b_after = next(n for n in out if n.id == "b")
    assert a_after.config["repartition_on"] == "id"
    assert b_after.config["repartition_on"] == "id"


def test_repartition_skips_broadcast_join():
    a = read_node("a", "/data/transactions.csv")
    b = read_node("b", "/data/customers.csv")
    j = join_node("j", "a", "b", key="id")
    j.config["strategy"] = "broadcast"
    out = RepartitionBeforeShuffleJoin()([a, b, j], fresh_report())
    a_after = next(n for n in out if n.id == "a")
    assert "repartition_on" not in a_after.config
