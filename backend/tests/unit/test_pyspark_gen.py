"""Codegen orchestration tests (per-component behaviour lives in test_components.py)."""
from backend.codegen.ksh_gen import generate_ksh
from backend.codegen.pyspark_gen import generate_pyspark
from backend.ir.models import IRNode


def _hand_built_ir():
    schema = {
        "type": "record",
        "fields": [
            {"name": "customer_id", "type": "string", "args": [20], "nullable": False, "array": False},
            {"name": "age", "type": "integer", "args": [], "nullable": True, "array": False},
        ],
    }
    return [
        IRNode(id="n1", name="In", component_type="InputFile", ir_type="read",
               inputs=[], outputs=["n2"], schema=schema,
               config={"filename": "data/in", "file_format": "parquet"}),
        IRNode(id="n2", name="Reformat", component_type="Reformat", ir_type="transform",
               inputs=["n1"], outputs=["n3"], schema=schema,
               config={"block": {"type": "transform",
                                 "assignments": [("age", "(`age` + 1)"),
                                                 ("customer_id", "`customer_id`")]}}),
        IRNode(id="n3", name="F", component_type="Filter", ir_type="filter",
               inputs=["n2"], outputs=["n4"], schema=schema,
               config={"__filter_expr": "(`age` > 18)"}),
        IRNode(id="n4", name="Out", component_type="OutputFile", ir_type="write",
               inputs=["n3"], outputs=[], schema=schema,
               config={"filename": "data/out", "file_format": "parquet"}),
    ]


def test_codegen_produces_compilable_python():
    src = generate_pyspark(_hand_built_ir(), app_name="t")
    compile(src, "<gen>", "exec")


def test_codegen_emits_per_node_schema():
    src = generate_pyspark(_hand_built_ir(), app_name="t")
    assert "SCHEMA_n1" in src
    # The Reformat does NOT emit its own SCHEMA literal — Reformat output
    # schema is implied by the `withColumn` chain.
    assert "spark.read" in src
    assert ".filter(" in src
    assert ".save('data/out')" in src


def test_codegen_uses_df_var_per_node_id():
    src = generate_pyspark(_hand_built_ir(), app_name="t")
    assert "df_n1" in src
    assert "df_n2" in src
    assert "df_n3" in src
    # write nodes don't allocate a new df_var
    assert "df_n4 =" not in src


def test_ksh_wraps_pipeline_correctly():
    ksh = generate_ksh(_hand_built_ir(), pipeline_name="t")
    assert "spark-submit" in ksh
    assert "pipeline.py" in ksh
    assert "INPUT_FILE" in ksh and "OUTPUT_FILE" in ksh
