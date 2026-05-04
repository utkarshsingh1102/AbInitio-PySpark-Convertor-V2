"""E4 — rewrite leftover Ab Initio-style UDF calls to native Spark functions.

The .xfr parser already maps known functions via ``FN_TABLE``, so most
expressions arrive native. This rule is a *safety net* for IR that was
hand-built or that came in via a custom path; it scans for known
Ab Initio function names and rewrites them. Unknown UDFs are flagged in
the report's ``warnings`` so the human knows the optimizer left a
black-box function in place.
"""
from __future__ import annotations

import re
from typing import List

from ....ir.models import IRNode
from ..base import OptimizerRule, OptimizationReport, ReportEntry

# Map snake_case Ab-Initio-style identifiers → native SQL form.
# Each value is a callable taking a list of arg strings and returning the
# rewritten expression.
_REWRITES = {
    "string_length":   lambda a: f"LENGTH({a[0]})",
    "trim_leading":    lambda a: f"LTRIM({a[0]})",
    "trim_trailing":   lambda a: f"RTRIM({a[0]})",
    "is_null":         lambda a: f"({a[0]} IS NULL)",
    "is_not_null":     lambda a: f"({a[0]} IS NOT NULL)",
    "to_upper":        lambda a: f"UPPER({a[0]})",
    "to_lower":        lambda a: f"LOWER({a[0]})",
    "coalesce_first":  lambda a: f"COALESCE({', '.join(a)})",
    "abs_value":       lambda a: f"ABS({a[0]})",
    "round_to":        lambda a: f"ROUND({a[0]}, {a[1]})",
    "mod":             lambda a: f"MOD({a[0]}, {a[1]})",
    "date_add_days":   lambda a: f"DATE_ADD({a[0]}, {a[1]})",
}

# Things that LOOK like function calls but are SQL syntax we leave alone:
# native functions, types used inside CAST(... AS T(...)), keywords.
_NATIVE = {
    # functions
    "LENGTH", "UPPER", "LOWER", "TRIM", "LTRIM", "RTRIM",
    "ABS", "ROUND", "FLOOR", "CEIL", "MOD", "SQRT",
    "COALESCE", "CAST",
    "TO_DATE", "TO_TIMESTAMP", "DATE_FORMAT", "DATEDIFF",
    "DATE_ADD", "DATE_SUB", "YEAR", "MONTH", "DAY",
    "SUBSTRING", "SUBSTR", "CONCAT", "REPLACE",
    # aggregates / window
    "SUM", "MIN", "MAX", "COUNT", "AVG", "FIRST", "LAST",
    "COLLECT_LIST", "COLLECT_SET", "EXPLODE",
    "ROW_NUMBER", "RANK", "DENSE_RANK",
    # SQL types — appear inside `CAST(expr AS DECIMAL(...))` etc.
    "DECIMAL", "INT", "INTEGER", "BIGINT", "SMALLINT", "TINYINT",
    "DOUBLE", "FLOAT", "STRING", "BOOLEAN",
    "DATE", "TIMESTAMP", "VARCHAR", "CHAR", "BINARY",
    "ARRAY", "MAP", "STRUCT",
    # keywords
    "CASE", "WHEN", "THEN", "ELSE", "END",
    "AND", "OR", "NOT", "IS", "NULL", "TRUE", "FALSE", "IN", "LIKE", "AS",
}

_FN_CALL_RE = re.compile(r"\b([a-z_][a-z0-9_]*)\s*\(", re.IGNORECASE)
_REWRITE_RE = re.compile(
    r"\b(" + "|".join(_REWRITES.keys()) + r")\s*\((.*?)\)",
    re.IGNORECASE,
)


class RewriteUDFsToNativeFunctions(OptimizerRule):
    name = "RewriteUDFsToNativeFunctions"
    stage = "expression"

    def apply(self, nodes: List[IRNode], report: OptimizationReport) -> List[IRNode]:
        affected: list[str] = []
        unresolved: set[tuple[str, str]] = set()
        for n in nodes:
            if n.ir_type != "transform":
                continue
            block = n.config.get("block") or {}
            assignments = block.get("assignments") or []
            if not assignments:
                continue
            new_assignments: list[tuple[str, object]] = []
            changed = False
            for col, expr in assignments:
                if isinstance(expr, str):
                    rewritten = _rewrite_calls(expr)
                    if rewritten != expr:
                        changed = True
                    new_assignments.append((col, rewritten))
                    for m in _FN_CALL_RE.finditer(rewritten):
                        fname = m.group(1)
                        if fname.upper() not in _NATIVE and fname.lower() not in _REWRITES:
                            unresolved.add((n.id, fname))
                else:
                    new_assignments.append((col, expr))
            if changed:
                new_block = dict(block)
                new_block["assignments"] = new_assignments
                cfg = dict(n.config)
                cfg["block"] = new_block
                n.config = cfg
                affected.append(n.id)

        if affected:
            report.add(ReportEntry(
                rule=self.name,
                nodes_affected=affected,
                description=f"Rewrote known UDFs to native Spark functions on {len(affected)} node(s)",
            ))
        for node_id, fname in sorted(unresolved):
            report.add(ReportEntry(
                rule=self.name,
                severity="warn",
                nodes_affected=[node_id],
                description=f"Unresolved function {fname!r} on node {node_id}; left as-is",
            ))
        return nodes


def _rewrite_calls(expr: str) -> str:
    def _replace(m: re.Match) -> str:
        fname = m.group(1).lower()
        raw_args = m.group(2)
        args = _split_args(raw_args)
        rule = _REWRITES.get(fname)
        if rule is None:
            return m.group(0)
        try:
            return rule(args)
        except (IndexError, KeyError):
            return m.group(0)

    return _REWRITE_RE.sub(_replace, expr)


def _split_args(s: str) -> list[str]:
    """Split top-level commas (respect nested parens)."""
    out, depth, buf = [], 0, ""
    for ch in s:
        if ch == "(":
            depth += 1
            buf += ch
        elif ch == ")":
            depth -= 1
            buf += ch
        elif ch == "," and depth == 0:
            out.append(buf.strip())
            buf = ""
        else:
            buf += ch
    if buf.strip():
        out.append(buf.strip())
    return out
