"""Optimization rule package.

Three stages, each containing pure ``OptimizerRule`` implementations.
The pipeline runner (``backend.codegen.optimizer``) chains them in a
fixed order and aggregates an ``OptimizationReport``.
"""
from .base import OptimizationReport, OptimizerRule, ReportEntry
from . import structural, expression, write

__all__ = [
    "OptimizationReport",
    "OptimizerRule",
    "ReportEntry",
    "structural",
    "expression",
    "write",
]
