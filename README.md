# LegalHackathon_OpenJustice – plan-based execution of reasoning protocols

Legal Hackathon HSG 2026 · Challenge "Swiss Law, Swiss Model: Benchmarking Apertus with OpenJustice" · Sub-challenge 2.
Domain: Swiss tenancy law (Mietrecht), protocol built by our legal team members in OpenJustice.

## Question
OpenJustice runs a reasoning protocol node by node (one LLM step per node). Can an agent that reads the
**whole protocol up front, turns it into a plan and executes it in one request** give answers that are as good
and as faithful to the protocol, at lower cost?

## Conditions, same model (`publicai-apertus-70b`), same cases
| Engine | What it does | Endpoint |
|---|---|---|
| `direct` | case + standard instruction, no protocol (control) | `POST /agent/v1/responses` |
| `openjustice` | existing node-by-node engine (baseline) | `POST /reasoning-protocol/v1/responses` |
| `plan_based` | protocol → plan (code) → one agent request with JSON trace | `POST /agent/v1/responses` |
| `plan_based_rag` | as `plan_based`, plus uploaded law texts (read_file, file_search) and verbatim quotes | `POST /agent/v1/responses` |

## Companion, not judge (responsible design)
The tool orients tenants; it does not decide. Legal grounding stays in the protocol, only the framing changes.
Every engine answers in the same frame (`ojbench/companion.py`): Einschätzung · Sicherheit · ⚠ Fristen (never
softened) · Optionen · Nächste Schritte · Fehlende Angaben · Wann beraten lassen · Hinweis ("keine Rechtsberatung,
kein Entscheid"). For the OpenJustice baseline the frame must be written into the outcome nodes
(`docs/companion_outcome_template.md`), because that endpoint takes no instructions. Rationale: clear labelling as
orientation rather than official decision (Guitton/Tamò-Larrieux/Mayer: "simulation vs. real-world impact"),
no automated individual decision (Art. 22 GDPR / Art. 21 revFADP), and a preparatory, non-replacing role that
speaks for the Art. 6(3) exception from high-risk under the AI Act (to be argued, not assumed).

## How the plan-based engine works
1. **Fetch** the Protocol Graph (`GET /reasoning-protocols/{id}`), cached per version in `data/protocols/`.
2. **Distil** the plan *deterministically from the graph* (no LLM): sub-reasoning children before their parent,
   fact definitions as questions, switches as explicit IF/OTHERWISE rules with the real branch conditions,
   annotation sources attached to their steps. → no branch, test, exception or source can be lost
   (`plan_coverage` must be 100 %).
3. **Execute** with one agent request; a strict JSON schema forces a typed `value` for every step it worked on.
4. **Check fidelity in code:** switches are re-evaluated on the agent's own values, giving the path the protocol
   prescribes. We measure coverage, order, off-path work, whether the claimed outcome follows the protocol,
   and whether it matches the reference outcome.

## Metrics (per case, averaged per engine, dev and test reported separately)
- Quality 1–5: citation quality, factual accuracy, legal reasoning (hand scores in `scores/manual.csv`
  override the LLM judge; the judge uses a different model than the answers).
- Faithfulness: `coverage`, `order_score`, `off_path_steps`, `outcome_follows`, `outcome_correct`.
- Citations (no LLM): `articles exist` – cited articles checked against `data/law/*.txt` (Fedlex export);
  `quotes verified` – verbatim quotes checked server-side via `POST /file-library/citations/pinpoints`.
- Companion completeness: share of the mandatory sections present; flags decision-like language.
- Cost: LLM calls, input/output tokens, seconds (from the API's `usage`; `--exact-calls` reads Node Traces).

## Setup
Python ≥ 3.10, standard library only.
```bash
cp .env.example .env            # paste your key after OJ_API_KEY= (.env is loaded automatically)
python3 -m ojbench --mock run   # offline smoke test with fake API, no key needed
python3 -m ojbench models       # which model ids are allowed (look for Apertus)
python3 -m ojbench protocols    # find our protocol id
python3 -m ojbench fetch <id>   # cache the graph
python3 -m ojbench plan  <id>   # inspect the distilled plan
python3 -m ojbench upload data/law/OR.txt --code OR          # law text for plan_based_rag (see data/law/README.md)
python3 -m ojbench files                                     # indexed: True = ready
python3 -m ojbench run --split dev --judge-model claude-sonnet-5-5
python3 -m ojbench run --split dev --engines plan_based_rag
python3 -m ojbench run --split dev --model claude-sonnet-5-5 --engines direct   # frontier reference
python3 -m ojbench run --split test ...                                         # ONCE at the end
python3 -m ojbench playground prompts/example.txt   # direct Apertus via Public AI (PUBLICAI_API_KEY), dev/own examples only
```

## Data
- `data/cases/dev/*.json` – one case per file: `id, protocol_id, jurisdiction, legal_date, facts, question,
  expected_outcome` (outcome node id), `reference_analysis`. `dummy_001` only tests the pipeline.
- `data/cases/test/` – **git-ignored**: challenge rule, test cases never go to public repos or external AI services.
- `data/protocols/example_mietzins__v1.raw.json` – simplified example in the real API format (pipeline test only).
- `docs/openjustice_api.md` – the API parts we rely on.

## Open points to verify on day 1
- Base URL: `https://api.openjustice.ai` vs. `.../api` (`OJ_BASE_URL`).
- Direction of `sub_reasoning` edges (`SUB_EDGE_FROM_IS_PARENT` in `ojbench/protocol.py`).
- Whether Apertus is offered by `/reasoning-protocol/v1/models` **and** `/agent/v1/models` (same model on both = fair).
- Replace `RUBRIC` in `ojbench/judge.py` with the official evaluation matrix.
- Legal team: paste `docs/companion_outcome_template.md` into every outcome node.

## Interfaces
| Interface | Used for | Key |
|---|---|---|
| OpenJustice Protocol Graph / Responses / Agent | protocol, baseline, plan engines, judge | `OJ_API_KEY` |
| OpenJustice File Library + Pinpoints | law texts for RAG, verified quotes | `OJ_API_KEY` |
| Fedlex (manual export) | local article-existence check | – |
| Public AI (Apertus direct) | prompt experiments only, not the benchmark | `PUBLICAI_API_KEY` |
Later / outlook: entscheidsuche.ch (court decisions), BWO reference rate + BFS consumer price index for rent cases.

## Team contributions
| Member | Contribution |
|---|---|
| … | … |

## AI use statement
- Claude (Anthropic): scaffolding of the benchmark code and README structure; reviewed and adapted by the team.
- … (list every further use: tool, purpose, where)
