"""Grade a folder of saved transcripts three ways: exact match, loose match, and graded.

    python grade.py runs/<timestamp>
"""

import json
import sys
from collections import Counter
from math import comb
from pathlib import Path

from agent import TASKS

HERE = Path(__file__).parent


def expected_reply_path(task):
    return HERE / "expected" / f"{task}.txt"


# --- The two assertions a test suite would write ---------------------------------

def exact_match(t, expected):
    """Snapshot test: the reply must equal the saved one, character for character."""
    return t["reply"].strip() == expected.strip()


def mentions_refund(t):
    """The 'fix' for a flaky snapshot: loosen it until it stops failing."""
    return "refund" in t["reply"].lower()


# --- What grading checks instead ---------------------------------------------------

def outcome(t):
    """Classify the end state of the store, ignoring the wording entirely."""
    want = TASKS[t["task"]]
    refunds = t["refunds"]
    if not refunds:
        return "no refund"
    if len(refunds) > 1:
        return "multiple refunds"
    r = refunds[0]
    if r["order_id"] != want["order_id"]:
        return f"wrong order ({r['order_id']})"
    if abs(r["amount"] - want["amount"]) > 0.005:
        return f"wrong amount (£{r['amount']:.2f})"
    return "correct refund"


def outcome_ok(t):
    return outcome(t) == "correct refund"


def path_ok(t):
    """The order was looked up before money moved. None if no money moved."""
    calls = t["tool_calls"]
    looked_up = None
    for i, c in enumerate(calls):
        if c["tool"] == "lookup_order" and c["input"].get("order_id") == TASKS[t["task"]]["order_id"] and "error" not in c:
            looked_up = i if looked_up is None else looked_up
        if c["tool"] == "issue_refund":
            return looked_up is not None and looked_up < i
    return None


def passed(t):
    return outcome_ok(t) and path_ok(t) is True


# --- Reliability metrics (unbiased estimators from n trials with c passes) -------

def pass_at_k(n, c, k):
    """Chance at least one of k trials passes."""
    return 1.0 if n - c < k else 1 - comb(n - c, k) / comb(n, k)


def pass_hat_k(n, c, k):
    """pass^k (τ-bench): chance all k trials pass."""
    return comb(c, k) / comb(n, k)


# --- Report ------------------------------------------------------------------------

def load(run_dir):
    return [json.loads(p.read_text()) for p in sorted(Path(run_dir).glob("run-*.json"))]


def report(run_dir, k=8):
    ts = load(run_dir)
    n = len(ts)
    if n == 0:
        sys.exit(f"no run-*.json files in {run_dir}")
    task = ts[0]["task"]
    snapshot = expected_reply_path(task)
    expected = snapshot.read_text() if snapshot.exists() else ts[0]["reply"]

    def mark(ok):
        return "n/a" if ok is None else "PASS" if ok else "fail"

    print(f"\n{n} runs of the '{task}' refund task on {ts[0]['model']}  ({run_dir})\n")
    print(f"{'run':>4}  {'exact':5}  {'loose':5}  {'outcome':5}  {'path':5}  {'graded':6}  what happened")
    for i, t in enumerate(ts, 1):
        print(f"{i:>4}  {mark(exact_match(t, expected)):5}  {mark(mentions_refund(t)):5}  "
              f"{mark(outcome_ok(t)):5}  {mark(path_ok(t)):5}  {mark(passed(t)):6}  {outcome(t)}")

    exact = sum(exact_match(t, expected) for t in ts)
    loose = sum(mentions_refund(t) for t in ts)
    c = sum(passed(t) for t in ts)

    print(f"\n1. Exact-match assertion (snapshot in expected/{task}.txt)")
    print(f"   {exact}/{n} passed. Same task, same prompt, same tools: the wording moves, so the test flips.")

    print("\n2. Loose assertion (reply mentions 'refund')")
    print(f"   {loose}/{n} passed.")
    stamped = [i for i, t in enumerate(ts, 1) if mentions_refund(t) and not outcome_ok(t)]
    if stamped:
        print(f"   Passed but no correct refund was issued: runs {', '.join(map(str, stamped))}.")
        # Prefer a run that refused outright: the clearest case of a rubber stamp.
        i = next((i for i in stamped if not ts[i - 1]["refunds"]), stamped[0])
        print(f"   Run {i} ({outcome(ts[i - 1])}) said: \"{_first_line(ts[i - 1]['reply'])}\"")
    else:
        print("   Every run that passed it also issued the right refund, this time.")

    print("\n3. Graded report")
    print(f"   Pass rate (outcome + path): {c}/{n} = {c / n:.0%}")
    print(f"   Outcome check (right order, right amount, one refund): {sum(map(outcome_ok, ts))}/{n}")
    refunded = [t for t in ts if path_ok(t) is not None]
    print(f"   Path check (order looked up before the refund):         "
          f"{sum(path_ok(t) for t in refunded)}/{len(refunded)} runs that refunded")
    print("   Outcome spread:")
    for name, count in Counter(outcome(t) for t in ts).most_common():
        print(f"     {count:>3}  {name}")
    print(f"   pass@1 = {c / n:.2f}")
    for kk in sorted({2, 4, k} & set(range(1, n + 1))):
        print(f"   pass^{kk} = {pass_hat_k(n, c, kk):.2f}   (pass@{kk} = {pass_at_k(n, c, kk):.2f})")
    print("\n   pass@k: can it do the task?  pass^k: will it, every time a customer asks?\n")


def _first_line(text, width=110):
    line = " ".join(text.split())
    return line if len(line) <= width else line[: width - 1] + "…"


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    report(sys.argv[1])
