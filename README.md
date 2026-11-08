# ProtoLex – legal reasoning protocols on Switzerland's open model

Legal Hackathon HSG 2026 · Challenge **"Swiss Law, Swiss Model: Benchmarking Apertus with OpenJustice"** ·
**Sub-challenge 1** (build and benchmark reasoning flows).
First domain: **defects of the rented property (Mängel an der Mietsache, Art. 258 ff. OR)**.

> ProtoLex is a first point of orientation for legal questions: it shows people where they stand, what they can do,
> which deadlines apply – and when they should see a lawyer. It is **orientation, not legal advice and not a decision**.

## 1. Idea
Lawyers write their reasoning as a **reasoning protocol** in OpenJustice (issues, tests, exceptions, in the order a
practitioner applies them). Apertus, the open Swiss LLM, follows this protocol instead of answering freely.
Every further area of law is simply another protocol – one guide, many protocols.

Benchmark question (sub-challenge 1): **Does Apertus give better answers when it follows our protocol?**

## 2. Benchmark (sub-challenge 1)
| Condition | What runs | Endpoint |
|---|---|---|
| **A – Direct** | Apertus, case + standard instruction, no protocol | `POST /agent/v1/responses` |
| **B – Protocol** | Apertus following our OpenJustice protocol (node by node) | `POST /reasoning-protocol/v1/responses` |
| **C – Reference** (optional) | frontier model, no protocol – does Apertus + protocol reach it? | `POST /agent/v1/responses` |

Same model id for A and B: `publicai-apertus-70b` (offered by both endpoints).

- **Cases:** `data/cases/dev/` (used to develop the protocol) and `data/cases/test/` (held back, run once at the end).
- **Scoring:** OpenJustice evaluation matrix, 1–5 on citation quality, factual accuracy, legal reasoning.
  Hand scores by the legal team in `scores/manual.csv`; an LLM judge (different model) only as a cross-check.
- **Additional checks without an LLM:** cited articles exist (against the Fedlex text in `data/law/OR.txt`),
  outcome = reference outcome, tokens / time / cost per case.

### Results
*(fill in after the final run – dev and test separately)*

| Condition | n | Citation | Facts | Reasoning | Outcome correct | Articles exist | Ø tokens | Ø sec |
|---|---|---|---|---|---|---|---|---|
| A – Apertus direct | | | | | | | | |
| B – Apertus + protocol | | | | | | | | |
| C – Frontier direct | | | | | | | | |

### Annotated failures
*(2–3 cases: what went wrong, why, in which condition)*

## 3. The app (demo)
Streamlit app on top of OpenJustice. The protocol is built in the OpenJustice editor; the app only calls it.

- **Ask a question:** situation + question + canton → answer that follows the protocol, written in the language of
  the question (DE/FR/IT/EN).
- **Prüfpfad:** every protocol step the model went through, with its reasoning and the exact LLM calls per step.
- **Cited articles:** checked against the law text; ✓ exists / ✕ not found, linked to Fedlex.
- **Missing facts** are asked back to the user instead of guessed.
- **Next steps:** draft e-mail to the landlord (Apertus via Public AI); search for help nearby (conciliation authority,
  tenants' association, lawyers – only entries with a source URL are kept).
- **Scope note:** the sidebar shows what the selected protocol covers; outcomes labelled "ausserhalb / nicht
  anwendbar" are shown as "not covered" with a referral.
- The answer is cleaned up by the app (`app/core/answer_parse.py`, no LLM): no letter greetings, tables turned
  into lists, side notes removed.

## 4. Responsible design
- **Companion, not judge:** clearly labelled as orientation, not an official decision (Guitton/Tamò-Larrieux/Mayer:
  simulation vs. real-world impact). No automated individual decision in the sense of Art. 22 GDPR / Art. 21 revFADP.
- **Transparency and contestability:** the full Prüfpfad is visible; missing facts can be supplied and the run resumed.
- **Hallucination guards:** article existence check, sourced-only help entries, no invented facts in e-mail drafts
  (placeholders instead).
- **AI Act:** a preparatory tool that does not replace human assessment speaks for the Art. 6(3) exception from
  high-risk (Annex III) – to be argued, not assumed.
- **Data minimisation:** the help search sends only area of law and place, not the facts of the case.
- **Openness:** Apertus (open weights, training data and code; Apache 2.0), OpenJustice open infrastructure.

## 5. Setup
Python ≥ 3.10.
```bash
cp .env.example .env                      # add OJ_API_KEY (and optionally PUBLICAI_API_KEY); .env is git-ignored
python3 -m pip install --user -r requirements.txt
python3 -m streamlit run app/streamlit_app.py     # app; without OJ_API_KEY it runs in demo mode
```
Benchmark (`ojbench`, standard library only):
```bash
python3 -m ojbench models                         # model ids of both endpoints
python3 -m ojbench protocols                      # find the protocol id
python3 -m ojbench fetch <protocol_id>            # cache the protocol graph (data/protocols/)
python3 -m ojbench run --split dev  --engines direct openjustice
python3 -m ojbench run --split dev  --engines direct --model <frontier model>      # condition C
python3 -m ojbench run --split test --engines direct openjustice                   # ONCE at the end
```
Results land in `results/<run>/` (`summary.md`, one JSON per case). `python3 -m ojbench --mock …` runs offline.

| Variable (`.env`) | Purpose |
|---|---|
| `OJ_API_KEY` | OpenJustice API key (required for real runs) |
| `OJ_PROTOCOL_ID` | protocol preselected in the app |
| `OJ_MODEL` | model preselected in the app (empty = first Apertus model) |
| `PUBLICAI_API_KEY`, `PUBLICAI_MODEL` | Apertus via Public AI for the e-mail draft and `ojbench playground` |
| `APP_NAME`, `APP_SCOPE`, `APP_MOCK` | app name, scope text, offline demo |

## 6. Repository
| Path | Content |
|---|---|
| `app/core` | OpenJustice access, answer clean-up, source check, follow-up actions (no Streamlit) |
| `app/ui`, `app/views` | theme, components, sidebar; the "ask a question" page |
| `ojbench/` | benchmark CLI: engines (`direct`, `openjustice`), citation check, judge, cost logging |
| `data/law/OR.txt` | Art. 253–274g OR from Fedlex (version 1.10.2026), also uploaded to OpenJustice |
| `data/cases/` | benchmark cases (`test/` is git-ignored – challenge rule) |
| `docs/` | OpenJustice API notes, outcome template for the legal team |

`ojbench` also contains a plan-based engine (`plan_based`, `fidelity.py`) from an earlier sub-challenge-2 idea.
It is **not part of this submission**.

## 7. Team contributions
| Member | Background | Contribution |
|---|---|---|
| … | Law | protocol in OpenJustice, cases and reference analyses, scoring |
| … | Law | … |
| Linus Ihringer | CS | Streamlit app (UI, OpenJustice service, follow-up actions) |
| Bruno Marinho | CS | benchmark pipeline (`ojbench`), API integration, answer view, documentation |

## 8. AI use statement
- **Claude (Anthropic):** scaffolding of the benchmark code (`ojbench`), parts of the app (answer clean-up, language
  handling), README structure. All code reviewed and tested by the team.
- **Apertus (via OpenJustice / Public AI):** the model under test; also drafts e-mails and searches for help in the app.
- Cases, reference analyses and the reasoning protocol were written by the team **without** LLM use
  (challenge rule); LLM use for proofreading, if any: …
- *(add every further use: tool, purpose, where)*
