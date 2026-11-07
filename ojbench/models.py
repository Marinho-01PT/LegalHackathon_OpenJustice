"""Internal data model, mirroring OpenJustice's Protocol Graph (GET /reasoning-protocols/{id})."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class Node:
    id: str
    type: str                       # start | fact | reasoning | switch | outcome
    label: str
    question: str = ""
    instructions: str = ""
    data_type: str = ""             # text | number | boolean | custom | ...
    enum_values: list[str] = field(default_factory=list)
    fact_definitions: list[dict] = field(default_factory=list)   # fact nodes
    sources: list[str] = field(default_factory=list)             # annotation sources, rendered as text
    template: str = ""              # outcome nodes


@dataclass
class Condition:
    source_node_id: str
    operator: str                   # == != > >= < <= contains starts_with ends_with
    compare_value: object
    join: str = "AND"               # how this condition joins the previous one


@dataclass
class Edge:
    src: str
    dst: str
    kind: str                       # next | branch | sub
    conditions: list[Condition] = field(default_factory=list)
    is_default: bool = False
    branch_id: str = ""


@dataclass
class Protocol:
    id: str
    name: str
    nodes: dict[str, Node]
    edges: list[Edge]
    start_ids: list[str]
    version: int | float = 0

    def out(self, nid: str, kind: str | None = None) -> list[Edge]:
        return [e for e in self.edges if e.src == nid and (kind is None or e.kind == kind)]

    def next(self, nid: str) -> Node | None:
        n = self.out(nid, "next")
        return self.nodes[n[0].dst] if n else None

    def subs(self, nid: str) -> list[Node]:
        return [self.nodes[e.dst] for e in self.out(nid, "sub")]

    def branches(self, nid: str) -> list[Edge]:
        return self.out(nid, "branch")

    def start(self) -> Node:
        return self.nodes[self.start_ids[0]]

    # --- cache format (plain JSON, versionable in git) -------------------
    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, ensure_ascii=False)

    @staticmethod
    def from_json(path: str | Path) -> "Protocol":
        d = json.loads(Path(path).read_text(encoding="utf-8"))
        return Protocol(
            id=d["id"], name=d["name"], version=d.get("version", 0), start_ids=d["start_ids"],
            nodes={k: Node(**v) for k, v in d["nodes"].items()},
            edges=[Edge(**{**e, "conditions": [Condition(**c) for c in e.get("conditions", [])]}) for e in d["edges"]],
        )


@dataclass
class Case:
    id: str
    facts: str
    question: str
    protocol_id: str
    jurisdiction: str = "CH"
    legal_date: str = ""
    expected_outcome: str | None = None      # outcome node id (or label) of the reference analysis
    reference_analysis: str = ""

    @staticmethod
    def from_json(path: str | Path) -> "Case":
        return Case(**json.loads(Path(path).read_text(encoding="utf-8")))

    def prompt_block(self) -> str:
        return (f"Jurisdiction: {self.jurisdiction}\nLegal date: {self.legal_date}\n\n"
                f"FACTS:\n{self.facts}\n\nQUESTION:\n{self.question}")


@dataclass
class TraceStep:
    node_id: str
    value: object = None            # typed value of the node (drives switches)
    finding: str = ""
    sources: list[str] = field(default_factory=list)


@dataclass
class EngineResult:
    """Common output of every engine -> identical fidelity, scoring and cost measurement."""
    engine: str
    case_id: str
    model: str
    answer: str
    trace: list[TraceStep]
    outcome_node_id: str | None
    follow_up_questions: list[str] = field(default_factory=list)
    usage: dict = field(default_factory=dict)    # llm_calls, input_tokens, output_tokens, total_tokens, seconds
    raw_ids: list[str] = field(default_factory=list)   # OpenJustice response ids, for audit
    error: str | None = None
    quotes: list[dict] = field(default_factory=list)   # verbatim law quotes [{file_id, quote}] (RAG engine)

    def values(self) -> dict:
        return {t.node_id: t.value for t in self.trace}

    def to_dict(self) -> dict:
        return asdict(self)
