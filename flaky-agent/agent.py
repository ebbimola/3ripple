"""A small refund agent: two lookup tools, one write tool, a mock order store.

Nothing here is deliberately random. Any variation between runs comes from the model.
"""

import copy
import json

TODAY = "2026-10-27"

SYSTEM = f"""You are the support agent for Northwind Audio. Today is {TODAY}.

Refund policy:
- Items can be refunded within 30 days of delivery.
- Items that arrived damaged, or that develop a fault, can be refunded at any time.
- Refund only the affected items, never more than was paid for them.

Use the tools to check the order before you act. The customer will not reply again,
so resolve the request (or decline it) in this conversation, then write your reply to them."""

# Each task has one right end state: a single refund of this amount on this order.
TASKS = {
    "cracked": {
        "prompt": "Hi, it's Priya Shah (priya.shah@example.com). The headphones I ordered from you "
                  "arrived with the left earcup cracked. Can I get my money back for them please?",
        "order_id": "A1041",
        "amount": 49.99,
    },
    # Faulty after the 30-day window, and the customer asks for more than policy allows:
    # the headphones qualify, the carry case does not.
    "stopped-charging": {
        "prompt": "Hi, Priya Shah here (priya.shah@example.com). My H200 headphones stopped charging "
                  "last week, so they're useless now, and so is the carry case I bought for them. "
                  "Please refund the whole order.",
        "order_id": "A1041",
        "amount": 49.99,
    },
}

# The mock store. Each trial gets a fresh deep copy.
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
        "input_schema": {
            "type": "object",
            "properties": {"email": {"type": "string"}},
            "required": ["email"],
            "additionalProperties": False,
        },
    },
    {
        "name": "lookup_order",
        "description": "Get one order's full details: items, prices and delivery date.",
        "input_schema": {
            "type": "object",
            "properties": {"order_id": {"type": "string"}},
            "required": ["order_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "issue_refund",
        "description": "Refund an amount (GBP) against an order. This moves real money.",
        "input_schema": {
            "type": "object",
            "properties": {
                "order_id": {"type": "string"},
                "amount": {"type": "number"},
                "reason": {"type": "string"},
            },
            "required": ["order_id", "amount", "reason"],
            "additionalProperties": False,
        },
    },
]


class Store:
    def __init__(self):
        self.orders = copy.deepcopy(ORDERS)
        self.refunds = []

    def find_orders(self, email):
        return [
            {"order_id": oid, "placed": o["placed"], "total": o["total"]}
            for oid, o in self.orders.items()
            if o["customer"] == email.strip().lower()
        ]

    def lookup_order(self, order_id):
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


def run_trial(client, task, model, effort, max_turns=10):
    """Run one task once. Returns a transcript: messages, tool calls, final state."""
    store = Store()
    messages = [{"role": "user", "content": TASKS[task]["prompt"]}]
    calls = []
    usage = {"input_tokens": 0, "output_tokens": 0}

    for _ in range(max_turns):
        resp = client.messages.create(
            model=model,
            max_tokens=16000,
            system=SYSTEM,
            tools=TOOLS,
            output_config={"effort": effort},
            messages=messages,
        )
        usage["input_tokens"] += resp.usage.input_tokens
        usage["output_tokens"] += resp.usage.output_tokens
        messages.append({"role": "assistant", "content": [b.model_dump(exclude_none=True) for b in resp.content]})
        if resp.stop_reason != "tool_use":
            break

        results = []
        for block in resp.content:
            if block.type != "tool_use":
                continue
            call = {"tool": block.name, "input": block.input}
            try:
                output = getattr(store, block.name)(**block.input)
                call["output"] = output
                results.append({"type": "tool_result", "tool_use_id": block.id, "content": json.dumps(output)})
            except Exception as e:  # tool errors go back to the model, as they would in production
                call["error"] = str(e)
                results.append({"type": "tool_result", "tool_use_id": block.id, "content": str(e), "is_error": True})
            calls.append(call)
        messages.append({"role": "user", "content": results})

    reply = "\n".join(b.text for b in resp.content if b.type == "text").strip()
    return {
        "task": task,
        "model": model,
        "effort": effort,
        "stop_reason": resp.stop_reason,
        "reply": reply,
        "tool_calls": calls,
        "refunds": store.refunds,
        "usage": usage,
        "messages": messages,
    }
