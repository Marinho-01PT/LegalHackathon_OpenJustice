"""Protocol Graph -> internal Protocol, plus deterministic switch evaluation.

OpenJustice switches are NOT decided by an LLM: each branch edge carries conditions on the
values of earlier nodes (sourceNodeId, operator, compareValue). We evaluate them in code, so the
path an answer *must* take is computable from the node values -> strong fidelity checks.
"""
from __future__ import annotations

import json
from pathlib import Path

from .models import Condition, Edge, Node, Protocol
from .oj_client import OJClient

# TODO verify with the first real graph: does a `sub_reasoning` edge point parent -> child
# (from = parent) or child -> parent? The docs only say the child "runs first and feeds its parent".
SUB_EDGE_FROM_IS_PARENT = True


def _sources(annotations: list[dict]) -> list[str]:
    out = []
    for a in annotations or []:
        for s in a.get("sources", []):
            if not s.get("accessible"):
                continue
            if s["type"] == "excerpt":
                out.append(" ".join(x for x in [s.get("sourceTitle") or s.get("title"), s.get("pinpoint") or ""] if x))
            else:
                out.append(s.get("name", s["id"]))
        if a.get("text"):
            out.append(f"Note: {a['text']}")
    return out


def map_graph(g: dict) -> Protocol:
    nodes: dict[str, Node] = {}
    for n in g["nodes"]:
        nodes[n["id"]] = Node(
            id=n["id"], type=n["type"], label=n.get("label", n["id"]),
            question=n.get("question") or "", instructions=n.get("instructions") or "",
            data_type=n.get("dataType") or "", enum_values=n.get("customEnumValues") or [],
            fact_definitions=n.get("factDefinitions") or [], sources=_sources(n.get("annotations")),
            template=n.get("template") or "")
    edges: list[Edge] = []
    for e in g["edges"]:
        if e["kind"] == "branch":
            b = e["branch"]
            edges.append(Edge(e["from"], e["to"], "branch", is_default=b.get("isDefault", False),
                              branch_id=b.get("branchId", ""),
                              conditions=[Condition(c["sourceNodeId"], c["operator"], c["compareValue"],
                                                    c.get("conditionOperator", "AND")) for c in b.get("conditions", [])]))
        elif e["kind"] == "sub_reasoning":
            src, dst = (e["from"], e["to"]) if SUB_EDGE_FROM_IS_PARENT else (e["to"], e["from"])
            edges.append(Edge(src, dst, "sub"))
        else:
            edges.append(Edge(e["from"], e["to"], "next"))
    return Protocol(id=g["id"], name=g["name"], nodes=nodes, edges=edges,
                    start_ids=g["startNodeId"], version=g.get("version", 0))


def load_protocol(pid: str, client: OJClient | None = None, cache: str | Path = "data/protocols",
                  refresh: bool = False) -> Protocol:
    """Cached per id AND version, so every benchmark run is reproducible."""
    cache = Path(cache)
    files = sorted(cache.glob(f"{pid}__v*.json"), key=lambda f: f.stat().st_mtime)
    raws = [f for f in files if f.name.endswith(".raw.json")]
    if raws and not refresh:
        return map_graph(json.loads(raws[-1].read_text(encoding="utf-8")))
    if client is None:
        raise FileNotFoundError(f"protocol {pid} not cached and no client given")
    raw = client.protocol_graph(pid)
    proto = map_graph(raw)
    # keep the raw API answer (source of truth, versioned) + a readable plan next to it
    (cache / f"{pid}__v{proto.version}.raw.json").write_text(json.dumps(raw, indent=2, ensure_ascii=False), encoding="utf-8")
    return proto


# ------------------------------------------------------------------ switches
def _norm(v):
    if isinstance(v, str):
        s = v.strip().lower()
        if s in ("true", "yes", "ja", "oui"):
            return True
        if s in ("false", "no", "nein", "non"):
            return False
        try:
            return float(s)
        except ValueError:
            return s
    return v


def _cmp(value, op: str, target) -> bool | None:
    if value is None:
        return None
    a, b = _norm(value), _norm(target)
    try:
        return {"==": lambda: a == b, "!=": lambda: a != b, ">": lambda: a > b, ">=": lambda: a >= b,
                "<": lambda: a < b, "<=": lambda: a <= b,
                "contains": lambda: str(b) in str(a), "starts_with": lambda: str(a).startswith(str(b)),
                "ends_with": lambda: str(a).endswith(str(b))}[op]()
    except TypeError:
        return False


def evaluate_switch(protocol: Protocol, switch_id: str, values: dict) -> tuple[Edge | None, bool]:
    """Return (chosen branch edge, decidable). Undecidable = a needed value is missing."""
    default = None
    for e in protocol.branches(switch_id):
        if e.is_default:
            default = e
            continue
        result = None
        for i, c in enumerate(e.conditions):
            r = _cmp(values.get(c.source_node_id), c.operator, c.compare_value)
            if r is None:
                return None, False
            result = r if i == 0 else (result and r if c.join.upper() == "AND" else result or r)
        if result:
            return e, True
    return default, True


def render_condition(e: Edge) -> str:
    if e.is_default:
        return "OTHERWISE (default)"
    parts = []
    for i, c in enumerate(e.conditions):
        txt = f"value of [node_id={c.source_node_id}] {c.operator} {c.compare_value!r}"
        parts.append(txt if i == 0 else f"{c.join} {txt}")
    return "IF " + " ".join(parts)
