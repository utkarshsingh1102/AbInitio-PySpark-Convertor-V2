"""Best-effort translator: Spark SQL expression string → native PySpark code.

Used by the ``RewriteExprToNativeAPI`` rule to replace ``F.expr("…")``
calls with idiomatic ``F.col / F.lit / F.upper / F.when / +`` expressions.

If parsing fails for any reason (an unsupported construct, a token we
don't recognise), the translator returns ``None`` and the caller keeps
the original ``F.expr(...)`` form. So this module is *additive* — it
never breaks correct pipelines, only upgrades expressions it understands.

Supported subset (matches what ``backend.parser.xfr_parser`` emits):

  - column refs:  `` `name` `` / bare ``name``
  - literals:     numbers, ``'string'``, ``TRUE``/``FALSE``/``NULL``
  - arithmetic:   ``+ - * /``
  - comparison:   ``= == != < <= > >=``
  - logical:      ``AND OR NOT``
  - null tests:   ``IS NULL`` / ``IS NOT NULL``
  - functions:    UPPER, LOWER, TRIM, LTRIM, RTRIM, LENGTH, SUBSTRING,
                  CONCAT, COALESCE, ABS, ROUND, FLOOR, CEIL, SQRT, MOD,
                  YEAR, MONTH, DAY, DATEDIFF, DATE_FORMAT,
                  TO_DATE, TO_TIMESTAMP, DATE_ADD, REPLACE,
                  SUM, MIN, MAX, COUNT, AVG
  - CASE WHEN … THEN … ELSE … END  (chained ELSE-IF flattens to .when().when().otherwise())
  - CAST(expr AS TYPE[(p[, s])])
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Optional

# ── tokenizer ──────────────────────────────────────────────────────────────


_TOKEN_RE = re.compile(
    r"""
    \s*(?:
        (?P<bt>`[A-Za-z_][A-Za-z0-9_]*`)             |
        (?P<num>-?\d+(?:\.\d+)?)                     |
        (?P<str>'(?:[^'\\]|\\.|'')*')                |
        (?P<ge>>=)|(?P<le><=)|(?P<eqeq>==)|(?P<ne>!=)|
        (?P<gt>>)|(?P<lt><)|(?P<eq>=)                |
        (?P<plus>\+)|(?P<minus>-)|(?P<mul>\*)|(?P<div>/) |
        (?P<lparen>\()|(?P<rparen>\))|(?P<comma>,)   |
        (?P<ident>[A-Za-z_][A-Za-z0-9_]*)
    )
    """,
    re.VERBOSE,
)

_KEYWORDS = {
    "AND", "OR", "NOT", "IS", "NULL", "TRUE", "FALSE",
    "CASE", "WHEN", "THEN", "ELSE", "END",
    "CAST", "AS", "IN", "LIKE",
}

_TYPE_NAMES = {
    "STRING": "StringType",
    "INT": "IntegerType", "INTEGER": "IntegerType", "SMALLINT": "IntegerType", "TINYINT": "IntegerType",
    "BIGINT": "LongType", "LONG": "LongType",
    "DOUBLE": "DoubleType", "FLOAT": "FloatType",
    "BOOLEAN": "BooleanType", "BOOL": "BooleanType",
    "DATE": "DateType",
    "TIMESTAMP": "TimestampType", "DATETIME": "TimestampType",
    "DECIMAL": "DecimalType", "NUMERIC": "DecimalType",
}


@dataclass
class Tok:
    kind: str
    value: str


def _tokenize(src: str) -> list[Tok]:
    out: list[Tok] = []
    pos = 0
    while pos < len(src):
        m = _TOKEN_RE.match(src, pos)
        if not m:
            if src[pos].isspace():
                pos += 1
                continue
            raise ValueError(f"Unexpected char {src[pos]!r} at {pos}")
        kind = m.lastgroup
        val = m.group(kind)  # type: ignore[arg-type]
        if kind == "ident":
            up = val.upper()
            if up in _KEYWORDS:
                kind = up
            elif up in _TYPE_NAMES:
                kind = "TYPE"
            else:
                kind = "IDENT"
        out.append(Tok(kind, val))  # type: ignore[arg-type]
        pos = m.end()
    return out


# ── AST ────────────────────────────────────────────────────────────────────


@dataclass
class Node:
    kind: str
    payload: Any = None
    children: list["Node"] = None  # type: ignore[assignment]

    def __post_init__(self):
        if self.children is None:
            self.children = []


# ── parser (recursive-descent) ─────────────────────────────────────────────


class _Parser:
    def __init__(self, tokens: list[Tok]):
        self.toks = tokens
        self.i = 0

    def peek(self, off: int = 0) -> Optional[Tok]:
        idx = self.i + off
        return self.toks[idx] if idx < len(self.toks) else None

    def eat(self, kind: Optional[str] = None, value: Optional[str] = None) -> Tok:
        tok = self.peek()
        if tok is None:
            raise ValueError("Unexpected EOF")
        if kind and tok.kind != kind:
            raise ValueError(f"Expected {kind}, got {tok}")
        if value and tok.value.upper() != value.upper():
            raise ValueError(f"Expected {value!r}, got {tok}")
        self.i += 1
        return tok

    def at_end(self) -> bool:
        return self.i >= len(self.toks)

    # ── grammar ────────────────────────────────────────────────────────

    def parse_expr(self) -> Node:
        return self.parse_or()

    def parse_or(self) -> Node:
        left = self.parse_and()
        while self.peek() and self.peek().kind == "OR":
            self.i += 1
            right = self.parse_and()
            left = Node("or", children=[left, right])
        return left

    def parse_and(self) -> Node:
        left = self.parse_not()
        while self.peek() and self.peek().kind == "AND":
            self.i += 1
            right = self.parse_not()
            left = Node("and", children=[left, right])
        return left

    def parse_not(self) -> Node:
        if self.peek() and self.peek().kind == "NOT":
            self.i += 1
            return Node("not", children=[self.parse_not()])
        return self.parse_cmp()

    def parse_cmp(self) -> Node:
        left = self.parse_add()
        nxt = self.peek()
        if nxt and nxt.kind == "IS":
            self.i += 1
            negated = False
            if self.peek() and self.peek().kind == "NOT":
                self.i += 1
                negated = True
            self.eat("NULL")
            return Node("is_not_null" if negated else "is_null", children=[left])
        if nxt and nxt.kind in {"eq", "eqeq", "ne", "lt", "le", "gt", "ge"}:
            op = nxt.kind
            self.i += 1
            right = self.parse_add()
            return Node("cmp", payload=op, children=[left, right])
        return left

    def parse_add(self) -> Node:
        left = self.parse_mul()
        while self.peek() and self.peek().kind in {"plus", "minus"}:
            op = self.peek().kind
            self.i += 1
            right = self.parse_mul()
            left = Node("bin", payload=op, children=[left, right])
        return left

    def parse_mul(self) -> Node:
        left = self.parse_unary()
        while self.peek() and self.peek().kind in {"mul", "div"}:
            op = self.peek().kind
            self.i += 1
            right = self.parse_unary()
            left = Node("bin", payload=op, children=[left, right])
        return left

    def parse_unary(self) -> Node:
        if self.peek() and self.peek().kind == "minus":
            self.i += 1
            return Node("neg", children=[self.parse_unary()])
        return self.parse_primary()

    def parse_primary(self) -> Node:
        tok = self.peek()
        if tok is None:
            raise ValueError("Unexpected EOF in primary")

        if tok.kind == "lparen":
            self.i += 1
            inner = self.parse_expr()
            self.eat("rparen")
            return inner

        if tok.kind == "bt":
            self.i += 1
            name = tok.value[1:-1]
            return Node("col", payload=name)

        if tok.kind == "num":
            self.i += 1
            return Node("num", payload=tok.value)

        if tok.kind == "str":
            self.i += 1
            return Node("str", payload=tok.value)

        if tok.kind == "TRUE":
            self.i += 1
            return Node("bool", payload=True)
        if tok.kind == "FALSE":
            self.i += 1
            return Node("bool", payload=False)
        if tok.kind == "NULL":
            self.i += 1
            return Node("null")

        if tok.kind == "CASE":
            return self.parse_case()
        if tok.kind == "CAST":
            return self.parse_cast()

        if tok.kind in {"IDENT", "TYPE"}:
            # could be a function call or a bare-column ref (rare; xfr emits backticks)
            nxt = self.peek(1)
            if nxt and nxt.kind == "lparen":
                return self.parse_func_call()
            self.i += 1
            return Node("col", payload=tok.value)

        raise ValueError(f"Unexpected primary {tok}")

    def parse_func_call(self) -> Node:
        name_tok = self.eat()
        self.eat("lparen")
        args: list[Node] = []
        if not (self.peek() and self.peek().kind == "rparen"):
            args.append(self.parse_expr())
            while self.peek() and self.peek().kind == "comma":
                self.i += 1
                args.append(self.parse_expr())
        self.eat("rparen")
        return Node("fn", payload=name_tok.value.upper(), children=args)

    def parse_case(self) -> Node:
        self.eat("CASE")
        whens: list[tuple[Node, Node]] = []
        else_node: Optional[Node] = None
        while self.peek() and self.peek().kind == "WHEN":
            self.i += 1
            cond = self.parse_expr()
            self.eat("THEN")
            then_e = self.parse_expr()
            whens.append((cond, then_e))
        if self.peek() and self.peek().kind == "ELSE":
            self.i += 1
            else_node = self.parse_expr()
        self.eat("END")
        node = Node("case", payload={"whens": whens, "else": else_node})
        return node

    def parse_cast(self) -> Node:
        self.eat("CAST")
        self.eat("lparen")
        inner = self.parse_expr()
        self.eat("AS")
        type_tok = self.eat()
        type_name = type_tok.value.upper()
        type_args: list[str] = []
        if self.peek() and self.peek().kind == "lparen":
            self.i += 1
            while True:
                t = self.eat()
                type_args.append(t.value)
                if self.peek() and self.peek().kind == "comma":
                    self.i += 1
                    continue
                break
            self.eat("rparen")
        self.eat("rparen")
        return Node("cast", payload={"type": type_name, "args": type_args}, children=[inner])


# ── renderer (AST → native PySpark code) ───────────────────────────────────


# Arg indices that PySpark expects as PLAIN Python str (not Column).
_PLAIN_STR_ARG = {
    "DATE_FORMAT":  {1},
    "TO_DATE":      {1},
    "TO_TIMESTAMP": {1},
}


_FN_NATIVE = {
    "UPPER":       ("F.upper",       1),
    "LOWER":       ("F.lower",       1),
    "TRIM":        ("F.trim",        1),
    "LTRIM":       ("F.ltrim",       1),
    "RTRIM":       ("F.rtrim",       1),
    "LENGTH":      ("F.length",      1),
    "ABS":         ("F.abs",         1),
    "FLOOR":       ("F.floor",       1),
    "CEIL":        ("F.ceil",        1),
    "SQRT":        ("F.sqrt",        1),
    "ROUND":       ("F.round",       2),
    "MOD":         ("F.pmod",        2),
    "SUBSTRING":   ("F.substring",   3),
    "SUBSTR":      ("F.substring",   3),
    "REPLACE":     ("F.regexp_replace", 3),
    "CONCAT":      ("F.concat",      None),
    "COALESCE":    ("F.coalesce",    None),
    "YEAR":        ("F.year",        1),
    "MONTH":       ("F.month",       1),
    "DAY":         ("F.dayofmonth",  1),
    "DATE_FORMAT": ("F.date_format", 2),
    "TO_DATE":     ("F.to_date",     2),
    "TO_TIMESTAMP": ("F.to_timestamp", 2),
    "DATE_ADD":    ("F.date_add",    2),
    "DATE_SUB":    ("F.date_sub",    2),
    "DATEDIFF":    ("F.datediff",    2),
    "SUM":         ("F.sum",         1),
    "MIN":         ("F.min",         1),
    "MAX":         ("F.max",         1),
    "COUNT":       ("F.count",       1),
    "AVG":         ("F.avg",         1),
}


def _render(n: Node) -> str:
    k = n.kind
    if k == "col":
        return f"F.col({n.payload!r})"
    if k == "num":
        return f"F.lit({n.payload})"
    if k == "str":
        # Strip outer quotes and SQL-double-single-quote escape
        raw = n.payload
        inner = raw[1:-1].replace("''", "'")
        return f"F.lit({inner!r})"
    if k == "bool":
        return f"F.lit({n.payload})"
    if k == "null":
        return "F.lit(None)"

    if k == "neg":
        return f"(-{_render(n.children[0])})"

    if k == "not":
        return f"(~({_render(n.children[0])}))"

    if k == "or":
        return f"({_render(n.children[0])} | {_render(n.children[1])})"
    if k == "and":
        return f"({_render(n.children[0])} & {_render(n.children[1])})"

    if k == "is_null":
        return f"({_render(n.children[0])}.isNull())"
    if k == "is_not_null":
        return f"({_render(n.children[0])}.isNotNull())"

    if k == "bin":
        op = {"plus": "+", "minus": "-", "mul": "*", "div": "/"}[n.payload]
        return f"({_render(n.children[0])} {op} {_render(n.children[1])})"

    if k == "cmp":
        sql_op = n.payload
        py_op = {
            "eq": "==", "eqeq": "==", "ne": "!=",
            "lt": "<", "le": "<=", "gt": ">", "ge": ">=",
        }[sql_op]
        return f"({_render(n.children[0])} {py_op} {_render(n.children[1])})"

    if k == "fn":
        fname = n.payload
        spec = _FN_NATIVE.get(fname)
        if spec is None:
            raise ValueError(f"Unsupported fn {fname}")
        py_fn, arity = spec
        plain_idxs = _PLAIN_STR_ARG.get(fname, set())
        args: list[str] = []
        for i, c in enumerate(n.children):
            if i in plain_idxs:
                if c.kind != "str":
                    raise ValueError(
                        f"{fname} arg {i} must be a string literal, got {c.kind}"
                    )
                inner = c.payload[1:-1].replace("''", "'")
                args.append(repr(inner))
            else:
                args.append(_render(c))
        if arity is not None and len(args) != arity:
            raise ValueError(f"{fname} expects {arity} args, got {len(args)}")
        return f"{py_fn}({', '.join(args)})"

    if k == "case":
        whens = n.payload["whens"]
        else_node = n.payload["else"]
        if not whens:
            raise ValueError("CASE with no WHEN")
        # Flatten chained `else (CASE WHEN ... END)` into chained .when()
        flat: list[tuple[Node, Node]] = list(whens)
        cur_else = else_node
        while isinstance(cur_else, Node) and cur_else.kind == "case":
            flat.extend(cur_else.payload["whens"])
            cur_else = cur_else.payload["else"]
        cond, then_e = flat[0]
        out = f"F.when({_render(cond)}, {_render(then_e)})"
        for cond_i, then_i in flat[1:]:
            out += f".when({_render(cond_i)}, {_render(then_i)})"
        if cur_else is not None:
            out += f".otherwise({_render(cur_else)})"
        return out

    if k == "cast":
        type_name = n.payload["type"]
        type_args = n.payload["args"]
        py_type = _TYPE_NAMES.get(type_name)
        if py_type is None:
            raise ValueError(f"Unknown type for CAST: {type_name}")
        if type_args:
            type_expr = f"{py_type}({', '.join(type_args)})"
        else:
            type_expr = f"{py_type}()"
        # bin/cmp/and/or/not children already self-parenthesise; col/fn/case
        # render as simple atoms — no extra wrapping needed.
        return f"{_render(n.children[0])}.cast({type_expr})"

    raise ValueError(f"Unknown node kind {k}")


# ── public entry point ────────────────────────────────────────────────────


def to_native(sql: str) -> Optional[str]:
    """Translate a Spark SQL expression to native PySpark code.

    Returns ``None`` if the expression contains anything we don't
    understand — caller falls back to ``F.expr(...)``.
    """
    if not sql or not sql.strip():
        return None
    try:
        tokens = _tokenize(sql)
        parser = _Parser(tokens)
        ast = parser.parse_expr()
        if not parser.at_end():
            return None
        return _render(ast)
    except Exception:
        return None
