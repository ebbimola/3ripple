# flaky-agent: one refund task, twenty runs

Companion lab for **"Why Your Test Suite Can't Catch Agent Failures"** (Agent Evaluation, part 1).

A small support agent handles one refund request. It has three tools over a mock order store:

| Tool | What it does |
| --- | --- |
| `find_orders(email)` | Lists the customer's orders: ids, dates and totals only |
| `lookup_order(order_id)` | Returns items, prices and the delivery date |
| `issue_refund(order_id, amount, reason)` | Records a refund in the mock store |

There are two tasks. Both have exactly one right end state: a single refund of **£49.99** (the headphones) on order **A1041**.

| Task | The customer says | Why it is not trivial |
| --- | --- | --- |
| `stopped-charging` (default) | Her headphones stopped charging, the case is useless without them, refund the whole order | The order is 55 days old, past the 30-day window. Faults are refundable at any time, but the £12 case is not faulty, so "the whole order" (£61.99) is wrong |
| `cracked` | Her headphones arrived with a cracked earcup | The order total (£61.99) and a newer order (A1057) are both there to be refunded by mistake |

The lab runs a task 20 times and grades the same transcripts three ways:

1. **Exact match.** A snapshot test: the reply must equal `expected/<task>.txt`, which is run 1's reply.
2. **Loose match.** The reply mentions "refund". This also passes "I'm afraid I can't process a refund".
3. **Graded.** It checks the store, not the wording:
   - **Outcome:** exactly one refund, on the right order, for the right amount.
   - **Path:** `lookup_order("A1041")` came before `issue_refund`.
   - Then pass rate, outcome spread, pass@1, and pass^k for k = 2, 4, 8.

pass^k is the [τ-bench](https://sierra.ai/blog/benchmarking-ai-agents) reliability metric: the chance that *all* k attempts succeed. With n trials and c passes it is estimated as C(c, k) / C(n, k).

## Run it

Requires Python 3.10+ and an Anthropic API key. Twenty runs cost about $0.60 on `claude-opus-5-5` at low effort, and about 2 cents on `claude-haiku-5-5`.

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...
python run.py
```

`run.py` also reads the key from a `.env` file in this folder, which git ignores. Each run's full transcript (messages, tool calls, refunds, token usage) is saved to `runs/<timestamp>/run-NN.json`, and the report prints at the end. To re-grade a saved batch without calling the API:

```bash
python grade.py runs/<timestamp>
```

No key? Grade the batches that ship with the repo:

```bash
python grade.py sample-runs/stopped-charging
python grade.py sample-runs/cracked
```

Options: `--task cracked`, `-n 40` for more runs, `-k 4` for a different headline k, and `--effort high` or `--model claude-haiku-5-5` to compare. Delete a file in `expected/` to take a fresh snapshot on the next run.

## What we got

Run on 27 October 2026. Each row is one batch of 20 runs, with the exact-match snapshot taken from that batch's run 1.

| Task | Model | Exact match | Loose match | Graded (outcome + path) | pass^8 | Cost |
| --- | --- | --- | --- | --- | --- | --- |
| `stopped-charging` | Claude Opus 5.5 | 1/20 | 20/20 | 20/20 | 1.00 | $0.64 |
| `stopped-charging` | Claude Haiku 5.5 | 1/20 | 20/20 | 20/20 | 1.00 | $0.02 |
| `cracked` | Claude Opus 5.5 | 1/20 | 20/20 | 20/20 | 1.00 | $0.59 |
| `cracked` | Claude Haiku 5.5 | 1/20 | 20/20 | 20/20 | 1.00 | $0.02 |

All 80 runs did the right thing, by the same route every time: `find_orders`, then `lookup_order` on both orders, then one £49.99 refund on A1041. Only the wording changed: all 80 replies were different. In every batch the exact-match test passed only run 1, the reply it was copied from, so it failed 76 correct runs out of 80.

What the batches did *not* show is just as useful:
- No run refused, so the loose assertion never had a refusal to wave through.
- With no failures, pass^k equals pass@1.

That is a result, not a dead end. Twenty passes out of twenty is evidence the agent handles this task. One green run would not have been.

If your agent fails sometimes, the spread and the drop from pass@1 to pass^k show up in the same report. To see it, try your own system prompt, a harder task in `agent.py`, or an older model.

## Sample output

`python grade.py sample-runs/stopped-charging`, trimmed:

```text
20 runs of the 'stopped-charging' refund task on claude-opus-5-5  (sample-runs/stopped-charging)

 run  exact  loose  outcome  path   graded  what happened
   1  PASS   PASS   PASS   PASS   PASS    correct refund
   2  fail   PASS   PASS   PASS   PASS    correct refund
   3  fail   PASS   PASS   PASS   PASS    correct refund
 ...
  20  fail   PASS   PASS   PASS   PASS    correct refund

1. Exact-match assertion (snapshot in expected/stopped-charging.txt)
   1/20 passed. Same task, same prompt, same tools: the wording moves, so the test flips.

2. Loose assertion (reply mentions 'refund')
   20/20 passed.
   Every run that passed it also issued the right refund, this time.

3. Graded report
   Pass rate (outcome + path): 20/20 = 100%
   Outcome check (right order, right amount, one refund): 20/20
   Path check (order looked up before the refund):         20/20 runs that refunded
   Outcome spread:
      20  correct refund
   pass@1 = 1.00
   pass^2 = 1.00   (pass@2 = 1.00)
   pass^4 = 1.00   (pass@4 = 1.00)
   pass^8 = 1.00   (pass@8 = 1.00)
```

## Files

| File | What it is |
| --- | --- |
| `agent.py` | System prompt, the two tasks, tools, mock store, and the tool-use loop |
| `run.py` | Runs a task n times in parallel, saves transcripts, prints the report |
| `grade.py` | The three graders and the pass@k / pass^k estimators |
| `expected/` | The snapshots the exact-match assertion compares against |
| `sample-runs/` | The two Opus 5.5 batches from the table above, 20 transcripts each |

Nothing in the lab is randomised on purpose. Any variation comes from the model.
