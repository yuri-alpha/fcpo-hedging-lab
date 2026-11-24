"""Export an offline dashboard from demo data or a user-supplied market CSV."""

import argparse
import json
import webbrowser
from pathlib import Path

from hedge_lab import read_market, summarize, walk_forward


ROOT = Path(__file__).resolve().parent
WINDOWS = (12, 24, 36)
COSTS = (0, 2, 5, 10)
DEMO_START = "2018-01"
DEMO_END = "2025-12"


def make_dashboard(market, start, end, provenance, demo=False):
    cases = {}
    for name in market.contracts:
        for window in WINDOWS:
            for cost in COSTS:
                rows = walk_forward(market, name, window, start, end, cost)
                cases[f"{name}/{window}/{cost}"] = {"rows": rows, "metrics": summarize(rows)}
    return {
        "contracts": market.contracts,
        "windows": WINDOWS,
        "costs": COSTS,
        "start": start,
        "end": end,
        "demo": demo,
        "provenance": provenance,
        "cases": cases,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, help="Use a local CSV instead of the synthetic demo.")
    parser.add_argument("--start", help="First evaluation end-month, YYYY-MM.")
    parser.add_argument("--end", help="Last evaluation end-month, YYYY-MM.")
    parser.add_argument("--source", help="Provenance label required for a custom dataset.")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--open", action="store_true", help="Open the exported HTML in a browser.")
    args = parser.parse_args()
    if args.input and (not args.start or not args.end or not (args.source or "").strip()):
        parser.error("--input requires --start, --end and --source.")
    if not args.input and args.source:
        parser.error("--source can only be used with --input.")
    demo = args.input is None
    input_path = args.input or ROOT / "data" / "demo.csv"
    output = (args.output or ROOT / ("docs" if demo else "build") / "index.html").resolve()
    try:
        result = make_dashboard(
            read_market(input_path), args.start or DEMO_START, args.end or DEMO_END,
            args.source.strip() if args.input else "Seeded simulation with seven specified stress intervals",
            demo=demo,
        )
        template = (ROOT / "web" / "template.html").read_text(encoding="utf-8")
        css = (ROOT / "web" / "style.css").read_text(encoding="utf-8")
        script = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        payload = json.dumps(result, allow_nan=False, separators=(",", ":")).replace("<", "\\u003c")
        page = template.replace("{{STYLE}}", css).replace("{{SCRIPT}}", script).replace("{{PAYLOAD}}", payload)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(page, encoding="utf-8", newline="\n")
    except (OSError, ValueError) as exc:
        parser.exit(1, f"Dashboard build failed: {exc}\n")
    print(f"Wrote {output} ({len(result['cases'])} scenarios).")
    if args.open:
        webbrowser.open(output.as_uri())


if __name__ == "__main__":
    main()
