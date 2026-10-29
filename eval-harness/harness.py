"""A minimal agent eval harness: tasks in, transcripts saved, graders run, metrics out.

    python harness.py                                    # scripted agent, no API key needed
    python harness.py --agent claude                     # claude-haiku-5-5, a few cents
    python harness.py --agent claude --model claude-opus-5-5 --task stopped-charging
    python harness.py --grade sample-runs/scripted       # re-grade saved transcripts, no agent
    python harness.py --gate                             # exit 1 if any task misses its gate
"""

import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

from graders import grade
from metrics import summarise

HERE = Path(__file__).parent


def load_dotenv(path=HERE / ".env"):
    if path.exists():
        for line in path.read_text().splitlines():
            key, sep, value = line.partition("=")
            if sep and not line.lstrip().startswith("#"):
                os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def load_suite(path=HERE / "tasks.json", only=None):
    suite = json.loads(Path(path).read_text())
    if only:
        suite["tasks"] = [t for t in suite["tasks"] if t["id"] in only]
    return suite


# --- 1. Run: every task, n trials each, one transcript file per trial -------------------

def run(suite, args, out):
    from agent import ClaudeAgent, ScriptedAgent, run_trial

    def one(job):
        task, i = job
        agent = (ScriptedAgent(task["id"], seed=f"{args.seed}-{i}") if args.agent == "scripted"
                 else ClaudeAgent(args.model, args.effort))
        t = run_trial(agent, task, i)
        path = out / task["id"] / f"trial-{i:02d}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(t, indent=2, ensure_ascii=False))
        return t

    jobs = [(task, i) for task in suite["tasks"] for i in range(1, args.n + 1)]
    with ThreadPoolExecutor(args.workers) as pool:
        for done, _ in enumerate(pool.map(one, jobs), 1):
            print(f"\r{done}/{len(jobs)} trials", end="", flush=True)
    print("\r", end="")


# --- 2. Grade + 3. Measure: read transcripts back from disk, never from memory ------------

def evaluate(suite, run_dir, k):
    summaries, results = [], {}
    for task in suite["tasks"]:
        files = sorted((Path(run_dir) / task["id"]).glob("trial-*.json"))
        if not files:
            continue
        graded = []
        for f in files:
            t = json.loads(f.read_text())
            verdict, grades = grade(t, task)
            graded.append((t, verdict, grades))
            results[f"{task['id']}/{f.name}"] = {"verdict": verdict, "grades": [g.to_dict() for g in grades]}
        summaries.append(summarise(task, graded, k))
    agent = json.loads(next(Path(run_dir).glob("*/trial-*.json")).read_text())["agent"]
    (Path(run_dir) / "results.json").write_text(json.dumps({"agent": agent, "k": k, "summaries": summaries,
                                                            "trials": results}, indent=2))
    return agent, summaries


def report(suite, run_dir, agent, summaries):
    k = summaries[0]["k"]
    n_trials = sum(s["n"] for s in summaries)
    print(f"\nSuite '{suite['suite']}': {len(summaries)} tasks, {n_trials} trials, agent {agent}  ({run_dir})\n")
    print(f"{'task':22} {'pass':>6} {'fail':>5} {'incomp':>6} {'pass@1':>7} {f'pass^{k}':>7} {'gate':>5}  result")
    for s in summaries:
        gate = "-" if s["gate"] is None else f"{s['gate']:.2f}"
        print(f"{s['task_id']:22} {s['passed']:>3}/{s['n']:<2} {s['failed']:>5} {s['incomplete']:>6} "
              f"{s['pass_rate']:>7.2f} {s['pass_hat_k']:>7.2f} {gate:>5}  {s['gate_result']}")

    failing = [s for s in summaries if s["failure_modes"]]
    if failing:
        print("\nFailure modes (from the graders, not the wording):")
        for s in failing:
            print(f"  {s['task_id']}  (trials {', '.join(map(str, s['failing_trials']))})")
            for grader, count, example in s["failure_modes"]:
                print(f"    {count}x {grader:21} e.g. {example}")
        s = failing[0]
        first = "trial-%02d.json" % s["failing_trials"][0]
        print(f"\n  Read one: {Path(run_dir) / s['task_id'] / first}")
    blocked = [s["task_id"] for s in summaries if s["incomplete"]]
    if blocked:
        print(f"\nIncomplete: a grader was skipped on {', '.join(blocked)} (set ANTHROPIC_API_KEY for the model grader).")

    passed = sum(s["passed"] for s in summaries)
    gated = [s for s in summaries if s["gate"] is not None]
    ok = sum(s["gate_result"] == "PASS" for s in gated)
    tokens = sum(s["tokens"] for s in summaries)
    print(f"\n{passed}/{n_trials} trials passed. {ok}/{len(gated)} tasks meet their pass^{k} gate."
          + (f" {tokens:,} tokens." if tokens else ""))
    return ok == len(gated)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--agent", default="scripted", choices=["scripted", "claude"])
    p.add_argument("--model", default="claude-haiku-5-5")
    p.add_argument("--effort", default="low", choices=["low", "medium", "high", "xhigh", "max"])
    p.add_argument("--task", action="append", help="run only this task (repeatable)")
    p.add_argument("-n", type=int, default=20, help="trials per task (default 20)")
    p.add_argument("-k", type=int, help="k for pass^k (default: from tasks.json)")
    p.add_argument("--seed", default="1", help="seed for the scripted agent")
    p.add_argument("--workers", type=int, default=5)
    p.add_argument("--grade", metavar="RUN_DIR", help="grade saved transcripts instead of running")
    p.add_argument("--gate", action="store_true", help="exit 1 if any task misses its gate")
    args = p.parse_args()

    load_dotenv()
    suite = load_suite(only=args.task)
    k = args.k or suite["k"]
    if args.grade:
        run_dir = Path(args.grade)
    else:
        run_dir = HERE / "runs" / datetime.now().strftime("%Y%m%d-%H%M%S")
        run(suite, args, run_dir)
    agent, summaries = evaluate(suite, run_dir, k)
    all_ok = report(suite, run_dir.relative_to(HERE) if run_dir.is_absolute() else run_dir, agent, summaries)
    if args.gate and not all_ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
