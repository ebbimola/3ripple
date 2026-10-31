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


def fail_rate_upper(n, f, confidence=0.95):
    """One-sided Clopper-Pearson upper bound on the true failure rate, given f failures in n trials.

    With f = 0 this is 1 - (1 - confidence) ** (1 / n): 20 clean trials bound the rate at 13.9%,
    100 at 3.0%, and it takes about 300 to get under 1%. A 1.00 gate is only as strong as n.
    """
    if f >= n:
        return 1.0
    alpha = 1 - confidence

    def cdf(p):  # P(X <= f) for X ~ Binomial(n, p)
        return sum(comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(f + 1))

    lo, hi = f / n, 1.0
    for _ in range(60):  # bisect: the largest p whose lower tail still contains f at level alpha
        mid = (lo + hi) / 2
        if cdf(mid) > alpha:
            lo = mid
        else:
            hi = mid
    return hi


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
    max_fail = task.get("max_fail_rate")  # optional: the 95% upper bound on the failure rate must clear this
    phk = pass_hat_k(n, c, k)
    upper = fail_rate_upper(n, verdicts["fail"] + verdicts["incomplete"])
    if verdicts["incomplete"]:
        gate_result = "BLOCKED"  # can't gate on a grader that didn't run
    elif gate is None and max_fail is None:
        gate_result = "-"
    elif (gate is not None and phk < gate) or (max_fail is not None and upper > max_fail):
        gate_result = "FAIL"
    else:
        gate_result = "PASS"
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
        "fail_rate_upper": upper,
        "max_fail_rate": max_fail,
        "gate": gate,
        "gate_result": gate_result,
        "failure_modes": modes,
        "failing_trials": [t["trial"] for t, v, _ in graded if v == "fail"],
        "mean_tool_calls": sum(len(t["tool_calls"]) for t, _, _ in graded) / n,
        "tokens": sum(t["usage"]["input_tokens"] + t["usage"]["output_tokens"] for t, _, _ in graded),
        "mean_latency_s": sum(t["latency_s"] for t, _, _ in graded) / n,
    }
