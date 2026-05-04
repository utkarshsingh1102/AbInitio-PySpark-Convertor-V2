"""S2 — insert ``.select(required_cols)`` on read nodes to drop columns
that are never referenced downstream.

Algorithm: walk the DAG from sinks backward. For every Write/Filter/Join/
Aggregate/Transform, accumulate the set of columns it touches. The
required column set for a Read is the union of columns referenced
anywhere downstream that exist in the Read's schema.
"""
from __future__ import annotations

import re
from typing import List

from ....ir.models import IRNode
from ..base import OptimizerRule, OptimizationReport, ReportEntry

_BT_RE = re.compile(r"`([A-Za-z_][A-Za-z0-9_]*)`")


class ProjectionPruning(OptimizerRule):
    name = "ProjectionPruning"
    stage = "structural"

    def apply(self, nodes: List[IRNode], report: OptimizationReport) -> List[IRNode]:
        by_id = {n.id: n for n in nodes}
        # required_at[node_id] = set of columns that must survive this node's input
        required_at: dict[str, set[str]] = {n.id: set() for n in nodes}

        # Process in reverse topological order so consumers seed first
        for n in reversed(nodes):
            outs_required: set[str] = set()
            for c_id in n.outputs:
                c = by_id.get(c_id)
                if c is None:
                    continue
                outs_required |= required_at[c.id]
            # Add columns this node itself reads
            self_refs = _refs_used_by(n)
            input_required = (outs_required | self_refs)
            # For Reformat: outs_required are *output* names; we need to map
            # to input columns (some come from upstream, some are derived).
            if n.ir_type == "transform":
                block = n.config.get("block") or {}
                assignments = block.get("assignments") or []
                derived = {col for col, _ in assignments}
                # Things consumed downstream but NOT derived must come from input
                inputs_used = (outs_required - derived)
                # Columns referenced in expression bodies of derived columns
                for col, expr in assignments:
                    if col in (outs_required | self_refs) and isinstance(expr, str):
                        inputs_used |= set(_BT_RE.findall(expr))
                input_required = inputs_used | self_refs
            required_at[n.id] = input_required

        affected: list[str] = []
        for n in nodes:
            if n.ir_type != "read" or not n.schema:
                continue
            available = [f["name"] for f in n.schema.get("fields", [])]
            # union of what every downstream consumer needs from THIS read
            needed: set[str] = set()
            for c_id in n.outputs:
                c = by_id.get(c_id)
                if c is None:
                    continue
                needed |= required_at[c.id]
            if not needed:
                continue
            preserved = [c for c in available if c in needed]
            if preserved and len(preserved) < len(available):
                cfg = dict(n.config)
                cfg["select_columns"] = preserved
                n.config = cfg
                affected.append(n.id)

        if affected:
            report.add(ReportEntry(
                rule=self.name,
                nodes_affected=affected,
                description=f"Pruned unused columns from {len(affected)} read(s)",
            ))
        return nodes


def _refs_used_by(n: IRNode) -> set[str]:
    """Columns this node directly references in its own config."""
    refs: set[str] = set()
    if n.ir_type == "filter":
        cond = (
            (n.config.get("block") or {}).get("condition")
            or n.config.get("__filter_expr")
            or n.config.get("condition")
            or ""
        )
        refs |= set(_BT_RE.findall(cond))
    if n.ir_type == "join":
        keys = n.config.get("join_key") or n.config.get("on") or ""
        if isinstance(keys, str):
            refs |= {k.strip() for k in keys.split(",") if k.strip()}
        elif isinstance(keys, list):
            refs |= set(keys)
    if n.ir_type == "aggregate":
        gb = n.config.get("group_by") or n.config.get("key") or ""
        if isinstance(gb, str):
            refs |= {k.strip() for k in gb.split(",") if k.strip()}
        # parse aggregates spec like "sum(x):y"
        agg_spec = n.config.get("aggregates") or ""
        for piece in str(agg_spec).split(","):
            if "(" in piece and ")" in piece:
                inner = piece[piece.index("(") + 1 : piece.index(")")]
                refs.add(inner.strip())
    if n.ir_type == "transform":
        block = n.config.get("block") or {}
        for _, expr in block.get("assignments") or []:
            if isinstance(expr, str):
                refs |= set(_BT_RE.findall(expr))
    return refs
