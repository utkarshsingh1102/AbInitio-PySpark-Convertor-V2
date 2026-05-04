"""Ab Initio ``${VAR}`` parameter interpolation.

Parameters are declared in the ``<parameters>`` block of the ``.mp`` file
and substituted into every string-valued attribute / property *at parse
time*, so the IR (and thus the generated PySpark) sees only concrete
literals.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Any

_VAR_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


def extract_params(root: ET.Element) -> dict[str, str]:
    """Pull ``<parameters><param name=.. value=../></parameters>`` into a dict.

    Tolerates both attribute-style (``<param name=.. value=..>``) and
    text-style (``<param name=..>value</param>``).
    """
    out: dict[str, str] = {}
    block = root.find("parameters") or root.find("Parameters")
    if block is None:
        return out
    for p in block.findall("param") + block.findall("Param"):
        name = p.get("name")
        if not name:
            continue
        if p.get("value") is not None:
            out[name] = p.get("value", "")
        else:
            out[name] = (p.text or "").strip()
    return out


def interpolate(value: str, params: dict[str, str]) -> str:
    """Replace every ``${VAR}`` occurrence with ``params[VAR]`` (recursive,
    bounded depth) — leaves unknown vars untouched.
    """
    if not value or "${" not in value:
        return value
    seen: set[str] = set()
    cur = value
    for _ in range(8):  # bounded recursion
        m = _VAR_RE.search(cur)
        if m is None:
            return cur
        if cur in seen:  # cycle
            return cur
        seen.add(cur)
        cur = _VAR_RE.sub(
            lambda mm: params.get(mm.group(1), mm.group(0)), cur
        )
    return cur


def interpolate_all(obj: Any, params: dict[str, str]) -> Any:
    """Recursively walk ``obj`` and ``interpolate`` every str leaf."""
    if isinstance(obj, str):
        return interpolate(obj, params)
    if isinstance(obj, dict):
        return {k: interpolate_all(v, params) for k, v in obj.items()}
    if isinstance(obj, list):
        return [interpolate_all(v, params) for v in obj]
    if isinstance(obj, tuple):
        return tuple(interpolate_all(v, params) for v in obj)
    return obj
