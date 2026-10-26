"""
Inspect an MCP server before you trust it.

    python inspect_server.py -- python poisoned_server.py

Connects over stdio, lists the tools, and for each one prints:
  * what an approval dialog typically shows (name + first line)
  * what the model actually receives (full description + input schema)
  * heuristic findings: hidden-instruction tags, secrecy language, file paths,
    control characters, unexpected recipients
Then it pins every tool definition by SHA-256 in mcp-lock.json. On the next
run, any changed definition is reported as a possible rug pull.

Heuristics catch the obvious cases only. Treat a clean result as "nothing
obvious", not "safe".
"""

import asyncio
import hashlib
import json
import re
import sys
from pathlib import Path

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

LOCK = Path(__file__).parent / "mcp-lock.json"

RULES = [
    ("hidden-instruction tag", re.compile(r"<\s*(important|system|instructions?)\s*>", re.I)),
    ("secrecy language", re.compile(r"do not (mention|tell|reveal)|don't (mention|tell)|without telling|silently", re.I)),
    ("file or secret path", re.compile(r"(~/|/home/|/etc/|\.ssh|id_rsa|mcp\.json|\.env\b|canary\.txt)", re.I)),
    ("pre-call instruction", re.compile(r"before (using|calling) (this|any) tool", re.I)),
    ("cross-tool instruction", re.compile(r"(any|other) tool|bcc|forward (all|every)", re.I)),
    ("control characters", re.compile(r"[\x00-\x08\x0b-\x1f\x7f]|​|‌|‍|⁠|﻿")),
]


def fingerprint(tool) -> str:
    blob = json.dumps(
        {"name": tool.name, "description": tool.description, "schema": tool.input_schema},
        sort_keys=True,
    )
    return hashlib.sha256(blob.encode()).hexdigest()


def scan_text(text: str) -> list[str]:
    return [label for label, rx in RULES if rx.search(text or "")]


def show(text: str) -> str:
    """Make control characters visible instead of letting the terminal act on them."""
    return (text or "").encode("unicode_escape").decode().replace("\\n", "\n")


async def main(cmd: list[str]) -> int:
    params = StdioServerParameters(command=cmd[0], args=cmd[1:])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = (await session.list_tools()).tools

    previous = json.loads(LOCK.read_text()) if LOCK.exists() else {}
    current, worst = {}, 0

    for tool in tools:
        fp = fingerprint(tool)
        current[tool.name] = fp
        schema_text = json.dumps(tool.input_schema)
        findings = scan_text(tool.description) + [f"schema: {f}" for f in scan_text(schema_text)]

        print("=" * 72)
        print(f"TOOL {tool.name}")
        print(f"  Approval dialog shows : {(tool.description or '').splitlines()[0] if tool.description else '(none)'}")
        print("  Model receives        :")
        for line in show(tool.description).splitlines():
            print(f"      {line}")
        print(f"  Input schema          : {schema_text}")

        if tool.name in previous and previous[tool.name] != fp:
            findings.insert(0, "DEFINITION CHANGED SINCE PINNED (possible rug pull)")
        elif tool.name not in previous and previous:
            findings.insert(0, "new tool since pinned")

        if findings:
            worst = 1
            for f in findings:
                print(f"  !! {f}")
        else:
            print("  ok: nothing obvious")

    removed = set(previous) - set(current)
    for name in sorted(removed):
        print(f"!! tool '{name}' was removed since pinned")

    if not previous:
        LOCK.write_text(json.dumps(current, indent=2))
        print(f"\nPinned {len(current)} tool definitions to {LOCK.name}.")
    else:
        print(f"\nCompared against {LOCK.name}. Delete it to re-pin after a reviewed change.")

    return worst


if __name__ == "__main__":
    if "--" not in sys.argv or sys.argv.index("--") == len(sys.argv) - 1:
        sys.exit("usage: python inspect_server.py -- <command to start the server>")
    sys.exit(asyncio.run(main(sys.argv[sys.argv.index("--") + 1 :])))
