"""Adapter that exposes the project's DML parser under the name the
external test suite expects.

The test suite imports ``parse_dml`` and treats its return value as an
"ast" that ``dml_to_spark.convert_to_spark_schema`` consumes. Internally
we call ``backend.parser.dml_parser.parse_dml_string`` and pass through
the first schema we find.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Ensure the project root is on sys.path when running pytest from this dir.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from backend.parser.dml_parser import parse_dml_string  # noqa: E402


def parse_dml(src: str) -> dict:
    """Parse a DML record/DEFINE and return the first schema dict found."""
    schemas = parse_dml_string(src)
    if not schemas:
        raise ValueError("No DEFINE/record block parsed")
    return next(iter(schemas.values()))
