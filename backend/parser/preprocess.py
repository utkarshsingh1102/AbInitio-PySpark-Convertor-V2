"""Source-level preprocessors shared by the .mp / .dml / .xfr parsers."""
from __future__ import annotations

import re

# ── DML / XFR comment stripping ───────────────────────────────────────────


def strip_sql_comments(src: str) -> str:
    """Strip ``--`` line comments. Leaves block / // comments alone."""
    out: list[str] = []
    for line in src.splitlines(keepends=True):
        # Find `--` outside of any string literal — simple heuristic that is
        # fine for DML and XFR (neither has -- inside strings in practice).
        in_dq = False
        in_sq = False
        i = 0
        cut = -1
        while i < len(line):
            ch = line[i]
            if ch == '"' and not in_sq:
                in_dq = not in_dq
            elif ch == "'" and not in_dq:
                in_sq = not in_sq
            elif (
                ch == "-"
                and i + 1 < len(line)
                and line[i + 1] == "-"
                and not in_dq
                and not in_sq
            ):
                cut = i
                break
            i += 1
        if cut >= 0:
            out.append(line[:cut].rstrip() + "\n")
        else:
            out.append(line)
    return "".join(out)


# ── MP XML pre-sanitization ───────────────────────────────────────────────

# Match `attr="...<...>..."` where the value contains raw `<` or `<=`
# that would break XML parsing. Our strategy: find all attribute values
# (attr="...") and HTML-escape `<`, `>`, `&` inside them.
_ATTR_VAL_RE = re.compile(r'(\w[\w:.-]*)\s*=\s*"([^"]*)"')


def escape_mp_attr_values(src: str) -> str:
    """Escape literal `<`, `>`, `&` inside XML attribute values.

    Realistic Ab Initio `.mp` files often contain expressions like
    ``value="x <= ${THRESH}"`` which is invalid XML. We escape the value
    portion before the XML parser ever sees it.
    """
    def _escape(m: re.Match) -> str:
        attr, val = m.group(1), m.group(2)
        # Don't double-escape entities that are already encoded
        encoded = (
            val.replace("&", "&amp;")
               .replace("&amp;amp;", "&amp;")
               .replace("&amp;lt;", "&lt;")
               .replace("&amp;gt;", "&gt;")
               .replace("&amp;quot;", "&quot;")
               .replace("&amp;apos;", "&apos;")
               .replace("<", "&lt;")
               .replace(">", "&gt;")
        )
        return f'{attr}="{encoded}"'

    return _ATTR_VAL_RE.sub(_escape, src)


def preprocess_mp(src: str) -> str:
    """Apply all .mp preprocessing in order."""
    return escape_mp_attr_values(src)


_DEFINE_RE = re.compile(
    r"^\s*\#define\s+([A-Za-z_][A-Za-z0-9_]*)\s+(.+?)\s*$",
    re.MULTILINE,
)


def expand_c_macros(src: str) -> str:
    """Expand C-style ``#define NAME value`` directives.

    Each ``#define`` line is removed (replaced by a blank line so source line
    numbers are preserved), then every word-boundary occurrence of ``NAME``
    in the remaining body is replaced with ``value``. Definitions found
    later override earlier ones (last-wins, matching C semantics).
    """
    macros: dict[str, str] = {}

    def _capture(m: re.Match) -> str:
        macros[m.group(1)] = m.group(2)
        return ""

    body = _DEFINE_RE.sub(_capture, src)
    if not macros:
        return body
    # Substitute longest names first so that, e.g., ``LONG_DELIM`` is not
    # partially clobbered by a separate ``DELIM``.
    for name in sorted(macros, key=len, reverse=True):
        body = re.sub(rf"\b{re.escape(name)}\b", macros[name], body)
    return body


_UNRESOLVED_VAR_RE = re.compile(r"\$\{[A-Za-z_][A-Za-z0-9_]*\}")


def strip_unresolved_vars(src: str) -> str:
    """Drop any leftover ``${VAR}`` references — the tokenizer has no ``$``
    token, so an unresolved macro would crash parsing. Lenient mode: remove
    them silently.
    """
    return _UNRESOLVED_VAR_RE.sub("", src)


def preprocess_dml(src: str) -> str:
    src = strip_sql_comments(src)
    src = expand_c_macros(src)
    return src


def preprocess_xfr(src: str) -> str:
    return strip_sql_comments(src)
