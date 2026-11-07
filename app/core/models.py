"""What the UI renders. One shape for both arms (with and without protocol)."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class Step:
    node_id: str
    kind: str                 # fact | reasoning | outcome
    label: str
    value: str = ""           # short value shown as a chip ("Ja", "Nein", "30 Tage")
    detail: str = ""          # full model output / rationale
    question: str = ""        # the node's question from the protocol
    nr_id: str = ""           # node_result id -> its Node Trace (exact LLM calls)
    response_id: str = ""     # Flow Response the node result belongs to


@dataclass
class Question:
    """A fact the protocol needs and could not find (pending_input)."""
    id: str
    label: str
    question: str
    data_type: str = "text"
    required: bool = False


@dataclass
class RunResult:
    mode: str                                   # protocol | direct
    answer: str = ""
    steps: list[Step] = field(default_factory=list)
    outcome_id: str | None = None
    outcome_label: str | None = None
    pending: list[Question] = field(default_factory=list)
    response_id: str | None = None
    status: str = "completed"                   # in_progress | completed | awaiting_input | failed
    execution_id: str | None = None
    usage: dict = field(default_factory=lambda: {"input_tokens": 0, "output_tokens": 0, "seconds": 0.0, "requests": 0})
    error: str | None = None

    @property
    def total_tokens(self) -> int:
        return self.usage.get("input_tokens", 0) + self.usage.get("output_tokens", 0)

    def to_dict(self) -> dict:
        return asdict(self)
