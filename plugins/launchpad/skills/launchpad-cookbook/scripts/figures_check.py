#!/usr/bin/env python3
"""Committee papers and other documents: check every figure, by script.

Usage
  python3 figures_check.py --draft draft.json [--fields decision_sought,recommendation,...]

The draft file holds:
  {"title": "...",
   "fields": {"decision_sought": "...", "recommendation": "...", "background": "...",
              "risks": "...", "next_steps": "..."},
   "figures": [{"id": "f1", "text": "US$4.2m", "value": 4.2, "unit": "US$m",
                "source": "Q3 forecast workbook", "as_at": "30 Sep 2026",
                "derived": {"op": "sum|difference|percent|ratio", "of": ["f2", "f3"]}}]}

It reports: front-sheet fields that are missing (they must say "not stated"
rather than be left out), figures without a source or as-at date, and derived
figures that do not match a recalculation. It never changes a figure.
Standard library only.
"""
from __future__ import annotations

import argparse
import json
import sys

DEFAULT_FIELDS = ["decision_sought", "recommendation", "background", "risks", "next_steps"]
LABELS = {"decision_sought": "Decision sought", "recommendation": "Recommendation",
          "background": "Background", "risks": "Risks", "next_steps": "Next steps"}
TOLERANCE = 0.05


def recalc(op: str, values: list[float]) -> float | None:
    if not values:
        return None
    if op == "sum":
        return sum(values)
    if op == "difference" and len(values) == 2:
        return values[0] - values[1]
    if op == "percent" and len(values) == 2 and values[1]:
        return values[0] / values[1] * 100
    if op == "ratio" and len(values) == 2 and values[1]:
        return values[0] / values[1]
    return None


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Check every figure in a draft.")
    parser.add_argument("--draft", required=True)
    parser.add_argument("--fields", default=",".join(DEFAULT_FIELDS))
    parser.add_argument("--out", help="also write the result to this file")
    args = parser.parse_args(argv)
    try:
        with open(args.draft, encoding="utf-8") as fh:
            draft = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"errors": [str(exc)]}))
        return 1
    fields = [f.strip() for f in args.fields.split(",") if f.strip()]
    findings = []
    given = draft.get("fields", {})
    for field in fields:
        value = str(given.get(field, "")).strip()
        if not value:
            findings.append({"kind": "mandatory", "where": LABELS.get(field, field),
                             "finding": "Missing. Write the content, or 'not stated' with the reason."})
    figures = {f.get("id"): f for f in draft.get("figures", [])}
    checked = 0
    for fid, fig in figures.items():
        where = f"Figure {fid} ({fig.get('text', fig.get('value'))})"
        if not str(fig.get("source", "")).strip():
            findings.append({"kind": "mandatory", "where": where, "finding": "No source. Add it, or mark the figure not stated."})
        if not str(fig.get("as_at", "")).strip():
            findings.append({"kind": "mandatory", "where": where, "finding": "No as-at date."})
        derived = fig.get("derived")
        if derived:
            parts = [figures.get(x, {}).get("value") for x in derived.get("of", [])]
            if any(p is None for p in parts):
                findings.append({"kind": "mandatory", "where": where,
                                 "finding": "Worked out from figures that are not in the paper."})
                continue
            expected = recalc(derived.get("op", ""), [float(p) for p in parts])
            checked += 1
            if expected is None:
                findings.append({"kind": "recommended", "where": where, "finding": "Cannot recalculate this figure."})
            elif abs(float(fig.get("value", 0)) - expected) > TOLERANCE:
                findings.append({"kind": "mandatory", "where": where,
                                 "finding": f"Recalculates to {expected:,.2f}, not {float(fig.get('value', 0)):,.2f}."})
    m = r = 0
    for f in findings:
        if f["kind"] == "mandatory":
            m += 1
            f["id"] = f"M{m}"
        else:
            r += 1
            f["id"] = f"R{r}"
    out = {"title": draft.get("title", ""), "figures": len(figures), "derived_checked": checked,
           "findings": findings, "mandatory": m, "recommended": r,
           "figures_ok": not any(f["kind"] == "mandatory" and f["where"].startswith("Figure") for f in findings)}
    text = json.dumps(out, ensure_ascii=False, indent=1)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
