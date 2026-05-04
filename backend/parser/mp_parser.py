"""Ab Initio ``.mp`` graph parser (realistic dialect).

Handles the production Ab Initio XML form:

    <graph name="...">
        <parameters>
            <param name="X" value="..."/>
        </parameters>

        <component id="node_01" name="..." type="InputFile">
            <property name="filename" value="${X}"/>
            <port name="out" type="output"/>
        </component>

        <component id="node_05" name="..." type="Join">
            <port name="in_left"  type="input" source="node_03.out"/>
            <port name="in_right" type="input" source="node_04.out"/>
            <port name="out"      type="output"/>
        </component>

        <connections>
            <edge from="node_01" to="node_03"/>
        </connections>
    </graph>

Notes:
  - ``<parameters>`` is extracted up-front; ``${VAR}`` is interpolated into
    every property/attribute value before the result is returned.
  - Edges may be inferred from ``<port source="node_X.port"/>`` elements
    or listed explicitly in ``<connections>`` — both are supported.
  - Unescaped ``<`` / ``<=`` inside attribute values is pre-escaped before
    XML parsing (production .mp files often contain these).
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from . import params as P
from .preprocess import preprocess_mp
from .types import ParsedEdge, ParsedGraph, ParsedNode

# Component types we recognise. The plugin REGISTRY is the authoritative
# list; this constant is informational only.
KNOWN_TYPES = {
    "InputFile", "OutputFile", "LookupFile", "IntermediateFile",
    "Reformat", "Filter", "Sort", "SortWithinGroups",
    "DedupSorted", "Rollup", "Aggregate", "Scan",
    "Normalize", "DenormalizeSorted", "Join", "Lookup",
    "MatchSorted", "Replicate", "Gather", "Concatenate",
    "RunProgram", "Trash",
}


def parse_mp_string(xml: str, params_override: dict[str, str] | None = None) -> ParsedGraph:
    src = preprocess_mp(xml)
    root = ET.fromstring(src)
    if root.tag.lower() != "graph":
        raise ValueError(f"Expected root <graph>, got <{root.tag}>")

    pipeline_name = root.get("name") or "unnamed_pipeline"
    parameters = P.extract_params(root)
    if params_override:
        parameters.update(params_override)

    components = _find_components(root)
    nodes: list[ParsedNode] = []
    for c in components:
        nodes.append(_parse_component(c, parameters))

    edges = _collect_edges(root, nodes)

    graph = ParsedGraph(
        pipeline_name=pipeline_name,
        nodes=nodes,
        edges=edges,
        params=parameters,
    )
    return graph


def parse_mp_file(path: str | Path, params_override: dict[str, str] | None = None) -> ParsedGraph:
    return parse_mp_string(Path(path).read_text(), params_override=params_override)


# ── component / property extraction ───────────────────────────────────────


def _find_components(root: ET.Element) -> list[ET.Element]:
    """Collect <component> elements regardless of whether they are nested
    inside a <components> wrapper.
    """
    nested = root.find("components") or root.find("Components")
    if nested is not None:
        return list(nested.findall("component")) + list(nested.findall("Component"))
    return list(root.findall("component")) + list(root.findall("Component"))


def _parse_component(comp: ET.Element, parameters: dict[str, str]) -> ParsedNode:
    cid = comp.get("id")
    if not cid:
        raise ValueError("<component> requires an `id` attribute")
    name = comp.get("name") or cid
    ctype = comp.get("type") or ""

    properties: dict[str, str] = {}
    for prop in list(comp.findall("property")) + list(comp.findall("Property")):
        pname = prop.get("name")
        if not pname:
            continue
        if prop.get("value") is not None:
            properties[pname] = prop.get("value", "")
        else:
            properties[pname] = (prop.text or "").strip()
    # also accept the simpler <param name=..>text</param> form
    for prop in list(comp.findall("param")) + list(comp.findall("Param")):
        pname = prop.get("name")
        if not pname:
            continue
        properties[pname] = prop.get("value") or (prop.text or "").strip()

    properties = {k: P.interpolate(v, parameters) for k, v in properties.items()}

    input_ports: dict[str, tuple[str, str]] = {}
    output_ports: list[str] = []
    for port in list(comp.findall("port")) + list(comp.findall("Port")):
        pname = port.get("name") or ""
        ptype = (port.get("type") or "").lower()
        source = port.get("source")
        if ptype == "input":
            if source:
                # `source="node_03.out"` or just `node_03`
                if "." in source:
                    src_id, src_port = source.split(".", 1)
                else:
                    src_id, src_port = source, "out"
                input_ports[pname] = (src_id, src_port)
            else:
                input_ports[pname] = ("", "out")
        elif ptype == "output":
            output_ports.append(pname)

    return ParsedNode(
        id=cid,
        name=name,
        type=ctype,
        properties=properties,
        input_ports=input_ports,
        output_ports=output_ports or ["out"],
    )


def _collect_edges(root: ET.Element, nodes: list[ParsedNode]) -> list[ParsedEdge]:
    """Combine explicit <connections><edge/> with port-source-derived edges.
    Deduplicates on (from_id, to_id, from_port, to_port).
    """
    edges: list[ParsedEdge] = []
    # Dedupe by (from_id, to_id) — port-derived edges (with real port names)
    # take precedence over <connections> edges (which carry no port info).
    by_endpoints: dict[tuple[str, str], ParsedEdge] = {}

    # 1. Port-source-derived (richer — port names come along for free)
    for n in nodes:
        for to_port, (up_id, up_port) in n.input_ports.items():
            if up_id:
                e = ParsedEdge(up_id, n.id, up_port, to_port)
                by_endpoints[(e.from_id, e.to_id)] = e

    # 2. Explicit <connections>/<edges> — only add if not already covered.
    for tag in ("connections", "Connections", "edges", "Edges"):
        block = root.find(tag)
        if block is None:
            continue
        for e in list(block.findall("edge")) + list(block.findall("Edge")):
            f = e.get("from")
            t = e.get("to")
            if not f or not t:
                continue
            from_id = f.split(".")[0]
            to_id = t.split(".")[0]
            if (from_id, to_id) in by_endpoints:
                continue
            by_endpoints[(from_id, to_id)] = ParsedEdge(
                from_id=from_id,
                to_id=to_id,
                from_port=f.split(".")[1] if "." in f else "out",
                to_port=t.split(".")[1] if "." in t else "in",
            )

    edges.extend(by_endpoints.values())
    return edges
