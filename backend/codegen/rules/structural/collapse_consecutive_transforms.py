"""S5 — merge consecutive Reformat nodes when safe.

Two adjacent ``transform`` nodes ``T1 → T2`` collapse into a single node
when:
  * ``T1.fan_out == 1`` (T2 is the only consumer)
  * No assignment in T2 references a column with the same name that
    T1 *redefines* AND that column requires T1's intermediate
    projection ordering to be visible — practical proxy: any T2
    expression referencing a column that T1 writes is allowed because
    we can chain the assignments preserving order.

We physically remove T1 from the IR list and prepend its assignments
to T2 (its outputs/inputs/edges already collapse since T1 only fed T2).
"""
from __future__ import annotations

from typing import List

from ....ir.models import IRNode
from ..base import OptimizerRule, OptimizationReport, ReportEntry


class CollapseConsecutiveTransforms(OptimizerRule):
    name = "CollapseConsecutiveTransforms"
    stage = "structural"

    def apply(self, nodes: List[IRNode], report: OptimizationReport) -> List[IRNode]:
        by_id = {n.id: n for n in nodes}
        affected: list[str] = []
        progress = True
        result = list(nodes)

        while progress:
            progress = False
            for i, t1 in enumerate(result):
                if t1.ir_type != "transform" or t1.fan_out != 1:
                    continue
                if t1.config.get("cache") or t1.config.get("passthrough"):
                    continue
                if not t1.outputs:
                    continue
                t2 = by_id.get(t1.outputs[0])
                if t2 is None or t2.ir_type != "transform":
                    continue
                if t2.config.get("cache"):
                    continue
                # Merge: prepend t1's assignments to t2; carry t2's order.
                merged = _merge_blocks(t1, t2)
                t2.config = dict(t2.config)
                t2.config["block"] = merged
                # Rewire DAG: T2 inherits T1's inputs.
                upstream_id = t1.inputs[0] if t1.inputs else None
                t2.inputs = [upstream_id] if upstream_id else []
                t2.port_inputs = {p: upstream_id for p in t2.port_inputs.keys() or ["in"]}
                if upstream_id:
                    upstream = by_id[upstream_id]
                    upstream.outputs = [t2.id if x == t1.id else x for x in upstream.outputs]
                # Drop T1
                result.pop(i)
                affected.extend([t1.id, t2.id])
                progress = True
                by_id = {n.id: n for n in result}
                break

        if affected:
            report.add(ReportEntry(
                rule=self.name,
                nodes_affected=sorted(set(affected)),
                description=f"Merged {len(affected) // 2} pair(s) of consecutive transforms",
            ))
        nodes[:] = result
        return nodes


def _merge_blocks(t1: IRNode, t2: IRNode) -> dict:
    """Concatenate assignments — t1 first, then t2. Later (t2) wins on conflicts."""
    a1 = (t1.config.get("block") or {}).get("assignments") or []
    a2 = (t2.config.get("block") or {}).get("assignments") or []
    seen: dict[str, object] = {}
    out: list[tuple[str, object]] = []
    for col, expr in a1 + a2:
        seen[col] = expr  # last write wins
    # Preserve original order: keys appear in the order they first appeared
    order: list[str] = []
    for col, _ in a1 + a2:
        if col not in order:
            order.append(col)
    for col in order:
        out.append((col, seen[col]))
    return {"type": "transform", "assignments": out}
