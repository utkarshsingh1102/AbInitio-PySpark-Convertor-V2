"""Ab Initio DML schema parser (realistic dialect).

Recognises:

    -- line comments
    /* block comments */
    DEFINE name BEGIN
        field_name      type            NOT NULL;
        field_name      type            NULL;
        field_name      string(N)       NOT NULL;
        field_name      decimal(p, s)   NULL;
        addr            record                          -- nested record
                            street      string(50);
                            city        string(30);
                        end                NOT NULL;
        addresses       record                          -- array of records
                            street      string(50);
                        end[]              NULL;
    END

Multiple DEFINE blocks per file are supported. The parser returns a
``dict[name, schema_dict]``; ``resolve(filename_or_name)`` strips a ``.dml``
suffix if present and looks up the matching DEFINE.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .preprocess import preprocess_dml

# ── tokenizer ──────────────────────────────────────────────────────────────

_TOKEN_RE = re.compile(
    r"""
    \s*(?:
        (?P<lparen>\()                          |
        (?P<rparen>\))                          |
        (?P<comma>,)                            |
        (?P<semi>;)                             |
        (?P<lbracket>\[)                        |
        (?P<rbracket>\])                        |
        (?P<eq2>==)                             |   # multi-char ops first
        (?P<neq>!=)                             |
        (?P<lte><=)                             |
        (?P<gte>>=)                             |
        (?P<lt><)                               |
        (?P<gt>>)                               |
        (?P<eq>=)                               |
        (?P<num>\d+)                            |
        (?P<dqstring>"(?:\\.|[^"\\])*")         |
        (?P<ident>[A-Za-z_][A-Za-z0-9_]*)
    )
    """,
    re.VERBOSE,
)

_COMPARISON_TOKENS = {"eq2", "neq", "lte", "gte", "lt", "gt", "eq"}
_COMPARISON_OP_TEXT = {
    "eq2": "==", "neq": "!=", "lte": "<=", "gte": ">=",
    "lt":  "<",  "gt":  ">",  "eq":  "=",
}


def _unescape_dqstring(raw: str) -> str:
    """Strip surrounding quotes and resolve standard escape sequences."""
    inner = raw[1:-1]
    out: list[str] = []
    i = 0
    while i < len(inner):
        ch = inner[i]
        if ch == "\\" and i + 1 < len(inner):
            nxt = inner[i + 1]
            out.append({
                "n": "\n", "t": "\t", "r": "\r",
                "\\": "\\", '"': '"', "0": "\0",
            }.get(nxt, nxt))
            i += 2
        else:
            out.append(ch)
            i += 1
    return "".join(out)

_PRIMITIVES = {
    "string", "integer", "long", "decimal", "date", "datetime",
    "double", "float", "boolean", "varchar", "char", "int",
    "bigint", "smallint", "tinyint", "timestamp",
    # Mainframe / binary types — recognised at parse time. The runtime
    # reader (cobrix etc.) is not in scope here; we map them to the
    # closest Spark type and tag the field as ``encoding=<original>`` so
    # downstream tools can pick the right reader.
    "packed_decimal", "binary", "ebcdic_string", "ebcdic", "bcd",
}

# Types that carry a non-default encoding flag for downstream readers.
_ENCODED_TYPES = {
    "packed_decimal": "packed_decimal",
    "binary": "binary",
    "ebcdic_string": "ebcdic",
    "ebcdic": "ebcdic",
    "bcd": "packed_decimal",
}

_KW_DEFINE = {"define"}
_KW_BEGIN = {"begin"}
_KW_END = {"end"}
_KW_RECORD = {"record", "group"}  # `group` is an Ab Initio alias for `record`

# Constructs we explicitly reject when they appear as a field starter. The
# parser's job is to surface them as an error rather than silently treat
# them as field names. ``if``/``then``/``else`` were previously here but are
# now handled in ``_parse_conditional`` (called from ``_parse_field_list``);
# only union and variant remain unimplemented.
_RESERVED_UNSUPPORTED = {
    "union", "variant",
}
_KW_NULL = {"null"}
_KW_NOT = {"not"}
_KW_NULLABLE = {"nullable"}
_KW_NOT_NULL = {"not_null", "notnull"}


def _tokenize(src: str) -> list[tuple[str, str]]:
    src = re.sub(r"/\*.*?\*/", " ", src, flags=re.DOTALL)
    src = re.sub(r"//[^\n]*", " ", src)
    out: list[tuple[str, str]] = []
    pos = 0
    while pos < len(src):
        m = _TOKEN_RE.match(src, pos)
        if not m:
            if src[pos].isspace():
                pos += 1
                continue
            raise ValueError(f"Unexpected char at {pos}: {src[pos]!r}")
        kind = m.lastgroup
        out.append((kind, m.group(kind)))  # type: ignore[arg-type]
        pos = m.end()
    return out


# ── parser ─────────────────────────────────────────────────────────────────


class _Parser:
    def __init__(self, tokens: list[tuple[str, str]]):
        self.toks = tokens
        self.i = 0

    def peek(self, off: int = 0):
        idx = self.i + off
        return self.toks[idx] if idx < len(self.toks) else None

    def eat(self, kind: str | None = None, value: str | None = None):
        tok = self.peek()
        if tok is None:
            raise ValueError("Unexpected EOF")
        if kind and tok[0] != kind:
            raise ValueError(f"Expected {kind}, got {tok}")
        if value and tok[1].lower() != value.lower():
            raise ValueError(f"Expected {value!r}, got {tok}")
        self.i += 1
        return tok

    def at_end(self) -> bool:
        return self.i >= len(self.toks)

    def parse_file(self) -> dict[str, dict[str, Any]]:
        """Parse all DEFINE blocks in the file. Returns ``{name: schema_dict}``."""
        defs: dict[str, dict[str, Any]] = {}
        while not self.at_end():
            tok = self.peek()
            if tok is None:
                break
            if tok[0] != "ident":
                raise ValueError(f"Expected DEFINE/record, got {tok}")
            kw = tok[1].lower()
            if kw in _KW_DEFINE:
                name, schema = self._parse_define()
                defs[name] = schema
            elif kw in _KW_RECORD:
                # legacy `record ... end;` form — name comes from `end <name>;`
                name, schema = self._parse_record_legacy()
                defs[name or f"record_{len(defs)}"] = schema
            else:
                raise ValueError(f"Unexpected top-level token {tok}")
        return defs

    # DEFINE name BEGIN ... END
    def _parse_define(self) -> tuple[str, dict[str, Any]]:
        self.eat("ident", "define")
        name_tok = self.eat("ident")
        self.eat("ident", "begin")
        fields = self._parse_field_list(end_keyword="end")
        self.eat("ident", "end")
        # Optional trailing `;` after END
        if self.peek() and self.peek()[0] == "semi":
            self.eat("semi")
        return name_tok[1], {"type": "record", "fields": fields}

    # legacy record ... end [name];
    def _parse_record_legacy(self) -> tuple[str | None, dict[str, Any]]:
        self.eat("ident", "record")
        fields = self._parse_field_list(end_keyword="end")
        self.eat("ident", "end")
        name: str | None = None
        if self.peek() and self.peek()[0] == "ident":
            name = self.eat("ident")[1]
        if self.peek() and self.peek()[0] == "semi":
            self.eat("semi")
        return name, {"type": "record", "fields": fields}

    def _maybe_type_args(self) -> tuple[list[int], str | None, str | None]:
        """Parse ``(arg [, arg]* [,])``.

        Each arg can be:
          - a number (length / precision / scale)
          - a quoted string (delimiter, or date format on date-typed fields)
          - a function-call-shaped arg like ``null("")`` (null indicator)
          - a bare identifier (treated as opaque — typically a leftover macro)

        Returns ``(numeric_args, delimiter, null_indicator)``. Trailing commas
        — e.g. ``("¨", )`` — are tolerated.
        """
        nums: list[int] = []
        delim: str | None = None
        null_indicator: str | None = None

        if self.peek() and self.peek()[0] == "lparen":
            self.eat("lparen")
            while True:
                tok = self.peek()
                if tok is None:
                    raise ValueError("Unexpected EOF in type args")
                if tok[0] == "rparen":   # trailing comma → empty slot
                    break
                if tok[0] == "num":
                    self.eat("num")
                    nums.append(int(tok[1]))
                elif tok[0] == "dqstring":
                    self.eat("dqstring")
                    delim = _unescape_dqstring(tok[1])
                elif tok[0] == "ident":
                    fname = self.eat("ident")[1].lower()
                    inner_strings: list[str] = []
                    if self.peek() and self.peek()[0] == "lparen":
                        # Consume nested arg list and capture string literals.
                        self.eat("lparen")
                        while self.peek() and self.peek()[0] != "rparen":
                            t = self.peek()
                            if t[0] == "dqstring":
                                self.eat("dqstring")
                                inner_strings.append(_unescape_dqstring(t[1]))
                            else:
                                self.i += 1   # skip num / ident / nested
                            if self.peek() and self.peek()[0] == "comma":
                                self.eat("comma")
                        self.eat("rparen")
                        if fname == "null":
                            # Always set, even to empty — presence of `null(...)`
                            # signals a null indicator was specified.
                            null_indicator = inner_strings[0] if inner_strings else ""
                    # Bare ident with no parens → opaque, ignore (probably an
                    # un-substituted macro). Don't crash.
                else:
                    raise ValueError(f"Unexpected token in type args: {tok}")
                nxt = self.peek()
                if nxt and nxt[0] == "comma":
                    self.eat("comma")
                    continue
                break
            self.eat("rparen")
        return nums, delim, null_indicator

    def _consume_array_brackets(self) -> list[int | None]:
        """Consume any sequence of ``[]`` / ``[N]`` and return a list of
        dimension lengths (``None`` for unbounded). Multiple bracket pairs
        produce a multi-dimensional array — e.g. ``[][]`` → two-dim.
        """
        dims: list[int | None] = []
        while self.peek() and self.peek()[0] == "lbracket":
            self.eat("lbracket")
            nxt = self.peek()
            length: int | None = None
            if nxt and nxt[0] == "num":
                self.eat("num")
                length = int(nxt[1])
            self.eat("rbracket")
            dims.append(length)
        return dims

    def _parse_field_list(self, end_keyword: str) -> list[dict[str, Any]]:
        fields: list[dict[str, Any]] = []
        while True:
            tok = self.peek()
            if tok is None:
                raise ValueError("Unexpected EOF in field list")
            if tok[0] == "ident" and tok[1].lower() == end_keyword:
                return fields
            # Conditional block: `if (cond) [then] <fields...> [else <fields...>] end;`
            # Each branch's fields get flattened into the parent's list with
            # nullable forced True and a `condition` annotation for codegen.
            if tok[0] == "ident" and tok[1].lower() == "if":
                fields.extend(self._parse_conditional())
                continue
            fields.append(self._parse_field())

    def _parse_conditional(self) -> list[dict[str, Any]]:
        """Parse an ``if (cond) [then] <fields> [else <fields>] end[;]`` block.

        The parsed fields are returned flattened, each tagged with a
        ``condition: {col, op, value, branch}`` dict and ``nullable=True``
        forced (since each row only populates one branch).
        """
        self.eat("ident", "if")
        self.eat("lparen")
        condition = self._parse_simple_condition()
        self.eat("rparen")

        # Optional `then` keyword
        nxt = self.peek()
        if nxt and nxt[0] == "ident" and nxt[1].lower() == "then":
            self.eat("ident", "then")

        then_fields = self._parse_branch_fields(stop=("else", "end"))

        else_fields: list[dict[str, Any]] = []
        nxt = self.peek()
        if nxt and nxt[0] == "ident" and nxt[1].lower() == "else":
            self.eat("ident", "else")
            else_fields = self._parse_branch_fields(stop=("end",))

        # Conditional MUST close with its own `end[;]` — otherwise we'd
        # consume the parent record's `end` and leave the parent unclosed.
        self.eat("ident", "end")
        if self.peek() and self.peek()[0] == "semi":
            self.eat("semi")

        out: list[dict[str, Any]] = []
        for f in then_fields:
            f["nullable"] = True
            f["condition"] = {**condition, "branch": "then"}
            out.append(f)
        for f in else_fields:
            f["nullable"] = True
            f["condition"] = {**condition, "branch": "else"}
            out.append(f)
        return out

    def _parse_simple_condition(self) -> dict[str, Any]:
        """Parse ``<column> <comparison-op> <literal>``. No AND/OR for v1."""
        left = self.eat("ident")[1]
        op_tok = self.peek()
        if op_tok is None or op_tok[0] not in _COMPARISON_TOKENS:
            raise ValueError(f"Expected comparison operator, got {op_tok}")
        op = _COMPARISON_OP_TEXT[op_tok[0]]
        self.i += 1

        rhs_tok = self.peek()
        if rhs_tok is None:
            raise ValueError("Expected literal after comparison operator")
        if rhs_tok[0] == "dqstring":
            self.eat("dqstring")
            value: Any = _unescape_dqstring(rhs_tok[1])
        elif rhs_tok[0] == "num":
            self.eat("num")
            value = int(rhs_tok[1])
        elif rhs_tok[0] == "ident":
            self.eat("ident")
            value = rhs_tok[1]   # bool-like / NULL / enum constant
        else:
            raise ValueError(f"Expected literal in condition, got {rhs_tok}")
        return {"col": left, "op": op, "value": value}

    def _parse_branch_fields(self, stop: tuple[str, ...]) -> list[dict[str, Any]]:
        fields: list[dict[str, Any]] = []
        while True:
            tok = self.peek()
            if tok is None:
                raise ValueError("Unexpected EOF in conditional branch")
            if tok[0] == "ident" and tok[1].lower() in stop:
                return fields
            # Disallow nested conditionals for v1 — keeps the IR simple.
            if tok[0] == "ident" and tok[1].lower() == "if":
                raise ValueError("Nested if/else conditionals are not supported")
            fields.append(self._parse_field())

    def _parse_field(self) -> dict[str, Any]:
        """Field syntax (realistic Ab Initio dialect).

        Four accepted forms:

          <name> <type>[(args)] [modifiers];                 (modern)
          <type>[(args)] <name> [modifiers];                 (legacy primitive)
          <name> record <fields> end[ <ignored>][[]] [mods]; (modern nested)
          record <fields> end <name> [[]] [mods];            (legacy nested)
        """
        first = self.eat("ident")
        first_word = first[1].lower()

        if first_word in _RESERVED_UNSUPPORTED:
            raise ValueError(
                f"Unsupported DML construct {first[1]!r} — union / variant / "
                "conditional fields are not supported."
            )

        struct_fields: list[dict[str, Any]] = []
        is_struct = False
        type_args: list[int] = []
        delimiter: str | None = None
        null_indicator: str | None = None
        is_array = False
        array_length: int | None = None
        array_dims: list[int | None] = []

        if first_word in _KW_RECORD:
            # Legacy nested record (or `group` alias). Accept all of:
            #   record … end <name>[N];      (name first)
            #   record … end[N] <name>;      (brackets first)
            #   record … end[N];             (anonymous, just brackets)
            #   record … end;                (anonymous, no array)
            struct_fields = self._parse_field_list(end_keyword="end")
            self.eat("ident", "end")

            # Optional brackets BEFORE the name (legacy variant). May be multi-dim.
            array_dims.extend(self._consume_array_brackets())

            # Optional name. Skip nullability keywords and `end` (outer terminator).
            field_name: str | None = None
            nxt = self.peek()
            if nxt and nxt[0] == "ident":
                kw = nxt[1].lower()
                if (kw not in _KW_NULL and kw not in _KW_NOT
                        and kw not in _KW_NOT_NULL and kw not in _KW_NULLABLE
                        and kw != "end"):
                    self.eat("ident")
                    field_name = nxt[1]
            if field_name is None:
                # Anonymous — synthesize a stable name from token position
                field_name = f"_anon_record_{self.i}"

            type_name = "struct"
            is_struct = True
        elif first_word in _PRIMITIVES:
            type_name = first_word
            type_args, delimiter, null_indicator = self._maybe_type_args()
            field_name = self.eat("ident")[1]
        else:
            field_name = first[1]
            type_tok = self.eat("ident")
            type_name = type_tok[1].lower()
            if type_name in _KW_RECORD:
                struct_fields = self._parse_field_list(end_keyword="end")
                self.eat("ident", "end")
                # Optional trailing identifier (e.g. `end addr`) before
                # array brackets / modifiers / semicolon. Only consume it
                # if it isn't actually a nullability keyword.
                nxt = self.peek()
                if nxt and nxt[0] == "ident":
                    kw = nxt[1].lower()
                    if (kw not in _KW_NULL and kw not in _KW_NOT
                            and kw not in _KW_NOT_NULL and kw not in _KW_NULLABLE):
                        self.eat("ident")
                type_name = "struct"
                is_struct = True
            else:
                if type_name not in _PRIMITIVES:
                    raise ValueError(f"Unknown DML type: {type_name}")
                type_args, delimiter, null_indicator = self._maybe_type_args()

        # Array / vector brackets after the name. May be multi-dim (`[][]`).
        # Combine with any pre-name brackets the legacy form might have set.
        array_dims.extend(self._consume_array_brackets())
        is_array = bool(array_dims)
        if array_dims and array_dims[0] is not None:
            array_length = array_dims[0]

        # Modifiers: NOT NULL | NULL | nullable | not_null | notnull
        nullable = True
        nxt = self.peek()
        if nxt and nxt[0] == "ident":
            kw = nxt[1].lower()
            if kw in _KW_NOT_NULL:
                self.i += 1
                nullable = False
            elif kw in _KW_NULL:
                self.i += 1
                nullable = True
            elif kw in _KW_NULLABLE:
                self.i += 1
                nullable = True
            elif kw in _KW_NOT:
                self.i += 1
                nxt2 = self.peek()
                if nxt2 and nxt2[0] == "ident" and nxt2[1].lower() in _KW_NULL:
                    self.i += 1
                    nullable = False
                else:
                    raise ValueError(f"Expected NULL after NOT, got {nxt2}")

        # Optional default value: `= <num | dqstring | ident>` (e.g. `= "\n"`,
        # `= 0`, `= NULL`). Stored as ``default`` on the field dict.
        default: Any = None
        has_default = False
        if self.peek() and self.peek()[0] == "eq":
            self.eat("eq")
            val_tok = self.peek()
            if val_tok is None:
                raise ValueError("Expected default value after `=`")
            if val_tok[0] == "num":
                self.eat("num"); default = int(val_tok[1])
            elif val_tok[0] == "dqstring":
                self.eat("dqstring"); default = _unescape_dqstring(val_tok[1])
            elif val_tok[0] == "ident":
                self.eat("ident"); default = val_tok[1]
            else:
                raise ValueError(f"Unexpected default-value token: {val_tok}")
            has_default = True

        self.eat("semi")

        if is_struct:
            out: dict[str, Any] = {
                "name": field_name,
                "type": "struct",
                "fields": struct_fields,
                "nullable": nullable,
                "array": is_array,
            }
            if array_length is not None:
                out["array_length"] = array_length
            if len(array_dims) > 1:
                out["array_dims"] = array_dims
            if has_default:
                out["default"] = default
            return out
        out = {
            "name": field_name,
            "type": _normalize_type(type_name),
            "args": type_args,
            "nullable": nullable,
            "array": is_array,
        }
        if array_length is not None:
            out["array_length"] = array_length
        if delimiter is not None:
            # On date/datetime/timestamp types the string-in-parens is a
            # *format*, not a delimiter. Store accordingly.
            if type_name in ("date", "datetime", "timestamp"):
                out["format"] = delimiter
            else:
                if delimiter == "":
                    raise ValueError(
                        f"Empty delimiter on field {field_name!r} is not valid"
                    )
                out["delimiter"] = delimiter
        if len(array_dims) > 1:
            out["array_dims"] = array_dims
        if null_indicator is not None:
            out["null_indicator"] = null_indicator
        if has_default:
            out["default"] = default
        if type_name in _ENCODED_TYPES:
            out["encoding"] = _ENCODED_TYPES[type_name]
        return out


def _normalize_type(name: str) -> str:
    # Collapse synonyms onto one canonical token.
    aliases = {
        "varchar": "string",
        "char": "string",
        "int": "integer",
        "bigint": "long",
        "smallint": "integer",
        "tinyint": "integer",
        "timestamp": "datetime",
        # Mainframe types map to closest Spark type. The original is preserved
        # on the field's `encoding` attribute so downstream readers can pick a
        # cobrix-style format. packed_decimal/bcd→decimal, binary→binary,
        # ebcdic_string/ebcdic→string.
        "packed_decimal": "decimal",
        "bcd": "decimal",
        "binary": "binary",
        "ebcdic_string": "string",
        "ebcdic": "string",
    }
    return aliases.get(name, name)


# ── layout / byte-offset analysis ─────────────────────────────────────────


# Approximate byte sizes for primitive types when no length arg is given.
# Aligns with Ab Initio's binary record encoding for the common cases.
_DEFAULT_BYTE_LENGTHS = {
    "integer": 4,
    "long":    8,
    "float":   4,
    "double":  8,
    "boolean": 1,
    "date":    10,        # YYYY-MM-DD
    "datetime": 19,       # YYYY-MM-DD HH:MM:SS
    "timestamp": 19,
}


def _field_byte_length(f: dict[str, Any]) -> int | None:
    """Best-effort byte size for one field. Returns None if it's variable-length
    (e.g. delimited string) or otherwise unknowable.
    """
    if f.get("delimiter") is not None:
        return None  # variable-length field
    t = f.get("type")
    args = f.get("args") or []
    if t == "string" or t == "binary":
        return args[0] if args else None
    if t == "decimal":
        # Default to precision in bytes (loose; Ab Initio packed_decimal uses
        # ceil(precision/2)+1 bytes — handle that branch when encoding signals it).
        if f.get("encoding") in ("packed_decimal",):
            precision = args[0] if args else 18
            return (precision // 2) + 1
        return args[0] if args else None
    if t in _DEFAULT_BYTE_LENGTHS:
        return _DEFAULT_BYTE_LENGTHS[t]
    return None


def _attach_layout(schema: dict[str, Any]) -> None:
    """Walk a schema once, attaching ``offset``/``length`` to fields when
    they're computable, and set ``layout`` + ``record_length`` at the root.

    Layout taxonomy:
      - ``"fixed"``     — every field is fixed-length and offsets line up
      - ``"delimited"`` — every field has an explicit delimiter
      - ``"mixed"``     — some of both, or unknowns
    """
    fields = schema.get("fields", [])
    has_delimited = False
    has_fixed = False
    has_unknown = False
    cursor = 0
    fully_fixed = True

    for f in fields:
        if f.get("delimiter") is not None:
            has_delimited = True
            fully_fixed = False
            continue
        if f.get("type") == "struct":
            # Recurse — nested struct doesn't contribute its own offset to
            # the flat layout, but we still annotate the inner schema.
            _attach_layout({"fields": f.get("fields", [])})
            fully_fixed = False
            continue
        size = _field_byte_length(f)
        if size is None:
            has_unknown = True
            fully_fixed = False
            continue
        f["offset"] = cursor
        f["length"] = size
        cursor += size
        has_fixed = True

    if fully_fixed and fields and has_fixed and not has_delimited:
        schema["layout"] = "fixed"
        schema["record_length"] = cursor
    elif has_delimited and not (has_fixed or has_unknown):
        schema["layout"] = "delimited"
    elif has_fixed or has_delimited:
        schema["layout"] = "mixed"


# ── public entry points ────────────────────────────────────────────────────


def parse_dml_string(
    src: str,
    params: dict[str, str] | None = None,
) -> dict[str, dict[str, Any]]:
    """Parse a DML file → ``{define_name: schema_dict}``.

    If ``params`` is provided, ``${VAR}`` references are interpolated
    *before* tokenisation — so the parser only ever sees concrete values.
    Unknown variables are left untouched.

    Each returned schema is annotated with ``layout`` (``fixed`` /
    ``delimited`` / ``mixed``) and, when fully fixed, a ``record_length``
    plus per-field ``offset`` and ``length``.
    """
    from .preprocess import strip_unresolved_vars
    src = preprocess_dml(src)
    if params:
        from .params import interpolate
        src = interpolate(src, params)
    # Anything still shaped like ${VAR} is unresolved — strip rather than
    # crash the tokenizer (which has no `$` token). Lenient on purpose so
    # macro-driven DML can be parsed even without the macro's value handy.
    src = strip_unresolved_vars(src)
    p = _Parser(_tokenize(src))
    schemas = p.parse_file()
    for schema in schemas.values():
        _attach_layout(schema)
    return schemas


def parse_dml_file(
    path: str | Path,
    params: dict[str, str] | None = None,
) -> dict[str, dict[str, Any]]:
    return parse_dml_string(Path(path).read_text(), params=params)


def resolve(schemas: dict[str, dict[str, Any]], key: str) -> dict[str, Any] | None:
    """Look up a schema by DEFINE name or by file basename.

    Components reference schemas via filenames (e.g.
    ``schema="customer.dml"``) or directly by DEFINE name. We try a few
    common transformations.
    """
    if key in schemas:
        return schemas[key]
    base = Path(key).stem  # `customer.dml` → `customer`
    if base in schemas:
        return schemas[base]
    # Try `customer_raw` ← `customer`, `customer_normalized` ← `customer`
    # (i.e. accept either direction loosely)
    for k in schemas:
        if k.startswith(base) or base.startswith(k):
            return schemas[k]
    return None


# ── PySpark conversion (kept from v1) ──────────────────────────────────────


def to_struct_type(schema: dict[str, Any], lossy: bool = False):
    """Lower a parsed DML schema dict to a PySpark ``StructType``.

    ``lossy`` controls how rich types are mapped:

      * ``False`` (default, production): every DML type maps to its closest
        Spark equivalent — ``decimal(p,s) → DecimalType``,
        ``date → DateType``, ``datetime/timestamp → TimestampType``.
        Preserves precision and type information for downstream Catalyst /
        Parquet operations.

      * ``True`` (lossy / simplified): collapses high-fidelity types onto
        a smaller alphabet — ``decimal → DoubleType``,
        ``date/datetime/timestamp → StringType``. Use when a downstream
        consumer can't handle ``DecimalType`` or expects ISO-string dates.
    """
    from pyspark.sql import types as T

    def field_to_spark(f):
        # ``array_dims`` (multi-dim) takes precedence; fall back to the
        # legacy boolean ``array`` flag for one-dim cases.
        dims = f.get("array_dims") or ([None] if f.get("array") else [])
        if f["type"] == "struct":
            spark_t = T.StructType([field_to_spark(sf) for sf in f["fields"]])
        else:
            spark_t = _primitive_to_spark(f["type"], f.get("args", []), lossy=lossy)
        for _ in dims:
            spark_t = T.ArrayType(spark_t, containsNull=True)
        return T.StructField(f["name"], spark_t, bool(f.get("nullable", True)))

    return T.StructType([field_to_spark(f) for f in schema["fields"]])


def _primitive_to_spark(name: str, args: list[int], lossy: bool = False):
    from pyspark.sql import types as T

    if lossy:
        # Simplified mapping for downstream consumers that can't handle
        # DecimalType / DateType. Numeric → Double, temporal → String.
        if name == "decimal":
            return T.DoubleType()
        if name in ("date", "datetime", "timestamp"):
            return T.StringType()

    if name == "string":
        return T.StringType()
    if name == "integer":
        return T.IntegerType()
    if name == "long":
        return T.LongType()
    if name == "double":
        return T.DoubleType()
    if name == "float":
        return T.FloatType()
    if name == "boolean":
        return T.BooleanType()
    if name == "decimal":
        precision = args[0] if args else 38
        scale = args[1] if len(args) > 1 else 0
        return T.DecimalType(precision, scale)
    if name == "binary":
        return T.BinaryType()
    if name == "date":
        return T.DateType()
    if name == "datetime":
        return T.TimestampType()
    raise ValueError(f"Unmapped primitive: {name}")
