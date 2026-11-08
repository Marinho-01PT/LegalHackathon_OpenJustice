# ProtoLex – legal reasoning protocols on Switzerland's open model

Legal Hackathon HSG 2026 · Challenge **"Swiss Law, Swiss Model: Benchmarking Apertus with OpenJustice"** ·
**Sub-challenge 1** (build and benchmark reasoning flows).
Domain: **Swiss tenancy law** – three reasoning protocols built by our legal team in OpenJustice (see below).

> ProtoLex is a first point of orientation for legal questions: it shows people where they stand, what they can do,
> which deadlines apply – and when they should see a lawyer. It is **orientation, not legal advice and not a decision**.

## 1. Idea
Lawyers write their reasoning as a **reasoning protocol** in OpenJustice (issues, tests, exceptions, in the order a
practitioner applies them). Apertus, the open Swiss LLM, follows this protocol instead of answering freely.
Every further area of law is simply another protocol – one guide, many protocols.

Benchmark question (sub-challenge 1): **Does Apertus give better answers when it follows our protocol?**

## 2. Our reasoning protocols
Built by our legal team in the OpenJustice editor (no code) and shared publicly:

| Protocol | Topic | Link |
|---|---|---|
| **Mängel Wohnung** | defects of the rented apartment: is it a defect, who is responsible, how serious – and which remedies the tenant has (repair, rent reduction, rent deposit, damages, termination) | [open in OpenJustice](https://openjustice.ai/shared/reasoning-protocol/85d311cc-1d43-45eb-b5e2-46f069ae2605) |
| **Eigenbedarf** | termination of the lease by the landlord for own use | [open in OpenJustice](https://openjustice.ai/shared/reasoning-protocol/5f3c6382-f3cb-4efd-9447-cf64ad00ebf9) |
| **Various Remedy Protocol** | remedies across various tenancy situations | [open in OpenJustice](https://openjustice.ai/shared/reasoning-protocol/df668251-7486-487c-9c2b-56158f8f7088) |

The app lists every protocol the API key can access; a new area of law = a new protocol, no code change.
Iteration example: a first defects protocol with 31 nodes took about 4 minutes per answer; the focused version with
12 nodes takes about 2 minutes.

## 3. What ProtoLex can do – and what it cannot
**ProtoLex can**
- give a first, structured assessment of a tenancy question along a protocol written by lawyers;
- show every reasoning step (Prüfpfad) and the exact LLM calls behind it;
- check whether the cited articles exist in the law text and link them to Fedlex;
- ask back when key facts are missing instead of guessing;
- answer in the language of the question (German, French, Italian, English);
- suggest next steps: draft an e-mail to the landlord, find conciliation authorities, tenants' associations and
  lawyers nearby (only entries with a source);
- tell the user when a question lies outside the selected protocol.

**ProtoLex cannot**
- give legal advice or make a binding decision – it is orientation; only the conciliation authority or a court decides;
- answer questions outside its protocols reliably (other areas of law, other tenancy topics);
- guarantee that the model follows the protocol perfectly or that every statement is correct – the reasoning path
  makes this checkable, not certain;
- verify the content of a citation – the check confirms that an article exists, not that it supports the statement;
- know cantonal practice, current court decisions or individual contract clauses unless the user provides them;
- calculate deadlines or amounts (e.g. a rent reduction in CHF) bindingly;
- send anything on its own – e-mail drafts must be checked and sent by the user;
- answer instantly – a protocol run takes about 2 minutes, because every node is a separate model call.

## 4. Benchmark (sub-challenge 1)
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

Results and annotated failures are presented in the pitch.

## 5. The app (demo)
Streamlit app on top of OpenJustice. The protocols are built in the OpenJustice editor; the app only calls them.

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

## 6. Responsible design
- **Companion, not judge:** clearly labelled as orientation, not an official decision (Guitton/Tamò-Larrieux/Mayer:
  simulation vs. real-world impact). No automated individual decision in the sense of Art. 22 GDPR / Art. 21 revFADP.
- **Transparency and contestability:** the full Prüfpfad is visible; missing facts can be supplied and the run resumed.
- **Hallucination guards:** article existence check, sourced-only help entries, no invented facts in e-mail drafts
  (placeholders instead).
- **AI Act:** a preparatory tool that does not replace human assessment speaks for the Art. 6(3) exception from
  high-risk (Annex III) – to be argued, not assumed.
- **Data minimisation:** the help search sends only area of law and place, not the facts of the case.
- **Openness:** Apertus (open weights, training data and code; Apache 2.0), OpenJustice open infrastructure.

## 7. Setup
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

## 8. Repository
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

## 9. Team contributions
| Member | Background | Contribution |
|---|---|---|
| Nicolas Rohner | Law | protocol in OpenJustice, cases and reference analyses, scoring |
| Artem Deych | Law | protocol in OpenJustice, cases and reference analyses, scoring |
| Linus Ihringer | CS | Streamlit app (UI, OpenJustice service, follow-up actions) |
| Bruno Marinho | CS | benchmark pipeline (`ojbench`), API integration, answer view, documentation |

## 10. AI use statement
- **Claude (Anthropic):** scaffolding of the benchmark code (`ojbench`), parts of the app (answer clean-up, language
  handling), README structure. All code reviewed and tested by the team.
- **Apertus (via OpenJustice / Public AI):** the model under test; also drafts e-mails and searches for help in the app.
- Cases, reference analyses and the reasoning protocol were written by the team **without** LLM use
  (challenge rule).
