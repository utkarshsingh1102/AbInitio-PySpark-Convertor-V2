"""S1 — push Filter nodes upstream past projection-only Reformats.

Goal: shrink data volume before joins / aggregations / expensive transforms.

Push is **safe** when:
  - the filter's referenced columns all exist in the upstream node's schema
  - the intermediate node is a projection-only Reformat: every assignment is
    either an identity or doesn't redefine a column the filter touches
  - the upstream is a single-input node (joins / aggregates block the push)

Push is **unsafe** when:
  - filter references a column computed by the intermediate Reformat
  - intermediate is a Join (filter may need both sides), Aggregate (filter
    may need post-grouped values), or has fan-out > 1

The transformation rewires the IR DAG: edges, ``port_inputs``, ``inputs``,
``outputs``. Topological order is preserved by re-sorting after rewiring.
"""
from __future__ import annotations

import re
from typing import List

from ....ir.models import IRNode
from ..base import OptimizerRule, OptimizationReport, ReportEntry

_BACKTICK_COL_RE = re.compile(r"`([A-Za-z_][A-Za-z0-9_]*)`")


class EarlyFilterPushdown(OptimizerRule):
    name = "EarlyFilterPushdown"
    stage = "structural"

    def apply(self, nodes: List[IRNode], report: OptimizationReport) -> List[IRNode]:
        affected: list[str] = []
        # Make ID-based lookups; iterate over a snapshot since we may mutate.
        by_id = {n.id: n for n in nodes}
        progress = True
        while progress:
            progress = False
            for f in [n for n in nodes if n.ir_type == "filter"]:
                up_id = f.inputs[0] if f.inputs else None
                if up_id is None:
                    continue
                up = by_id[up_id]
                if not _can_push_past(up, f, by_id):
                    continue
                # Rewire: filter takes upstream's input(s); upstream's output
                # consumers replace filter where appropriate.
                new_filter_inputs = list(up.inputs)
                _rewire_push(up, f, by_id, nodes)
                affected.append(f.id)
                progress = True
                break  # restart the scan since the DAG mutated

        if affected:
            report.add(ReportEntry(
                rule=self.name,
                nodes_affected=sorted(set(affected)),
                description=f"Pushed {len(set(affected))} filter(s) upstream",
            ))
        return nodes


def _can_push_past(up: IRNode, f: IRNode, by_id: dict) -> bool:
    if up.ir_type not in ("transform",):
        return False
    if up.fan_out > 1:
        return False
    refs = _refs_in_filter(f)
    if not refs:
        return False

    block = up.config.get("block") or {}
    assignments = block.get("assignments") or []
    redefined_non_identity: set[str] = set()
    for col, expr in assignments:
        if isinstance(expr, str):
            inner = expr.strip().strip("`")
            if inner == col:
                continue
        if isinstance(expr, dict):
            redefined_non_identity.add(col)
            continue
        redefined_non_identity.add(col)

    if refs & redefined_non_identity:
        return False
    # Filter columns must exist in the upstream node's input schema.
    if up.inputs:
        upstream_node = by_id.get(up.inputs[0])
        if upstream_node and upstream_node.schema:
            avail = {fld["name"] for fld in upstream_node.schema.get("fields", [])}
            if refs - avail:
                return False
    return True


def _refs_in_filter(f: IRNode) -> set[str]:
    cond = ""
    block = f.config.get("block") or {}
    if block.get("type") == "filter":
        cond = block.get("condition") or ""
    cond = cond or f.config.get("__filter_expr") or f.config.get("condition") or ""
    cond_no_str = _strip_quoted(cond)
    return set(_BACKTICK_COL_RE.findall(cond_no_str)) | _bare_refs(cond_no_str)


_QUOTED_RE = re.compile(r"'(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\"")
_BARE_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\b")
_RESERVED = {"AND", "OR", "NOT", "TRUE", "FALSE", "NULL", "IS", "IN",
             "CASE", "WHEN", "THEN", "ELSE", "END", "LIKE", "BETWEEN"}


def _strip_quoted(s: str) -> str:
    return _QUOTED_RE.sub("''", s)


def _bare_refs(cond: str) -> set[str]:
    # Skip identifiers that ARE inside backticks — those are already counted.
    cond = re.sub(r"`[^`]+`", "", cond)
    return {
        m.group(1) for m in _BARE_RE.finditer(cond)
        if m.group(1).upper() not in _RESERVED and not m.group(1).isdigit()
    }


def _rewire_push(up: IRNode, f: IRNode, by_id: dict, all_nodes: list) -> None:
    """``A → up → f → C``  becomes  ``A → f → up → C``.

    Updates: f.inputs, up.inputs, up.outputs, f.outputs, port_inputs on the
    affected nodes. Then re-orders ``all_nodes`` topologically.
    """
    a_id = up.inputs[0] if up.inputs else None
    if a_id is None:
        return
    a = by_id[a_id]
    consumers = [n for n in all_nodes if f.id in n.inputs]

    # Edge a→up becomes a→f
    f.inputs = [a_id]
    f.port_inputs = {p: a_id for p in (f.port_inputs or {"in": a_id}).keys()}
    if not f.port_inputs:
        f.port_inputs = {"in": a_id}

    # Edge up→f becomes up's input ← f
    up.inputs = [f.id]
    up.port_inputs = {"in": f.id}

    # f.outputs were consumers C; now up.outputs = [c.id for c in consumers]
    up.outputs = [c.id for c in consumers]
    for c in consumers:
        c.inputs = [up.id if x == f.id else x for x in c.inputs]
        c.port_inputs = {p: (up.id if v == f.id else v) for p, v in c.port_inputs.items()}

    f.outputs = [up.id]

    # a's outputs: drop up.id, add f.id
    a.outputs = [f.id if x == up.id else x for x in a.outputs]

    # Re-sort all_nodes topologically (by mutating in place)
    _retopo(all_nodes)


def _retopo(nodes: list) -> None:
    indeg = {n.id: 0 for n in nodes}
    by_id = {n.id: n for n in nodes}
    for n in nodes:
        for up in n.inputs:
            if up in indeg:
                indeg[n.id] += 1
    queue = sorted([nid for nid, d in indeg.items() if d == 0])
    order: list = []
    while queue:
        nid = queue.pop(0)
        order.append(by_id[nid])
        for nxt in by_id[nid].outputs:
            if nxt in indeg:
                indeg[nxt] -= 1
                if indeg[nxt] == 0:
                    queue.append(nxt)
                    queue.sort()
    if len(order) == len(nodes):
        nodes[:] = order
