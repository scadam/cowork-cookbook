#!/usr/bin/env python3
"""Budget round: the summary tiles and overdue list, worked out by a script.

Usage
  python3 tracker_summary.py --tracker tracker.json --today 2026-11-13 [--due 2026-11-20]

The tracker file holds {"name": "...", "unit": "US$m", "columns": [...],
"rows": [{"cost_centre": "...", "owner": "...", "status": "...",
"submitted_date": "2026-11-09" or "", "value": 1.2, "target": 1.0,
"due": "2026-11-12"}]}. Statuses are matched loosely (submitted, in review,
in progress, not started, overdue). A line is overdue when it is not
submitted or in review and its due date (or --due) has passed.
Standard library only.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date


def parse_day(text) -> date | None:
    try:
        return date.fromisoformat(str(text)[:10]) if text else None
    except ValueError:
        return None


def status_of(raw: str) -> str:
    s = str(raw or "").strip().lower()
    if "review" in s:
        return "In review"
    if "submit" in s or s in {"done", "complete", "completed"}:
        return "Submitted"
    if "overdue" in s or "late" in s:
        return "Overdue"
    if "progress" in s or "draft" in s or "started" in s and "not" not in s:
        return "In progress"
    return "Not started"


def money(value: float, unit: str) -> str:
    sign = "-" if value < 0 else ("+" if value > 0 else "")
    return f"{sign}{abs(value):,.1f} {unit}".strip()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Budget round summary tiles.")
    parser.add_argument("--tracker", required=True)
    parser.add_argument("--today", default=date.today().isoformat())
    parser.add_argument("--due")
    parser.add_argument("--out", help="also write the result to this file")
    args = parser.parse_args(argv)
    try:
        with open(args.tracker, encoding="utf-8") as fh:
            tracker = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"errors": [str(exc)]}))
        return 1
    today = parse_day(args.today) or date.today()
    default_due = parse_day(args.due)
    unit = tracker.get("unit", "")
    counts = {"Submitted": 0, "In review": 0, "In progress": 0, "Not started": 0, "Overdue": 0}
    overdue, gap, rows = [], 0.0, []
    for row in tracker.get("rows", []):
        status = status_of(row.get("status"))
        due = parse_day(row.get("due")) or default_due
        if status not in ("Submitted", "In review") and due and due < today:
            status = "Overdue"
        counts[status] += 1
        if status in ("Submitted", "In review") and row.get("value") is not None and row.get("target") is not None:
            gap += float(row["value"]) - float(row["target"])
        if status == "Overdue":
            overdue.append({"cost_centre": row.get("cost_centre", ""), "owner": row.get("owner", "Owner not stated"),
                            "due": due.isoformat() if due else "not stated"})
        rows.append({**row, "status_now": status})
    total = sum(counts.values())
    owners = sorted({o["owner"] for o in overdue})
    out = {
        "name": tracker.get("name", "Tracker"), "today": today.isoformat(), "lines": total,
        "counts": counts, "gap_to_target": round(gap, 1), "gap_text": money(round(gap, 1), unit),
        "overdue": overdue, "overdue_owners": owners,
        "tiles": [
            {"label": "Submitted", "value": f"{counts['Submitted']} of {total}"},
            {"label": "In review", "value": str(counts["In review"])},
            {"label": "Overdue", "value": str(counts["Overdue"])},
            {"label": "Gap to target", "value": money(round(gap, 1), unit)},
        ],
        "progress": {"value": counts["Submitted"] + counts["In review"], "max": max(total, 1)},
        "chasers_to_draft": len(owners),
    }
    text = json.dumps(out, ensure_ascii=False, indent=1)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
