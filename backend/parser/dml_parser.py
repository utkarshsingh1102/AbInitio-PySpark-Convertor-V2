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
        (?P<rbrace>\})                          |   # brace-close nested record
        (?P<at>@)                               |   # @style="..." annotations
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
    """Strip surrounding quotes and resolve escape sequences.

    Handles:
      * single-char escapes  ``\\n``  ``\\t``  ``\\r``  ``\\\\``  ``\\"``
      * octal escapes ``\\NNN`` (1-3 octal digits) — required for Hive's
        ``\\001`` SOH delimiter, which is a common field-terminator.
        Plain ``\\0`` still resolves to NUL when no octal digits follow.
    """
    inner = raw[1:-1]
    out: list[str] = []
    i = 0
    while i < len(inner):
        ch = inner[i]
        if ch == "\\" and i + 1 < len(inner):
            nxt = inner[i + 1]
            # Octal escape: consume up to 3 octal digits.
            if nxt in "01234567":
                end = i + 2
                while end < len(inner) and end - (i + 1) < 3 and inner[end] in "01234567":
                    end += 1
                out.append(chr(int(inner[i + 1:end], 8)))
                i = end
                continue
            out.append({
                "n": "\n", "t": "\t", "r": "\r",
                "\\": "\\", '"': '"',
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
    "packed_decimal", "binary", "bytes", "ebcdic_string", "ebcdic", "bcd",
    # Hive-DML idiom: ``integer(N)`` where N is a byte width (1, 2, 4, 8).
    # Already covered by ``integer`` above; listed for clarity.
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

# Storage-encoding prefixes that may appear before a primitive type
# (e.g. ``utf8 string``, ``ascii decimal(5)``, ``packed decimal(9,2)``).
# These don't change the Spark type mapping; they're recorded on the
# field's ``encoding`` attribute for downstream readers (cobrix, EBCDIC).
_ENCODING_PREFIXES = {"utf8", "ascii", "ebcdic", "packed"}

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
        # Set by ``_consume_array_brackets`` when it encounters
        # ``[<fieldname>]``. The current field-building call site reads and
        # clears it so the depending-on reference lands on the right field.
        self._pending_depends_on: str | None = None
        # User-defined type registry — populated by Phase 2 ``type X = record …``
        # declarations and consulted when ``_parse_field`` sees an unknown
        # identifier as a type.
        self.types_by_name: dict[str, dict[str, Any]] = {}

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
        """Parse all top-level definitions in the file.

        Recognised top-level forms:
          ``DEFINE name BEGIN … END``         — modern named schema
          ``record … end[;]``                 — legacy unnamed/named schema
          ``utf8|ascii|ebcdic|packed record …`` — same with encoding prefix
          ``type NAME = record … end;``       — type alias (stored in registry,
                                                NOT returned as a schema)
          ``metadata type = record … end;``   — root schema using the
                                                ``metadata`` keyword variant

        Returns ``{schema_name: schema_dict}``.
        """
        defs: dict[str, dict[str, Any]] = {}
        while not self.at_end():
            tok = self.peek()
            if tok is None:
                break
            if tok[0] != "ident":
                raise ValueError(f"Expected DEFINE/record/type, got {tok}")

            kw = tok[1].lower()

            # Optional storage-encoding prefix on the top-level record.
            # E.g. ``utf8 record …`` — strip and continue dispatching.
            if kw in _ENCODING_PREFIXES:
                # Only treat as a prefix if it's followed by `record` /
                # `group`. Otherwise leave it alone (could be a stray ident
                # we want to surface as an error).
                lookahead = self.toks[self.i + 1] if self.i + 1 < len(self.toks) else None
                if lookahead and lookahead[0] == "ident" and lookahead[1].lower() in _KW_RECORD:
                    self.eat("ident")  # consume the encoding word
                    tok = self.peek()
                    kw = tok[1].lower() if tok else ""

            if kw in _KW_DEFINE:
                name, schema = self._parse_define()
                defs[name] = schema
            elif kw in _KW_RECORD:
                # legacy `record ... end;` form — name comes from `end <name>;`
                name, schema = self._parse_record_legacy()
                defs[name or f"record_{len(defs)}"] = schema
            elif kw == "type":
                # `type NAME = record … end;` — alias declaration.
                name, schema = self._parse_type_alias()
                # Store under both original and lowercased keys so case-
                # insensitive lookups from `_parse_field` succeed regardless
                # of how the field references the type.
                self.types_by_name[name] = schema
                self.types_by_name[name.lower()] = schema
                # Aliases are NOT returned as top-level schemas; they're
                # only inlined when referenced from a field.
            elif kw == "metadata":
                # `metadata type = record … end;` — root schema variant
                # used by Ab Initio's xml-to-dml output.
                name, schema = self._parse_metadata_root()
                defs[name] = schema
            else:
                raise ValueError(f"Unexpected top-level token {tok}")
        return defs

    def _parse_type_alias(self) -> tuple[str, dict[str, Any]]:
        """``type NAME = record … end;`` — register a reusable type."""
        self.eat("ident", "type")
        name_tok = self.eat("ident")
        self.eat("eq")
        # Allow encoding prefix on the inner record too: `type X = utf8 record …`.
        peek = self.peek()
        if peek and peek[0] == "ident" and peek[1].lower() in _ENCODING_PREFIXES:
            lookahead = self.toks[self.i + 1] if self.i + 1 < len(self.toks) else None
            if lookahead and lookahead[0] == "ident" and lookahead[1].lower() in _KW_RECORD:
                self.eat("ident")
        self.eat("ident", "record")
        fields = self._parse_field_list(end_keyword="end")
        self._close_record_body()
        if self.peek() and self.peek()[0] == "semi":
            self.eat("semi")
        return name_tok[1], {"type": "record", "fields": fields}

    def _parse_metadata_root(self) -> tuple[str, dict[str, Any]]:
        """``metadata type = record … end;`` — root schema with the
        ``metadata`` keyword variant. Returns (``"metadata"``, schema)."""
        self.eat("ident", "metadata")
        # Optional `type` literal between `metadata` and `=`.
        if self.peek() and self.peek()[0] == "ident" and self.peek()[1].lower() == "type":
            self.eat("ident", "type")
        self.eat("eq")
        peek = self.peek()
        if peek and peek[0] == "ident" and peek[1].lower() in _ENCODING_PREFIXES:
            lookahead = self.toks[self.i + 1] if self.i + 1 < len(self.toks) else None
            if lookahead and lookahead[0] == "ident" and lookahead[1].lower() in _KW_RECORD:
                self.eat("ident")
        self.eat("ident", "record")
        fields = self._parse_field_list(end_keyword="end")
        self._close_record_body()
        if self.peek() and self.peek()[0] == "semi":
            self.eat("semi")
        return "metadata", {"type": "record", "fields": fields}

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
        """Consume any sequence of bracket pairs. Returns a list of dimension
        lengths — ``None`` for any unbounded / variable-length dimension.

        Three accepted forms per pair:
          - ``[]``           → unbounded                         (length = None)
          - ``[N]``           → fixed-length                      (length = N)
          - ``[int]``         → unbounded vector marker           (length = None)
          - ``[<fieldname>]`` → variable-length, depending-on     (length = None)

        For depending-on references, the referenced field name is recorded
        on ``self._pending_depends_on`` so callers can attach it to the field
        AST. Multiple bracket pairs produce a multi-dimensional array.
        """
        dims: list[int | None] = []
        while self.peek() and self.peek()[0] == "lbracket":
            self.eat("lbracket")
            nxt = self.peek()
            length: int | None = None
            if nxt and nxt[0] == "num":
                self.eat("num")
                length = int(nxt[1])
            elif nxt and nxt[0] == "ident":
                ident_name = self.eat("ident")[1]
                if ident_name.lower() == "int":
                    length = None  # unbounded marker
                else:
                    length = None
                    self._pending_depends_on = ident_name
            self.eat("rbracket")
            dims.append(length)
        return dims

    def _parse_field_list(self, end_keyword: str) -> list[dict[str, Any]]:
        fields: list[dict[str, Any]] = []
        while True:
            tok = self.peek()
            if tok is None:
                raise ValueError("Unexpected EOF in field list")
            # Accept either the `end` keyword or `}` (brace-close form). The
            # caller decides which closer was used by peeking at the next
            # token after this returns.
            if tok[0] == "ident" and tok[1].lower() == end_keyword:
                return fields
            if tok[0] == "rbrace":
                return fields
            # Conditional block: `if (cond) [then] <fields...> [else <fields...>] end;`
            # Each branch's fields get flattened into the parent's list with
            # nullable forced True and a `condition` annotation for codegen.
            if tok[0] == "ident" and tok[1].lower() == "if":
                fields.extend(self._parse_conditional())
                continue
            fields.append(self._parse_field())

    def _close_record_body(self) -> str:
        """Consume the closer of a record body. Returns ``"end"`` or ``"}"``.

        Caller is responsible for any post-close processing (name, array
        brackets, modifiers, semicolon).
        """
        tok = self.peek()
        if tok is None:
            raise ValueError("Unexpected EOF — expected `end` or `}` closer")
        if tok[0] == "rbrace":
            self.eat("rbrace")
            return "}"
        if tok[0] == "ident" and tok[1].lower() == "end":
            self.eat("ident", "end")
            return "end"
        raise ValueError(f"Expected `end` or `}}` closer, got {tok}")

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

        Accepted forms (all combinable with optional modifiers + annotations):

          <name> <type>[(args)] [modifiers];                 (modern)
          <type>[(args)] <name> [modifiers];                 (legacy primitive)
          <name> record <fields> end [<ignored>][[]] [mods]; (modern nested)
          record <fields> end [<name>] [[]] [mods];          (legacy nested)
          record <fields> } [[N]] <name>;                    (brace-close)
          [utf8|ascii|ebcdic|packed] <type>(args) <name>;    (encoding prefix)
        """
        # Clear any depending-on state from a previous field's brackets.
        self._pending_depends_on = None

        # Optional storage-encoding prefix: utf8 | ascii | ebcdic | packed
        # before a primitive type. Doesn't affect Spark mapping, but the
        # prefix is stored on the AST for downstream readers (cobrix etc).
        encoding_prefix: str | None = None
        peek = self.peek()
        if peek and peek[0] == "ident" and peek[1].lower() in _ENCODING_PREFIXES:
            # Only treat as a prefix if the *next* token is an ident (the type).
            # That avoids consuming a field literally named `ascii` etc.
            after = self.toks[self.i + 1] if self.i + 1 < len(self.toks) else None
            if after and after[0] == "ident":
                encoding_prefix = peek[1].lower()
                self.eat("ident")

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
        udt_name: str | None = None
        # ``decimal_format`` captures the string form ``decimal(".2")``.
        decimal_format: str | None = None

        if first_word in _KW_RECORD:
            # Legacy nested record (or `group` alias). Accept all of:
            #   record … end <name>[N];      (name first)
            #   record … end[N] <name>;      (brackets first)
            #   record … end[N];             (anonymous, just brackets)
            #   record … end;                (anonymous, no array)
            #   record … } <name>;           (brace-close form)
            #   record … } [int] <name>;     (brace-close + brackets-before-name)
            struct_fields = self._parse_field_list(end_keyword="end")
            self._close_record_body()  # consumes either "end" or "}"

            # Optional brackets BEFORE the name. Both `end[N] name` and
            # `} [int] name` orderings put dimensions ahead of the field name.
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
            # Brackets MAY come between the args and the name (generator
            # idiom: ``string(",")[int] tags;``). Consume them here; the
            # post-name pass below will pick up any additional brackets.
            array_dims.extend(self._consume_array_brackets())
            field_name = self.eat("ident")[1]
        elif first_word in self.types_by_name:
            # Legacy form with a user-defined type: ``policy_address_t Address;``
            # First token is the UDT name, second is the field name.
            udt = self.types_by_name[first_word] or self.types_by_name.get(first[1])
            struct_fields = [dict(f) for f in udt.get("fields", [])]
            type_name = "struct"
            is_struct = True
            udt_name = first[1]
            # Optional brackets between the UDT name and the field name —
            # ``vehicle_info_t[int] Vehicle;``.
            array_dims.extend(self._consume_array_brackets())
            field_name = self.eat("ident")[1]
        else:
            field_name = first[1]
            type_tok = self.eat("ident")
            type_name = type_tok[1].lower()
            if type_name in _KW_RECORD:
                struct_fields = self._parse_field_list(end_keyword="end")
                closer = self._close_record_body()  # "end" or "}"
                if closer == "end":
                    # Optional trailing identifier (e.g. `end addr`) before
                    # array brackets / modifiers / semicolon. Only consume it
                    # if it isn't actually a nullability keyword.
                    nxt = self.peek()
                    if nxt and nxt[0] == "ident":
                        kw = nxt[1].lower()
                        if (kw not in _KW_NULL and kw not in _KW_NOT
                                and kw not in _KW_NOT_NULL and kw not in _KW_NULLABLE):
                            self.eat("ident")
                # If closer == "}", the name was already consumed before
                # `record` (modern form), so no trailing-identifier rule.
                type_name = "struct"
                is_struct = True
            else:
                if type_name not in _PRIMITIVES:
                    # Could be a user-defined type from `type X = record …`
                    # declarations (Phase 2). Look it up in the registry.
                    udt = self.types_by_name.get(type_name) or self.types_by_name.get(type_tok[1])
                    if udt is None:
                        raise ValueError(f"Unknown DML type: {type_name}")
                    # Inline the UDT's body. Keep the original name on the
                    # field so downstream codegen can preserve identity.
                    struct_fields = [dict(f) for f in udt.get("fields", [])]
                    type_name = "struct"
                    is_struct = True
                    udt_name = type_tok[1]
                else:
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

        # Annotations: ``@key="value"`` (multi: ``@key="v", name="other"``).
        annotations = self._consume_annotations()

        self.eat("semi")

        # Snapshot any depending-on reference picked up by the most recent
        # ``_consume_array_brackets`` call before the next field clobbers it.
        depends_on = self._pending_depends_on
        self._pending_depends_on = None

        # ``decimal("format")`` form: a string arg on a decimal type CAN be
        # a format like ``".2"`` (scale 2) or ``"9999.99"`` (precision 6,
        # scale 2). It can ALSO be a real delimiter like ``"¨"`` or ``","``.
        # Treat as a format only when the string actually looks like a
        # numeric format — otherwise leave it as a delimiter.
        if type_name == "decimal" and not type_args and delimiter is not None:
            if _looks_like_decimal_format(delimiter):
                decimal_format = delimiter
                type_args = _decimal_format_to_args(delimiter)
                delimiter = None

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
            if udt_name is not None:
                out["udt_name"] = udt_name
            if encoding_prefix is not None:
                out["encoding"] = encoding_prefix
            if annotations:
                out["annotations"] = annotations
            if depends_on:
                out["depends_on"] = depends_on
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
        elif encoding_prefix is not None:
            # Encoding prefix wins over no-prefix; preserves whichever was
            # specified (utf8 / ascii / ebcdic / packed).
            out["encoding"] = encoding_prefix
        if decimal_format is not None:
            out["decimal_format"] = decimal_format
        if annotations:
            out["annotations"] = annotations
        if depends_on:
            out["depends_on"] = depends_on
        return out

    def _consume_annotations(self) -> dict[str, str]:
        """Consume zero or more ``@key="value"`` annotations.

        Forms recognised:
          ``@style="element"``                        — single
          ``@style="attribute", name="type"``         — multi-annotation
                                                        (additional pairs share
                                                         the leading ``@``)

        Annotations are skipped semantically — they don't affect the Spark
        type — but the parsed ``{key: value}`` dict is returned so callers
        can attach it to the AST for later XML/Cobrix-aware codegen.
        """
        if not (self.peek() and self.peek()[0] == "at"):
            return {}
        out: dict[str, str] = {}
        # Consume the leading @ once.
        self.eat("at")
        while True:
            key_tok = self.eat("ident")
            self.eat("eq")
            val_tok = self.peek()
            if val_tok is None or val_tok[0] != "dqstring":
                raise ValueError(f"Expected string value after @{key_tok[1]}=")
            self.eat("dqstring")
            out[key_tok[1]] = _unescape_dqstring(val_tok[1])
            # Multi-annotation: a comma followed by another `key="value"`
            # pair (with or without a fresh leading `@`).
            if self.peek() and self.peek()[0] == "comma":
                self.eat("comma")
                if self.peek() and self.peek()[0] == "at":
                    self.eat("at")
                continue
            break
        return out


def _looks_like_decimal_format(s: str) -> bool:
    """True if the string is plausibly a decimal *format* (e.g. ``".2"``,
    ``"9999.99"``) rather than a *delimiter* (e.g. ``","``, ``"¨"``,
    ``"\\0"``).

    Rule: must contain at least one digit or `9` (Ab Initio's mask char),
    and consist only of digits, `9`s, dots, signs, and whitespace.
    """
    if not s:
        return False
    has_digit = any(c.isdigit() or c == "9" for c in s)
    if not has_digit:
        return False
    return all(c.isdigit() or c in ".+-9 \t" for c in s)


def _decimal_format_to_args(fmt: str) -> list[int]:
    """Translate an Ab Initio decimal format string to ``[precision, scale]``.

    Ab Initio writes ``decimal(".2")`` (scale 2, default precision) or
    ``decimal("9999.99")`` (precision 6, scale 2). Spark needs explicit
    precision + scale. Defaults: when precision can't be inferred, use
    Spark's max precision of 38.
    """
    fmt = fmt.strip()
    # Plain `.N` → scale N, default precision 38
    m = re.match(r"^\.(\d+)$", fmt)
    if m:
        return [38, int(m.group(1))]
    # Plain `N` → precision N, scale 0
    m = re.match(r"^(\d+)$", fmt)
    if m:
        return [int(m.group(1)), 0]
    # ``9999.99`` style — count digits before/after the dot
    m = re.match(r"^(9*)\.(9*)$", fmt)
    if m:
        before = len(m.group(1))
        after = len(m.group(2))
        return [max(before + after, 1), after]
    # Last-ditch: count any digits + decimal point. Default to 38, 0.
    if "." in fmt:
        before, after = fmt.split(".", 1)
        before_d = sum(c.isdigit() for c in before)
        after_d = sum(c.isdigit() for c in after)
        if after_d:
            return [max(before_d + after_d, after_d, 1), after_d]
    return [38, 0]


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
        "bytes": "binary",
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
    if t == "integer" and args:
        # ``integer(N)`` — N is byte width.
        return args[0]
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
        # ``integer(N)`` — N is byte width (Hive/Ab Initio convention):
        #   1 → ByteType, 2 → ShortType, 4 → IntegerType, 8 → LongType.
        width = args[0] if args else 4
        if width <= 1:
            return T.ByteType()
        if width <= 2:
            return T.ShortType()
        if width <= 4:
            return T.IntegerType()
        return T.LongType()
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
