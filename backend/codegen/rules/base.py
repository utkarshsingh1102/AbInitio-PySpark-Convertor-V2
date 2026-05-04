"""Optimizer rule contract + per-rule report entries.

Every rule is a stateless callable that takes ``list[IRNode]`` and returns
a (possibly mutated) ``list[IRNode]``. Rules also report what they changed
into a shared ``OptimizationReport`` so the frontend can show a human
audit trail of "what the optimizer did to your code".
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List

from ...ir.models import IRNode


@dataclass
class ReportEntry:
    rule: str
    nodes_affected: list[str] = field(default_factory=list)
    description: str = ""
    severity: str = "info"  # info | warn | error


@dataclass
class OptimizationReport:
    pipeline_id: str = ""
    rules_applied: list[ReportEntry] = field(default_factory=list)
    warnings: list[ReportEntry] = field(default_factory=list)
    unresolved: list[ReportEntry] = field(default_factory=list)

    def add(self, entry: ReportEntry) -> None:
        bucket = (
            self.warnings if entry.severity == "warn"
            else self.unresolved if entry.severity == "error"
            else self.rules_applied
        )
        bucket.append(entry)

    def to_dict(self) -> dict:
        return {
            "pipeline_id": self.pipeline_id,
            "rules_applied": [e.__dict__ for e in self.rules_applied],
            "warnings":      [e.__dict__ for e in self.warnings],
            "unresolved":    [e.__dict__ for e in self.unresolved],
        }


class OptimizerRule(ABC):
    """Abstract base class for every optimization rule."""

    name: str = ""
    enabled: bool = True
    stage: str = "structural"  # structural | expression | write

    @abstractmethod
    def apply(self, nodes: List[IRNode], report: OptimizationReport) -> List[IRNode]:
        """Mutate IR and append zero or more ``ReportEntry`` rows."""
        raise NotImplementedError

    def __call__(self, nodes: List[IRNode], report: OptimizationReport) -> List[IRNode]:
        if not self.enabled:
            return nodes
        return self.apply(nodes, report)
