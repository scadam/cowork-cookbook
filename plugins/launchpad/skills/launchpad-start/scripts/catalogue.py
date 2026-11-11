#!/usr/bin/env python3
"""Launchpad for Cowork: the wider cookbook ("people like you").

  python3 catalogue.py people [--role "..."] [--sector banking|capital-markets|asset-wealth|insurance|payments]
                              [--function finance] [--said "their words"] [--patterns patterns.json]
                              [--signals signals.json] [--exclude id,id] [--limit 4] [--out people.json]
  python3 catalogue.py entry --id ID [--out entry.json]
  python3 catalogue.py list

"people" returns a card and a question card: work that people in roles like this
one hand to Cowork, each with what changes, a short film where there is one, and
"Why you" taken from the person's own titles when their work matches.
"entry" returns the card for one piece of work (film, value, how we would build
it together), its question card and the design to start from.
Weights are internal: they order entries and are never shown. No counts of other
organisations, ever. Every card is checked by cards.py before it is returned.
Standard library only.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CAT = HERE.parent / "references" / "catalogue.json"
CARDS = HERE / "cards.py"
STOP = {"with", "from", "that", "this", "your", "head", "lead", "manager", "officer", "senior", "team",
        "chief", "director", "analyst", "group", "global", "regional", "vice", "president", "associate"}
# single words too general to prove that a piece of the person's work matches an entry
GENERIC = {"audit", "controls", "strategy", "status", "exceptions", "consultant", "scheme", "bid", "matter", "claim",
           "claims", "proposal", "supervisor", "regulator", "renewal", "board", "forecast", "register", "timeline",
           "tender", "dispute", "disputes", "litigation", "pursuit", "payables", "complaints", "complaint", "exco",
           "breaks", "bundle", "tracker", "submissions", "regulation", "fund update", "evidence", "check-in", "stand-up"}
KIND_BADGE = {"skill": "Skill", "app": "App", "routine": "Routine"}


def load() -> dict:
    return json.loads(CAT.read_text(encoding="utf-8"))


def toks(text: str) -> set:
    return {w for w in re.findall(r"[a-z]+", (text or "").lower()) if len(w) > 3 and w not in STOP}


def hits(phrases, text: str) -> list:
    return [p for p in phrases if re.search(r"\b" + re.escape(p) + r"\b", text)]


def read_items(patterns_path, signals_path) -> list:
    items = []
    for path, key in ((patterns_path, "patterns"), (signals_path, "signals")):
        if not path:
            continue
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for it in data.get(key, []):
            work = str(it.get("work", "")).strip()
            if work:
                text = (work + " " + str(it.get("text", ""))).lower()
                items.append((work, str(it.get("evidence", "")).strip(), text))
    return items


def score(entry: dict, a, items: list):
    s = float(entry.get("weight", 0.5))
    sig = entry["signals"]
    phrases = sig["file_names"] + sig["meeting_titles"] + sig["email_subjects"]
    best = None
    for work, evidence, text in items:
        h = [x for x in hits(phrases, text) if " " in x or x not in GENERIC]
        if h and (best is None or len(h) > best[0]):
            best = (len(h), work, evidence)
    why = None
    if best:
        s += 10 + best[0]
        why = f"{best[1]}, {best[2]}" if best[2] else best[1]
    said = (a.said or "").lower()
    if said and hits(phrases, said):
        s += 6
    s += min(6, 3 * len(toks(a.role) & toks(" ".join(entry["roles"]) + " " + entry["function"])))
    if a.function and a.function.lower() in (entry["function"] + " " + " ".join(entry["roles"])).lower():
        s += 4
    if a.sector:
        if a.sector in entry["sectors"]:
            s += 3
        elif "all" in entry["sectors"]:
            s += 1
        else:
            s -= 20
    if entry.get("film"):
        s += 1.5
    return s, why


# ------------------------------------------------------------------ card parts
def text(t, **kw):
    d = {"type": "TextBlock", "text": t, "wrap": True}
    d.update(kw)
    return d


def icon(name, size="Medium"):
    return {"type": "Icon", "name": name, "size": size, "color": "Default"}


def badge(t):
    return {"type": "Badge", "text": t, "appearance": "Tint", "shape": "Rounded", "size": "Medium", "style": "Default"}


def header(title, subtitle):
    return {"type": "ColumnSet", "columns": [{"type": "Column", "width": "stretch", "items": [
        text(title, size="Large", weight="Bolder"), text(subtitle, isSubtle=True, spacing="None")]}]}


def film_url(cat: dict, entry: dict):
    return cat["film_prefix"] + entry["film"] if entry.get("film") else None


def tick_line(t):
    return {"type": "ColumnSet", "spacing": "Small", "columns": [
        {"type": "Column", "width": "auto", "items": [icon("CheckmarkCircle", "Small")]},
        {"type": "Column", "width": "stretch", "items": [text(t, size="Small")]}]}


def check(card: dict, questions: list) -> dict:
    """Check the card and its questions with the same rules as cards.py, in this process."""
    try:
        sys.dont_write_bytecode = True  # leave no cache files in the skill folder
        spec = importlib.util.spec_from_file_location("launchpad_cards", CARDS)
        cards = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cards)
        probs = cards.Problems()
        cards.check_card(card, cards.config(cards.load_templates()), probs)
        cards.check_questions(questions, probs)
    except Exception as exc:  # the checker itself could not run
        return {"exit": 1, "output": f"could not check the card: {exc}"}
    out = {"exit": 1 if probs.errors else 0}
    if probs.errors:
        out["output"] = "; ".join(probs.errors)[:2000]
    if probs.warnings:
        out["warnings"] = probs.warnings[:10]
    return out


# ------------------------------------------------------------------ people like you
def people(cat: dict, a) -> dict:
    items = read_items(a.patterns, a.signals)
    exclude = {x.strip() for x in (a.exclude or "").split(",") if x.strip()}
    ranked = []
    for entry in cat["entries"]:
        if entry["id"] in exclude:
            continue
        if entry["design"].get("recipe") and not a.all:
            continue  # already offered in "Is this your work?"
        s, why = score(entry, a, items)
        if s > -5:
            ranked.append((s, why, entry))
    ranked.sort(key=lambda r: -r[0])
    picked = ranked[:max(1, min(4, a.limit))]
    parts = []
    if a.sector and a.sector in cat["sectors"]:
        parts.append(cat["sectors"][a.sector])
    if a.role:
        parts.append(a.role.strip())
    subtitle = " · ".join(parts) if parts else "Chosen from the Cowork Cookbook"
    body = [header("What people like you do with Cowork", subtitle)]
    for s, why, entry in picked:
        why_line = f"Why you: {why}." if why else "For: " + ", ".join(entry["roles"][:2]) + "."
        inner = [{"type": "ColumnSet", "columns": [
            {"type": "Column", "width": "auto", "verticalContentAlignment": "Center", "items": [icon(entry["icon"])]},
            {"type": "Column", "width": "stretch", "items": [
                text(entry["title"], weight="Bolder"),
                text(entry["what_you_get"], size="Small", spacing="None"),
                text(why_line, isSubtle=True, size="Small", spacing="Small")]},
            {"type": "Column", "width": "auto", "items": [badge(KIND_BADGE[entry["kind"]])]}]},
            text("**What changes:** " + entry["what_changes"], size="Small", spacing="Small")]
        url = film_url(cat, entry)
        if url:
            inner.append(text(f"[Watch the short film]({url})", size="Small", spacing="Small"))
        body.append({"type": "Container", "showBorder": True, "roundedCorners": True, "spacing": "Medium", "items": inner})
    body.append(text("Pick one below to co-develop it for your own work, or say keep looking.",
                     isSubtle=True, size="Small", spacing="Small"))
    card = {"type": "AdaptiveCard", "version": "1.6", "body": body}
    options = [{"label": e["short"], "description": e["choice_description"]} for _, _, e in picked]
    options.append({"label": "Keep looking", "description": "Show me other things people like me do"})
    questions = [{"header": "Try one", "question": "Which would you like to co-develop for your own work?",
                  "multiSelect": False, "options": options[:5]}]
    return {"card": card, "questions": questions, "picked": [e["id"] for _, _, e in picked],
            "from_your_work": [e["id"] for _, w, e in picked if w],
            "labels": {e["short"]: e["id"] for _, _, e in picked},
            "left": max(0, len(ranked) - len(picked)), "check": check(card, questions)}


# ------------------------------------------------------------------ one entry
def entry_card(cat: dict, entry_id: str) -> dict:
    entry = next((e for e in cat["entries"] if e["id"] == entry_id), None)
    if entry is None:
        return {"error": f"no entry called {entry_id}", "ids": [e["id"] for e in cat["entries"]], "check": {"exit": 1}}
    body = [header(entry["title"], "From the Cowork Cookbook · " + entry["function"])]
    url = film_url(cat, entry)
    if url:
        body.append({"type": "Container", "style": "emphasis", "roundedCorners": True, "spacing": "Medium", "items": [
            {"type": "ColumnSet", "columns": [
                {"type": "Column", "width": "auto", "verticalContentAlignment": "Center", "items": [icon("Eye")]},
                {"type": "Column", "width": "stretch", "items": [
                    text(f"[Watch the short film]({url})", weight="Bolder"),
                    text("See it done on sample data before you decide.", size="Small", isSubtle=True, spacing="None")]}]}]})
    facts = [{"title": "What you get", "value": entry["what_you_get"]},
             {"title": "Who it is for", "value": ", ".join(entry["roles"])},
             {"title": "What changes", "value": entry["what_changes"]},
             {"title": "What to measure", "value": entry["measure"]}]
    if entry.get("money"):
        facts.append({"title": "Where money can come from", "value": entry["money"]})
    body.append({"type": "FactSet", "spacing": "Medium", "facts": facts})
    design = entry["design"]
    if design.get("caution"):
        body.append(text(design["caution"], isSubtle=True, size="Small"))
    how = ["1. You show me one you have already made, and I read that one file with your OK.",
           "2. I build your skill from the cookbook design: your sections, your sources and a script for every figure.",
           "3. We test it on a past one where you know the answer, and you keep it only if it fits."]
    body.append({"type": "Accordion", "spacing": "Medium", "pages": [
        {"type": "AccordionPage", "headerTitle": "Why this suits Cowork", "headerIconName": "CheckmarkCircle",
         "isExpanded": False, "items": [tick_line(f) for f in entry["fit"]] + [tick_line(design["who_decides"])]},
        {"type": "AccordionPage", "headerTitle": "How we would build it together", "headerIconName": "Wrench",
         "isExpanded": False, "items": [text(h, size="Small", spacing="Small") for h in how]}]})
    body.append(text("Nothing is read, kept or sent without your OK.", isSubtle=True, size="Small", spacing="Small"))
    card = {"type": "AdaptiveCard", "version": "1.6", "body": body}
    questions = [{"header": "Co-develop", "question": "Would you like to co-develop this for your own work?",
                  "multiSelect": False, "options": [
                      {"label": "Co-develop it", "description": "Build it on one of your own examples"},
                      {"label": "Show me another", "description": "Back to what people like me do"},
                      {"label": "Not now", "description": "Leave it here"}]}]
    out_design = dict(design)
    out_design.update({"title": entry["title"], "kind": entry["kind"], "what_you_get": entry["what_you_get"],
                       "measure": entry["measure"], "money": entry.get("money"), "fit": entry["fit"]})
    return {"card": card, "questions": questions, "id": entry["id"], "design": out_design, "film": url,
            "check": check(card, questions)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="The wider Cowork Cookbook.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("people")
    for flag in ("--role", "--sector", "--function", "--said", "--patterns", "--signals", "--exclude", "--out"):
        p.add_argument(flag)
    p.add_argument("--limit", type=int, default=4)
    p.add_argument("--all", action="store_true", help="include the recipes already offered in Is this your work?")
    en = sub.add_parser("entry")
    en.add_argument("--id", required=True)
    en.add_argument("--out")
    sub.add_parser("list")
    a = ap.parse_args(argv)
    cat = load()
    if a.cmd == "list":
        print(json.dumps([{"id": e["id"], "title": e["title"], "area": e["area"], "sectors": e["sectors"],
                           "function": e["function"], "film": e.get("film")} for e in cat["entries"]], indent=1))
        return 0
    result = people(cat, a) if a.cmd == "people" else entry_card(cat, a.id)
    out = json.dumps(result, ensure_ascii=False, indent=1)
    if a.out:
        Path(a.out).write_text(out + "\n", encoding="utf-8")
    print(out)
    return 0 if result.get("check", {}).get("exit") == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
