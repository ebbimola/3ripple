"""Metrics: turn many graded trials into a few numbers per task, and a gate decision.

pass@k and pass^k use the unbiased estimators from n trials with c passes:
  pass@k = 1 - C(n-c, k) / C(n, k)   chance at least one of k tries passes (can it?)
  pass^k = C(c, k) / C(n, k)         chance all k tries pass (will it, every time?)
"""

from collections import Counter
from math import comb


def pass_at_k(n, c, k):
    return 1.0 if n - c < k else 1 - comb(n - c, k) / comb(n, k)


def pass_hat_k(n, c, k):
    return comb(c, k) / comb(n, k)


def summarise(task, graded, k):
    """graded: list of (transcript, verdict, grades) for one task."""
    n = len(graded)
    verdicts = Counter(v for _, v, _ in graded)
    c = verdicts["pass"]
    k = min(k, n)
    # Which grader failed, and how: the failure modes, not just the count.
    failures = [g for _, v, gs in graded if v == "fail" for g in gs if g.passed is False]
    modes = [(name, count, next(g.reason for g in failures if g.grader == name))
             for name, count in Counter(g.grader for g in failures).most_common()]
    gate = task.get("gate")
    phk = pass_hat_k(n, c, k)
    if verdicts["incomplete"]:
        gate_result = "BLOCKED"  # can't gate on a grader that didn't run
    elif gate is None:
        gate_result = "-"
    else:
        gate_result = "PASS" if phk >= gate else "FAIL"
    return {
        "task_id": task["id"],
        "n": n,
        "passed": c,
        "failed": verdicts["fail"],
        "incomplete": verdicts["incomplete"],
        "pass_rate": c / n,
        "k": k,
        "pass_at_k": pass_at_k(n, c, k),
        "pass_hat_k": phk,
        "gate": gate,
        "gate_result": gate_result,
        "failure_modes": modes,
        "failing_trials": [t["trial"] for t, v, _ in graded if v == "fail"],
        "mean_tool_calls": sum(len(t["tool_calls"]) for t, _, _ in graded) / n,
        "tokens": sum(t["usage"]["input_tokens"] + t["usage"]["output_tokens"] for t, _, _ in graded),
        "mean_latency_s": sum(t["latency_s"] for t, _, _ in graded) / n,
    }
