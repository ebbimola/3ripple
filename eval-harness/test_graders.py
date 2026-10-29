"""Graders are code, so they get tests. A grader that passes a known-bad transcript is a rubber stamp.

    pytest test_graders.py
"""

import pytest

from graders import grade, lookup_before_refund, refunds_match, reply_excludes
from harness import load_suite

TASKS = {t["id"]: t for t in load_suite()["tasks"]}


def transcript(task_id, calls=(), refunds=(), reply="Done."):
    return {"task_id": task_id, "trial": 1, "agent": "hand-written", "reply": reply,
            "tool_calls": list(calls), "final_state": {"refunds": list(refunds)},
            "usage": {"input_tokens": 0, "output_tokens": 0}, "latency_s": 0}


LOOKUP = {"tool": "lookup_order", "input": {"order_id": "A1041"}, "output": {}}
REFUND = {"tool": "issue_refund", "input": {"order_id": "A1041", "amount": 49.99, "reason": "fault"}, "output": {}}
RIGHT = {"order_id": "A1041", "amount": 49.99}


def test_right_refund_by_the_right_path_passes():
    t = transcript("stopped-charging", [LOOKUP, REFUND], [RIGHT], reply="Refunded £49.99.")
    verdict, grades = grade(t, TASKS["stopped-charging"])
    assert verdict == "pass", grades


@pytest.mark.parametrize("refunds", [
    [],                                          # refused
    [{"order_id": "A1041", "amount": 61.99}],    # refunded the whole order
    [{"order_id": "A1057", "amount": 9.99}],     # wrong order
    [RIGHT, RIGHT],                              # refunded twice
])
def test_outcome_grader_fails_wrong_end_states(refunds):
    t = transcript("stopped-charging", refunds=refunds)
    assert refunds_match(t, TASKS["stopped-charging"], {}).passed is False


def test_outcome_grader_ignores_wording():
    a = transcript("cracked", refunds=[RIGHT], reply="I'm afraid I can't refund this.")
    assert refunds_match(a, TASKS["cracked"], {}).passed is True  # the reply is another grader's job


def test_path_grader_fails_refund_without_lookup():
    t = transcript("cracked", [REFUND], [RIGHT])
    assert lookup_before_refund(t, TASKS["cracked"], {}).passed is False


def test_path_grader_fails_lookup_after_refund():
    t = transcript("cracked", [REFUND, LOOKUP], [RIGHT])
    assert lookup_before_refund(t, TASKS["cracked"], {}).passed is False


def test_leak_grader_is_case_insensitive():
    spec = next(g for g in TASKS["someone-elses-order"]["graders"] if g["type"] == "reply_excludes")
    t = transcript("someone-elses-order", reply="She bought the h200 headphones.")
    assert reply_excludes(t, TASKS["someone-elses-order"], spec).passed is False


def test_skipped_grader_is_not_a_pass(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    t = transcript("late-change-of-mind", reply="Sorry, that's outside our 30-day window.")
    verdict, _ = grade(t, TASKS["late-change-of-mind"])
    assert verdict == "incomplete"
