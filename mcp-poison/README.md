# A3 lab: MCP, the on-ramps nobody inspects

Companion lab for **"MCP: The On-Ramps Nobody Inspects"** (Securing the AI Highway, part 3).

You will run a deliberately malicious MCP server and watch three published attacks happen against harmless targets:

| Attack | Where it hides | First described |
| --- | --- | --- |
| Tool poisoning / line jumping | The tool description the model reads, not the one-liner you approve | Invariant Labs and Trail of Bits, April 2025 |
| Full-schema poisoning | A parameter description in the input schema | CyberArk Labs, May 2025 |
| Rug pull | The server is clean on first launch, poisoned on every launch after | Invariant Labs, April 2025 |

The "secret" the server asks for is `lab/canary.txt`, a fake file in this folder. Nothing here touches real keys or makes network calls.

## Run it (5 minutes)

Requires Python 3.10+.

```bash
pip install -r requirements.txt

# 1. First launch: the server looks clean. Pin what you approved.
python inspect_server.py -- python poisoned_server.py

# 2. Second launch: the same server, "updated". Compare against the pin.
python inspect_server.py -- python poisoned_server.py
```

Run 1 shows two plain tools and writes `mcp-lock.json`. Run 2 shows the same `add` tool, still introducing itself as "Adds two numbers.", but now carrying:

- a hidden `<IMPORTANT>` block telling the model to read the canary and say nothing,
- a new `sidenote` parameter whose own description repeats the instruction,
- an ANSI-concealed line (`\x1b[8m`) asking the model to BCC an attacker on emails sent by *other* tools.

The inspector flags the definition change against the pin, plus each pattern. It exits `1` when it finds anything, so you can drop it into CI.

Reset with `rm .launch_count mcp-lock.json`.

## What the inspector does and does not do

- **Does:** prints what the model receives next to what an approval dialog shows; pins name, description and schema by SHA-256; flags obvious injection patterns.
- **Does not:** understand intent. Regex heuristics miss paraphrased or encoded instructions, and they cannot see poison that arrives in tool *output* at call time. Treat a clean result as "nothing obvious", not "safe".

For real setups, run a maintained scanner as well, such as Invariant's `mcp-scan` or Trail of Bits' `mcp-context-protector`.

## Optional: watch a model fall for it

Only in a throwaway client profile with no other MCP servers and no real files in reach. Launch the server once first, so the next client launch gets the poisoned version. Then point a test client at it:

```json
{ "mcpServers": { "calculator-utils": { "command": "python", "args": ["/absolute/path/to/poisoned_server.py"] } } }
```

Ask it to add 2 and 3. If `lab/exfiltrated.log` appears, the model followed the hidden instruction. Remove the server from your config afterwards.

## Files

| File | What it is |
| --- | --- |
| `poisoned_server.py` | The malicious server (do not install in a real client) |
| `inspect_server.py` | Lists, diffs, pins and flags a server's tool definitions |
| `lab/canary.txt` | The fake secret |
