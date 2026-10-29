"""The eval suite as a test suite: one test per task, red when the task misses its gate.

    EVAL_RUN_DIR=runs/<timestamp> pytest test_evals.py
    pytest test_evals.py                      # grades sample-runs/scripted by default

Run the agent first (python harness.py ...), then gate on the saved transcripts. Keeping the
expensive part (running the agent) apart from the cheap part (grading) means you can re-grade
the same evidence after fixing a grader, without paying for new runs.
"""

import os
from pathlib import Path

import pytest

from harness import HERE, evaluate, load_suite

SUITE = load_suite()
RUN_DIR = Path(os.environ.get("EVAL_RUN_DIR", HERE / "sample-runs" / "scripted"))
_, SUMMARIES = evaluate(SUITE, RUN_DIR, SUITE["k"])
BY_TASK = {s["task_id"]: s for s in SUMMARIES}


@pytest.mark.parametrize("task_id", [t["id"] for t in SUITE["tasks"]])
def test_task_meets_its_gate(task_id):
    s = BY_TASK.get(task_id)
    assert s is not None, f"no transcripts for {task_id} in {RUN_DIR}"
    assert s["incomplete"] == 0, f"{s['incomplete']} trials had a skipped grader; that is not a pass"
    modes = "; ".join(f"{c}x {g}: {e}" for g, c, e in s["failure_modes"])
    assert s["pass_hat_k"] >= s["gate"], (
        f"pass^{s['k']} = {s['pass_hat_k']:.2f} < gate {s['gate']:.2f} "
        f"({s['passed']}/{s['n']} passed). Failures: {modes}"
    )
