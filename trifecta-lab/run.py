"""Run the same request under each trifecta configuration, save every transcript, then grade.

    python run.py                          # 10 runs per configuration on claude-haiku-5-5
    python run.py -n 20 --model claude-opus-5-5
    python run.py --config all-three -n 5
    python run.py --model obedient         # no API key: a scripted agent that obeys the planted email
"""

import argparse
import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

from agent import CONFIGS, run_obedient, run_trial
from grade import report

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
    p.add_argument("--config", choices=list(CONFIGS), help="run one configuration (default: all four)")
    p.add_argument("-n", type=int, default=10, help="runs per configuration (default 10)")
    p.add_argument("--model", default="claude-haiku-5-5", help="a Claude model id, or 'obedient'")
    p.add_argument("--effort", default="low", choices=["low", "medium", "high", "xhigh", "max"])
    p.add_argument("--workers", type=int, default=5)
    args = p.parse_args()

    obedient = args.model == "obedient"
    if obedient:
        args.n = 1  # scripted, so every run is identical
    else:
        import anthropic  # only the real-model path needs the SDK

        load_dotenv()
        client = anthropic.Anthropic()
    out = HERE / "runs" / datetime.now().strftime("%Y%m%d-%H%M%S")
    out.mkdir(parents=True)
    jobs = [(c, i) for c in ([args.config] if args.config else CONFIGS) for i in range(1, args.n + 1)]

    def one(job):
        config, i = job
        t = run_obedient(config) if obedient else run_trial(client, config, args.model, args.effort)
        (out / f"{config}-{i:02d}.json").write_text(json.dumps(t, indent=2, ensure_ascii=False))
        print(f"{config} {i:02d} done: {len(t['tool_calls'])} tool calls, {len(t['outbox'])} email(s)")

    with ThreadPoolExecutor(args.workers) as pool:
        list(pool.map(one, jobs))

    report(out)


if __name__ == "__main__":
    main()
