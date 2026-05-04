"""Hive `CREATE TABLE` DDL → Ab Initio DML text.

Pipeline:

    Hive DDL  →  schema dict  →  DML text
    └ tokenize + parse ┘   └ schema_to_dml ┘

The schema dict is purely an in-memory intermediate; only the DML text is
returned. Output matches the format Ab Initio's `hive-to-dml` utility
produces — see [real-dml.md](../../real-dml.md) Example 4.

Supported grammar:

    CREATE [EXTERNAL|TEMPORARY] TABLE [IF NOT EXISTS] [db.]name (
        col TYPE [COMMENT 'string']  [, …]
    )
    [PARTITIONED BY (col TYPE, …)]
    [CLUSTERED BY ...]                       -- ignored
    [ROW FORMAT DELIMITED
        [FIELDS TERMINATED BY 'c']
        [COLLECTION ITEMS TERMINATED BY 'c']
        [LINES TERMINATED BY 'c']]
    [STORED AS PARQUET|ORC|AVRO|TEXTFILE|SEQUENCEFILE]
    [LOCATION 'path']
    [TBLPROPERTIES (...)]                    -- ignored

Type vocabulary → DML primitive:

    TINYINT  → integer(1)
    SMALLINT → integer(2)
    INT/INTEGER → integer(4)
    BIGINT   → integer(8)
    FLOAT    → float
    DOUBLE   → double
    STRING   → string("<delim>")  (delim from ROW FORMAT, or "" for parquet)
    VARCHAR(n) / CHAR(n) → string(n)
    DECIMAL(p,s) / NUMERIC(p,s) → decimal(p,s)
    BOOLEAN  → boolean
    DATE     → date
    TIMESTAMP → datetime
    BINARY   → binary
    ARRAY<T> → T[int]
    MAP<K,V> → record { K key; V value; } [int] map_entries;
    STRUCT<a:T1, b:T2> → nested record
"""
from __future__ import annotations

import re
from typing import Any

from .dml_emitter import schema_to_dml

# ── tokenizer ──────────────────────────────────────────────────────────────

_TOKEN_RE = re.compile(
    r"""
    \s*(?:
        (?P<lparen>\()                          |
        (?P<rparen>\))                          |
        (?P<langle><)                           |
        (?P<rangle>>)                           |
        (?P<comma>,)                            |
        (?P<semi>;)                             |
        (?P<colon>:)                            |
        (?P<dot>\.)                             |
        (?P<eq>=)                               |
        (?P<num>\d+)                            |
        (?P<sqstring>'(?:\\.|[^'\\])*')         |
        (?P<dqstring>"(?:\\.|[^"\\])*")         |
        (?P<bqstring>`[^`]*`)                   |
        (?P<ident>[A-Za-z_][A-Za-z0-9_]*)
    )
    """,
    re.VERBOSE,
)


# CTAS: ``CREATE [EXTERNAL|TEMPORARY] TABLE [IF NOT EXISTS] name [...]
# AS SELECT ...``. The ``[^(]*`` between ``TABLE`` and ``AS SELECT``
# ensures we only match when there's no column list — a regular DDL with
# ``CREATE TABLE name (...) AS …`` has a ``(`` in that span.
_CTAS_RE = re.compile(
    r"create\s+(external\s+|temporary\s+)*table\b"
    r"(\s+if\s+not\s+exists\b)?"
    r"[^(]*\bas\s+select\b",
    re.IGNORECASE | re.DOTALL,
)
# CREATE TABLE LIKE — copies a schema from another table; also requires
# metastore access we don't have.
_CT_LIKE_RE = re.compile(
    r"create\s+(external\s+|temporary\s+)*table\b"
    r"(\s+if\s+not\s+exists\b)?"
    r"\s+\S+\s+like\b",
    re.IGNORECASE,
)


def _strip_comments(src: str) -> str:
    src = re.sub(r"/\*.*?\*/", " ", src, flags=re.DOTALL)
    src = re.sub(r"--[^\n]*", "", src)
    return src


def _unquote_with_octal(s: str) -> str:
    """Strip ``'...'`` / ``"..."`` and resolve ``\\NNN`` octal + common escapes.

    Octal handling is required for Hive's default ``\\001`` (SOH) field
    terminator.
    """
    if len(s) < 2:
        return s
    inner = s[1:-1]
    out: list[str] = []
    i = 0
    while i < len(inner):
        ch = inner[i]
        if ch == "\\" and i + 1 < len(inner):
            nxt = inner[i + 1]
            if nxt in "01234567":
                end = i + 2
                while end < len(inner) and end - (i + 1) < 3 and inner[end] in "01234567":
                    end += 1
                out.append(chr(int(inner[i + 1:end], 8)))
                i = end
                continue
            out.append({
                "n": "\n", "t": "\t", "r": "\r",
                "\\": "\\", "'": "'", '"': '"',
            }.get(nxt, nxt))
            i += 2
        else:
            out.append(ch)
            i += 1
    return "".join(out)


def _tokenize(src: str) -> list[tuple[str, str]]:
    src = _strip_comments(src)
    out: list[tuple[str, str]] = []
    pos = 0
    while pos < len(src):
        m = _TOKEN_RE.match(src, pos)
        if not m:
            if src[pos].isspace():
                pos += 1
                continue
            raise ValueError(f"Unexpected character at {pos}: {src[pos]!r}")
        kind = m.lastgroup
        out.append((kind, m.group(kind)))  # type: ignore[arg-type]
        pos = m.end()
    return out


# ── primitive type map ─────────────────────────────────────────────────────

_PRIMITIVE: dict[str, tuple[str, list[int], str]] = {
    # name → (dml_type, default args, hive-origin label for inline comment)
    #
    # Byte-width forms follow the canonical Ab Initio hive-to-dml mapping:
    #   FLOAT  → float(4)     DOUBLE   → float(8)
    #   BOOLEAN → integer(1)  TIMESTAMP → timestamp
    #   BINARY → bytes        DATE     → date
    "tinyint":  ("integer",   [1], "TINYINT"),
    "smallint": ("integer",   [2], "SMALLINT"),
    "int":      ("integer",   [4], "INT"),
    "integer":  ("integer",   [4], "INTEGER"),
    "bigint":   ("integer",   [8], "BIGINT"),
    "long":     ("integer",   [8], "LONG → BIGINT alias"),
    "float":    ("float",     [4], "FLOAT"),
    "double":   ("float",     [8], "DOUBLE"),
    "boolean":  ("integer",   [1], "BOOLEAN"),
    "date":     ("date",      [], "DATE"),
    "timestamp":("timestamp", [], "TIMESTAMP"),
    "binary":   ("bytes",     [], "BINARY"),
}


# ── parser → schema dict ───────────────────────────────────────────────────


class _Parser:
    def __init__(self, tokens: list[tuple[str, str]]):
        self.toks = tokens
        self.i = 0
        # original-backticked-name → sanitized-DML-name. Populated whenever
        # `_eat_name_token` rewrites a Hive-only-legal identifier into a
        # DML-legal one, so callers can preserve the mapping for lineage.
        self.column_renames: dict[str, str] = {}

    def peek(self, off: int = 0) -> tuple[str, str] | None:
        idx = self.i + off
        return self.toks[idx] if idx < len(self.toks) else None

    def eat(self, kind: str | None = None, value: str | None = None) -> tuple[str, str]:
        tok = self.peek()
        if tok is None:
            raise ValueError("Unexpected end of input")
        if kind is not None and tok[0] != kind:
            raise ValueError(f"Expected {kind}, got {tok}")
        if value is not None and tok[1].lower() != value.lower():
            raise ValueError(f"Expected {value!r}, got {tok!r}")
        self.i += 1
        return tok

    def at_end(self) -> bool:
        return self.i >= len(self.toks)

    def _is_kw(self, kw: str, off: int = 0) -> bool:
        tok = self.peek(off)
        return tok is not None and tok[0] == "ident" and tok[1].lower() == kw

    def _has_select_ahead(self) -> bool:
        """Scan the remaining tokens for a ``SELECT`` keyword. CTAS is the
        only CREATE TABLE form that contains a SELECT, so this is a
        sufficient discriminator (and avoids the false-positive on
        ``STORED AS PARQUET`` that a naive ``AS SELECT`` lookahead has)."""
        return any(
            tok[0] == "ident" and tok[1].lower() == "select"
            for tok in self.toks[self.i:]
        )

    # entry: returns one schema dict (the LAST CREATE TABLE if multiple) plus
    # the table name. We only support one table per request.
    def parse(self) -> tuple[str, dict[str, Any]]:
        # Skip leading semicolons or stray tokens until we see CREATE.
        while not self.at_end():
            tok = self.peek()
            if tok and tok[0] == "semi":
                self.eat("semi")
                continue
            if self._is_kw("create"):
                break
            # Disambiguate common wrong-statement-type cases for a more
            # helpful error.
            if self._is_kw("alter"):
                raise ValueError(
                    "ALTER TABLE is not supported — provide a CREATE TABLE "
                    "statement instead."
                )
            if self._is_kw("drop"):
                raise ValueError(
                    "DROP TABLE is not supported — provide a CREATE TABLE "
                    "statement instead."
                )
            if tok and tok[0] == "ident":
                raise ValueError(
                    f"Expected CREATE TABLE statement, got {tok[1]!r}. "
                    "Input does not appear to be valid Hive DDL."
                )
            raise ValueError(
                f"Expected CREATE TABLE statement, got {tok}. "
                "Input does not appear to be valid Hive DDL."
            )
        if self.at_end():
            raise ValueError("No CREATE TABLE statement found")
        return self._parse_create_table()

    def _parse_create_table(self) -> tuple[str, dict[str, Any]]:
        self.eat("ident", "create")
        if self._is_kw("external"):
            self.eat("ident", "external")
        if self._is_kw("temporary"):
            self.eat("ident", "temporary")
        # Catch CREATE VIEW / INDEX / DATABASE / FUNCTION etc. with a
        # helpful message instead of a raw "expected 'table'" error.
        nxt = self.peek()
        if nxt and nxt[0] == "ident" and nxt[1].lower() != "table":
            kind = nxt[1].upper()
            raise ValueError(
                f"CREATE {kind} is not supported — provide a CREATE TABLE "
                "statement instead."
            )
        self.eat("ident", "table")
        if self._is_kw("if"):
            self.eat("ident", "if"); self.eat("ident", "not"); self.eat("ident", "exists")

        name = self._parse_qualified_name()

        # If the next token isn't `(`, the user gave us something other than
        # a column-list DDL — most commonly a CTAS or CREATE TABLE LIKE.
        # Surface a targeted error for each so the caller knows the
        # workaround instead of a generic "expected lparen".
        nxt = self.peek()
        if not (nxt and nxt[0] == "lparen"):
            if self._is_kw("like"):
                raise ValueError(
                    "CREATE TABLE LIKE is not supported — provide a "
                    "CREATE TABLE with an explicit column list. Run "
                    "`DESCRIBE EXTENDED <other_table>` to get the schema "
                    "and paste that DDL instead."
                )
            if self._has_select_ahead():
                raise ValueError(
                    "CTAS (CREATE TABLE … AS SELECT …) is not supported — "
                    "the schema is derived by running the SELECT against "
                    "a live Hive metastore, which the converter has no "
                    "access to. Run the CTAS in Hive, then "
                    "`DESCRIBE EXTENDED <resulting_table>` and paste that "
                    "DDL instead."
                )
            # Fall through to `eat("lparen")` for the generic error.
        self.eat("lparen")
        fields = self._parse_column_list()
        self.eat("rparen")

        delimiter: str | None = None
        partition_cols: list[dict[str, Any]] = []
        stored_format: str | None = None

        while not self.at_end():
            tok = self.peek()
            if tok is None or tok[0] == "semi":
                break
            if tok[0] != "ident":
                break
            kw = tok[1].lower()
            if kw == "partitioned":
                self.eat("ident", "partitioned")
                self.eat("ident", "by")
                self.eat("lparen")
                partition_cols = self._parse_column_list()
                self.eat("rparen")
            elif kw == "clustered":
                self._skip_clause()
            elif kw == "row":
                self.eat("ident", "row"); self.eat("ident", "format")
                if self._is_kw("delimited"):
                    self.eat("ident", "delimited")
                    delimiter = self._parse_row_format_delimited()
                else:
                    self._skip_clause()
            elif kw == "stored":
                self.eat("ident", "stored")
                sub = self.peek()
                if sub and sub[0] == "ident" and sub[1].lower() == "by":
                    # ``STORED BY 'org.apache...HBaseStorageHandler'
                    #   [WITH SERDEPROPERTIES (...)]``
                    # Schema is unaffected — we just walk past the clause.
                    self.eat("ident", "by")
                    self.eat()  # consume the serde class string literal
                    if self._is_kw("with"):
                        self.eat("ident", "with")
                        self.eat("ident", "serdeproperties")
                        self.eat("lparen")
                        depth = 1
                        while depth > 0 and not self.at_end():
                            t = self.eat()
                            if t[0] == "lparen":
                                depth += 1
                            elif t[0] == "rparen":
                                depth -= 1
                    stored_format = "by_serde"
                else:
                    self.eat("ident", "as")
                    nxt2 = self.peek()
                    if nxt2 and nxt2[0] == "ident":
                        stored_format = self.eat("ident")[1].lower()
            elif kw == "location":
                self.eat("ident", "location"); self.eat()
            elif kw == "tblproperties":
                self.eat("ident", "tblproperties")
                self.eat("lparen")
                depth = 1
                while depth > 0 and not self.at_end():
                    t = self.eat()
                    if t[0] == "lparen":
                        depth += 1
                    elif t[0] == "rparen":
                        depth -= 1
            elif kw == "comment":
                self.eat("ident", "comment"); self.eat()
            else:
                break

        # Pin a delimiter onto every flat field — but only for text storage.
        # PARQUET / ORC / AVRO are binary formats; the delimiter is a Hive
        # serde detail that has no meaning in DML for those formats. When
        # absent (the default) we treat the table as text.
        fmt = (stored_format or "").lower() or None
        if delimiter is not None and fmt in _TEXT_STORAGE_FORMATS:
            _stamp_delimiter(fields, delimiter)
            _stamp_delimiter(partition_cols, delimiter)

        # Reject duplicate column names — Hive normalises to lowercase, so
        # ``Name`` / ``name`` / ``NAME`` are the same identifier. Catching
        # this here prevents emitting DML with two fields of the same name,
        # which downstream tools (and our own DML parser) would mishandle.
        _check_duplicate_columns(fields, partition_cols)

        # Decorate the field list with section banners.
        # "Basic Hive Types" sits above the first run of primitives; later
        # complex columns (ARRAY → vector, MAP → record-vector) get their
        # own banners attached directly so the emitter renders them
        # inline. Partition columns are appended under their own banner.
        _attach_section_banners(fields)

        if partition_cols:
            partition_cols[0]["block_comment"] = "Partition columns"
            fields.extend(partition_cols)

        schema: dict[str, Any] = {"type": "record", "fields": fields}
        if stored_format:
            schema["stored_as"] = stored_format
        return name, schema

    # ── helpers ────────────────────────────────────────────────────────────

    def _parse_qualified_name(self) -> str:
        first = self._eat_name_token()
        if self.peek() and self.peek()[0] == "dot":
            self.eat("dot")
            return self._eat_name_token()
        return first

    def _eat_name_token(self) -> str:
        tok = self.peek()
        if tok is None:
            raise ValueError("Expected identifier, got EOF")
        if tok[0] == "bqstring":
            self.eat("bqstring")
            original = tok[1].strip("`")
            sanitized = _sanitize_identifier(original)
            if sanitized != original:
                self.column_renames[original] = sanitized
            return sanitized
        if tok[0] == "ident":
            self.eat("ident")
            return tok[1]
        raise ValueError(f"Expected identifier, got {tok}")

    def _parse_column_list(self) -> list[dict[str, Any]]:
        fields: list[dict[str, Any]] = []
        # Hive permits an empty parenthesised column list when the schema
        # comes entirely from PARTITIONED BY. Bail before parsing so we
        # don't try to read a column off the closing paren.
        nxt = self.peek()
        if nxt and nxt[0] == "rparen":
            return fields
        while True:
            fields.append(self._parse_column())
            if self.peek() and self.peek()[0] == "comma":
                self.eat("comma")
                # Tolerate a trailing comma immediately before the closing
                # paren — some DDL generators emit it.
                nxt2 = self.peek()
                if nxt2 and nxt2[0] == "rparen":
                    break
                continue
            break
        return fields

    def _parse_column(self) -> dict[str, Any]:
        name = self._eat_name_token()
        type_dict = self._parse_type()
        if self._is_kw("comment"):
            self.eat("ident", "comment")
            t = self.peek()
            if t and t[0] in ("sqstring", "dqstring"):
                self.eat()
        nullable = True
        if self._is_kw("not"):
            self.eat("ident", "not"); self.eat("ident", "null"); nullable = False
        elif self._is_kw("null"):
            self.eat("ident", "null"); nullable = True
        return {"name": name, **type_dict, "nullable": nullable}

    def _parse_type(self) -> dict[str, Any]:
        tok = self.peek()
        if tok is None or tok[0] != "ident":
            raise ValueError(f"Expected type, got {tok}")
        type_name = tok[1].lower()

        if type_name == "array":
            self.eat("ident"); self.eat("langle")
            inner = self._parse_type()
            self.eat("rangle")
            # Wrap ARRAY in a single-field record:
            #   record { T[int] item; } colname;
            # This matches Ab Initio's hive-to-dml utility output. The
            # outer struct has array=False; the inner `item` field carries
            # array=True so the emitter renders `[int]` after its type.
            inner["array"] = True
            inner["name"] = "item"
            inner.setdefault("nullable", True)
            return {
                "type": "struct",
                "fields": [inner],
                "array": False,
                "block_comment": "Hive ARRAY becomes a DML Vector",
            }

        if type_name == "map":
            self.eat("ident"); self.eat("langle")
            key_t = self._parse_type()
            self.eat("comma")
            val_t = self._parse_type()
            self.eat("rangle")
            # Outer wrap matches Ab Initio's canonical MAP form:
            #   record { record { K key; V value; } [int] map_entries; } colname;
            # The inner struct carries the [int] vector marker and is named
            # `map_entries`; the outer struct gives the column its name.
            entries = {
                "type": "struct",
                "name": "map_entries",
                "fields": [
                    {"name": "key",   "nullable": True, **key_t, "array": key_t.get("array", False)},
                    {"name": "value", "nullable": True, **val_t, "array": val_t.get("array", False)},
                ],
                "array": True,
                "nullable": True,
            }
            return {
                "type": "struct",
                "fields": [entries],
                "array": False,
                "block_comment": "Hive MAP becomes a Vector of Key-Value pairs",
            }

        if type_name == "struct":
            self.eat("ident"); self.eat("langle")
            # Empty STRUCT<> is invalid Hive — reject with a clear message
            # rather than crashing on the unexpected `>` token.
            if self.peek() and self.peek()[0] == "rangle":
                self.eat("rangle")
                raise ValueError(
                    "Empty STRUCT<> is not valid — Hive STRUCT requires "
                    "at least one named field."
                )
            sf: list[dict[str, Any]] = []
            while True:
                fname = self._eat_name_token()
                self.eat("colon")
                ftype = self._parse_type()
                sf.append({"name": fname, "nullable": True, **ftype, "array": ftype.get("array", False)})
                if self.peek() and self.peek()[0] == "comma":
                    self.eat("comma")
                    continue
                break
            self.eat("rangle")
            return {"type": "struct", "fields": sf, "array": False}

        if type_name == "uniontype":
            raise ValueError("Hive UNIONTYPE is not supported")

        self.eat("ident")
        if type_name in ("varchar", "char"):
            args: list[int] = []
            if self.peek() and self.peek()[0] == "lparen":
                self.eat("lparen")
                args.append(int(self.eat("num")[1]))
                self.eat("rparen")
            return {
                "type": "string", "args": args, "array": False,
                "origin_comment": f"{type_name.upper()}{f'({args[0]})' if args else ''}",
            }
        if type_name == "string":
            return {
                "type": "string", "args": [], "array": False,
                "origin_comment": "STRING",
            }
        if type_name in ("decimal", "numeric"):
            args = []
            if self.peek() and self.peek()[0] == "lparen":
                self.eat("lparen")
                args.append(int(self.eat("num")[1]))
                if self.peek() and self.peek()[0] == "comma":
                    self.eat("comma")
                    args.append(int(self.eat("num")[1]))
                self.eat("rparen")
            else:
                args = [10, 0]
            return {
                "type": "decimal", "args": args, "array": False,
                "origin_comment": f"{type_name.upper()}({args[0]},{args[1] if len(args) > 1 else 0})",
            }
        if type_name not in _PRIMITIVE:
            raise ValueError(f"Unknown Hive type: {type_name}")
        dml_t, default_args, label = _PRIMITIVE[type_name]
        # Hive 3.x: TIMESTAMP WITH LOCAL TIME ZONE — timezone metadata
        # discarded; we map to plain `timestamp` per the doc.
        if type_name == "timestamp" and self._is_kw("with"):
            self.eat("ident", "with")
            self.eat("ident", "local")
            self.eat("ident", "time")
            self.eat("ident", "zone")
            label = "TIMESTAMP WITH LOCAL TIME ZONE → timestamp (timezone discarded)"
        return {
            "type": dml_t, "args": list(default_args), "array": False,
            "origin_comment": label,
        }

    def _parse_row_format_delimited(self) -> str | None:
        delim: str | None = None
        while not self.at_end():
            tok = self.peek()
            if tok is None or tok[0] != "ident":
                break
            kw = tok[1].lower()
            if kw == "fields":
                self.eat("ident", "fields"); self.eat("ident", "terminated"); self.eat("ident", "by")
                t = self.eat()
                if t[0] in ("sqstring", "dqstring"):
                    delim = _unquote_with_octal(t[1])
                if self._is_kw("escaped"):
                    self.eat("ident", "escaped"); self.eat("ident", "by"); self.eat()
            elif kw in ("collection", "map", "lines", "null"):
                # COLLECTION ITEMS TERMINATED BY / MAP KEYS TERMINATED BY /
                # LINES TERMINATED BY / NULL DEFINED AS — skip the rest of
                # the clause (3 or 4 idents + literal).
                while not self.at_end():
                    nxt = self.peek()
                    if nxt is None or nxt[0] != "ident":
                        # consume the literal
                        if nxt is not None:
                            self.eat()
                        break
                    nkw = nxt[1].lower()
                    if nkw in ("by", "as"):
                        self.eat("ident")
                        if self.peek() and self.peek()[0] in ("sqstring", "dqstring"):
                            self.eat()
                        break
                    self.eat("ident")
            else:
                break
        return delim

    def _skip_clause(self) -> None:
        """Advance until the next top-level table-clause keyword."""
        top_kws = {"partitioned", "row", "stored", "location", "tblproperties",
                   "comment", "create"}
        depth = 0
        while not self.at_end():
            tok = self.peek()
            if tok is None:
                return
            if tok[0] == "lparen":
                depth += 1
            elif tok[0] == "rparen":
                depth -= 1
                if depth < 0:
                    return
            elif depth == 0:
                if tok[0] == "semi":
                    return
                if tok[0] == "ident" and tok[1].lower() in top_kws:
                    return
            self.i += 1


def _check_duplicate_columns(
    fields: list[dict[str, Any]],
    partition_cols: list[dict[str, Any]],
) -> None:
    """Hive normalises column names to lowercase, so ``Name``, ``name`` and
    ``NAME`` collide as a single identifier — and ``CREATE TABLE`` fails with
    "Duplicate column name". Mirror that behaviour: any case-insensitive
    duplicate (within data columns, within partitions, or across the two)
    raises ``ValueError`` so the caller knows to fix the source DDL rather
    than emit broken DML downstream.
    """
    seen: dict[str, str] = {}  # lowercase → first-seen original casing

    def _record(name: str, where: str) -> None:
        key = name.lower()
        if key in seen:
            prior = seen[key]
            if prior == name:
                raise ValueError(
                    f"Duplicate column name: {name!r} appears more than once."
                )
            raise ValueError(
                f"Duplicate column names after case normalization: "
                f"{prior!r} and {name!r} both collapse to {key!r} in Hive."
            )
        seen[key] = name

    for f in fields:
        _record(f["name"], "data")
    for f in partition_cols:
        _record(f["name"], "partition")


def _sanitize_identifier(name: str) -> str:
    """Hive permits backticked identifiers that DML can't accept verbatim
    (e.g. ``user-id``, ``@timestamp``, ``$amount``, Unicode names). Map
    those onto ASCII-safe identifiers so the resulting DML re-parses.

    Strategy:
      * Empty → ``_``.
      * ASCII alphanumeric or ``_`` → kept as-is.
      * Other ASCII (``-``, ``@``, ``#``, ``$``, ``.``, ``/`` …) → ``_``.
        Reads naturally for the common case (``user-id`` → ``user_id``).
      * Non-ASCII (``产品``, ``Café``…) → ``u<HEX>_`` per char, preserving
        uniqueness without state.
      * Digit-leading after the above → prefix with ``_``.

    Collisions (``a-b`` and ``a_b`` both → ``a_b``) are detected later by
    `_check_duplicate_columns`, which raises a clear error rather than
    silently emitting two fields with the same name.
    """
    if not name:
        return "_"
    out: list[str] = []
    for ch in name:
        if ch.isascii():
            if ch.isalnum() or ch == "_":
                out.append(ch)
            else:
                out.append("_")
        else:
            out.append(f"u{ord(ch):04x}_")
    sanitized = "".join(out)
    if sanitized[0].isdigit():
        sanitized = f"_{sanitized}"
    return sanitized


# Storage formats that read text and therefore care about the FIELDS
# TERMINATED BY delimiter. Anything else (PARQUET / ORC / AVRO and friends)
# is binary — DML output drops the per-string delimiter.
_TEXT_STORAGE_FORMATS = {None, "textfile", "sequencefile"}


def _attach_section_banners(fields: list[dict[str, Any]]) -> None:
    """Add a 'Basic Hive Types' banner above the first run of primitive
    columns, if such a run exists at the head of `fields`.

    Skipped when the table opens with a complex type (ARRAY/MAP/STRUCT) —
    in that case the banner would just attach to a single primitive in
    isolation, which looks worse than no banner.
    """
    if not fields:
        return
    first = fields[0]
    if first.get("type") == "struct" or first.get("array"):
        return
    # Only stamp the banner when at least one primitive precedes the first
    # complex column — otherwise it's redundant.
    has_complex_after = any(
        f.get("type") == "struct" or f.get("array") for f in fields[1:]
    )
    if not has_complex_after:
        return
    # Don't clobber an existing block_comment.
    if not first.get("block_comment"):
        first["block_comment"] = "Basic Hive Types"


def _stamp_delimiter(fields: list[dict[str, Any]], delim: str) -> None:
    """Set `delimiter` on every string field; numeric/temporal/struct fields
    use their natural type-arg form. The delimiter on a Hive table is the
    inter-field separator; for non-string columns it's implied by row format,
    for string columns it terminates the variable-length value.

    This matches the Hive→DML output style in real-dml.md Example 4 where
    ``customer_name`` becomes ``string("\\001") customer_name;`` while
    ``transaction_id`` stays ``integer(8) transaction_id;``.
    """
    for f in fields:
        t = f.get("type")
        if t == "struct":
            # Stamp recursively into struct children so nested string fields
            # also pick up the delimiter (matches the MAP<STRING,STRING> idiom
            # where each `key`/`value` becomes ``string("\\001")``).
            _stamp_delimiter(f.get("fields", []), delim)
            continue
        if t == "string":
            f["delimiter"] = delim
            # Keep `args` (VARCHAR/CHAR length) — emitter combines them into
            # `string("delim", N)`. STRING (no length) keeps args=[] so the
            # output is just `string("delim")`.


# ── public entry point ─────────────────────────────────────────────────────


def hive_ddl_to_dml(src: str) -> dict[str, Any]:
    """Parse Hive `CREATE TABLE` text and return ``{table_name, dml}``.

    Returns:
        ``{
            "table_name": str,
            "dml": str,            # the DML text
            "stored_as": str|None  # PARQUET / ORC / AVRO / TEXTFILE / ...
         }``
    """
    if not src or not src.strip():
        raise ValueError("Hive DDL is empty")

    # Detect CTAS / CREATE TABLE LIKE BEFORE tokenizing — these forms
    # commonly contain characters our tokenizer doesn't recognise (``*`` in
    # ``SELECT *``, arithmetic operators, etc.), which would surface as a
    # confusing "Unexpected character" error. Both forms have their own
    # parser-level check too; this entry-level check is a lower-level
    # fast-path that matches against the raw text.
    cleaned = _strip_comments(src)
    if _CTAS_RE.search(cleaned):
        raise ValueError(
            "CTAS (CREATE TABLE … AS SELECT …) is not supported — the "
            "schema is derived by running the SELECT against a live Hive "
            "metastore, which the converter has no access to. Run the "
            "CTAS in Hive, then `DESCRIBE EXTENDED <resulting_table>` and "
            "paste that DDL instead."
        )
    if _CT_LIKE_RE.search(cleaned):
        raise ValueError(
            "CREATE TABLE LIKE is not supported — provide a CREATE TABLE "
            "with an explicit column list. Run `DESCRIBE EXTENDED "
            "<other_table>` to get the schema and paste that DDL instead."
        )

    try:
        tokens = _tokenize(src)
    except ValueError as e:
        # Tokenizer hit a character it can't classify — usually means the
        # input isn't Hive DDL at all (e.g. plain prose, JSON, etc.).
        raise ValueError(
            f"Input does not appear to be valid Hive DDL ({e})"
        ) from e

    p = _Parser(tokens)
    name, schema = p.parse()

    stored_as = schema.pop("stored_as", None)
    dml = schema_to_dml(
        schema,
        header_comment=f"Generated from Hive Table: {name}",
    )

    result: dict[str, Any] = {
        "table_name": name,
        "dml": dml,
        "stored_as": stored_as,
    }
    if p.column_renames:
        # Lineage map: every Hive-only-legal identifier (backticked names
        # with ``-``, ``@``, ``#`` …) that we rewrote, alongside its DML
        # form. Useful for downstream debugging and reverse-mapping.
        result["column_renames"] = p.column_renames
    return result
