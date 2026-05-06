"""COBOL copybook → Ab Initio DML text.

Pipeline:

    Copybook text  →  schema dict  →  DML text
    └ line + PIC parser ┘  └ schema_to_dml ┘

Output mirrors Ab Initio's `cobol-to-dml` utility — see
[real-dml.md](../../real-dml.md) Example 3.

PIC clause translations:

    PIC X(n)              → string(n)         encoding=ascii
    PIC 9(n)              → ascii decimal(n)
    PIC S9(n)V99 COMP-3   → packed decimal(n+2,2)
    PIC 9(n) COMP         → integer (byte width inferred from n)

Modifiers:

    OCCURS n TIMES                      → array_length=n
    OCCURS m TO n DEPENDING ON field    → depends_on=<field>, max=n

Reserved (rejected with a clear error):
    REDEFINES          — needs a discriminator-column design
    66 / 88 levels     — RENAMES / condition-names
"""
from __future__ import annotations

import re
from typing import Any

from .dml_emitter import schema_to_dml

# ── line preprocessing ─────────────────────────────────────────────────────


def _strip_comments(src: str) -> list[str]:
    """Drop comment lines and return trimmed content lines.

    Comment forms:
      * Free-format ``*>`` at the start of a line.
      * Fixed-format with ``*`` or ``/`` in column 7 (when columns 1-6 are
        sequence digits or spaces).
    """
    out: list[str] = []
    for raw in src.splitlines():
        line = raw.rstrip()
        stripped = line.lstrip()
        if not stripped:
            continue
        if stripped.startswith("*>"):
            continue
        if len(line) >= 7 and line[6] in ("*", "/"):
            seq = line[:6]
            if all(c.isdigit() or c == " " for c in seq):
                continue
        out.append(stripped)
    return out


def _coalesce(lines: list[str]) -> list[str]:
    """Glue continuation lines together; split on the period terminator."""
    out: list[str] = []
    buf: list[str] = []
    for line in lines:
        buf.append(line.strip())
        if "." in line:
            joined = " ".join(buf).strip()
            for piece in re.split(r"\.\s*", joined):
                piece = piece.strip()
                if piece:
                    out.append(piece)
            buf = []
    if buf:
        joined = " ".join(buf).strip()
        if joined:
            out.append(joined)
    return out


# ── PIC clause translator ──────────────────────────────────────────────────


def _expand_pic(pic: str) -> str:
    """`X(5)` → `XXXXX`, `9(3)V99` → `999V99`."""
    def repl(m: re.Match[str]) -> str:
        return m.group(1) * int(m.group(2))
    return re.sub(r"([X9SAVZP])\((\d+)\)", repl, pic, flags=re.IGNORECASE)


def _pic_to_field(pic_raw: str, comps: list[str]) -> dict[str, Any]:
    """Translate PIC + USAGE/COMP modifiers to a partial field dict."""
    pic = _expand_pic(pic_raw.upper().strip())
    cu = [c.upper() for c in comps]
    is_packed = any(c in ("COMP-3", "COMPUTATIONAL-3", "PACKED-DECIMAL") for c in cu)
    is_binary = any(c in ("COMP", "COMPUTATIONAL", "COMP-4", "COMP-5", "BINARY") for c in cu)
    is_ebcdic = any("EBCDIC" in c for c in cu)

    # Alphanumeric: PIC X / A
    if "X" in pic or "A" in pic:
        n = sum(1 for c in pic if c in ("X", "A"))
        return {
            "type": "string", "args": [n],
            "encoding": "ebcdic" if is_ebcdic else "ascii",
            "origin_comment": f"PIC {pic_raw}",
        }

    digits = pic.count("9")
    has_v = "V" in pic
    has_s = pic.startswith("S")
    after_v = pic.split("V", 1)[1] if has_v else ""
    scale = sum(1 for c in after_v if c == "9")

    if not digits:
        return {
            "type": "string", "args": [0],
            "encoding": "ebcdic" if is_ebcdic else "ascii",
            "origin_comment": f"PIC {pic_raw}",
        }

    if is_packed:
        return {
            "type": "decimal", "args": [digits, scale],
            "encoding": "packed",
            "origin_comment": f"PIC {pic_raw} COMP-3",
        }
    if is_binary:
        if scale > 0:
            return {
                "type": "decimal", "args": [digits, scale],
                "encoding": "ebcdic" if is_ebcdic else "ascii",
                "origin_comment": f"PIC {pic_raw} COMP",
            }
        if digits <= 4:
            width = 2
        elif digits <= 9:
            width = 4
        else:
            width = 8
        return {
            "type": "integer", "args": [width],
            "origin_comment": f"PIC {pic_raw} COMP",
        }

    # Default DISPLAY (zoned).
    return {
        "type": "decimal", "args": [digits, scale],
        "encoding": "ebcdic" if is_ebcdic else "ascii",
        "origin_comment": f"PIC {pic_raw}",
    }


# ── data item parsing ─────────────────────────────────────────────────────


_LEVEL_RE = re.compile(r"^(\d{1,2})\s+(\S+)\s*(.*)$")


def _parse_item(stmt: str) -> dict[str, Any] | None:
    """Parse a single data item (one period-terminated statement)."""
    stmt = stmt.strip()
    if not stmt:
        return None

    upper = stmt.upper()
    if " REDEFINES " in upper:
        raise ValueError(
            "COBOL REDEFINES is not supported — it needs a discriminator-"
            "column design we haven't implemented."
        )
    if upper.startswith("66 ") or upper.startswith("88 "):
        raise ValueError(
            f"COBOL level-{upper[:2]} items (RENAMES / condition-names) are "
            "not supported."
        )

    m = _LEVEL_RE.match(stmt)
    if not m:
        return None

    level = int(m.group(1))
    name = m.group(2).rstrip(".")
    rest = m.group(3).strip()
    item: dict[str, Any] = {
        "level": level, "name": name, "is_group": False,
        "occurs": None, "occurs_depending_on": None,
    }

    if not rest:
        item["is_group"] = True
        return item

    # OCCURS clause
    occurs_m = re.search(
        r"OCCURS\s+(\d+)(?:\s+TO\s+(\d+))?\s+TIMES"
        r"(?:\s+DEPENDING\s+ON\s+([A-Za-z][\w-]*))?",
        rest, re.IGNORECASE,
    )
    if occurs_m:
        item["occurs"] = int(occurs_m.group(2) or occurs_m.group(1))
        if occurs_m.group(3):
            item["occurs_depending_on"] = occurs_m.group(3)
        rest = re.sub(
            r"OCCURS\s+\d+(?:\s+TO\s+\d+)?\s+TIMES"
            r"(?:\s+DEPENDING\s+ON\s+[A-Za-z][\w-]*)?",
            "", rest, flags=re.IGNORECASE,
        ).strip()

    # PIC clause
    pic_m = re.search(
        r"PIC(?:TURE)?(?:\s+IS)?\s+([0-9XSAVZP\.()/+\-]+)",
        rest, re.IGNORECASE,
    )
    if pic_m:
        pic_raw = pic_m.group(1)
        rest_after = (rest[:pic_m.start()] + rest[pic_m.end():]).strip()
        comps = re.findall(
            r"\b(COMP(?:UTATIONAL)?(?:-[1-5])?|PACKED-DECIMAL|BINARY|DISPLAY|EBCDIC)\b",
            rest_after, re.IGNORECASE,
        )
        item.update(_pic_to_field(pic_raw, comps))
    else:
        # Differentiate "no PIC clause at all (group item)" from "PIC keyword
        # is present but the class characters are invalid (e.g. PIC Q(5))" —
        # the latter must raise rather than silently degrade to an empty
        # group item, which produced broken `record { } name;` DML.
        bad_pic_m = re.search(r"\bPIC(?:TURE)?\b", rest, re.IGNORECASE)
        if bad_pic_m:
            after = rest[bad_pic_m.end():].strip()
            after = re.sub(r"^IS\s+", "", after, flags=re.IGNORECASE)
            bad_value = after.split()[0] if after else "<empty>"
            raise ValueError(
                f"Unsupported PIC clause {bad_value!r} for field {name!r}. "
                f"Valid PIC characters are 9 X A S V Z P (with optional "
                f"parens for repetition, e.g. X(20), S9(5)V99)."
            )
        item["is_group"] = True
    return item


# ── tree builder ──────────────────────────────────────────────────────────


def _normalize(name: str) -> str:
    return name.lower().replace("-", "_")


def _check_duplicate_field_names(
    fields: list[dict[str, Any]], path: str = "",
) -> None:
    """Reject duplicate field names at any single nesting level.

    COBOL data items inside one record (one struct in the schema dict) must
    have unique names — so two ``05 A PIC X(10).`` lines in the same record
    is invalid input. Catching this here prevents emitting broken DML with
    two fields of the same name.

    Cross-level reuse (``05 OUTER. 10 A …`` and ``05 A …`` at the same
    record's children) is fine and not flagged — those are separate scopes.
    """
    seen: dict[str, str] = {}
    for f in fields:
        key = f["name"].lower()
        if key in seen:
            scope = f" in {path!r}" if path else ""
            raise ValueError(
                f"Duplicate field name {f['name']!r}{scope} — "
                f"COBOL data items at the same level must have unique names."
            )
        seen[key] = f["name"]
        if f.get("type") == "struct":
            child_path = f"{path}.{f['name']}" if path else f["name"]
            _check_duplicate_field_names(f.get("fields", []), child_path)


def _build_tree(items: list[dict[str, Any]]) -> tuple[str, dict[str, Any]]:
    """Return ``(record_name, schema_dict)`` for the first level-01 record."""
    for top_idx, item in enumerate(items):
        if item["level"] != 1:
            continue
        end = len(items)
        for j in range(top_idx + 1, len(items)):
            if items[j]["level"] == 1:
                end = j
                break
        head = items[top_idx]
        fields = _children(items[top_idx:end], parent_idx=0)
        return _normalize(head["name"]), {"type": "record", "fields": fields}
    raise ValueError("No level-01 record found in the copybook")


def _children(items: list[dict[str, Any]], parent_idx: int) -> list[dict[str, Any]]:
    parent_level = items[parent_idx]["level"]
    children_level: int | None = None
    end = len(items)
    for i in range(parent_idx + 1, len(items)):
        lvl = items[i]["level"]
        if lvl <= parent_level:
            end = i
            break
        if children_level is None or lvl < children_level:
            children_level = lvl
    if children_level is None:
        return []
    out: list[dict[str, Any]] = []
    i = parent_idx + 1
    while i < end:
        if items[i]["level"] == children_level:
            out.append(_field_from_item(items, i, end))
        i += 1
    return out


def _field_from_item(items: list[dict[str, Any]], idx: int, end: int) -> dict[str, Any]:
    it = items[idx]
    name = _normalize(it["name"])
    occurs = it.get("occurs")
    depends = it.get("occurs_depending_on")

    if it.get("is_group"):
        my_end = end
        for j in range(idx + 1, end):
            if items[j]["level"] <= it["level"]:
                my_end = j
                break
        sub = _children(items[:my_end], parent_idx=idx)
        out: dict[str, Any] = {
            "name": name, "type": "struct", "fields": sub,
            "nullable": True, "array": occurs is not None,
        }
        if occurs is not None and not depends:
            out["array_length"] = occurs
        if depends:
            out["depends_on"] = _normalize(depends)
        return out

    out = {
        "name": name, "type": it["type"], "args": it.get("args", []),
        "nullable": True, "array": occurs is not None,
    }
    if occurs is not None and not depends:
        out["array_length"] = occurs
    if depends:
        out["depends_on"] = _normalize(depends)
    enc = it.get("encoding")
    if enc:
        out["encoding"] = enc
    if it.get("origin_comment"):
        out["origin_comment"] = it["origin_comment"]
    return out


# ── public entry point ─────────────────────────────────────────────────────


def cobol_copybook_to_dml(src: str) -> dict[str, Any]:
    """Translate a copybook to DML.

    Returns:
        ``{"record_name": str, "dml": str}``
    """
    if not src or not src.strip():
        raise ValueError("Copybook is empty")

    lines = _strip_comments(src)
    statements = _coalesce(lines)
    items: list[dict[str, Any]] = []
    for stmt in statements:
        item = _parse_item(stmt)
        if item is not None:
            items.append(item)
    if not items:
        raise ValueError("No COBOL data items found")

    name, schema = _build_tree(items)
    # Reject same-level duplicate field names (recursively into structs).
    _check_duplicate_field_names(schema["fields"], path=name)
    dml = schema_to_dml(schema)
    return {"record_name": name, "dml": dml}
