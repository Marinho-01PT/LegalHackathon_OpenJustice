"""Command line:  python3 -m ojbench <command>      (add --mock to use the offline fake API)

  models                         models of the protocol engine and the agent endpoint
  protocols                      list protocols you can run
  fetch  <protocol_id>           download + cache the Protocol Graph (data/protocols/)
  plan   <protocol_id>           print the distilled plan + coverage check
  files                          list uploaded files + indexing status
  upload <file> [--code OR]      upload a law text to OpenJustice (for plan_based_rag + quote checks)
  playground <prompt.txt>        send a prompt directly to Apertus via Public AI (prompt experiments)
  run    --split dev|test        run engines on cases, write results/<run>/ and summary.md
"""
from __future__ import annotations

import argparse
import json
import os
import statistics as st
import time
from pathlib import Path

from .citations import build_index, exists_check, law_files, verify_quotes
from .companion import companion_check
from .engines.direct import DirectEngine
from .engines.openjustice import OpenJusticeEngine
from .engines.plan_based import PlanBasedEngine, distill_plan, plan_coverage
from .fidelity import fidelity
from .judge import DIMS, llm_judge, manual_scores
from .models import Case
from .oj_client import OJClient
from .protocol import load_protocol

ENGINES = ("direct", "openjustice", "plan_based", "plan_based_rag")
DEFAULT_ENGINES = ("direct", "openjustice", "plan_based")


def load_dotenv(path: str = ".env") -> None:
    """Read KEY=VALUE lines from .env into the environment (no extra package needed)."""
    f = Path(path)
    if not f.exists():
        return
    for line in f.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def client_for(args):
    if args.mock:
        from .mock import MockOJClient
        return MockOJClient()
    return OJClient()


# ------------------------------------------------------------------ summary table
def summarize(rows: list[dict]) -> str:
    def avg(rs, k):
        v = [r[k] for r in rs if isinstance(r.get(k), (int, float)) and not isinstance(r.get(k), bool)]
        return f"{st.mean(v):.2f}" if v else "–"

    def rate(rs, k):
        v = [r[k] for r in rs if isinstance(r.get(k), bool)]
        return f"{sum(v) / len(v):.0%}" if v else "–"

    cols = [("engine", None), ("n", None),
            ("citation", "q_citation_quality"), ("facts", "q_factual_accuracy"), ("reasoning", "q_legal_reasoning"),
            ("coverage", "f_coverage"), ("order", "f_order_score"), ("outcome follows", "f_outcome_follows"),
            ("outcome correct", "f_outcome_correct"), ("articles exist", "c_exists_rate"),
            ("quotes verified", "c_verified_quote_rate"), ("companion", "m_completeness"),
            ("Ø LLM calls", "llm_calls"), ("Ø tokens", "total_tokens"), ("Ø sec", "seconds"), ("errors", None)]
    out = ["| " + " | ".join(c for c, _ in cols) + " |", "|" + "---|" * len(cols)]
    for eng in dict.fromkeys(r["engine"] for r in rows):
        rs = [r for r in rows if r["engine"] == eng]
        cells = []
        for c, k in cols:
            if c == "engine":
                cells.append(eng)
            elif c == "n":
                cells.append(str(len(rs)))
            elif c == "errors":
                cells.append(str(sum(1 for r in rs if r["error"])))
            elif k in ("f_outcome_follows", "f_outcome_correct"):
                cells.append(rate(rs, k))
            else:
                cells.append(avg(rs, k))
        out.append("| " + " | ".join(cells) + " |")
    return "\n".join(out)


# ------------------------------------------------------------------ run
def cmd_run(args, client):
    model, files = args.model, law_files()
    engines = {"direct": lambda: DirectEngine(client, model),
               "openjustice": lambda: OpenJusticeEngine(client, model, exact_calls=args.exact_calls),
               "plan_based": lambda: PlanBasedEngine(client, model),
               "plan_based_rag": lambda: PlanBasedEngine(client, model, law_files=files or [{"id": "file_mock", "name": "mock"}] if args.mock else files)}
    if "plan_based_rag" in args.engines and not files and not args.mock:
        raise SystemExit("plan_based_rag needs uploaded law files: python3 -m ojbench upload data/law/OR.pdf --code OR")
    cases = [Case.from_json(p) for p in sorted(Path(f"data/cases/{args.split}").glob("*.json"))]
    if not cases:
        raise SystemExit(f"no cases in data/cases/{args.split}/")
    if args.split == "test" and not args.yes:
        if input("TEST split: run only once, at the very end. Continue? [y/N] ").lower() != "y":
            raise SystemExit("aborted")
    manual, index = manual_scores(), build_index()
    run_dir = Path("results") / f"{time.strftime('%Y%m%d-%H%M%S')}-{args.split}-{model.replace('/', '_')}"
    run_dir.mkdir(parents=True)
    rows = []
    for name in args.engines:
        engine = engines[name]()
        for case in cases:
            proto = load_protocol(case.protocol_id, client)
            res = engine.run(proto, case)
            cit = exists_check(res.answer + " " + " ".join(s for t in res.trace for s in (t.sources or [])), index)
            quotes = verify_quotes(client, res.quotes) if res.quotes else {}
            row = {"engine": res.engine, "case_id": case.id, "model": model, "error": res.error, **res.usage,
                   **{f"f_{k}": v for k, v in fidelity(proto, res, case).items()},
                   **{f"c_{k}": v for k, v in (cit | quotes).items()},
                   **{f"m_{k}": v for k, v in companion_check(res.answer).items()}}
            key = (res.engine, case.id)
            if key in manual:
                row |= {f"q_{d}": manual[key][d] for d in DIMS} | {"q_source": "manual"}
            elif args.judge_model and not res.error:
                g = llm_judge(client, args.judge_model, case, res)
                row |= {f"q_{d}": g[d] for d in DIMS} | {"q_source": f"llm:{args.judge_model}", "q_rationale": g["rationale"]}
            rows.append(row)
            (run_dir / f"{res.engine}__{case.id}.json").write_text(json.dumps(res.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"{res.engine:26} {case.id:14} calls={row.get('llm_calls')} tokens={row.get('total_tokens')} "
                  f"cov={row.get('f_coverage')} outcome_ok={row.get('f_outcome_correct')} "
                  f"companion={row.get('m_completeness')} err={res.error}")
    (run_dir / "rows.json").write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    summary = summarize(rows)
    (run_dir / "summary.md").write_text(f"# {args.split} · {model}\n\n{summary}\n", encoding="utf-8")
    print("\n" + summary + f"\n\n-> {run_dir}")


def cmd_upload(args, client):
    rec = client.upload(args.file, strategy=args.strategy, metadata={"code": args.code} if args.code else None)
    reg = Path("data/law/files.json")
    entries = law_files(reg)
    entries.append({"id": rec["id"], "name": rec.get("name", Path(args.file).name), "code": args.code})
    reg.write_text(json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"uploaded {rec.get('name')} -> id {rec['id']} (indexing continues in the background; check with GET /files)")


def cmd_playground(args):
    from .publicai import PublicAI
    pa = PublicAI(model=args.model)
    if args.list:
        print("\n".join(pa.list_models()))
        return
    if not pa.model:
        raise SystemExit("set PUBLICAI_MODEL in .env or pass --model (see: playground --list)")
    system = Path(args.system).read_text(encoding="utf-8") if args.system else "You are a careful Swiss legal analyst."
    for pfile in args.prompts:
        r = pa.chat(system, Path(pfile).read_text(encoding="utf-8"))
        print(f"\n===== {pfile} · {r['seconds']}s · {r['prompt_tokens']}+{r['completion_tokens']} tokens\n{r['text']}")


def main():
    ap = argparse.ArgumentParser(prog="ojbench")
    ap.add_argument("--mock", action="store_true", help="offline fake API")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("models")
    sub.add_parser("protocols")
    sub.add_parser("files", help="your uploaded files and whether they are indexed")
    f = sub.add_parser("fetch"); f.add_argument("protocol_id")
    p = sub.add_parser("plan"); p.add_argument("protocol_id")
    u = sub.add_parser("upload"); u.add_argument("file"); u.add_argument("--code", default=None, help="e.g. OR, ZPO, VMWG")
    u.add_argument("--strategy", default="statute", help="OpenJustice enrichment: statute | regulation | case | none")
    g = sub.add_parser("playground", help="direct Apertus calls via Public AI (needs PUBLICAI_API_KEY)")
    g.add_argument("prompts", nargs="*", help="one or more prompt files, answers are printed one after another")
    g.add_argument("--system", default=None, help="file with a system prompt")
    g.add_argument("--model", default=None); g.add_argument("--list", action="store_true", help="list Public AI models")
    r = sub.add_parser("run")
    r.add_argument("--split", choices=["dev", "test"], default="dev")
    r.add_argument("--engines", nargs="+", choices=ENGINES, default=list(DEFAULT_ENGINES))
    r.add_argument("--model", default="publicai-apertus-70b", help="same model for every engine (fair comparison), see `models`")
    r.add_argument("--judge-model", default=None, help="different model used as LLM judge (optional)")
    r.add_argument("--exact-calls", action="store_true", help="read Node Traces for exact LLM call counts (slower)")
    r.add_argument("--yes", action="store_true", help="skip the test-split confirmation")
    args = ap.parse_args()
    load_dotenv()
    if args.cmd == "upload" and args.strategy == "none":
        args.strategy = None
    if args.cmd == "playground":
        return cmd_playground(args)
    client = client_for(args)

    if args.cmd == "models":
        print(json.dumps(client.models(), indent=2))
    elif args.cmd == "protocols":
        for pr in client.list_protocols():
            print(pr.get("id"), "·", pr.get("name"))
    elif args.cmd == "fetch":
        proto = load_protocol(args.protocol_id, client, refresh=True)
        print(f"cached {proto.id} v{proto.version}: {len(proto.nodes)} nodes, {len(proto.edges)} edges")
    elif args.cmd == "plan":
        proto = load_protocol(args.protocol_id, client)
        plan = distill_plan(proto)
        print(plan, "\n\ncoverage:", plan_coverage(proto, plan))
    elif args.cmd == "upload":
        cmd_upload(args, client)
    elif args.cmd == "files":
        for fl in client.files():
            print(fl["id"], "·", fl["name"], "· indexed:", fl.get("isVectorized"), "· status:", fl.get("processingStatus", "?"))
    elif args.cmd == "run":
        cmd_run(args, client)


if __name__ == "__main__":
    main()
