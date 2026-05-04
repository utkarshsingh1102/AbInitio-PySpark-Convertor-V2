"""Shared helpers for component plugins."""
from __future__ import annotations

from typing import Any


def py_repr(value: Any) -> str:
    """Stable repr suitable for embedding in generated Python source."""
    return repr(value)


def csv_to_list(value: str | list | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    return [v.strip() for v in str(value).split(",") if v.strip()]


def escape_sql(s: str) -> str:
    """Escape a string for embedding inside a Python `"..."` SQL expr."""
    return s.replace("\\", "\\\\").replace('"', '\\"')


def schema_dict_to_struct_code(schema: dict[str, Any] | None) -> str:
    """Render a DML schema dict (from dml_parser) as a `StructType(...)` literal."""
    if schema is None:
        return "StructType([])"
    fields = schema.get("fields", [])
    if not fields:
        return "StructType([])"
    parts = [_field_to_code(f) for f in fields]
    return "StructType([\n    " + ",\n    ".join(parts) + ",\n])"


def _field_to_code(f: dict[str, Any]) -> str:
    dims = f.get("array_dims") or ([None] if f.get("array") else [])
    if f.get("type") == "struct":
        inner = schema_dict_to_struct_code({"fields": f["fields"]})
        for _ in dims:
            inner = f"ArrayType({inner}, True)"
        return f"StructField({f['name']!r}, {inner}, {bool(f.get('nullable', True))!r})"
    spark_t = _primitive_to_code(f["type"], f.get("args", []))
    for _ in dims:
        spark_t = f"ArrayType({spark_t}, True)"
    return f"StructField({f['name']!r}, {spark_t}, {bool(f.get('nullable', True))!r})"


def _primitive_to_code(name: str, args: list[int]) -> str:
    table = {
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
    if name in table:
        return table[name]
    if name == "decimal":
        precision = args[0] if args else 38
        scale = args[1] if len(args) > 1 else 0
        return f"DecimalType({precision}, {scale})"
    return "StringType()  # unmapped"


def order_by_args(keys: list[str], asc: bool = True) -> str:
    """Render an ``orderBy(...)`` argument list."""
    if not keys:
        return ""
    if asc:
        return ", ".join(f"F.col({k!r})" for k in keys)
    return ", ".join(f"F.col({k!r}).desc()" for k in keys)
