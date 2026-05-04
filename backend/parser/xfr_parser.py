"""Ab Initio ``.xfr`` transform / filter parser (realistic dialect).

Supports:

    -- comments
    /* and */ block comments

    TRANSFORM name BEGIN
        out.<col> = <expr>;
        ...
    END

    FILTER name BEGIN
        CONDITION: <expr>;
    END

Where <expr> covers:
  - identifiers: in.col, out.col (self-ref), bare col
  - literals: numbers, double- or single-quoted strings, true / false, null
  - arithmetic: + - * /  (string `+` lowered to CONCAT(...) when an
    operand is a string literal)
  - comparison: == != < <= > >=  AND single `=` (Ab Initio convention)
  - logical:    and / or / not   plus &&, ||, !
  - functions:  via xfr_functions.FN_TABLE
  - conditionals: if (cond) then A else B  /  if cond then A else B
                  (chained: ``else if`` works because the else body is
                  itself any expr)

Returns ``dict[block_name, BlockBody]`` where BlockBody is either:
  - a list[(out_col, sql_expr)] for TRANSFORM blocks (in source order)
  - a string (the boolean SQL expression) for FILTER blocks
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence

from lark import Lark, Transformer, v_args

from .preprocess import preprocess_xfr
from .xfr_functions import render_fn

XFR_GRAMMAR = r"""
    start: block+

    block: transform_block | filter_block | bare_block

    transform_block: TRANSFORM NAME "begin"i assign_list "end"i ";"?
    filter_block:    FILTER NAME "begin"i "condition"i ":" expr ";" "end"i ";"?
    bare_block:      assign_list                              -> bare_block

    assign_list: (assign ";")+
    assign: "out" "." NAME "=" expr

    ?expr: or_expr
    ?or_expr: and_expr (OR and_expr)*
    ?and_expr: not_expr (AND and_expr)*
    ?not_expr: NOT not_expr      -> not_op
             | cmp_expr
    ?cmp_expr: arith (CMP_OP arith)?
    ?arith: term (ADD_OP term)*
    ?term: factor (MUL_OP factor)*
    ?factor: "(" expr ")"
           | if_expr
           | func_call
           | column_ref
           | literal

    if_expr: "if" "(" expr ")" ("then")? expr "else" expr  -> if_paren
           | "if" expr "then" expr "else" expr             -> if_bare

    func_call: NAME "(" [expr ("," expr)*] ")"
    column_ref: "in" "." NAME    -> in_col
              | "out" "." NAME   -> out_col
              | NAME             -> bare_col
    literal: NUMBER         -> num_lit
           | ESCAPED_STRING -> dq_str_lit
           | SQ_STRING      -> sq_str_lit
           | "true"i        -> true_lit
           | "false"i       -> false_lit
           | "null"i        -> null_lit

    TRANSFORM.3: "transform"i
    FILTER.3:    "filter"i
    OR.2: "or" | "||"
    AND.2: "and" | "&&"
    NOT.2: "not" | "!"
    CMP_OP: "==" | "!=" | "<=" | ">=" | "<" | ">" | "="
    ADD_OP: "+" | "-"
    MUL_OP: "*" | "/"

    SQ_STRING: /'(?:[^'\\]|\\.)*'/

    %import common.CNAME -> NAME
    %import common.SIGNED_NUMBER -> NUMBER
    %import common.ESCAPED_STRING
    %import common.WS
    %ignore WS
    %ignore /\/\/[^\n]*/
    %ignore /\/\*[\s\S]*?\*\//
"""


@v_args(inline=True)
class _XfrTransformer(Transformer):
    # ── top-level structure ────────────────────────────────────────────
    def start(self, *blocks):
        out: dict[str, Any] = {}
        anon = 0
        for b in blocks:
            kind = b["kind"]
            if kind == "bare":
                anon += 1
                out[f"__bare_{anon}"] = {"type": "transform", "assignments": b["assignments"]}
            elif kind == "transform":
                out[b["name"]] = {"type": "transform", "assignments": b["assignments"]}
            elif kind == "filter":
                out[b["name"]] = {"type": "filter", "condition": b["condition"]}
        return out

    def block(self, b):
        return b

    def transform_block(self, _kw, name_tok, assignments):
        return {"kind": "transform", "name": str(name_tok), "assignments": assignments}

    def filter_block(self, _kw, name_tok, expr):
        return {"kind": "filter", "name": str(name_tok), "condition": str(expr)}

    def bare_block(self, assignments):
        return {"kind": "bare", "assignments": assignments}

    def assign_list(self, *assignments):
        return list(assignments)

    def assign(self, name, expr):
        return (str(name), str(expr))

    # ── boolean / comparison ───────────────────────────────────────────
    def or_expr(self, *items):
        return _join_logical(items, "OR")

    def and_expr(self, *items):
        return _join_logical(items, "AND")

    def not_op(self, _tok, expr):
        return f"(NOT {expr})"

    def cmp_expr(self, left, op=None, right=None):
        if op is None:
            return left
        # Single `=` becomes SQL `=` already (we just emit the operator literally)
        return f"({left} {op} {right})"

    # ── arithmetic / string concat ─────────────────────────────────────
    def arith(self, *items):
        return _join_arith_or_concat(items)

    def term(self, *items):
        return _join_arith_explicit(items)

    # ── if / function / refs ───────────────────────────────────────────
    def if_paren(self, cond, then_e, else_e):
        return f"(CASE WHEN {cond} THEN {then_e} ELSE {else_e} END)"

    def if_bare(self, cond, then_e, else_e):
        return f"(CASE WHEN {cond} THEN {then_e} ELSE {else_e} END)"

    def func_call(self, name, *args):
        rendered = [str(a) for a in args]
        out = render_fn(str(name), rendered)
        if out is not None:
            return out
        # Unknown function — passthrough; mark as string-typed if its name
        # suggests so (used by the concat detector below).
        return f"{str(name).upper()}({', '.join(rendered)})"

    def in_col(self, name):
        return _StrType(f"`{name}`", maybe_string=True)

    def out_col(self, name):
        # `out.X` self-reference — within the same Reformat block, the
        # `withColumn` chain ensures the column exists by this point.
        return _StrType(f"`{name}`", maybe_string=True)

    def bare_col(self, name):
        return _StrType(f"`{name}`", maybe_string=True)

    # ── literals ───────────────────────────────────────────────────────
    def num_lit(self, tok):
        return str(tok)

    def dq_str_lit(self, tok):
        # Lark gives `"..."`; Spark SQL needs `'...'`.
        inner = str(tok)[1:-1].replace("'", "''")
        return _StrType(f"'{inner}'", is_string=True)

    def sq_str_lit(self, tok):
        # Already single-quoted; pass through verbatim.
        return _StrType(str(tok), is_string=True)

    def true_lit(self):
        return "TRUE"

    def false_lit(self):
        return "FALSE"

    def null_lit(self):
        return "NULL"


# ── helpers ────────────────────────────────────────────────────────────────


class _StrType(str):
    """A string whose ``is_string`` / ``maybe_string`` attrs let downstream
    operators (especially ``+``) decide whether to emit ``CONCAT``.
    """

    is_string: bool = False
    maybe_string: bool = False

    def __new__(cls, value: str, is_string: bool = False, maybe_string: bool = False):
        s = super().__new__(cls, value)
        s.is_string = is_string
        s.maybe_string = maybe_string
        return s


def _join_logical(items: Sequence[Any], op: str) -> str:
    if len(items) == 1:
        return str(items[0])
    out = str(items[0])
    i = 1
    while i < len(items):
        # items[i] is the OP token, items[i+1] is the rhs
        right = items[i + 1]
        out = f"({out} {op} {right})"
        i += 2
    return out


def _join_arith_explicit(items: Sequence[Any]) -> str:
    if len(items) == 1:
        return str(items[0])
    out = str(items[0])
    i = 1
    while i < len(items):
        op = str(items[i])
        right = items[i + 1]
        out = f"({out} {op} {right})"
        i += 2
    return out


def _join_arith_or_concat(items: Sequence[Any]) -> Any:
    """Same as _join_arith_explicit but lowers `+` to ``CONCAT(...)`` when
    ANY operand is a string literal.
    """
    if len(items) == 1:
        return items[0]

    # Detect: are we doing string concatenation? Yes iff at least one
    # operand is a `_StrType` with ``is_string=True`` AND every operator is `+`.
    has_string = any(isinstance(x, _StrType) and x.is_string for x in items[::2])
    all_plus = all(str(items[i]) == "+" for i in range(1, len(items), 2))
    if has_string and all_plus:
        operands = [str(items[i]) for i in range(0, len(items), 2)]
        return _StrType(f"CONCAT({', '.join(operands)})", is_string=True)
    # Fallback: normal arithmetic.
    return _join_arith_explicit(items)


_PARSER = Lark(XFR_GRAMMAR, parser="lalr", transformer=_XfrTransformer())


# ── public entry points ────────────────────────────────────────────────────


def parse_xfr_string(src: str) -> dict[str, Any]:
    src = preprocess_xfr(src)
    return _PARSER.parse(src)  # type: ignore[return-value]


def parse_xfr_file(path: str | Path) -> dict[str, Any]:
    return parse_xfr_string(Path(path).read_text())


def parse_filter_condition(src: str) -> str:
    """Parse a single boolean condition (e.g. from a Filter component's
    ``condition`` property in .mp). Returns a Spark SQL expression.
    """
    src = src.strip().rstrip(";")
    wrapped = f"out.__cond = {src};"
    blocks = parse_xfr_string(wrapped)
    block = next(iter(blocks.values()))
    return block["assignments"][0][1]
