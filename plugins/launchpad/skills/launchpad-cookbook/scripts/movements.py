#!/usr/bin/env python3
"""MBR brief: what moved since last month, worked out by a script.

Usage
  python3 movements.py --current current.json --previous previous.json
                       [--forecast forecast.json] [--threshold 0.5] [--top 5]

Each file holds {"period": "...", "unit": "US$m", "lines": [{"line": "...",
"value": 12.3, "business": "optional"}]}. The output lists every line with its
movement since last month (and against forecast when given), ranked by size,
with the lines at or above the threshold flagged for questions. Figures are
read and compared, never changed. Standard library only.
"""
from __future__ import annotations

import argparse
import json
import sys


def load(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def fmt(value: float) -> str:
    if round(value, 1) == 0:
        return "0.0"
    return ("+" if value > 0 else "-") + f"{abs(value):.1f}"


def index(block: dict) -> dict:
    return {str(item["line"]).strip().lower(): item for item in block.get("lines", [])}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="What moved since last month.")
    parser.add_argument("--current", required=True)
    parser.add_argument("--previous", required=True)
    parser.add_argument("--forecast")
    parser.add_argument("--threshold", type=float, default=0.0)
    parser.add_argument("--top", type=int, default=5)
    parser.add_argument("--out", help="also write the result to this file")
    args = parser.parse_args(argv)
    try:
        cur, prev = load(args.current), load(args.previous)
        fc = load(args.forecast) if args.forecast else None
    except (OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"errors": [str(exc)]}))
        return 1
    prev_i = index(prev)
    fc_i = index(fc) if fc else {}
    rows, missing = [], []
    for item in cur.get("lines", []):
        key = str(item["line"]).strip().lower()
        value = float(item["value"])
        row = {"line": item["line"], "business": item.get("business", ""), "value": value}
        if key in prev_i:
            move = round(value - float(prev_i[key]["value"]), 1)
            row.update({"previous": float(prev_i[key]["value"]), "movement": move, "movement_text": fmt(move)})
        else:
            row.update({"previous": None, "movement": None, "movement_text": "new this month"})
            missing.append(item["line"])
        if key in fc_i:
            gap = round(value - float(fc_i[key]["value"]), 1)
            row.update({"forecast": float(fc_i[key]["value"]), "against_forecast": gap,
                        "against_forecast_text": fmt(gap)})
        row["flag"] = row["movement"] is not None and abs(row["movement"]) >= args.threshold
        rows.append(row)
    dropped = [prev_i[k]["line"] for k in prev_i if k not in index(cur)]
    ranked = sorted((r for r in rows if r["movement"] is not None), key=lambda r: -abs(r["movement"]))
    flagged = [r for r in ranked if r["flag"]][: args.top]
    out = {
        "period": cur.get("period", ""), "previous_period": prev.get("period", ""),
        "unit": cur.get("unit", prev.get("unit", "")), "threshold": args.threshold,
        "lines": rows, "moved": [{"line": r["line"], "movement_text": r["movement_text"],
                                  "business": r["business"]} for r in flagged],
        "new_lines": missing, "dropped_lines": dropped,
        "summary": f"{len(flagged)} line{'s' if len(flagged) != 1 else ''} moved by "
                   f"{args.threshold:g} {cur.get('unit', '')} or more since last month".replace("  ", " "),
    }
    text = json.dumps(out, ensure_ascii=False, indent=1)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
