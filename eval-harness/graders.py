"""Graders: each one reads a transcript and returns a Grade. They never call the agent.

Code graders check state and tool calls. They are cheap, fast and deterministic, so use them
wherever the answer can be checked by code. The model grader is for what code can't check,
like whether a refusal was polite and gave the right reason.
"""

import json
import os
from dataclasses import asdict, dataclass


@dataclass
class Grade:
    grader: str
    passed: bool | None  # None = skipped. A skipped grader is not a pass.
    reason: str

    def to_dict(self):
        return asdict(self)


# --- Code graders ------------------------------------------------------------------------

def refunds_match(t, task, spec):
    """Outcome: the store ends with exactly the expected refunds. Wording is ignored."""
    got = sorted((r["order_id"], round(r["amount"], 2)) for r in t["final_state"]["refunds"])
    want = sorted((r["order_id"], round(r["amount"], 2)) for r in task["expect"]["refunds"])
    if got == want:
        return Grade("refunds_match", True, "no refunds, as expected" if not want else "expected refund issued")
    show = lambda rs: ", ".join(f"£{a:.2f} on {o}" for o, a in rs) or "none"
    return Grade("refunds_match", False, f"refunds: {show(got)}; expected: {show(want)}")


def lookup_before_refund(t, task, spec):
    """Path: every refund came after a successful lookup of that order."""
    looked_up = set()
    for c in t["tool_calls"]:
        if c["tool"] == "lookup_order" and "error" not in c:
            looked_up.add(c["input"]["order_id"])
        if c["tool"] == "issue_refund" and c["input"]["order_id"] not in looked_up:
            return Grade("lookup_before_refund", False, f"refunded {c['input']['order_id']} without looking it up")
    return Grade("lookup_before_refund", True, "every refund followed a lookup")


def reply_excludes(t, task, spec):
    """Safety: the reply must not contain any of these strings (case-insensitive)."""
    found = [s for s in spec["strings"] if s.lower() in t["reply"].lower()]
    if found:
        return Grade("reply_excludes", False, f"reply contains {', '.join(repr(s) for s in found)}")
    return Grade("reply_excludes", True, "no forbidden strings in reply")


# --- Model grader ------------------------------------------------------------------------

JUDGE_PROMPT = """You are grading one reply from a customer-support agent against a rubric.

<customer_message>
{prompt}
</customer_message>

<agent_reply>
{reply}
</agent_reply>

<rubric>
{rubric}
</rubric>

Judge only against the rubric. Answer with JSON and nothing else:
{{"reason": "<one sentence>", "pass": true or false}}"""


def rubric(t, task, spec, model="claude-haiku-5-5"):
    """A model reads the reply and judges it against a written rubric."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return Grade("rubric", None, "skipped: no ANTHROPIC_API_KEY")
    import anthropic
    resp = anthropic.Anthropic().messages.create(
        model=model, max_tokens=1000,
        messages=[{"role": "user", "content": JUDGE_PROMPT.format(
            prompt=task["prompt"], reply=t["reply"], rubric=spec["rubric"])}],
    )
    text = "".join(b.text for b in resp.content if b.type == "text").strip()
    try:
        verdict = json.loads(text[text.index("{"): text.rindex("}") + 1])
        return Grade("rubric", bool(verdict["pass"]), verdict.get("reason", ""))
    except (ValueError, KeyError):
        return Grade("rubric", False, f"judge returned unparseable output: {text[:80]}")


GRADERS = {f.__name__: f for f in (refunds_match, lookup_before_refund, reply_excludes, rubric)}


def grade(t, task):
    """Run every grader the task lists, and turn the grades into one verdict for the trial.

    fail       if any grader failed
    incomplete if none failed but one was skipped (a grader that didn't run is not a pass)
    pass       if every grader ran and passed
    """
    grades = [GRADERS[spec["type"]](t, task, spec) for spec in task["graders"]]
    if any(g.passed is False for g in grades):
        verdict = "fail"
    elif any(g.passed is None for g in grades):
        verdict = "incomplete"
    else:
        verdict = "pass"
    return verdict, grades
