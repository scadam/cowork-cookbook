#!/usr/bin/env python3
"""Launchpad for Cowork: rank the recipes for this person.

Ranks the recipe index (../references/recipes.json) against the person's own
signals (from signals.py) or what they told you, and returns card-ready data:
annotated "Is this your work?" groups, up to four suggestions for the question
card, offers for the cookbook's offer card, or one recipe for "Would you like
this?". Weights are internal: they order recipes and are never shown.

Usage
  python3 rank.py [--signals signals.json] [--said "words the person used"]
                  [--function finance] [--exclude id,id] [--limit 4]
                  [--sample] [--recipe ID] [--out ranked.json]
Standard library only.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
RECIPES = HERE.parent / "references" / "recipes.json"
NUMBER_WORDS = {1: "One", 2: "Two", 3: "Three", 4: "Four", 5: "Five"}
FIELD_BY_TYPE = {
    "versioned_document": "file_names", "stated_document": "file_names",
    "shared_tracker": "file_names", "status_emails": "email_subjects",
    "recurring_meeting": "meeting_titles", "stated_meeting": "meeting_titles",
}
GENERIC_SCORE = 0.5


def words(text: str) -> list[str]:
    text = str(text).lower().replace("&", " & ")
    text = re.sub(r"\.[a-z0-9]{2,4}$", "", text)
    text = re.sub(r"[_\-\u2013\u2014.,;:!?()\[\]{}/\\+\"'|#*]", " ", text)
    return text.split()


def norm(text: str) -> str:
    return " ".join(words(text))


def hit(keyword: str, text: str) -> bool:
    kw = norm(keyword)
    if not kw or not text:
        return False
    return re.search(r"(?<![a-z0-9])" + re.escape(kw) + r"s?(?![a-z0-9])", text) is not None


def lower_first(text: str) -> str:
    return text[:1].lower() + text[1:] if text and not text[:2].isupper() else text


def short_work(work: str, n: int = 3) -> str:
    toks = work.split()
    return " ".join(toks[:n]).lower()


def short_evidence(evidence: str, limit: int = 48) -> str:
    """The first clauses of an evidence line, kept short for a question option."""
    parts = [p.strip() for p in re.split(r"[;,]", evidence) if p.strip()]
    out = ""
    for part in parts:
        candidate = f"{out}, {part}" if out else part
        if out and len(candidate) > limit:
            break
        out = candidate
    return out


def one_line(text: str, limit: int = 100) -> str:
    text = " ".join(str(text).split())
    if len(text) <= limit:
        return text
    cut = text[:limit - 1].rsplit(" ", 1)[0].rstrip(",;:")
    return cut + "\u2026"


def load(path: Path) -> dict:
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def score_recipe(recipe: dict, signals: list[dict], titles: dict, said: str) -> dict:
    total = 0.0
    best = None  # (contribution, why, signal id, short description)
    matched = []
    keys = recipe["signals"]
    other = set(keys.get("other", []))
    for s in signals:
        field = FIELD_BY_TYPE.get(s["type"])
        contribution = 0.0
        if field and any(hit(k, s.get("text", "")) for k in keys.get(field, [])):
            contribution = 1.0
        elif s["type"] == "status_emails" and any(hit(k, s.get("text", "")) for k in keys.get("file_names", [])):
            contribution = 0.75
        types = set(s.get("types", [s["type"]]))
        if types & other:
            contribution = max(contribution, 0.6 * len(types & other))
        if contribution:
            total += contribution
            matched.append(s["id"])
            if s["type"].startswith("stated_"):
                why = f"Why you: {lower_first(s['evidence'])}: {s['work']}."
                desc = f"{s['evidence']}: {s['work']}"
            else:
                why = f"Why you: {s['work']}, {lower_first(s['evidence'])}."
                desc = f"{s['work']}: {lower_first(short_evidence(s['evidence']))}"
            if best is None or contribution > best[0]:
                best = (contribution, why, s["id"], desc)
    weak = 0.0
    weak_why = None
    for field in ("file_names", "meeting_titles", "email_subjects"):
        for title in titles.get(field, []):
            if any(hit(k, title) for k in keys.get(field, [])):
                weak += 0.25
                if weak_why is None:
                    where = {"file_names": "a file called", "meeting_titles": "a meeting called",
                             "email_subjects": "an email you sent called"}[field]
                    weak_why = f"Why you: {where} \u201c{title[:1].upper() + title[1:]}\u201d."
    total += min(weak, 0.5)
    stated_hits = 0
    if said:
        said_n = norm(said)
        for field in ("file_names", "meeting_titles", "email_subjects"):
            stated_hits += sum(1 for k in keys.get(field, []) if hit(k, said_n))
        if stated_hits:
            total += min(2.0, float(stated_hits))
            if best is None or best[0] < 1.0:
                best = (1.0, f"Why you: you asked about \u201c{one_line(said, 60)}\u201d.", None,
                        f"You asked about \u201c{one_line(said, 60)}\u201d")
    why = best[1] if best else weak_why
    desc = best[3] if best else (weak_why.replace("Why you: ", "").rstrip(".") if weak_why else None)
    return {"total": total, "match": min(1.0, total / 2.0), "why": why, "matched": matched,
            "best_signal": best[2] if best else None, "desc": desc}


def kind_badge(index: dict, kind: str) -> tuple[str, str]:
    k = index["kinds"][kind]
    return k["badge"], k["badge_style"]


def offer_entry(index: dict, recipe: dict, why: str | None) -> dict:
    badge, style = kind_badge(index, recipe["kind"])
    entry = {
        "id": recipe["id"], "icon": recipe["icon"], "title": recipe["title"],
        "what_you_get": recipe["what_you_get"],
        "why_line": why or recipe["why_you_if"],
        "badge": badge, "badge_style": style,
        "example_picture": recipe.get("example_picture") or "",
        "example_alt": recipe.get("example_alt") or "",
        "label": recipe["choice_label"],
        "description": one_line(recipe["choice_description"]),
        "lines": recipe["would_you_like"], "kind": recipe["kind"],
    }
    return entry


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Rank Launchpad recipes for this person.")
    parser.add_argument("--signals", help="signals.json from signals.py")
    parser.add_argument("--said", default="", help="the person's own words, when nothing was read")
    parser.add_argument("--function", default="", help="filter by function, for example finance")
    parser.add_argument("--exclude", default="", help="recipe ids already shown, comma separated")
    parser.add_argument("--limit", type=int, default=4)
    parser.add_argument("--sample", action="store_true", help="invented sample data route")
    parser.add_argument("--recipe", help="return card data for one recipe")
    parser.add_argument("--recipes", default=str(RECIPES), help=argparse.SUPPRESS)
    parser.add_argument("--out", help="also write the result to this file")
    args = parser.parse_args(argv)

    try:
        index = load(Path(args.recipes))
        sig = load(Path(args.signals)) if args.signals else {}
    except (OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"errors": [f"cannot read input: {exc}"]}))
        return 1

    signals = sig.get("signals", [])
    titles = sig.get("titles", {})
    said = args.said
    if sig.get("stated") and not said:
        said = " ".join(titles.get("stated", []))
    has_evidence = bool(signals or titles.get("file_names") or titles.get("meeting_titles")
                        or titles.get("email_subjects") or said)
    sample = args.sample or bool(sig.get("sample"))
    excluded = {x.strip() for x in args.exclude.split(",") if x.strip()}
    recipes = index["recipes"]
    if args.function:
        f = args.function.lower()
        recipes = [r for r in recipes if f in r["function"].lower()
                   or any(f in role.lower() for role in r["roles"])] or recipes

    ranking = []
    for order, recipe in enumerate(recipes):
        result = score_recipe(recipe, signals, titles, said)
        if has_evidence:
            score = round(0.65 * result["match"] + 0.35 * recipe["weight"], 4)
        else:
            score = recipe["weight"]
        ranking.append({"id": recipe["id"], "score": score, "match": round(result["match"], 4),
                        "why": result["why"], "desc": result["desc"], "best_signal": result["best_signal"],
                        "matched_signals": result["matched"], "order": order, "recipe": recipe})
    ranking.sort(key=lambda r: (-r["score"], r["order"]))

    out = {k: sig[k] for k in ("as_of", "as_of_text", "source_line", "skipped_line", "stated",
                               "profile_draft", "counts") if k in sig}
    out["sample"] = sample

    # One recipe, for "Would you like this?"
    if args.recipe:
        match = next((r for r in ranking if r["id"] == args.recipe), None)
        if match is None:
            print(json.dumps({"errors": [f"unknown recipe {args.recipe}"]}))
            return 1
        entry = offer_entry(index, match["recipe"], match["why"])
        out.update({k: entry[k] for k in ("id", "title", "icon", "badge", "badge_style", "example_picture",
                                          "example_alt", "lines", "why_line", "kind")})
        if sample:
            out["why_line"] = "Invented sample data: Contoso Asset Management. Nothing of yours is read."
        return finish(out, args.out)

    # Annotate the "Is this your work?" groups with the kind of their best match.
    best_kind, best_score = {}, {}
    main_evidence = {r["best_signal"] for r in ranking if r["best_signal"] and r["match"] > 0}
    for r in ranking:
        for sid in r["matched_signals"]:
            if r["match"] > 0 and sid not in best_kind:
                best_kind[sid] = r["recipe"]["kind"]
                best_score[sid] = r["score"]
        if r["best_signal"] and r["match"] > 0:
            best_kind[r["best_signal"]] = r["recipe"]["kind"]
    groups = sig.get("groups")
    if groups:
        for name, lines in groups.items():
            for line in lines:
                kind = best_kind.get(line.get("signal"))
                if kind:
                    line["badge"], line["badge_style"] = kind_badge(index, kind)
            ordered = sorted(enumerate(lines), key=lambda p: (
                p[1].get("signal") not in main_evidence, -best_score.get(p[1].get("signal"), 0), p[0]))
            groups[name] = [line for _, line in ordered][:3]
        out["groups"] = groups

    # Suggestions for "Which would you like help with?"
    suggestions = []
    for r in ranking:
        if r["id"] in excluded:
            continue
        if has_evidence and r["match"] <= 0:
            continue
        rec = r["recipe"]
        why = r["why"] or rec["why_you_if"]
        suggestions.append({"label": rec["choice_label"],
                            "description": one_line(r["desc"] or rec["choice_description"]),
                            "recipe": rec["id"], "kind": rec["kind"], "title": rec["title"],
                            "why_line": why, "score": r["score"]})
    strong = {sid for r in ranking for sid in r["matched_signals"] if r["match"] >= 0.5}
    for s in signals:
        if s["id"] in strong:
            continue
        short = short_work(s["work"])
        label = {"versioned_document": f"Draft {short}", "stated_document": f"Draft {short}",
                 "shared_tracker": f"Build {short} app", "status_emails": f"Summarise {short}",
                 "recurring_meeting": f"Prepare for {short}", "stated_meeting": f"Prepare for {short}"}[s["type"]]
        suggestions.append({"label": label[:1].upper() + label[1:],
                            "description": one_line(f"{s['work']}: {lower_first(short_evidence(s['evidence']))}"),
                            "recipe": "generic", "signal": s["id"], "kind": s["kind"], "title": s["work"],
                            "why_line": f"Why you: {s['work']}, {lower_first(s['evidence'])}.",
                            "score": GENERIC_SCORE})
    suggestions.sort(key=lambda x: -x["score"])
    seen, unique = set(), []
    for s in suggestions:
        if s["label"].lower() not in seen:
            seen.add(s["label"].lower())
            unique.append(s)
    suggestions = unique[:max(1, min(args.limit, 4))]
    if len(suggestions) < 2:
        suggestions.append({"label": "Show me the cookbook", "description": "Four things I can make, with examples",
                            "recipe": "cookbook", "kind": "skill", "title": "The cookbook", "why_line": "",
                            "score": 0})
    out["suggestions"] = suggestions

    # Offers for the cookbook's offer card.
    offers = []
    for r in ranking:
        if r["id"] in excluded:
            continue
        why = r["why"] if (has_evidence and r["match"] > 0) else None
        offers.append(offer_entry(index, r["recipe"], why))
    offers = offers[:max(1, min(args.limit, 4))]
    out["offers"] = offers
    out["exhausted"] = not offers
    n = NUMBER_WORDS.get(len(offers), str(len(offers)))
    if excluded:
        out["heading"] = "More things I could make"
    else:
        out["heading"] = "Where Cowork could help you first"
    if sample:
        out["subtitle"] = "Invented sample data. Nothing of yours is read."
    elif sig.get("stated"):
        out["subtitle"] = "Chosen from what you told me. Nothing of yours was read."
    elif signals or titles.get("file_names") or titles.get("meeting_titles"):
        out["subtitle"] = f"Chosen from your recent work, as of {sig.get('as_of_text', 'today')}."
    elif args.said:
        out["subtitle"] = "Chosen from what you asked. Nothing of yours has been read."
    elif args.function:
        out["subtitle"] = f"{n} things I can make for {args.function.lower()} work. Nothing of yours has been read."
    else:
        out["subtitle"] = f"{n} things I can make. Nothing of yours has been read."
    out["ranking"] = [{"id": r["id"], "score": r["score"], "match": r["match"]} for r in ranking]
    return finish(out, args.out)


def finish(out: dict, path: str | None) -> int:
    text = json.dumps(out, ensure_ascii=False, indent=1)
    if path:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
