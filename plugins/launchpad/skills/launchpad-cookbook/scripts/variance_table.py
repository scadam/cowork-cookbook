#!/usr/bin/env python3
"""Variance commentary: every figure, worked out by a script.

Subcommands
  table      variance per line against budget, materiality and ranking
  tieout     sum of the lines against the control totals you were given
  questions  one question per gap, grouped by owner (drafted, never sent)
  figures    check that every figure in a draft matches the table exactly

Usage
  python3 variance_table.py table --data period.json [--threshold 3.0] [--percent 0]
  python3 variance_table.py tieout --data period.json
  python3 variance_table.py questions --data period.json
  python3 variance_table.py figures --draft draft.json --table table.json

The period file holds: entity, period, unit, threshold, control_totals
(optional) and lines [{line, type: income|cost, actual, budget, owner,
explanation: {text, status, evidence, asked_on}}]. Favourable variances are
positive: actual minus budget for income, budget minus actual for costs.
Figures are never changed; the script only reads and compares them.
Standard library only.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import OrderedDict

STATUSES = ["Supported", "Partly supported", "Not supported", "Awaiting owner"]
GAP_STATUSES = {"Partly supported", "Not supported"}


def load(path: str):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def period_block(data: dict, period: str | None) -> dict:
    """Accept either a single period file or a sample file with several periods."""
    if "lines" in data:
        return data
    periods = data.get("periods", {})
    if period and period in periods:
        return periods[period]
    if data.get("current") in periods:
        return periods[data["current"]]
    raise ValueError("no period with lines found; pass --period")


def fmt(value: float) -> str:
    text = f"{abs(value):.1f}"
    if round(value, 1) == 0:
        return "0.0"
    return ("+" if value > 0 else "-") + text


def table(block: dict, threshold: float | None, percent: float | None) -> dict:
    unit = block.get("unit", "")
    threshold = float(block.get("threshold", 0) if threshold is None else threshold)
    percent = float(block.get("threshold_percent", 0) if percent is None else percent)
    rows = []
    for item in block["lines"]:
        actual, budget = float(item["actual"]), float(item["budget"])
        kind = item.get("type", "income").lower()
        variance = round(actual - budget if kind == "income" else budget - actual, 1)
        pct = round(variance / budget * 100, 1) if budget else None
        material = abs(variance) >= threshold or (percent and pct is not None and abs(pct) >= percent)
        if kind == "income":
            words = "above budget" if actual > budget else ("below budget" if actual < budget else "on budget")
        else:
            words = "above budget" if actual > budget else ("below budget" if actual < budget else "on budget")
        rows.append(OrderedDict([
            ("line", item["line"]), ("type", kind), ("actual", actual), ("budget", budget),
            ("variance", variance), ("variance_text", fmt(variance)),
            ("direction", "favourable" if variance > 0 else ("adverse" if variance < 0 else "none")),
            ("against_budget", words), ("percent", pct), ("material", bool(material)),
            ("owner", item.get("owner", "Not stated")),
        ]))
    material_rows = sorted((r for r in rows if r["material"]), key=lambda r: -abs(r["variance"]))
    for rank, r in enumerate(material_rows, 1):
        r["rank"] = rank
    income = [r for r in rows if r["type"] == "income"]
    costs = [r for r in rows if r["type"] == "cost"]
    totals = {
        "income_actual": round(sum(r["actual"] for r in income), 1),
        "income_budget": round(sum(r["budget"] for r in income), 1),
        "cost_actual": round(sum(r["actual"] for r in costs), 1),
        "cost_budget": round(sum(r["budget"] for r in costs), 1),
        "net_variance": round(sum(r["variance"] for r in rows), 1),
    }
    totals["net_variance_text"] = fmt(totals["net_variance"])
    rule = f"lines at or above {threshold:g} {unit} against budget".strip()
    if percent:
        rule += f", or {percent:g}% of budget"
    return {
        "entity": block.get("entity", ""), "period": block.get("period", ""), "unit": unit,
        "rule": rule, "lines": rows, "material": [r["line"] for r in material_rows],
        "material_count": len(material_rows), "totals": totals,
        "card_lines": [{"line": r["line"], "variance_text": r["variance_text"],
                        "against_budget": r["against_budget"]} for r in material_rows],
    }


def tieout(block: dict) -> dict:
    controls = block.get("control_totals") or {}
    t = table(block, None, None)["totals"]
    checks = []
    for key, label in (("income_actual", "Income, actual"), ("income_budget", "Income, budget"),
                       ("cost_actual", "Costs, actual"), ("cost_budget", "Costs, budget")):
        if key in controls:
            diff = round(t[key] - float(controls[key]), 1)
            checks.append({"total": label, "from_lines": t[key], "control": float(controls[key]),
                           "difference": diff, "tied": diff == 0})
    return {"period": block.get("period", ""), "checks": checks,
            "tied": all(c["tied"] for c in checks) if checks else None,
            "note": "No control totals were given." if not checks else ""}


def questions(block: dict) -> dict:
    t = table(block, None, None)
    by_line = {r["line"]: r for r in t["lines"]}
    by_owner: "OrderedDict[str, list]" = OrderedDict()
    awaiting = []
    counts = {s: 0 for s in STATUSES}
    for item in block["lines"]:
        row = by_line[item["line"]]
        if not row["material"]:
            continue
        exp = item.get("explanation") or {}
        status = exp.get("status", "Awaiting owner")
        if status not in STATUSES:
            status = "Awaiting owner"
        counts[status] += 1
        owner = item.get("owner", "Owner not stated")
        if status in GAP_STATUSES:
            by_owner.setdefault(owner, []).append({
                "line": item["line"], "variance_text": row["variance_text"], "status": status,
                "gap": exp.get("gap", "The evidence does not fully support the explanation."),
            })
        elif status == "Awaiting owner":
            awaiting.append({"line": item["line"], "owner": owner, "asked_on": exp.get("asked_on", "Not stated")})
    total = sum(len(v) for v in by_owner.values())
    return {
        "period": block.get("period", ""), "status_counts": counts,
        "questions_total": total, "owners_total": len(by_owner),
        "by_owner": [{"owner": o, "questions": q} for o, q in by_owner.items()],
        "awaiting_owner": awaiting,
        "summary": f"{total} question{'s' if total != 1 else ''} drafted for owners, not sent",
    }


def figures(draft: dict, table_out: dict) -> dict:
    expected = {r["line"].lower(): r for r in table_out.get("lines", [])}
    changed, checked = [], 0
    for line in draft.get("lines", []):
        key = str(line.get("line", "")).lower()
        if key not in expected or line.get("figure") is None:
            continue
        checked += 1
        want = expected[key]["variance"]
        got = round(float(line["figure"]), 1)
        if got != want:
            changed.append({"line": line["line"], "draft": fmt(got), "source": fmt(want)})
    return {"checked": checked, "changed": changed, "figures_ok": not changed}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Variance figures, worked out by a script.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("table", "tieout", "questions"):
        p = sub.add_parser(name)
        p.add_argument("--data", required=True)
        p.add_argument("--period")
        p.add_argument("--out", help="also write the result to this file")
        if name == "table":
            p.add_argument("--threshold", type=float)
            p.add_argument("--percent", type=float)
    f = sub.add_parser("figures")
    f.add_argument("--draft", required=True)
    f.add_argument("--table", required=True)
    f.add_argument("--out", help="also write the result to this file")
    args = parser.parse_args(argv)
    try:
        if args.cmd == "figures":
            result = figures(load(args.draft), load(args.table))
        else:
            block = period_block(load(args.data), args.period)
            if args.cmd == "table":
                result = table(block, args.threshold, args.percent)
            elif args.cmd == "tieout":
                result = tieout(block)
            else:
                result = questions(block)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(json.dumps({"errors": [str(exc)]}))
        return 1
    text = json.dumps(result, ensure_ascii=False, indent=1)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
