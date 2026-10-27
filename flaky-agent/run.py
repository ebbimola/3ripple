"""Run a refund task N times, save every transcript, then grade the batch.

    python run.py                          # 20 runs of the 'stopped-charging' task on claude-opus-5-5
    python run.py --task cracked           # the easy one
    python run.py -n 40 --effort high
"""

import argparse
import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import anthropic

from agent import TASKS, run_trial
from grade import expected_reply_path, report

HERE = Path(__file__).parent


def load_dotenv(path=HERE / ".env"):
    """Read KEY=value lines from .env, if present, without overriding the environment."""
    if path.exists():
        for line in path.read_text().splitlines():
            key, sep, value = line.partition("=")
            if sep and not line.lstrip().startswith("#"):
                os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--task", default="stopped-charging", choices=list(TASKS))
    p.add_argument("-n", type=int, default=20, help="number of runs (default 20)")
    p.add_argument("--model", default="claude-opus-5-5")
    p.add_argument("--effort", default="low", choices=["low", "medium", "high", "xhigh", "max"])
    p.add_argument("-k", type=int, default=8, help="k for pass^k (default 8)")
    p.add_argument("--workers", type=int, default=5)
    args = p.parse_args()

    load_dotenv()
    client = anthropic.Anthropic()
    out = HERE / "runs" / datetime.now().strftime("%Y%m%d-%H%M%S")
    out.mkdir(parents=True)

    def one(i):
        t = run_trial(client, args.task, args.model, args.effort)
        (out / f"run-{i:02d}.json").write_text(json.dumps(t, indent=2, ensure_ascii=False))
        print(f"run {i:02d} done: {len(t['tool_calls'])} tool calls, {len(t['refunds'])} refund(s)")
        return t

    with ThreadPoolExecutor(args.workers) as pool:
        first = list(pool.map(one, range(1, args.n + 1)))[0]

    # Like a snapshot test: the first reply ever recorded becomes the expected string.
    snapshot = expected_reply_path(args.task)
    if not snapshot.exists():
        snapshot.parent.mkdir(exist_ok=True)
        snapshot.write_text(first["reply"] + "\n")
        print(f"\nSaved run 01's reply as the snapshot in expected/{snapshot.name}")

    report(out, k=args.k)


if __name__ == "__main__":
    main()
