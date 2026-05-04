"""End-to-end golden test for `Input → Reformat → Filter → Output`.

Codegen is exercised always; the PySpark execution part is skipped if
PySpark is not installed locally.
"""
from pathlib import Path

from backend.codegen.ksh_gen import generate_ksh
from backend.codegen.pyspark_gen import generate_pyspark
from backend.components import REGISTRY
from backend.ir.models import IRNode
from backend.parser.dml_parser import parse_dml_file, resolve
from backend.parser.mp_parser import parse_mp_file
from backend.parser.xfr_parser import parse_xfr_file

EX = Path(__file__).resolve().parents[3] / "examples" / "simple_pipeline"


def _build_ir():
    """Bypass Neo4j: parse files, hand-build IR via the plugin registry."""
    g = parse_mp_file(EX / "customer_pipeline.mp")
    schemas = parse_dml_file(EX / "customer.dml")
    xfr = parse_xfr_file(EX / "customer.xfr")

    incoming = {n.id: [] for n in g.nodes}
    outgoing = {n.id: [] for n in g.nodes}
    for e in g.edges:
        outgoing[e.from_id].append(e.to_id)
        incoming[e.to_id].append(e.from_id)
    indeg = {nid: len(incoming[nid]) for nid in incoming}
    order: list[str] = []
    queue = sorted([nid for nid, d in indeg.items() if d == 0])
    while queue:
        nid = queue.pop(0)
        order.append(nid)
        for nxt in outgoing[nid]:
            indeg[nxt] -= 1
            if indeg[nxt] == 0:
                queue.append(nxt)
                queue.sort()
    by_id = {n.id: n for n in g.nodes}

    ir: list[IRNode] = []
    for nid in order:
        n = by_id[nid]
        plugin = REGISTRY[n.type]
        cfg = plugin.parse_props(dict(n.properties), g.params)
        block_name = (cfg.get("transform_file") or "").rsplit(".", 1)[0]
        if block_name in xfr:
            cfg["block"] = xfr[block_name]
        schema = resolve(schemas, cfg.get("schema", ""))
        ir.append(IRNode(
            id=n.id, name=n.name,
            component_type=n.type, ir_type=plugin.ir_type,
            inputs=incoming[nid], outputs=outgoing[nid],
            port_inputs={p: up for p, (up, _) in n.input_ports.items()},
            fan_out=len(outgoing[nid]),
            schema=schema, config=cfg, params=g.params,
        ))
    return ir


def test_simple_pipeline_codegen_compiles():
    ir = _build_ir()
    py = generate_pyspark(ir, app_name="customer_pipeline")
    compile(py, "<gen>", "exec")
    assert "df_node_1" in py
    assert ".filter(" in py
    # Native API translation — RewriteExprToNativeAPI rule
    assert "F.col('age')" in py
    assert "F.upper(F.col('name'))" in py


def test_simple_pipeline_ksh_paths():
    ir = _build_ir()
    ksh = generate_ksh(ir, pipeline_name="customer_pipeline")
    assert "data/input/customers.parquet" in ksh
    assert "data/output/customers_filtered.parquet" in ksh


def test_simple_pipeline_runs_pyspark(tmp_path):
    """Generate, save, and execute the pipeline against a tiny parquet file."""
    pytest = __import__("pytest")
    try:
        from datetime import date
        from decimal import Decimal
        from pyspark.sql import SparkSession
        from pyspark.sql.types import (
            DateType, DecimalType, IntegerType, StringType,
            StructField, StructType,
        )
    except Exception:
        pytest.skip("PySpark not installed")

    ir = _build_ir()
    py = generate_pyspark(ir, app_name="customer_pipeline")
    pp = tmp_path / "pipeline.py"
    pp.write_text(py)

    in_dir = tmp_path / "data" / "input"
    out_dir = tmp_path / "data" / "output" / "customers_filtered.parquet"
    in_path = in_dir / "customers.parquet"
    in_dir.mkdir(parents=True)

    spark = SparkSession.builder.appName("seed").master("local[1]").getOrCreate()
    try:
        schema = StructType([
            StructField("customer_id", StringType(), False),
            StructField("name",        StringType(), True),
            StructField("age",         IntegerType(), True),
            StructField("balance",     DecimalType(10, 2), True),
            StructField("signup_date", DateType(), True),
        ])
        rows = [
            ("c1", "alice",   25, Decimal("100.00"), date(2024, 1, 1)),
            ("c2", "bob",     17, Decimal( "50.00"), date(2024, 2, 1)),
            ("c3", "charlie", 42, Decimal("200.00"), date(2024, 3, 1)),
        ]
        spark.createDataFrame(rows, schema).write.mode("overwrite").parquet(str(in_path))
    finally:
        spark.stop()

    import subprocess, sys
    res = subprocess.run(
        [sys.executable, str(pp)],
        cwd=str(tmp_path),
        capture_output=True, text=True, timeout=180,
    )
    assert res.returncode == 0, f"stdout={res.stdout}\nstderr={res.stderr}"

    spark = SparkSession.builder.appName("verify").master("local[1]").getOrCreate()
    try:
        df = spark.read.parquet(str(out_dir))
        names = sorted(r.name for r in df.collect())
        assert names == ["ALICE", "CHARLIE"]
    finally:
        spark.stop()
