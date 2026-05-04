"""Adapter for Set C — exposes ``parse_dml`` over the project's parser."""
from __future__ import annotations

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from backend.parser.dml_parser import parse_dml_string  # noqa: E402


def parse_dml(src: str) -> dict:
    schemas = parse_dml_string(src)
    if not schemas:
        raise ValueError("No DEFINE/record block parsed")
    return next(iter(schemas.values()))
