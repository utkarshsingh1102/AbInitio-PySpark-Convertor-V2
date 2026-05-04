"""E6 — extract subexpressions that appear ≥ 2 times within a single
Reformat block into a shared intermediate column.

We're conservative: only extract expressions that are
  * non-trivial (length > 12 chars, not a single column ref / literal)
  * appear in the rendered RHS of two or more assignments
The shared column is named ``__cse_<hash>`` and is added as a
non-output column at the head of the block; the original assignments
are rewritten to reference it. Codegen drops the temp via the final
``.select(*output_columns)``.
"""
from __future__ import annotations

import hashlib
import re
from collections import Counter
from typing import List

from ....ir.models import IRNode
from ..base import OptimizerRule, OptimizationReport, ReportEntry

_MIN_LEN = 12
_TRIVIAL_RE = re.compile(r"^\s*`?\w+`?\s*$")  # plain column ref

# Find balanced parenthesised subexpressions of reasonable length.
_PAREN_GROUP_RE = re.compile(r"\([^()]+\)")


class DeduplicateCommonSubexpressions(OptimizerRule):
    name = "DeduplicateCommonSubexpressions"
    stage = "expression"

    def apply(self, nodes: List[IRNode], report: OptimizationReport) -> List[IRNode]:
        affected: list[str] = []
        total_extracted = 0
        for n in nodes:
            if n.ir_type != "transform":
                continue
            block = n.config.get("block") or {}
            assignments = block.get("assignments") or []
            if len(assignments) < 2:
                continue

            # Tally interior parenthesised subexpressions across all string RHSs
            counts: Counter[str] = Counter()
            for _, expr in assignments:
                if not isinstance(expr, str):
                    continue
                for m in _PAREN_GROUP_RE.finditer(expr):
                    e = m.group(0)
                    if _is_substantial(e):
                        counts[e] += 1

            extractable = [e for e, c in counts.most_common() if c >= 2]
            if not extractable:
                continue

            # Build a shared-name table (deterministic short hash)
            mapping: dict[str, str] = {}
            for e in extractable:
                h = hashlib.sha1(e.encode()).hexdigest()[:8]
                mapping[e] = f"__cse_{h}"

            new_assignments: list[tuple[str, object]] = []
            for shared_expr, alias in mapping.items():
                new_assignments.append((alias, shared_expr))
            for col, expr in assignments:
                if isinstance(expr, str):
                    rewritten = expr
                    for shared_expr, alias in mapping.items():
                        rewritten = rewritten.replace(shared_expr, f"`{alias}`")
                    new_assignments.append((col, rewritten))
                else:
                    new_assignments.append((col, expr))

            new_block = dict(block)
            new_block["assignments"] = new_assignments
            cfg = dict(n.config)
            cfg["block"] = new_block
            # The CSE columns must NOT appear in the final select projection.
            n.config = cfg
            affected.append(n.id)
            total_extracted += len(mapping)

        if affected:
            report.add(ReportEntry(
                rule=self.name,
                nodes_affected=affected,
                description=f"Extracted {total_extracted} common subexpression(s) across {len(affected)} node(s)",
            ))
        return nodes


def _is_substantial(s: str) -> bool:
    if len(s) < _MIN_LEN:
        return False
    if _TRIVIAL_RE.match(s.strip("()")):
        return False
    return True
