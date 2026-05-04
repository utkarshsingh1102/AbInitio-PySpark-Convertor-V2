"""Adapter for ``convert_to_spark_schema`` used by the external test suite."""
from __future__ import annotations

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from backend.parser.dml_parser import to_struct_type  # noqa: E402


def convert_to_spark_schema(ast: dict, lossy: bool = True):
    """Lower a parser AST (schema dict) to a PySpark ``StructType``.

    The external test fixtures expect the simplified mapping
    (``decimal → DoubleType``, ``date/datetime → StringType``), so this
    adapter defaults to ``lossy=True``. The project's own callers stick
    with the precise default in ``to_struct_type``.
    """
    return to_struct_type(ast, lossy=lossy)
