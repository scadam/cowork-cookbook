#!/usr/bin/env python3
"""Launchpad for Cowork: signs of repeatable work, from titles and counts only.

  python3 patterns.py --input discovery.json [--out patterns.json]

Reads the same discovery file as signals.py (meeting titles, subjects of sent
mail, names of files, and counts such as editors and people shared with). It
never reads contents. It looks for five signs that work could become a skill,
an app or a routine:
  versions   the same document in several versions
  similar    many similar documents (one per client, week or month)
  people     several people work on it, or it is shared widely
  rhythm     it happens every week, month or quarter
  meeting    it is prepared for a recurring meeting
Private, confidential, personal, HR and medical items are dropped first.
Standard library only.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

SENSITIVE = re.compile(r"\b(private|personal|confidential|hr|human resources|medical|salary|salaries|payroll|bonus|"
                       r"appraisal|performance review|disciplinary|grievance|redundan\w+|interview|candidate|"
                       r"1:1|1-1|one to one)\b", re.I)
KIND = {"docx": "Document", "doc": "Document", "pdf": "Document", "pptx": "Deck", "ppt": "Deck",
        "xlsx": "Workbook", "xlsm": "Workbook", "xls": "Workbook", "csv": "Workbook"}
MONTH = (r"\b(january|jan|february|feb|march|mar|april|apr|may|june|jun|july|jul|august|aug|september|sept|sep|"
         r"october|oct|november|nov|december|dec)\b")
NOISE = re.compile(r"\b(v\d+(\.\d+)*|version\s*\d+|final|draft|rev\s*\d+|updated|latest|clean|copy|tracked|"
                   r"wk\s?\d+|week\s?\d+|q[1-4]|h[12]|fy\d{2,4}|\d{1,4})\b", re.I)
STOP = {"the", "and", "for", "with", "from", "pack", "review", "meeting", "call", "update", "weekly", "monthly",
        "team", "check", "sync", "draft", "final", "paper", "report"}


def is_sensitive(name: str, label: str = "") -> bool:
    return bool(SENSITIVE.search(name or "")) or (label or "").lower() in {"confidential", "highly confidential", "restricted", "private"}


def stem(name: str) -> str:
    base = name.rsplit(".", 1)[0].lower()
    base = re.sub(MONTH, " ", base)
    base = NOISE.sub(" ", base)
    return re.sub(r"[^a-z&]+", " ", base).strip()


def rhythm_of(names) -> str | None:
    joined = " ".join(names).lower()
    if re.search(r"\b(wk\s?\d+|week\s?\d+|weekly)\b", joined):
        return "every week"
    if re.search(MONTH, joined) or "monthly" in joined or "month-end" in joined or "month end" in joined:
        return "every month"
    if re.search(r"\b(q[1-4]|quarterly)\b", joined):
        return "every quarter"
    return None


def tokens(text: str) -> set:
    return {w for w in re.findall(r"[a-z]+", text.lower()) if len(w) > 3 and w not in STOP}


def build(disc: dict) -> dict:
    skipped = 0
    groups = defaultdict(list)
    for f in disc.get("files", []):
        name = str(f.get("name", "")).strip()
        if not name:
            continue
        if is_sensitive(name, str(f.get("label", ""))):
            skipped += 1
            continue
        key = stem(name)
        if key:
            groups[key].append(f)
    families = defaultdict(set)
    for key in groups:
        words = key.split()
        if len(words) >= 3:
            families[" ".join(words[:2])].add(key)
    meetings = defaultdict(list)
    for m in disc.get("calendar", []):
        title = str(m.get("title", "")).strip()
        if not title or is_sensitive(title, str(m.get("sensitivity", ""))):
            continue
        meetings[title].append(m)
    recurring = {t: ms for t, ms in meetings.items() if len(ms) >= 2 or any(x.get("recurring") for x in ms)}
    patterns = []
    for key, files in groups.items():
        names = [str(f.get("name")) for f in files]
        ext = names[-1].rsplit(".", 1)[-1].lower() if "." in names[-1] else ""
        kind = KIND.get(ext, "File")
        versions = len(files)
        editors = max(int(f.get("editors") or 0) for f in files)
        shared = max(int(f.get("shared_with") or 0) for f in files)
        words = key.split()
        similar = len(families.get(" ".join(words[:2]), ())) if len(words) >= 3 else 0
        rhythm = rhythm_of(names)
        meeting = None
        for title, ms in recurring.items():
            if tokens(title) & tokens(key):
                meeting = title
                if not rhythm:
                    rhythm = "every week" if len(ms) >= 3 else "every month"
                break
        signs, points = [], 0
        if versions >= 2:
            signs.append(f"{versions} versions in the last 30 days")
            points += 2
        if similar >= 3:
            signs.append(f"one of {similar} similar documents")
            points += 2
        if editors >= 3:
            signs.append(f"{editors} people work on it")
            points += 2
        if shared >= 5:
            signs.append(f"shared with {shared} people")
            points += 2
        if rhythm:
            signs.append(f"made {rhythm}")
            points += 2
        if meeting:
            signs.append(f"prepared for {meeting}")
            points += 3
        if points < 4:
            continue
        comes_round = bool(rhythm or similar >= 3 or meeting)
        reviewed = versions >= 2 or editors >= 2 or shared >= 3
        waited_for = bool(meeting or shared >= 5)
        passed = sum((comes_round, reviewed, waited_for))
        latest = max(files, key=lambda f: str(f.get("modified", "")))
        work = re.sub(r"\s+", " ", NOISE.sub(" ", str(latest.get("name")).rsplit(".", 1)[0])).strip(" -_")
        patterns.append({
            "work": work or key.title(), "kind": kind,
            "made_as": "App" if kind == "Workbook" and editors >= 4 else "Skill",
            "evidence": ", ".join(signs),
            "signs": {"versions": versions, "similar": similar, "editors": editors, "shared_with": shared,
                      "rhythm": rhythm, "meeting": meeting},
            "checks": {"comes_round_again": comes_round, "someone_reviews_it": reviewed, "someone_waits_for_it": waited_for},
            "fit": "Strong fit" if passed == 3 else "Good fit" if passed == 2 else "Ask first",
            "points": points, "text": key + " " + " ".join(n.lower() for n in names)})
    patterns.sort(key=lambda p: -p["points"])
    theirs = sorted({p["work"] for p in patterns[:8]} | {p["signs"]["meeting"] for p in patterns[:8] if p["signs"]["meeting"]})
    return {"as_of": disc.get("as_of"), "sample": bool(disc.get("sample")),
            "source_line": "From file names, meeting titles and counts only. Nothing was opened.",
            "left_out": skipped, "patterns": patterns[:8], "theirs": theirs}


def save_theirs(out_path: str, words) -> None:
    """Keep the person's own words beside the result, so the card checker shows them as they wrote them."""
    path = Path(out_path).resolve().parent / "theirs.json"
    have = []
    try:
        have = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    except (OSError, ValueError):
        have = []
    merged = sorted({w for w in list(have if isinstance(have, list) else []) + list(words) if isinstance(w, str) and w.strip()})
    path.write_text(json.dumps(merged, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Signs of repeatable work, from titles and counts only.")
    ap.add_argument("--input", required=True)
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    try:
        disc = json.loads(Path(a.input).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(json.dumps({"errors": [f"could not read the look file: {exc}"]}))
        return 1
    result = build(disc)
    out = json.dumps(result, ensure_ascii=False, indent=1)
    if a.out:
        Path(a.out).write_text(out + "\n", encoding="utf-8")
        save_theirs(a.out, result.get("theirs", []))
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
