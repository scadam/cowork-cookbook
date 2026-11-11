#!/usr/bin/env python3
"""Test a new skill on a period with a known answer.

Compares the draft the new skill produced for a past period with the version
the person actually sent, line by line, and checks that no figure changed.

Usage
  python3 test_compare.py --draft draft.json --approved approved.json
                          [--table table.json] [--period "September 2026"]

draft.json and approved.json hold {"period": "...", "lines": [{"line": "...",
"figure": 6.1, "text": "...", "status": "Supported"}], "questions": [{"owner":
"...", "question": "..."}]}. table.json is the script output for the period
(for example from variance_table.py table); when given, every draft figure is
checked against it, otherwise against the approved version.
The output is card-ready: lines covered, the same as approved, different with
reasons, questions it would have sent, and figures changed (must be none).
Standard library only.
"""
from __future__ import annotations

import argparse
import json
import re
import sys

STOP = {"the", "a", "an", "and", "or", "of", "for", "to", "in", "on", "at", "by", "with", "from", "was",
        "were", "is", "are", "be", "been", "this", "that", "than", "after", "but", "its", "it", "as",
        "source", "budget", "above", "below", "against", "month", "period", "because", "due", "which",
        "into", "their", "there", "has", "had", "have", "per", "cent", "m", "us"}
UP = re.compile(r"\b(above|higher|ahead|over|favourable|up)\b", re.I)
DOWN = re.compile(r"\b(below|lower|behind|under|adverse|down)\b", re.I)


def load(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def key(name: str) -> str:
    text = re.sub(r"[^a-z0-9& ]", " ", str(name).lower())
    text = text.replace("general and administration", "g&a").replace("g & a", "g&a")
    return " ".join(text.split())


def stem(token: str) -> str:
    for suffix in ("ing", "ed", "es", "s"):
        if len(token) > 4 and token.endswith(suffix):
            return token[: -len(suffix)]
    return token


def content(text: str, line_name: str) -> set[str]:
    skip = set(key(line_name).split())
    toks = re.findall(r"[a-z]+", str(text).lower())
    return {stem(t) for t in toks if t not in STOP and t not in skip and len(t) > 2}


def direction(text: str, figure) -> str | None:
    t = str(text)
    t = re.sub(r"^[^:]*:", "", t)  # ignore the line name before the colon
    first = t.split(".")[0] if t else ""
    if UP.search(first) and not DOWN.search(first):
        return "up"
    if DOWN.search(first) and not UP.search(first):
        return "down"
    return None


def fmt(value) -> str:
    if value is None:
        return "none"
    value = round(float(value), 1)
    return ("+" if value > 0 else ("-" if value < 0 else "")) + f"{abs(value):.1f}"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Compare a test draft with what was actually sent.")
    parser.add_argument("--draft", required=True)
    parser.add_argument("--approved", required=True)
    parser.add_argument("--table")
    parser.add_argument("--period")
    parser.add_argument("--out", help="also write the result to this file")
    args = parser.parse_args(argv)
    try:
        draft, approved = load(args.draft), load(args.approved)
        table = load(args.table) if args.table else None
    except (OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"errors": [str(exc)]}))
        return 1

    d_lines = {key(l["line"]): l for l in draft.get("lines", [])}
    a_lines = {key(l["line"]): l for l in approved.get("lines", [])}
    source = {}
    if table:
        for row in table.get("lines", []):
            source[key(row["line"])] = row.get("variance", row.get("value"))
    else:
        for k, l in a_lines.items():
            source[k] = l.get("figure")

    same, different, missing, results = 0, [], [], []
    for k, a in a_lines.items():
        d = d_lines.get(k)
        if d is None:
            missing.append(a["line"])
            results.append({"line": a["line"], "result": "missing"})
            continue
        reasons = []
        if a.get("figure") is not None and d.get("figure") is not None and \
                round(float(a["figure"]), 1) != round(float(d["figure"]), 1):
            reasons.append(f"figure {fmt(d['figure'])} where the sent version has {fmt(a['figure'])}")
        da, dd = direction(a.get("text", ""), a.get("figure")), direction(d.get("text", ""), d.get("figure"))
        if da and dd and da != dd:
            reasons.append("says the opposite direction against budget")
        ca, cd = content(a.get("text", ""), a["line"]), content(d.get("text", ""), d["line"])
        overlap = len(ca & cd) / len(ca | cd) if (ca | cd) else 1.0
        if overlap < 0.34:
            reasons.append("gives a different driver")
        if a.get("status") and d.get("status") and a["status"] != d["status"]:
            reasons.append(f"evidence status {d['status']} where the sent version is {a['status']}")
        if reasons:
            different.append({"line": a["line"], "reasons": reasons,
                              "reasons_text": "; ".join(reasons)[:1].upper() + "; ".join(reasons)[1:] + "."})
            results.append({"line": a["line"], "result": "different", "overlap": round(overlap, 2)})
        else:
            same += 1
            results.append({"line": a["line"], "result": "same", "overlap": round(overlap, 2)})
    extra = [d["line"] for k, d in d_lines.items() if k not in a_lines]

    changed = []
    for k, d in d_lines.items():
        if d.get("figure") is None or k not in source or source[k] is None:
            continue
        if round(float(d["figure"]), 1) != round(float(source[k]), 1):
            changed.append({"line": d["line"], "draft": fmt(d["figure"]), "source": fmt(source[k])})

    questions = [{"owner": q.get("owner", "Owner not stated"), "question": q.get("question", "")}
                 for q in draft.get("questions", [])]
    total = len(a_lines)
    covered = total - len(missing)
    period = args.period or approved.get("period") or draft.get("period") or "the test period"
    if changed:
        verdict = "Not ready: a figure changed. Fix it before keeping the skill."
    elif not different and not missing:
        verdict = "Ready to keep: every line matches what you sent."
    else:
        verdict = "Close: check the differences before keeping it."
    out = {
        "period_text": period, "lines_total": total, "covered": covered,
        "covered_text": f"{covered} of {total}", "same": same,
        "different": different, "different_count": len(different),
        "missing": missing, "missing_text": ", ".join(missing),
        "extra": extra, "extra_text": ", ".join(extra),
        "questions": questions, "questions_count": len(questions),
        "figures_changed": changed, "figures_changed_count": len(changed), "figures_ok": not changed,
        "verdict_text": verdict, "line_results": results,
    }
    text = json.dumps(out, ensure_ascii=False, indent=1)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
