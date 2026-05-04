"""Component plugin package.

Importing this package triggers auto-discovery of every sibling module so
that each plugin's ``@register`` decorator runs and populates ``REGISTRY``.

Side effect on import: ``REGISTRY`` is populated.
"""
from __future__ import annotations

import importlib
import pkgutil
from pathlib import Path

from .base import REGISTRY, ComponentPlugin, EmitContext, register

__all__ = ["REGISTRY", "ComponentPlugin", "EmitContext", "register", "discover"]


def discover() -> None:
    """Import every sibling module so plugins self-register."""
    pkg_path = Path(__file__).parent
    for mod in pkgutil.iter_modules([str(pkg_path)]):
        if mod.name.startswith("_") or mod.name == "base":
            continue
        importlib.import_module(f"{__name__}.{mod.name}")


discover()
