"""Deterministic faithfulness metrics (no LLM).

From the node values an engine reports we recompute, in code, the path the protocol prescribes
(switches evaluated on their real conditions). Then:
- coverage          share of nodes on that prescribed path that the engine actually worked on
- order_score       share of step pairs in protocol order
- off_path_steps    steps from branches the protocol did NOT take (wasted / confused work)
- outcome_follows   the engine's outcome == the outcome the protocol dictates for its own values
- outcome_correct   prescribed outcome == the case's reference outcome
- undecidable       a switch could not be evaluated because a value was missing
Engines without a trace (direct) get None for the path metrics.
"""
from __future__ import annotations

from .models import Case, EngineResult, Protocol
from .protocol import evaluate_switch


def prescribed_path(p: Protocol, values: dict) -> tuple[list[str], str | None, bool]:
    order: list[str] = []
    nid = p.start().id
    for _ in range(1000):
        n = p.nodes[nid]
        if n.type in ("fact", "reasoning"):
            order += [c.id for c in p.subs(n.id)] + [n.id]
        if n.type == "switch":
            edge, decidable = evaluate_switch(p, n.id, values)
            if not decidable or edge is None:
                return order, None, not decidable
            nid = edge.dst
            continue
        if n.type == "outcome":
            return order, n.id, False
        nxt = p.next(n.id)
        if nxt is None:
            return order, None, False
        nid = nxt.id
    return order, None, False


def _matches(p: Protocol, outcome: str | None, expected: str | None) -> bool:
    if not outcome or not expected:
        return False
    return outcome == expected or p.nodes.get(outcome) is not None and p.nodes[outcome].label.lower() == expected.lower()


def fidelity(p: Protocol, r: EngineResult, case: Case | None = None) -> dict:
    if not r.trace:
        return {"coverage": None, "order_score": None, "off_path_steps": None, "outcome_follows": None,
                "undecidable": None, "outcome_correct": None if not case else (_matches(p, r.outcome_node_id, case.expected_outcome) if r.outcome_node_id else None)}
    required, prescribed, undecidable = prescribed_path(p, r.values())
    seen = [t.node_id for t in r.trace]
    pos = {n: i for i, n in enumerate(required)}
    on = [n for n in seen if n in pos]
    pairs = [(a, b) for i, a in enumerate(on) for b in on[i + 1:]]
    return {
        "coverage": round(sum(1 for n in required if n in seen) / max(len(required), 1), 3),
        "missing_nodes": [n for n in required if n not in seen],
        "order_score": round(sum(pos[a] < pos[b] for a, b in pairs) / len(pairs), 3) if pairs else 1.0,
        "off_path_steps": sorted(set(seen) - set(required)),
        "prescribed_outcome": prescribed,
        "outcome_follows": (r.outcome_node_id == prescribed) if prescribed else None,
        "undecidable": undecidable,
        "outcome_correct": _matches(p, prescribed or r.outcome_node_id, case.expected_outcome) if case and case.expected_outcome else None,
    }
