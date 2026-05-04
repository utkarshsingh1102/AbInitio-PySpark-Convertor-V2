"""Per-component plugin tests.

Each test builds a single-node IR by hand, asks the plugin to emit code,
and asserts on a few essential substrings. Strict full-string golden
matching is brittle; we want signal that the plugin emits the right
operator chain.
"""
from backend.components import REGISTRY
from backend.components.base import EmitContext
from backend.ir.models import IRNode


def _emit(node: IRNode, ctx: EmitContext | None = None) -> str:
    plugin = REGISTRY[node.component_type]
    if ctx is None:
        ctx = EmitContext(pipeline_id="t")
    return plugin.emit_pyspark(node, ctx)


def _node(component_type: str, **kw) -> IRNode:
    plugin = REGISTRY[component_type]
    return IRNode(
        id=kw.get("id", "n"),
        name=kw.get("name", "N"),
        component_type=component_type,
        ir_type=plugin.ir_type,
        inputs=kw.get("inputs", []),
        outputs=kw.get("outputs", []),
        port_inputs=kw.get("port_inputs", {}),
        fan_out=kw.get("fan_out", 0),
        schema=kw.get("schema"),
        config=kw.get("config", {}),
        params=kw.get("params", {}),
    )


# ── basic IO ─────────────────────────────────────────────────────────────


def test_input_file_emits_read_with_schema():
    out = _emit(_node("InputFile", id="r",
                      config={"filename": "/x.parquet"},
                      schema={"type": "record", "fields": []}))
    assert "spark.read" in out and "/x.parquet" in out and "SCHEMA_r" in out


def test_input_file_csv_with_header():
    out = _emit(_node("InputFile", id="r",
                      config={"filename": "/x.csv", "file_format": "delimited",
                              "delimiter": ",", "has_header": "true"}))
    assert ".option(\"sep\", ',')" in out
    assert ".format('csv')" in out
    assert ".option(\"header\", \"true\")" in out


def test_output_file_writes_to_path():
    out = _emit(_node("OutputFile", inputs=["src"],
                      config={"filename": "/out", "mode": "overwrite"}))
    assert ".write" in out and "/out" in out and "'overwrite'" in out


def test_intermediate_file_writes_then_reads():
    out = _emit(_node("IntermediateFile", inputs=["src"],
                      config={"filename": "/tmp/i.parquet"}))
    assert ".write.mode('overwrite').parquet('/tmp/i.parquet')" in out
    assert "spark.read.parquet('/tmp/i.parquet')" in out


# ── transforms ────────────────────────────────────────────────────────────


def test_reformat_emits_withcolumn_chain_in_source_order():
    out = _emit(_node("Reformat", id="r2", inputs=["r1"],
                      config={"block": {"type": "transform",
                                        "assignments": [
                                            ("a", "(`x` * 2)"),
                                            ("b", "(`a` + 1)"),
                                        ]}}))
    # 'a' must be defined before 'b' references it
    assert out.index("withColumn('a'") < out.index("withColumn('b'")
    assert ".select('a', 'b')" in out


def test_filter_uses_block_when_present():
    out = _emit(_node("Filter", inputs=["r"],
                      config={"block": {"type": "filter",
                                        "condition": "(`x` > 0)"}}))
    assert ".filter(F.expr(\"(`x` > 0)\"))" in out


def test_filter_falls_back_to_inline_condition():
    plugin = REGISTRY["Filter"]
    cfg = plugin.parse_props({"condition": "x > 0"}, {})
    out = _emit(_node("Filter", inputs=["r"], config=cfg))
    assert "(`x` > 0)" in out


# ── joins / lookups ───────────────────────────────────────────────────────


def test_join_uses_named_ports():
    out = _emit(_node("Join", id="j",
                      port_inputs={"in_left": "L", "in_right": "R"},
                      inputs=["L", "R"],
                      config={"join_key": "id", "join_type": "inner"}))
    assert "df_L.join(df_R" in out
    assert "on=['id']" in out
    assert "how='inner'" in out


def test_lookup_emits_broadcast():
    out = _emit(_node("Lookup",
                      port_inputs={"in": "M", "in_lookup": "L"},
                      inputs=["M", "L"],
                      config={"key": "id"}))
    assert "F.broadcast(df_L)" in out
    assert "df_M.join" in out
    assert "how='left'" in out


def test_match_sorted_inner_join():
    out = _emit(_node("MatchSorted",
                      port_inputs={"in_left": "A", "in_right": "B"},
                      inputs=["A", "B"], config={"key": "k"}))
    assert "how='inner'" in out and "df_A.join(df_B" in out


# ── sort / dedup / aggregate ──────────────────────────────────────────────


def test_sort_orderby():
    out = _emit(_node("Sort", inputs=["r"], config={"key": "a, b", "order": "desc"}))
    assert ".orderBy(F.col('a').desc(), F.col('b').desc())" in out


def test_dedup_sorted_first():
    out = _emit(_node("DedupSorted", inputs=["r"],
                      config={"key": "id", "which": "first"}))
    assert ".dropDuplicates(['id'])" in out


def test_rollup_parses_aggregates():
    out = _emit(_node("Rollup", inputs=["r"],
                      config={"group_by": "k1, k2",
                              "aggregates": "sum(x):total, count(y):n"}))
    assert "groupBy(['k1', 'k2'])" in out
    assert "F.sum('x').alias('total')" in out
    assert "F.count('y').alias('n')" in out


def test_aggregate_alias_for_rollup():
    out = _emit(_node("Aggregate", inputs=["r"],
                      config={"group_by": "k", "aggregates": "sum(x):s"}))
    assert "groupBy(['k'])" in out


# ── scan / normalize / denormalize ────────────────────────────────────────


def test_scan_emits_window_function():
    out = _emit(_node("Scan", id="s", inputs=["r"],
                      config={"key": "k", "sort_by": "t",
                              "aggregates": "sum(x):running"}))
    assert "Window" in out and "partitionBy" in out and "rowsBetween" in out
    assert "F.sum('x').over" in out


def test_normalize_explodes_array():
    out = _emit(_node("Normalize", inputs=["r"],
                      config={"array_field": "items", "item_alias": "item"}))
    assert "F.explode(F.col('items'))" in out


def test_denormalize_collects():
    out = _emit(_node("DenormalizeSorted", inputs=["r"],
                      config={"group_by": "k", "collect": "v"}))
    assert "F.collect_list('v').alias('v_list')" in out
    assert "groupBy(['k'])" in out


# ── fan-in / fan-out ──────────────────────────────────────────────────────


def test_replicate_aliases_input():
    out = _emit(_node("Replicate", inputs=["src"]))
    assert "df_n = df_src" in out


def test_gather_unionByName():
    out = _emit(_node("Gather", inputs=["A", "B", "C"]))
    assert "unionByName" in out
    assert "[df_A, df_B, df_C]" in out


def test_concatenate_unionByName():
    out = _emit(_node("Concatenate", inputs=["A", "B"]))
    assert "unionByName" in out


# ── side effects ──────────────────────────────────────────────────────────


def test_run_program_subprocess():
    out = _emit(_node("RunProgram", config={"command": "echo hi"}))
    assert "subprocess" in out and "'echo hi'" in out


def test_trash_noop_sink():
    out = _emit(_node("Trash", inputs=["r"]))
    assert "format('noop')" in out


# ── registry hygiene ──────────────────────────────────────────────────────


def test_all_common_20_registered():
    expected = {
        "InputFile", "OutputFile", "LookupFile", "IntermediateFile",
        "Reformat", "Filter", "Sort", "SortWithinGroups",
        "DedupSorted", "Rollup", "Aggregate", "Scan",
        "Normalize", "DenormalizeSorted", "Join", "Lookup",
        "MatchSorted", "Replicate", "Gather", "Concatenate",
        "RunProgram", "Trash",
    }
    missing = expected - set(REGISTRY)
    assert not missing, f"Missing plugins: {missing}"
