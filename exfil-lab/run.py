"""Run every exfiltration scenario against each defence layer, save the transcripts, print the matrix.

    python run.py                    # all scenarios x {none, each layer, all}
    python run.py --encode base64    # the attacker changes one phrase: base64 instead of URL-encoding
    python run.py --scenario image --show

No API key, no dependencies beyond Python 3.10+. Nothing leaves 127.0.0.1.
"""

import argparse
import json
from datetime import datetime
from pathlib import Path

from lab import CANARY, LAYER_HELP, LAYERS, SCENARIOS, run_scenario

HERE = Path(__file__).parent
COLUMNS = [("none", [])] + [(layer, [layer]) for layer in LAYERS] + [("all", LAYERS)]


def short(text, n=110):
    text = text.replace("\n", "\\n")
    return text if len(text) <= n else text[: n - 3] + "..."


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--scenario", choices=list(SCENARIOS), help="run one scenario (default: all five)")
    p.add_argument("--encode", choices=["url", "base64"], default="url",
                   help="how the planted text asks for the conversation to be encoded (default url)")
    p.add_argument("--show", action="store_true", help="print what the attacker's server received")
    p.add_argument("--out", type=Path, help="where to save transcripts (default runs/<timestamp>)")
    args = p.parse_args()

    out = args.out or HERE / "runs" / datetime.now().strftime("%Y%m%d-%H%M%S")
    out.mkdir(parents=True, exist_ok=True)
    scenarios = [args.scenario] if args.scenario else list(SCENARIOS)

    results = {}
    for s in scenarios:
        for col, layers in COLUMNS:
            r = run_scenario(s, layers, args.encode)
            results[s, col] = r
            (out / f"{s}__{col}.json").write_text(json.dumps(r, indent=2, ensure_ascii=False))

    print(f"\nexfil-lab: did the canary {CANARY} reach the attacker?  (encoding: {args.encode})\n")
    print(f"{'scenario':16}" + "".join(f"{col:>11}" for col, _ in COLUMNS))
    for s in scenarios:
        cells = ["LEAKED" if results[s, col]["leaked"] else "-" for col, _ in COLUMNS]
        print(f"{s:16}" + "".join(f"{c:>11}" for c in cells))

    print("\nHow it left, with no defences:")
    for s in scenarios:
        print(f"  {s:16} {results[s, 'none']['leaked_via'] or 'did not leak'}")

    print("\nLayers:")
    for layer in LAYERS:
        print(f"  {layer:10} {LAYER_HELP[layer]}")

    if args.show:
        for s in scenarios:
            print(f"\n--- {s}: what the attacker's server received (no defences) ---")
            for e in results[s, "none"]["attacker_log"]:
                print(f"  {e['method']} {e['host']}{short(e['path'] + (' ' + e['body'] if e['body'] else ''))}")
                print(f"      via {e['via']}")

    print(f"\nTranscripts: {out}")


if __name__ == "__main__":
    main()
