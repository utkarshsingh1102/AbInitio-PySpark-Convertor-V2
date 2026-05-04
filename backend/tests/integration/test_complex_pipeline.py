"""End-to-end test for the complex pipeline.

Builds IR from parsers (bypassing Neo4j), generates PySpark, then actually
runs it against tiny CSV inputs and verifies the three outputs land where
expected and contain the right rows.
"""
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pytest

from backend.codegen.pyspark_gen import generate_pyspark
from backend.components import REGISTRY
from backend.ir.models import IRNode
from backend.parser.dml_parser import parse_dml_file, resolve
from backend.parser.mp_parser import parse_mp_file
from backend.parser.xfr_parser import parse_xfr_file

EX = Path(__file__).resolve().parents[3] / "examples" / "complex_pipeline"


def _build_ir(params_override: dict[str, str] | None = None) -> list[IRNode]:
    g = parse_mp_file(EX / "customer_order_enrichment.mp", params_override=params_override)
    schemas = parse_dml_file(EX / "customer_order_enrichment.dml")
    xfr = parse_xfr_file(EX / "customer_order_enrichment.xfr")

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


def test_complex_pipeline_codegen_compiles():
    ir = _build_ir()
    py = generate_pyspark(ir, app_name="complex")
    compile(py, "<gen>", "exec")
    assert "df_node_05.join" not in py  # join takes two inputs
    assert "df_node_05 = df_node_03.join(df_node_04" in py
    # fan-out from node_06 to node_07 / 08 / 13:
    assert "df_node_07 = df_node_06" in py
    assert "df_node_08 = df_node_06" in py
    # final filters reference the FILTER block (with `is_valid = 1`)
    assert "is_valid" in py


def test_complex_pipeline_runs_pyspark(tmp_path):
    """Run the complex pipeline against tiny synthetic CSV inputs."""
    try:
        from pyspark.sql import SparkSession
    except Exception:
        pytest.skip("PySpark not installed")

    in_dir = tmp_path / "data" / "input"
    out_dir = tmp_path / "data" / "output"
    in_dir.mkdir(parents=True)
    out_dir.mkdir(parents=True)

    # write tiny CSVs (with headers)
    (in_dir / "customers.csv").write_text(
        "customer_id,first_name,last_name,email,country,signup_date,loyalty_points\n"
        "1,alice,smith,a@x.com,United States,2020-01-15,5500\n"
        "2,bob,jones,b@x.com,Germany,2022-03-10,800\n"
        "3,charlie,brown,c@x.com,,2021-06-01,2500\n"
    )
    (in_dir / "orders.csv").write_text(
        "order_id,customer_id,order_date,product_code,quantity,unit_price,order_amount,status\n"
        "o1,1,2024-01-15 10:00:00,prodA,2,500.00,1200.00,confirmed\n"
        "o2,2,2024-02-20 11:30:00,prodB,1,400.00,400.00,confirmed\n"
        "o3,3,2024-03-05 09:15:00,prodC,4,300.00,,shipped\n"
    )

    # Override params so the pipeline reads from tmp_path, not /data/...
    ir = _build_ir({
        "INPUT_CUSTOMERS":  str(in_dir / "customers.csv"),
        "INPUT_ORDERS":     str(in_dir / "orders.csv"),
        "OUTPUT_HIGH_VALUE": str(out_dir / "high_value"),
        "OUTPUT_STANDARD":   str(out_dir / "standard"),
        "OUTPUT_AUDIT":      str(out_dir / "audit"),
    })
    py = generate_pyspark(ir, app_name="complex")
    pp = tmp_path / "pipeline.py"
    pp.write_text(py)

    import subprocess, sys
    res = subprocess.run(
        [sys.executable, str(pp)],
        cwd=str(tmp_path),
        capture_output=True, text=True, timeout=240,
    )
    assert res.returncode == 0, f"stdout={res.stdout}\nstderr={res.stderr[-1500:]}"

    spark = SparkSession.builder.appName("verify").master("local[1]").getOrCreate()
    try:
        # Audit log: every joined+enriched row (3 customers × 1 order each = 3)
        audit = spark.read.parquet(str(out_dir / "audit"))
        assert audit.count() == 3

        # High-value (order_amount > 1000):
        #   o1 alice → $1200 (>1000) → in
        #   o2 bob   → $400  (<=1000) → out
        #   o3 charlie → null order_amount, but derived = 4×300 = 1200 → in
        hv = spark.read.parquet(str(out_dir / "high_value"))
        hv_rows = sorted([r.order_id for r in hv.collect()])
        assert hv_rows == ["o1", "o3"]
        # Loyalty tier mapping verified: alice (5500) → GOLD/15%; charlie (2500) → SILVER/10%
        hv_by_id = {r.order_id: r for r in hv.collect()}
        assert hv_by_id["o1"].loyalty_tier == "GOLD"
        assert hv_by_id["o3"].loyalty_tier == "SILVER"
        # final_amount uses out.X self-reference (out.discount_pct):
        # alice: 1200 * (1 - 15/100) = 1020.00
        from decimal import Decimal
        assert hv_by_id["o1"].final_amount == Decimal("1020.00")

        # Standard bucket = orders with amount <= 1000: only bob's o2.
        std = spark.read.parquet(str(out_dir / "standard"))
        std_rows = std.collect()
        assert len(std_rows) == 1
        assert std_rows[0].customer_id == 2
        assert std_rows[0].order_count == 1
    finally:
        spark.stop()
