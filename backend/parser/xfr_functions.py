"""Ab Initio xfr function → Spark SQL function mapping table.

Adding a new mapping is one line in ``FN_TABLE``. The xfr parser looks up
function names here and renders them via the spec's template.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Sequence


@dataclass(frozen=True)
class FnSpec:
    """Single function-mapping rule.

    ``template`` is a ``str.format``-style string. ``{0}``..``{N}`` are the
    rendered arguments; ``{args}`` is the comma-joined arg list (variadic).

    ``arity`` is None for variadic functions.

    ``format_arg_idx`` (when non-None) marks an argument that is an Ab Initio
    date/time format string and must be translated to Spark's format codes
    (e.g. ``YYYY-MM-DD`` → ``yyyy-MM-dd``).
    """

    template: str
    arity: int | None
    format_arg_idx: int | None = None
    # Optional post-processor for further reshaping (rare).
    post: Callable[[Sequence[str]], str] | None = None


# ── format string translation ──────────────────────────────────────────────

# Ab Initio uses uppercase `YYYY-MM-DD HH:MM:SS`; Spark uses `yyyy-MM-dd
# HH:mm:ss`. The mapping is character-by-character in length, so we
# translate token by token.
_FORMAT_TOKENS: list[tuple[str, str]] = [
    ("YYYY", "yyyy"),
    ("YY",   "yy"),
    ("MMM",  "MMM"),
    ("MM",   "MM"),
    ("DD",   "dd"),
    ("HH24", "HH"),
    ("HH",   "HH"),
    ("MI",   "mm"),
    # ":MM:" between HH and SS in Ab Initio is minutes (not month);
    # we translate explicitly via context — handled below.
    ("SS",   "ss"),
    ("FF",   "SSS"),
    ("AM",   "a"),
    ("PM",   "a"),
]


def translate_format(ab_fmt: str) -> str:
    """Translate an Ab Initio date/time format → Spark format string.

    Heuristic: scan tokens longest-first. Special-case the ambiguous ``MM``
    after ``HH`` (minutes) vs after ``-`` or start (month).
    """
    if ab_fmt is None:
        return ab_fmt
    s = ab_fmt
    # Greedy token replacement, longest first.
    for src, dst in sorted(_FORMAT_TOKENS, key=lambda p: -len(p[0])):
        s = s.replace(src, dst)
    # Fix ambiguous `MM`: between `HH` and `:` it's minutes (`mm`),
    # otherwise month (`MM`). The greedy replacement above already turned
    # all `MM` into `MM`. Disambiguate by context: `HH:MM` → `HH:mm`.
    s = re.sub(r"(?<=HH:)MM", "mm", s)
    s = re.sub(r"(?<=HH:mm:)SS", "ss", s)  # noop today, defensive
    return s


# ── function table ────────────────────────────────────────────────────────


FN_TABLE: dict[str, FnSpec] = {
    # string fns
    "string_length": FnSpec("LENGTH({0})", 1),
    "length":        FnSpec("LENGTH({0})", 1),
    "trim":          FnSpec("TRIM({0})", 1),
    "ltrim":         FnSpec("LTRIM({0})", 1),
    "rtrim":         FnSpec("RTRIM({0})", 1),
    "upper":         FnSpec("UPPER({0})", 1),
    "lower":         FnSpec("LOWER({0})", 1),
    "substring":     FnSpec("SUBSTRING({0}, {1}, {2})", 3),
    "concat":        FnSpec("CONCAT({args})", None),
    "replace":       FnSpec("REPLACE({0}, {1}, {2})", 3),

    # null / coalesce
    "is_null":       FnSpec("({0} IS NULL)", 1),
    "is_not_null":   FnSpec("({0} IS NOT NULL)", 1),
    "coalesce":      FnSpec("COALESCE({args})", None),
    "nvl":           FnSpec("COALESCE({0}, {1})", 2),

    # numeric
    "abs":           FnSpec("ABS({0})", 1),
    "round":         FnSpec("ROUND({0}, {1})", 2),
    "floor":         FnSpec("FLOOR({0})", 1),
    "ceil":          FnSpec("CEIL({0})", 1),
    "ceiling":       FnSpec("CEIL({0})", 1),
    "sqrt":          FnSpec("SQRT({0})", 1),

    # type casts (Ab Initio convention `decimal(expr, p, s)`)
    "decimal":       FnSpec("CAST({0} AS DECIMAL({1}, {2}))", 3),
    "integer":       FnSpec("CAST({0} AS INT)", 1),
    "string":        FnSpec("CAST({0} AS STRING)", 1),
    "double":        FnSpec("CAST({0} AS DOUBLE)", 1),

    # date/time
    "string_to_date":     FnSpec("TO_DATE({0}, {1})", 2, format_arg_idx=1),
    "string_to_datetime": FnSpec("TO_TIMESTAMP({0}, {1})", 2, format_arg_idx=1),
    "to_date":            FnSpec("TO_DATE({0}, {1})", 2, format_arg_idx=1),
    "to_timestamp":       FnSpec("TO_TIMESTAMP({0}, {1})", 2, format_arg_idx=1),
    "date_diff":          FnSpec("DATEDIFF({0}, {1})", 3),  # 3rd arg "days" ignored
    "datediff":           FnSpec("DATEDIFF({0}, {1})", 2),
    "current_date":       FnSpec("CURRENT_DATE()", 0),
    "current_timestamp":  FnSpec("CURRENT_TIMESTAMP()", 0),
    "year":               FnSpec("YEAR({0})", 1),
    "month":              FnSpec("MONTH({0})", 1),
    "day":                FnSpec("DAY({0})", 1),
}


def render_fn(fn_name: str, args: list[str]) -> str | None:
    """Render a function call using ``FN_TABLE``. Returns None if unknown."""
    spec = FN_TABLE.get(fn_name.lower())
    if spec is None:
        return None
    rendered = list(args)
    if spec.format_arg_idx is not None and spec.format_arg_idx < len(rendered):
        rendered[spec.format_arg_idx] = _translate_format_literal(
            rendered[spec.format_arg_idx]
        )
    if spec.arity is None:
        return spec.template.format(args=", ".join(rendered))
    if len(rendered) != spec.arity:
        # Special case: date_diff has 2- and 3-arg forms (3rd is unit).
        if fn_name.lower() == "date_diff" and len(rendered) >= 2:
            return f"DATEDIFF({rendered[0]}, {rendered[1]})"
        return None
    return spec.template.format(*rendered)


def _translate_format_literal(arg: str) -> str:
    """If ``arg`` is a quoted SQL string literal, translate the format inside."""
    if len(arg) >= 2 and arg[0] == "'" and arg[-1] == "'":
        inner = arg[1:-1]
        return f"'{translate_format(inner)}'"
    return arg
