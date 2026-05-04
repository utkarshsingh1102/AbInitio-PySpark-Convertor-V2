"""Adapter for Set C — uses lossy mapping to match the test fixtures."""
from __future__ import annotations

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from backend.parser.dml_parser import to_struct_type  # noqa: E402


def convert_to_spark_schema(ast: dict, lossy: bool = True):
    return to_struct_type(ast, lossy=lossy)
