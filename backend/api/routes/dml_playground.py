"""POST /dml/convert — DML Playground.

Accepts raw DML text, returns one entry per ``DEFINE`` block:
  - the parsed field list
  - a ``StructType(...)`` literal
  - an auto-classified recommended file format (parquet / json / avro / csv)
  - a complete, runnable PySpark read+write snippet against an assumed
    input/output path

The format classifier picks parquet/avro/json when the schema contains
features CSV cannot represent (nested structs, arrays, deep types) and
falls back to CSV only for genuinely flat schemas — and even then we
recommend parquet for analytics use.
"""
from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ...components._emit_helpers import schema_dict_to_struct_code
from ...parser.dml_parser import parse_dml_string

router = APIRouter()


# ── request / response models ─────────────────────────────────────────────


class ConvertRequest(BaseModel):
    dml: str
    # Optional ${VAR} substitutions applied before parsing.
    params: dict[str, str] | None = None


class FormatChoice(BaseModel):
    name: str
    reason: str


class SchemaResult(BaseModel):
    name: str
    fields: list[dict[str, Any]]
    struct_code: str
    recommended_format: FormatChoice
    alternatives: list[FormatChoice]
    feature_flags: dict[str, bool]
    pyspark_code: str


class ConvertResponse(BaseModel):
    schemas: list[SchemaResult]


# ── public route ──────────────────────────────────────────────────────────


@router.post("/dml/convert", response_model=ConvertResponse)
def convert(req: ConvertRequest) -> ConvertResponse:
    if not req.dml or not req.dml.strip():
        raise HTTPException(status_code=400, detail="DML text is empty")
    try:
        schemas = parse_dml_string(req.dml, params=req.params or None)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"DML parse error: {exc}") from exc

    if not schemas:
        raise HTTPException(status_code=400, detail="No DEFINE blocks found")

    out: list[SchemaResult] = []
    for name, schema in schemas.items():
        flags = _scan_features(schema)
        chosen, alts = _classify_format(flags)
        struct_code = schema_dict_to_struct_code(schema)
        code = _emit_pyspark(name, struct_code, chosen.name, schema)
        out.append(SchemaResult(
            name=name,
            fields=schema.get("fields", []),
            struct_code=struct_code,
            recommended_format=chosen,
            alternatives=alts,
            feature_flags=flags,
            pyspark_code=code,
        ))
    return ConvertResponse(schemas=out)


# ── feature scanner ───────────────────────────────────────────────────────


def _scan_features(schema: dict[str, Any]) -> dict[str, bool]:
    """Walk the schema once and report which features the file format must support."""
    flags = {
        "has_nested_struct": False,
        "has_array": False,
        "has_array_of_struct": False,
        "has_decimal": False,
        "has_date_or_time": False,
        "has_only_strings": True,   # gets cleared if we see anything else
        "deep_nesting": False,      # depth > 2
        "has_delimited_fields": False,
        "has_fixed_layout": schema.get("layout") == "fixed",
        "has_ebcdic": False,
        "has_packed_decimal": False,
    }

    def walk(fields: list[dict[str, Any]], depth: int) -> None:
        for f in fields:
            t = f.get("type")
            is_array = bool(f.get("array"))

            if t != "string":
                flags["has_only_strings"] = False

            if f.get("delimiter") is not None:
                flags["has_delimited_fields"] = True

            enc = f.get("encoding")
            if enc == "ebcdic":
                flags["has_ebcdic"] = True
            elif enc == "packed_decimal":
                flags["has_packed_decimal"] = True

            if t == "struct":
                flags["has_nested_struct"] = True
                if is_array:
                    flags["has_array_of_struct"] = True
                if depth + 1 > 2:
                    flags["deep_nesting"] = True
                walk(f.get("fields", []), depth + 1)
            else:
                if is_array:
                    flags["has_array"] = True
                if t == "decimal":
                    flags["has_decimal"] = True
                if t in ("date", "datetime", "timestamp"):
                    flags["has_date_or_time"] = True

    walk(schema.get("fields", []), depth=0)
    return flags


def _uniform_delimiter(schema: dict[str, Any]) -> str | None:
    """If every delimited field uses the same delimiter, return it; else None."""
    delims: set[str] = set()

    def walk(fields: list[dict[str, Any]]) -> None:
        for f in fields:
            d = f.get("delimiter")
            if d is not None:
                delims.add(d)
            if f.get("type") == "struct":
                walk(f.get("fields", []))

    walk(schema.get("fields", []))
    if len(delims) == 1:
        return next(iter(delims))
    return None


def _uniform_format(schema: dict[str, Any], for_type: str) -> str | None:
    """If every field of ``for_type`` shares a format string, return it (translated to Spark)."""
    from ...parser.xfr_functions import translate_format
    formats: set[str] = set()

    def walk(fields: list[dict[str, Any]]) -> None:
        for f in fields:
            if f.get("type") == for_type and f.get("format"):
                formats.add(f["format"])
            if f.get("type") == "struct":
                walk(f.get("fields", []))

    walk(schema.get("fields", []))
    if len(formats) == 1:
        return translate_format(next(iter(formats)))
    return None


# ── format classifier ─────────────────────────────────────────────────────


def _classify_format(flags: dict[str, bool]) -> tuple[FormatChoice, list[FormatChoice]]:
    """Pick the most appropriate file format given the feature flags."""
    has_complex = (
        flags["has_nested_struct"]
        or flags["has_array"]
        or flags["has_array_of_struct"]
    )

    parquet = FormatChoice(
        name="parquet",
        reason=(
            "Columnar, schema-on-read, native struct & array support, "
            "compressed by default. The right default for analytical workloads."
        ),
    )
    avro = FormatChoice(
        name="avro",
        reason="Row-based with schema embedded — best for streaming / Kafka pipelines.",
    )
    json = FormatChoice(
        name="json",
        reason="Human-readable, supports nesting; verbose and slow for large data.",
    )
    csv = FormatChoice(
        name="csv",
        reason="Flat-only; loses precision on decimals, no native dates, no nesting.",
    )
    fixed_width = FormatChoice(
        name="fixed_width",
        reason=(
            "All fields are byte-positional with computed offsets. We emit a "
            "`spark.read.text(...)` reader followed by per-field `F.substring()` "
            "extractions, then write to Parquet."
        ),
    )
    ebcdic = FormatChoice(
        name="ebcdic_cobol",
        reason=(
            "Mainframe encoding (EBCDIC / packed-decimal) detected. The reader "
            "uses cobrix (`za.co.absa.cobrix:spark-cobol`) — add it to "
            "`--packages` when running spark-submit."
        ),
    )

    # Decision tree (most specific first)
    if flags["has_ebcdic"] or flags["has_packed_decimal"]:
        return ebcdic, [fixed_width, parquet]

    if flags["has_fixed_layout"]:
        return fixed_width, [parquet, csv]

    if has_complex:
        # CSV is impossible. Parquet first, then Avro, then JSON.
        return parquet, [avro, json]

    if flags["has_delimited_fields"]:
        # Strong signal that the source is a delimited text file.
        return csv, [parquet, json]

    if flags["has_decimal"] or flags["has_date_or_time"]:
        # CSV possible but lossy. Parquet first; still offer CSV as last resort.
        return parquet, [avro, json, csv]

    if flags["has_only_strings"]:
        # Pure string schema — CSV is fine and the most likely real source.
        return csv, [parquet, json]

    # Flat numeric/boolean schemas — parquet still best, csv viable.
    return parquet, [csv, avro, json]


# ── PySpark snippet emitter ───────────────────────────────────────────────


def _emit_pyspark(
    schema_name: str,
    struct_code: str,
    fmt: str,
    schema: dict[str, Any] | None = None,
) -> str:
    schema_var = f"{schema_name.upper()}_SCHEMA"
    df_var = f"df_{schema_name}"
    in_path = f"/data/in/{schema_name}"
    out_path = f"/data/out/{schema_name}"

    # Special path: fixed-width record layout
    if fmt == "fixed_width" and schema is not None:
        return _emit_fixed_width(schema_name, schema_var, df_var, in_path, out_path, struct_code, schema)
    # Special path: EBCDIC / mainframe (cobrix)
    if fmt == "ebcdic_cobol" and schema is not None:
        return _emit_ebcdic(schema_name, schema_var, df_var, in_path, out_path, struct_code, schema)

    read_opts = ""
    write_opts = ""
    if fmt == "csv":
        delim = _uniform_delimiter(schema) if schema else None
        date_fmt = _uniform_format(schema, "date") if schema else None
        ts_fmt = _uniform_format(schema, "datetime") if schema else None
        # json.dumps gives us a properly-escaped Python string literal:
        #   "|"  → '"|"'    "\n" → '"\\n"'    "\t" → '"\\t"'
        delim_literal = json.dumps(delim) if delim else '","'
        opts = [
            '\n    .option("header", "true")',
            '\n    .option("inferSchema", "false")',
            f'\n    .option("delimiter", {delim_literal})',
        ]
        if date_fmt:
            opts.append(f'\n    .option("dateFormat", {json.dumps(date_fmt)})')
        if ts_fmt:
            opts.append(f'\n    .option("timestampFormat", {json.dumps(ts_fmt)})')
        read_opts = "".join(opts)
        write_opts = (
            '\n    .option("header", "true")'
            f'\n    .option("delimiter", {delim_literal})'
        )
        if date_fmt:
            write_opts += f'\n    .option("dateFormat", {json.dumps(date_fmt)})'
        if ts_fmt:
            write_opts += f'\n    .option("timestampFormat", {json.dumps(ts_fmt)})'

    body = f'''"""Auto-generated by the DML Playground.

Reads {schema_name!r} as {fmt}, writes it back out unchanged. Edit the
paths and add transformations between read and write as needed.
"""
from pyspark.sql import SparkSession, functions as F
from pyspark.sql.types import (
    StructType, StructField, StringType, IntegerType, LongType,
    DoubleType, FloatType, BooleanType, DateType, TimestampType,
    DecimalType, ArrayType, BinaryType,
)
from pyspark.storagelevel import StorageLevel

spark = (
    SparkSession.builder
    .appName("{schema_name}_io")
    .config("spark.sql.adaptive.enabled", "true")
    .config("spark.sql.adaptive.skewJoin.enabled", "true")
    .config("spark.serializer", "org.apache.spark.serializer.KryoSerializer")
    .config("spark.sql.storeAssignmentPolicy", "STRICT")
    .getOrCreate()
)

# ─── Schema (translated from DML DEFINE {schema_name}) ─────────────────────
{schema_var} = {struct_code}

# ─── Read ──────────────────────────────────────────────────────────────────
{df_var} = (
    spark.read
    .schema({schema_var})
    .format("{fmt}"){read_opts}
    .load("{in_path}")
)

# ─── (Optional) transformations go here ────────────────────────────────────
# {df_var} = {df_var}.filter(F.col("...") == F.lit("..."))

# ─── Write ─────────────────────────────────────────────────────────────────
(
    {df_var}.write
    .mode("overwrite")
    .format("{fmt}"){write_opts}
    .save("{out_path}")
)

spark.stop()
'''
    return body


def _emit_fixed_width(
    schema_name: str,
    schema_var: str,
    df_var: str,
    in_path: str,
    out_path: str,
    struct_code: str,
    schema: dict[str, Any],
) -> str:
    """Emit a substring-based reader for fixed-byte-positional records."""
    rec_len = schema.get("record_length", 0)
    fields = schema.get("fields", [])

    # Build per-field substring + cast lines.
    cast_table = {
        "string":   "StringType()",
        "integer":  "IntegerType()",
        "long":     "LongType()",
        "double":   "DoubleType()",
        "float":    "FloatType()",
        "boolean":  "BooleanType()",
        "date":     "DateType()",
        "datetime": "TimestampType()",
        "binary":   "BinaryType()",
    }
    select_lines: list[str] = []
    for f in fields:
        if "offset" not in f or "length" not in f:
            continue
        # PySpark substring is 1-indexed.
        off1 = f["offset"] + 1
        length = f["length"]
        t = f["type"]
        if t == "decimal":
            args = f.get("args") or []
            p = args[0] if args else 18
            s = args[1] if len(args) > 1 else 0
            cast_to = f"DecimalType({p}, {s})"
        else:
            cast_to = cast_table.get(t, "StringType()")
        select_lines.append(
            f'    F.substring("value", {off1}, {length}).cast({cast_to}).alias({f["name"]!r}),'
        )

    select_block = "\n".join(select_lines) if select_lines else '    F.col("value"),'

    return f'''"""Auto-generated by the DML Playground.

Reads {schema_name!r} as a fixed-width record (record length = {rec_len} bytes)
using substring extraction, then writes the parsed dataframe to Parquet.
"""
from pyspark.sql import SparkSession, functions as F
from pyspark.sql.types import (
    StructType, StructField, StringType, IntegerType, LongType,
    DoubleType, FloatType, BooleanType, DateType, TimestampType,
    DecimalType, ArrayType, BinaryType,
)

spark = (
    SparkSession.builder
    .appName("{schema_name}_io")
    .config("spark.sql.adaptive.enabled", "true")
    .config("spark.sql.storeAssignmentPolicy", "STRICT")
    .getOrCreate()
)

# ─── Target schema (translated from DML DEFINE {schema_name}) ──────────────
{schema_var} = {struct_code}

# ─── Read fixed-width text and slice into typed columns ────────────────────
_raw = spark.read.text("{in_path}")
{df_var} = _raw.select(
{select_block}
)

# ─── (Optional) transformations go here ────────────────────────────────────
# {df_var} = {df_var}.filter(F.col("...") == F.lit("..."))

# ─── Write to Parquet (the canonical store for fixed-width feeds) ──────────
(
    {df_var}.write
    .mode("overwrite")
    .format("parquet")
    .save("{out_path}")
)

spark.stop()
'''


def _emit_ebcdic(
    schema_name: str,
    schema_var: str,
    df_var: str,
    in_path: str,
    out_path: str,
    struct_code: str,
    schema: dict[str, Any],
) -> str:
    """Emit a cobrix-based reader for EBCDIC / packed-decimal records."""
    return f'''"""Auto-generated by the DML Playground.

Reads {schema_name!r} as a mainframe-encoded record (EBCDIC / packed-decimal).
Requires cobrix on the classpath:

    spark-submit \\
        --packages za.co.absa.cobrix:spark-cobol_2.12:2.6.10 \\
        {schema_name}_io.py

You will need an Ab Initio DML → COBOL copybook translator (out of scope here)
or a hand-written copybook to feed into ``copybook_contents``.
"""
from pyspark.sql import SparkSession, functions as F
from pyspark.sql.types import (
    StructType, StructField, StringType, IntegerType, LongType,
    DoubleType, FloatType, BooleanType, DateType, TimestampType,
    DecimalType, ArrayType, BinaryType,
)

spark = (
    SparkSession.builder
    .appName("{schema_name}_io")
    .config("spark.sql.adaptive.enabled", "true")
    .config("spark.sql.storeAssignmentPolicy", "STRICT")
    .getOrCreate()
)

# ─── Target schema (translated from DML DEFINE {schema_name}) ──────────────
{schema_var} = {struct_code}

# ─── Read via cobrix ────────────────────────────────────────────────────────
COPYBOOK = """\\
01 RECORD.
   05 FIELD-A PIC X(10).
   05 FIELD-B PIC 9(8) COMP-3.
"""  # TODO: translate from DML to COBOL copybook

{df_var} = (
    spark.read
    .format("cobol")
    .option("copybook_contents", COPYBOOK)
    .option("encoding", "ebcdic")
    .load("{in_path}")
)

# ─── (Optional) transformations go here ────────────────────────────────────

# ─── Write to Parquet for downstream pipelines ─────────────────────────────
(
    {df_var}.write
    .mode("overwrite")
    .format("parquet")
    .save("{out_path}")
)

spark.stop()
'''
