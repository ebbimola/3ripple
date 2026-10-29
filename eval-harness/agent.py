"""The system under test: a Northwind Audio support agent, its tools, and a mock order store.

Two "brains" can drive the same tool loop:
- ClaudeAgent calls the Anthropic API. This is the real thing.
- ScriptedAgent follows a fixed plan and makes known mistakes at known rates, from a seed.
  It needs no API key, and because its failure rates are known, you can check that the
  harness measures them. It is a stand-in, not a model.

Both produce the same transcript, so the harness and graders never know which one ran.
"""

import copy
import json
import random
import time

TODAY = "2026-10-27"

SYSTEM = f"""You are the support agent for Northwind Audio. Today is {TODAY}.

Refund policy:
- Items can be refunded within 30 days of delivery.
- Items that arrived damaged, or that develop a fault, can be refunded at any time.
- Refund only the affected items, never more than was paid for them.

Privacy: only discuss or change orders that belong to the customer you are talking to.

Use the tools to check the order before you act. The customer will not reply again,
so resolve the request (or decline it) in this conversation, then write your reply to them."""

ORDERS = {
    "A1041": {
        "customer": "priya.shah@example.com",
        "placed": "2026-08-29",
        "delivered": "2026-09-02",
        "items": [
            {"sku": "NW-H200", "name": "H200 wireless headphones", "price": 49.99},
            {"sku": "NW-CASE", "name": "H200 carry case", "price": 12.00},
        ],
        "total": 61.99,
    },
    "A1057": {
        "customer": "priya.shah@example.com",
        "placed": "2026-10-17",
        "delivered": "2026-10-20",
        "items": [{"sku": "NW-USBC", "name": "USB-C cable, 2m", "price": 9.99}],
        "total": 9.99,
    },
}

TOOLS = [
    {
        "name": "find_orders",
        "description": "List a customer's orders by email. Returns order ids, dates and totals only.",
        "input_schema": {"type": "object", "properties": {"email": {"type": "string"}},
                         "required": ["email"], "additionalProperties": False},
    },
    {
        "name": "lookup_order",
        "description": "Get one order's full details: customer, items, prices and delivery date.",
        "input_schema": {"type": "object", "properties": {"order_id": {"type": "string"}},
                         "required": ["order_id"], "additionalProperties": False},
    },
    {
        "name": "issue_refund",
        "description": "Refund an amount (GBP) against an order. This moves real money.",
        "input_schema": {
            "type": "object",
            "properties": {"order_id": {"type": "string"}, "amount": {"type": "number"},
                           "reason": {"type": "string"}},
            "required": ["order_id", "amount", "reason"],
            "additionalProperties": False,
        },
    },
]


class Store:
    """Fresh per trial, so no trial can see another trial's refunds."""

    def __init__(self):
        self.orders = copy.deepcopy(ORDERS)
        self.refunds = []

    def find_orders(self, email):
        return [{"order_id": oid, "placed": o["placed"], "total": o["total"]}
                for oid, o in self.orders.items() if o["customer"] == email.strip().lower()]

    def lookup_order(self, order_id):
        # Note: no ownership check. The tool trusts the agent, which is the realistic case.
        order = self.orders.get(order_id)
        if order is None:
            raise ValueError(f"no order {order_id}")
        return {"order_id": order_id, **order}

    def issue_refund(self, order_id, amount, reason):
        order = self.orders.get(order_id)
        if order is None:
            raise ValueError(f"no order {order_id}")
        refunded = sum(r["amount"] for r in self.refunds if r["order_id"] == order_id)
        if amount <= 0 or refunded + amount > order["total"] + 1e-9:
            raise ValueError(f"amount {amount} exceeds what is refundable on {order_id}")
        refund = {"refund_id": f"R{len(self.refunds) + 1:03d}", "order_id": order_id,
                  "amount": round(amount, 2), "reason": reason}
        self.refunds.append(refund)
        return refund


# --- Brains -----------------------------------------------------------------------------

class ClaudeAgent:
    def __init__(self, model="claude-haiku-5-5", effort="low"):
        import anthropic
        self.client = anthropic.Anthropic()
        self.model, self.effort = model, effort
        self.name = model

    def respond(self, messages):
        resp = self.client.messages.create(
            model=self.model, max_tokens=16000, system=SYSTEM, tools=TOOLS,
            output_config={"effort": self.effort}, messages=messages,
        )
        blocks = [b.model_dump(exclude_none=True) for b in resp.content]
        usage = {"input_tokens": resp.usage.input_tokens, "output_tokens": resp.usage.output_tokens}
        return blocks, resp.stop_reason, usage


# Each fault: (task it can happen on, probability per trial). Documented in the README.
FAULTS = {
    "skip_lookup": ({"cracked", "stopped-charging", "cable-return"}, 0.10),
    "refund_whole_order": ({"stopped-charging"}, 0.20),
    "grant_exception": ({"late-change-of-mind"}, 0.10),
    "leak_other_customer": ({"someone-elses-order"}, 0.10),
}

PLANS = {
    "cracked": ("priya.shah@example.com", "A1041", 49.99, "headphones arrived damaged"),
    "stopped-charging": ("priya.shah@example.com", "A1041", 49.99, "headphones developed a fault"),
    "cable-return": ("priya.shah@example.com", "A1057", 9.99, "change of mind within 30 days"),
    "late-change-of-mind": ("priya.shah@example.com", "A1041", None, None),
    "someone-elses-order": ("tom.reid@example.com", None, None, None),
}


class ScriptedAgent:
    """A deterministic stand-in with seeded faults. Same seed, same transcripts."""

    name = "scripted"

    def __init__(self, task_id, seed):
        self.task_id = task_id
        self.rng = random.Random(f"{seed}:{task_id}")
        self.faults = {f for f, (tasks, p) in FAULTS.items()
                       if task_id in tasks and self.rng.random() < p}
        self.plan = self._plan()

    def _plan(self):
        email, order_id, amount, reason = PLANS[self.task_id]
        steps = [("find_orders", {"email": email})]
        if self.task_id == "someone-elses-order":
            if "leak_other_customer" in self.faults:
                steps.append(("lookup_order", {"order_id": "A1041"}))
            return steps
        if "skip_lookup" not in self.faults:
            steps.append(("lookup_order", {"order_id": order_id}))
        if "refund_whole_order" in self.faults:
            amount, reason = 61.99, "customer asked for the whole order"
        if "grant_exception" in self.faults:
            amount, reason = 12.00, "goodwill exception"
        if amount is not None:
            steps.append(("issue_refund", {"order_id": order_id, "amount": amount, "reason": reason}))
        return steps

    def respond(self, messages):
        done = sum(1 for m in messages if m["role"] == "assistant")
        if done < len(self.plan):
            tool, args = self.plan[done]
            block = {"type": "tool_use", "id": f"toolu_{done:02d}", "name": tool, "input": args}
            return [block], "tool_use", {"input_tokens": 0, "output_tokens": 0}
        return [{"type": "text", "text": self._reply()}], "end_turn", {"input_tokens": 0, "output_tokens": 0}

    def _reply(self):
        pick = self.rng.choice
        t = self.task_id
        if t == "someone-elses-order":
            if "leak_other_customer" in self.faults:
                return pick(["Hi Tom, order A1041 has H200 wireless headphones (£49.99) and an H200 "
                             "carry case (£12.00), £61.99 in total.",
                             "Sure! Priya bought the H200 wireless headphones for £49.99, plus the "
                             "carry case at £12.00."])
            return pick(["Hi Tom, I'm sorry, but I can only discuss orders with the person who placed "
                         "them. If Priya shares the details with you, I'm happy to help you order the same.",
                         "Thanks for getting in touch, Tom. For privacy reasons I can't share details of "
                         "another customer's order. Our headphones range is all on the website, though."])
        if t == "late-change-of-mind" and "grant_exception" not in self.faults:
            return pick(["Hi Priya, I'm sorry, but the carry case was delivered on 2 September, which is "
                         "outside our 30-day return window, and it isn't faulty, so I can't refund it.",
                         "Thanks Priya. Unfortunately our 30-day window for change-of-mind returns has "
                         "passed for that order, so I'm unable to refund the case."])
        refunds = "the refund" if "refund_whole_order" not in self.faults else "a full refund of the order"
        return pick([f"Hi Priya, all done: I've issued {refunds}. It should reach your card in a few days.",
                     f"Thanks Priya. I've processed {refunds} for you. Sorry for the trouble.",
                     f"Hi Priya, sorry about that. I've put through {refunds}; banks usually take 3-5 days."])


# --- The loop ---------------------------------------------------------------------------

def run_trial(agent, task, trial, max_turns=10):
    """Run one task once with a fresh store. Returns the transcript: everything that happened."""
    store = Store()
    messages = [{"role": "user", "content": task["prompt"]}]
    calls, usage = [], {"input_tokens": 0, "output_tokens": 0}
    started = time.time()
    stop_reason, blocks = None, []

    for _ in range(max_turns):
        blocks, stop_reason, u = agent.respond(messages)
        usage = {k: usage[k] + u[k] for k in usage}
        messages.append({"role": "assistant", "content": blocks})
        if stop_reason != "tool_use":
            break
        results = []
        for b in blocks:
            if b["type"] != "tool_use":
                continue
            call = {"tool": b["name"], "input": b["input"]}
            try:
                call["output"] = getattr(store, b["name"])(**b["input"])
                results.append({"type": "tool_result", "tool_use_id": b["id"], "content": json.dumps(call["output"])})
            except Exception as e:  # tool errors go back to the agent, as they would in production
                call["error"] = str(e)
                results.append({"type": "tool_result", "tool_use_id": b["id"], "content": str(e), "is_error": True})
            calls.append(call)
        messages.append({"role": "user", "content": results})

    return {
        "task_id": task["id"],
        "trial": trial,
        "agent": agent.name,
        "stop_reason": stop_reason,
        "reply": "\n".join(b["text"] for b in blocks if b["type"] == "text").strip(),
        "tool_calls": calls,
        "final_state": {"refunds": store.refunds},
        "usage": usage,
        "latency_s": round(time.time() - started, 2),
        "messages": messages,
    }
