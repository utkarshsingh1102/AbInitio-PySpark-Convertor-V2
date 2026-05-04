"""Schema dict → Ab Initio DML text.

Inverse of `parse_dml_string`. Walks a schema dict (the structure produced
by [parse_dml_string](dml_parser.py)) and emits DML source text in the
brace-close style used by Ab Initio's `xml-to-dml`, `cobol-to-dml`, and
`hive-to-dml` utilities (see [real-dml.md](../../real-dml.md)).

The output is always parseable by `parse_dml_string`. Each converter
(`hive_to_dml`, `cobol_to_dml`, `xml_to_dml`) builds a schema dict and
calls `schema_to_dml(...)` to render the final text.

Conventions followed:

  * Top-level: ``record\n  ...\nend``  (no trailing semicolon)
  * Nested record: ``record\n  ...\n} name;``  (brace-close form)
  * Encoding prefix: ``utf8|ascii|ebcdic|packed`` before primitive type
  * Array marker: ``[N]`` fixed · ``[int]`` unbounded · ``[name]`` depending-on
  * Default value: ``string(1) newline = "\\n";``
  * Nullability: omitted when nullable; `` NOT NULL`` appended otherwise
  * Comments next to fields show the source-format origin when present
    (``/* PIC X(10) */``, ``/* BIGINT */``, ``/* xs:int */``).
"""
from __future__ import annotations

import re
from typing import Any

INDENT = "  "

# Storage-encoding prefixes the parser accepts at the head of a primitive.
# Stored on the field as ``encoding=<value>``.
_PREFIX_ENCODINGS = {"utf8", "ascii", "ebcdic", "packed"}


def schema_to_dml(
    schema: dict[str, Any],
    *,
    top_encoding: str | None = None,
    schema_name: str | None = None,
    header_comment: str | None = None,
) -> str:
    """Render a schema dict to DML text.

    `top_encoding`: optional ``utf8`` / ``ascii`` / ``ebcdic`` / ``packed``
    prefix to apply to the top-level ``record`` (used by xml-to-dml's
    `utf8 record` opener). Pass `None` to omit.

    `schema_name`: when set, the rendered DML wraps the record in a
    ``DEFINE name BEGIN … END`` block instead of the bare ``record … end``
    form. Useful for chaining the output through the DML Playground, which
    keys schemas by DEFINE name.

    `header_comment`: when set, emitted as ``/* <text> */`` on its own line
    above the ``record`` opener, with one blank line separating the two.
    Used by `hive_ddl_to_dml` to stamp the source table name on the output.
    """
    fields = schema.get("fields", [])
    body = "\n".join(_render_field(f, depth=1) for f in fields)
    # First field with a banner emits a leading blank line; strip it so the
    # banner sits directly under the `record` opener.
    body = body.lstrip("\n")

    if schema_name:
        return _align_trailing_comments(f"DEFINE {schema_name}\nBEGIN\n{body}\nEND\n")

    head = "record" if not top_encoding else f"{top_encoding} record"
    out = f"{head}\n{body}\nend\n"
    if header_comment:
        out = f"/* {header_comment} */\n\n{out}"
    return _align_trailing_comments(out)


# ── field rendering ────────────────────────────────────────────────────────


def _render_field(f: dict[str, Any], depth: int) -> str:
    """Render one field. Recurses for nested struct fields.

    Two comment slots are honoured:
      * ``block_comment`` — rendered as a separate line *above* the field.
        Used for section banners ("Basic Hive Types", "Partition columns",
        MAP/ARRAY origin notes).
      * ``origin_comment`` — rendered inline after the trailing semicolon,
        column-aligned across runs by `_align_trailing_comments`.

    A "banner-only" spacer (``_banner_only=True``) emits just the block
    comment on its own line — used to inject section headings without a
    real field.
    """
    indent = INDENT * depth

    parts: list[str] = []
    if f.get("block_comment"):
        # Leading blank visually separates the banner from the previous
        # field. The very first field's leading blank is stripped in
        # `schema_to_dml` so the record opener doesn't get an empty gap.
        parts.append("")
        parts.append(f"{indent}/* {f['block_comment']} */")

    if f.get("_banner_only"):
        return "\n".join(parts) if parts else ""

    inline = f.get("origin_comment")
    inline_str = f"  /* {inline} */" if inline else ""

    if f.get("type") == "struct":
        parts.append(_render_struct_field(f, depth, inline_str))
    else:
        parts.append(_render_primitive_field(f, indent, inline_str))

    return "\n".join(parts)


def _render_struct_field(f: dict[str, Any], depth: int, comment_str: str) -> str:
    """Render a nested record:

        record
          <inner fields>
        } name[N];
    """
    indent = INDENT * depth
    inner_lines = [_render_field(sf, depth + 1) for sf in f.get("fields", [])]
    inner = "\n".join(inner_lines)

    array_part = _render_array_marker(f)
    name = f["name"]

    # Brace-close form. Convention from real-dml.md:
    #   * Unbounded ``[int]`` markers go BEFORE the name (Hive MAP idiom):
    #         } [int] map_entries;
    #   * Depending-on ``[fieldname]`` and fixed-length ``[N]`` go AFTER:
    #         } projects[project_count];   } items[5];
    if array_part and _is_unbounded(f):
        close = f"{indent}}} {array_part} {name};"
    else:
        close = f"{indent}}} {name}{array_part};"

    # `record` opener line: same indent as close.
    open_line = f"{indent}record"
    return f"{open_line}{comment_str}\n{inner}\n{close}"


def _render_primitive_field(
    f: dict[str, Any],
    indent: str,
    comment_str: str,
) -> str:
    """Render a primitive (or array-of-primitive) field.

    Forms:
      ``ascii decimal(5,2) name NOT NULL = 0;``
      ``string(",")[int] tags;``
      ``string(1) newline = "\n";``
    """
    encoding = f.get("encoding")
    prefix = f"{encoding} " if encoding in _PREFIX_ENCODINGS else ""

    type_str = _render_primitive_type(f)
    array_part = _render_array_marker(f)
    name = f["name"]

    line = f"{indent}{prefix}{type_str}{array_part} {name}"

    # Default value: written as `= <literal>`. Strings need quoting + escaping.
    if "default" in f and f["default"] is not None:
        line += f" = {_render_default(f['default'])}"

    # Modifier: explicit NOT NULL when the field declared nullable=False.
    if f.get("nullable") is False:
        line += " NOT NULL"

    line += ";"
    if comment_str:
        line += comment_str
    return line


# ── type / args rendering ──────────────────────────────────────────────────


def _render_primitive_type(f: dict[str, Any]) -> str:
    """Build the ``type(args)`` string for a non-struct field.

    Special cases:
      * ``string`` with `delimiter` → ``string("delim")``
      * ``date`` / ``datetime`` with `format` → ``date("format")``
      * ``decimal`` with `decimal_format` → ``decimal("9999.99")``
      * Otherwise: ``type(arg, arg, ...)`` from ``args`` if present, else bare ``type``
    """
    t = f["type"]
    args = f.get("args") or []

    if t == "string":
        if f.get("delimiter") is not None:
            # When both delimiter and length are present (Hive VARCHAR/CHAR
            # with FIELDS TERMINATED BY), emit `string("delim", N)` — the
            # canonical Ab Initio form that preserves both pieces of info.
            if args:
                return f'string({_quote_string_arg(f["delimiter"])},{args[0]})'
            return f'string({_quote_string_arg(f["delimiter"])})'
        if args:
            return f"string({args[0]})"
        return "string"

    if t in ("date", "datetime", "timestamp"):
        if f.get("format"):
            return f'{t}({_quote_string_arg(f["format"])})'
        return t

    if t == "decimal":
        if f.get("decimal_format"):
            return f'decimal({_quote_string_arg(f["decimal_format"])})'
        if f.get("delimiter") is not None:
            return f'decimal({_quote_string_arg(f["delimiter"])})'
        if len(args) == 2:
            return f"decimal({args[0]},{args[1]})"
        if len(args) == 1:
            return f"decimal({args[0]})"
        return "decimal"

    if t == "integer":
        return f"integer({args[0]})" if args else "integer"

    if t == "binary":
        return f"binary({args[0]})" if args else "binary"

    if t == "float":
        return f"float({args[0]})" if args else "float"

    if t == "bytes":
        return f"bytes({args[0]})" if args else "bytes"

    # Plain primitives: long, double, boolean, timestamp, date, datetime
    return t


def _render_array_marker(f: dict[str, Any]) -> str:
    """Render ``[N]`` / ``[int]`` / ``[fieldname]``. Empty if not an array."""
    if not f.get("array"):
        return ""
    if f.get("depends_on"):
        return f"[{f['depends_on']}]"
    if f.get("array_length") is not None:
        return f"[{f['array_length']}]"
    # Unbounded vector marker. Multi-dim is rendered as repeated ``[int]``.
    dims = f.get("array_dims") or [None]
    return "".join(
        f"[{d}]" if d is not None else "[int]"
        for d in dims
    )


def _is_unbounded(f: dict[str, Any]) -> bool:
    """True for arrays with no fixed length and no depending-on reference."""
    return (
        bool(f.get("array"))
        and not f.get("depends_on")
        and f.get("array_length") is None
    )


# ── string / default escaping ──────────────────────────────────────────────


def _quote_string_arg(s: str) -> str:
    """Wrap ``s`` in double quotes, escaping in DML's convention.

    ``\\n`` `` \\t`` `` \\\\`` ``\\"`` `` \\0`` are escaped; every other
    control character is rendered as ``\\NNN`` octal so the output stays
    7-bit-safe (matters for Hive's ``\\001`` / SOH delimiter).
    """
    out: list[str] = ['"']
    for ch in s:
        if ch == "\\":
            out.append("\\\\")
        elif ch == '"':
            out.append('\\"')
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\t":
            out.append("\\t")
        elif ch == "\r":
            out.append("\\r")
        elif ch == "\0":
            out.append("\\0")
        elif ord(ch) < 0x20:
            out.append(f"\\{oct(ord(ch))[2:].zfill(3)}")
        else:
            out.append(ch)
    out.append('"')
    return "".join(out)


def _render_default(value: Any) -> str:
    """Render a default literal. Strings get quoted; numbers/idents bare."""
    if isinstance(value, str):
        return _quote_string_arg(value)
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return _quote_string_arg(str(value))


# ── post-render alignment ──────────────────────────────────────────────────

# A field line with a trailing /* ... */ comment. The first capture is the
# code (everything up to and including the terminating semicolon); the
# second is the comment block.
_TRAILING_COMMENT_RE = re.compile(r"^(?P<code>.*?;)\s+(?P<comment>/\*.*\*/)\s*$")


def _align_trailing_comments(text: str) -> str:
    """Pad inline trailing ``/* ... */`` comments to a consistent column.

    Operates on contiguous runs of commented lines — any non-commented line
    (including blanks and standalone block-comment banners) breaks the run
    and resets the alignment column. This way each section gets its own
    locally-tidy column, instead of one long line forcing every other row
    to balloon out.
    """
    lines = text.split("\n")
    out: list[str] = []
    run: list[tuple[int, str, str]] = []  # (line_index, code, comment)

    def flush() -> None:
        if not run:
            return
        target = max(len(code) for _, code, _ in run) + 2
        for idx, code, comment in run:
            out[idx] = f"{code}{' ' * (target - len(code))}{comment}"
        run.clear()

    for line in lines:
        out.append(line)
        m = _TRAILING_COMMENT_RE.match(line)
        if m:
            run.append((len(out) - 1, m.group("code"), m.group("comment")))
        else:
            flush()
    flush()

    return "\n".join(out)
