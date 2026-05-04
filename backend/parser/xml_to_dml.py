"""XML / XSD → Ab Initio DML text.

Two parser paths share one entry point. `mode="auto"` sniffs the root
element: ``<xs:schema …>`` / ``<schema xmlns="…XMLSchema…">`` → XSD path,
anything else → sample-XML inference. Output style mirrors Ab Initio's
`xml-to-dml` utility — see [real-dml.md](../../real-dml.md) Examples 1 and 2.

**Sample XML inference** (used when the user pastes a real document):
  * Each element becomes a struct field.
  * Repeated sibling elements with the same tag → array (renders as ``[int]``
    unbounded marker).
  * Attributes become struct fields tagged with `annotations={"style": "attribute"}`.
  * Leaf text content → primitive type (decimal / decimal-with-scale / string).

**XSD parsing** (used when the user pastes the formal schema):
  * `xs:element name="X" type="xs:Y"` → primitive field, type from `xs:` map.
  * `xs:complexType` with `xs:sequence` → nested record.
  * `minOccurs="0"` → nullable; `maxOccurs="unbounded"` → array.
  * `xs:attribute` → field annotated with `style=attribute`.
  * `xs:simpleType` with `xs:restriction` + `totalDigits` / `fractionDigits`
    → `decimal(precision, scale)`.
  * Named complex types are inlined; the original name is recorded for
    future reference but doesn't change the emitted DML.

The top-level record always opens as ``utf8 record`` (matches xml-to-dml's
default and signals to downstream readers that the source is text).
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Any, Literal

from .dml_emitter import schema_to_dml

# ── module-level helpers ───────────────────────────────────────────────────


_NS_RE = re.compile(r"^\{[^}]+\}")
_INT_RE = re.compile(r"^-?\d+$")
_DEC_RE = re.compile(r"^-?\d+\.\d+$")


def _localname(tag: str) -> str:
    return _NS_RE.sub("", tag)


def _safe_name(n: str) -> str:
    """Make XML element/attribute names safe for DML / SQL identifiers."""
    return re.sub(r"[^A-Za-z0-9_]", "_", n)


# ── public entry point ─────────────────────────────────────────────────────


def xml_to_dml(
    src: str,
    mode: Literal["auto", "sample", "xsd"] = "auto",
) -> dict[str, Any]:
    """Convert XML or XSD text to DML.

    Returns:
        ``{"record_name": str, "dml": str, "mode": "sample"|"xsd"}``
    """
    if not src or not src.strip():
        raise ValueError("XML input is empty")
    try:
        root = ET.fromstring(src)
    except ET.ParseError as exc:
        raise ValueError(f"Malformed XML: {exc}") from exc

    if mode == "auto":
        mode = "xsd" if _localname(root.tag) == "schema" else "sample"

    if mode == "xsd":
        name, schema = _parse_xsd(root)
    else:
        name, schema = _parse_sample(root)

    # xml-to-dml's convention is to open with `utf8 record` so downstream
    # readers know the source is text-encoded UTF-8.
    dml = schema_to_dml(schema, top_encoding="utf8")
    return {"record_name": name, "dml": dml, "mode": mode}


# ── sample-XML inference ───────────────────────────────────────────────────


def _parse_sample(root: ET.Element) -> tuple[str, dict[str, Any]]:
    name = _safe_name(_localname(root.tag))
    fields = _sample_children_to_fields(root)
    # Root attributes also become fields (inserted at the front).
    for attr_name, attr_val in root.attrib.items():
        fields.insert(0, _make_attr_field(attr_name, attr_val))
    return name, {"type": "record", "fields": fields}


def _sample_children_to_fields(elem: ET.Element) -> list[dict[str, Any]]:
    """Collect children + attributes into a field list. Repeated siblings
    with the same tag collapse into a single array field.
    """
    fields: list[dict[str, Any]] = []
    seen: dict[str, list[ET.Element]] = {}
    for child in list(elem):
        seen.setdefault(_localname(child.tag), []).append(child)
    for tag, children in seen.items():
        is_array = len(children) > 1
        sample = children[0]
        fields.append(_sample_element_to_field(sample, tag, is_array))
    return fields


def _sample_element_to_field(
    elem: ET.Element,
    tag: str,
    is_array: bool,
) -> dict[str, Any]:
    name = _safe_name(tag)
    attribs = elem.attrib
    children = list(elem)

    if not children and not attribs:
        text = (elem.text or "").strip()
        return _primitive_field(name, text, is_array)

    # Compound element → struct, with optional inline attributes prepended.
    sub = _sample_children_to_fields(elem)
    for attr_name, attr_val in attribs.items():
        sub.insert(0, _make_attr_field(attr_name, attr_val))
    return {
        "name": name, "type": "struct", "fields": sub,
        "nullable": True, "array": is_array,
        "origin_comment": f"Mapping for the '{tag}' element",
    }


def _primitive_field(name: str, text: str, is_array: bool) -> dict[str, Any]:
    """Pick a primitive based on the leaf's text content. Arrays use the
    unbounded ``[int]`` marker."""
    base: dict[str, Any] = {
        "name": name, "nullable": True, "array": is_array,
        "origin_comment": f"Mapping for the '{name}' element",
    }
    # Default xml-to-dml uses `\0` as the field delimiter (NUL char) so that
    # the resulting DML is parseable by a delimited reader. Match that.
    if not text:
        return {**base, "type": "string", "args": [], "delimiter": "\0"}
    if _INT_RE.match(text):
        return {**base, "type": "decimal", "args": [], "delimiter": "\0"}
    if _DEC_RE.match(text):
        return {**base, "type": "decimal", "args": [], "delimiter": "\0"}
    return {**base, "type": "string", "args": [], "delimiter": "\0"}


def _make_attr_field(attr_name: str, attr_val: str) -> dict[str, Any]:
    """Translate an XML attribute into a flat DML field with a comment hint."""
    name = _safe_name(attr_name)
    if attr_val and _INT_RE.match(attr_val):
        t = "decimal"
    else:
        t = "string"
    return {
        "name": name, "type": t, "args": [],
        "delimiter": "\0",
        "nullable": True, "array": False,
        "annotations": {"style": "attribute"},
        "origin_comment": f"Mapping for the '{attr_name}' attribute",
    }


# ── XSD path ───────────────────────────────────────────────────────────────


_XSD_PRIMITIVE: dict[str, tuple[str, list[int]]] = {
    "string":   ("string", []),
    "normalizedString": ("string", []),
    "token":    ("string", []),
    "anyURI":   ("string", []),
    "ID":       ("string", []),
    "IDREF":    ("string", []),
    "QName":    ("string", []),
    "NCName":   ("string", []),
    "NMTOKEN":  ("string", []),
    "language": ("string", []),
    "base64Binary":  ("binary", []),
    "hexBinary":     ("binary", []),
    "boolean":   ("boolean", []),
    "byte":      ("integer", [1]),
    "short":     ("integer", [2]),
    "int":       ("integer", [4]),
    "integer":   ("integer", [4]),
    "long":      ("integer", [8]),
    "unsignedByte":  ("integer", [1]),
    "unsignedShort": ("integer", [2]),
    "unsignedInt":   ("integer", [4]),
    "unsignedLong":  ("integer", [8]),
    "decimal":   ("decimal", [38, 0]),
    "float":     ("float",   []),
    "double":    ("double",  []),
    "date":      ("date",     []),
    "dateTime":  ("datetime", []),
    "time":      ("string",   []),
    "duration":  ("string",   []),
}


def _parse_xsd(root: ET.Element) -> tuple[str, dict[str, Any]]:
    """Parse `<xs:schema>` and return ``(record_name, schema_dict)``."""
    types_by_name: dict[str, dict[str, Any]] = {}
    for child in root:
        tag = _localname(child.tag)
        if tag == "complexType" and child.get("name"):
            types_by_name[child.get("name")] = _xsd_complex(child, types_by_name)

    # Pick the first top-level <xs:element name=…> as the schema root.
    for child in root:
        if _localname(child.tag) != "element":
            continue
        name = child.get("name")
        if not name:
            continue
        field = _xsd_element(child, types_by_name)
        # Lift the field's struct body to the top-level schema if it's a
        # struct; otherwise wrap it.
        if field.get("type") == "struct":
            return _safe_name(name), {"type": "record", "fields": field["fields"]}
        return _safe_name(name), {"type": "record", "fields": [field]}

    raise ValueError("XSD has no top-level <xs:element name=...>")


def _xsd_element(elem: ET.Element, types_by_name: dict[str, dict[str, Any]]) -> dict[str, Any]:
    name = _safe_name(elem.get("name") or "")
    type_ref = elem.get("type")
    min_occ = elem.get("minOccurs", "1")
    max_occ = elem.get("maxOccurs", "1")
    is_array = max_occ == "unbounded" or (max_occ.isdigit() and int(max_occ) > 1)
    nullable = (min_occ == "0")

    if type_ref:
        body = _xsd_resolve(type_ref, types_by_name)
        out = {"name": name, **body, "nullable": nullable, "array": is_array}
        # Carry the type origin as a comment for human-readable DML.
        out["origin_comment"] = f"xs:{type_ref.split(':', 1)[-1]}"
        return out

    # Inline complexType
    for c in elem:
        if _localname(c.tag) == "complexType":
            body = _xsd_complex(c, types_by_name)
            return {"name": name, **body, "nullable": nullable, "array": is_array}
        if _localname(c.tag) == "simpleType":
            body = _xsd_simple(c)
            return {"name": name, **body, "nullable": nullable, "array": is_array}

    # No type info: fall back to string.
    return {
        "name": name, "type": "string", "args": [],
        "nullable": nullable, "array": is_array,
        "delimiter": "\0",
    }


def _xsd_complex(ct: ET.Element, types_by_name: dict[str, dict[str, Any]]) -> dict[str, Any]:
    fields: list[dict[str, Any]] = []
    for c in ct:
        if _localname(c.tag) == "attribute":
            fields.append(_xsd_attribute(c))
    for container in ct:
        if _localname(container.tag) in ("sequence", "all", "choice"):
            for sub in container:
                if _localname(sub.tag) == "element":
                    fields.append(_xsd_element(sub, types_by_name))
    return {"type": "struct", "fields": fields}


def _xsd_simple(st: ET.Element) -> dict[str, Any]:
    restriction = None
    for c in st:
        if _localname(c.tag) == "restriction":
            restriction = c
            break
    if restriction is None:
        return {"type": "string", "args": []}
    base = restriction.get("base", "")
    body = _xsd_primitive(base)
    facets = {_localname(c.tag): c for c in restriction}
    if body.get("type") == "decimal":
        total = facets.get("totalDigits")
        frac = facets.get("fractionDigits")
        precision = int(total.get("value")) if total is not None else 38
        scale = int(frac.get("value")) if frac is not None else 0
        body["args"] = [precision, scale]
    if body.get("type") == "string":
        length = facets.get("maxLength")
        if length is not None:
            body["args"] = [int(length.get("value"))]
    return body


def _xsd_attribute(attr: ET.Element) -> dict[str, Any]:
    name = _safe_name(attr.get("name") or "")
    type_ref = attr.get("type") or "xs:string"
    body = _xsd_primitive(type_ref)
    return {
        "name": name, **body,
        "nullable": attr.get("use") != "required",
        "array": False,
        "annotations": {"style": "attribute"},
        "origin_comment": f"@{attr.get('name')} attribute",
    }


def _xsd_primitive(type_ref: str) -> dict[str, Any]:
    local = type_ref.split(":", 1)[-1]
    if local in _XSD_PRIMITIVE:
        t, args = _XSD_PRIMITIVE[local]
        return {"type": t, "args": list(args)}
    return {"type": "string", "args": []}


def _xsd_resolve(type_ref: str, types_by_name: dict[str, dict[str, Any]]) -> dict[str, Any]:
    local = type_ref.split(":", 1)[-1]
    if local in _XSD_PRIMITIVE:
        t, args = _XSD_PRIMITIVE[local]
        return {"type": t, "args": list(args)}
    if local in types_by_name:
        return _deep_copy(types_by_name[local])
    return {"type": "string", "args": []}


def _deep_copy(d: dict[str, Any]) -> dict[str, Any]:
    out = dict(d)
    if "fields" in out and isinstance(out["fields"], list):
        out["fields"] = [_deep_copy(f) for f in out["fields"]]
    return out
