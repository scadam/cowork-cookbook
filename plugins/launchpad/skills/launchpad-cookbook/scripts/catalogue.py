#!/usr/bin/env python3
"""Launchpad for Cowork: the wider cookbook ("people like you").

  python3 catalogue.py people [--role "..."] [--industry "..."] [--region "..."] [--function finance]
                              [--said "their words"] [--patterns patterns.json] [--signals signals.json]
                              [--exclude id,id] [--limit 4] [--all] [--out people.json]
  python3 catalogue.py entry --id ID [--out entry.json]
  python3 catalogue.py find --said "their words" [--industry "..."] [--role "..."] [--region "..."] [--limit 5]
  python3 catalogue.py industries
  python3 catalogue.py list

"people" returns a card and a question card: work that people in roles like this one, in this industry,
hand to Cowork. Each piece of work shows what they would get, what changes, a short film where there is
one, and "Why you" when the person's own titles match. "entry" returns the card for one piece of work, its
question card and the design to start from. "find" returns the closest pieces of work to something the
person described, to shape a skill they bring themselves. "industries" lists the industry names it knows.

--industry takes the person's industry or organisation type in plain words ("asset manager", "insurance
company", "water utility") or a name from "industries". --sector (banking, capital-markets, asset-wealth, insurance,
payments) still works. --region takes a country or region ("United Kingdom", "Japan", "EU-UK").

Weights are internal: they order entries and are never shown. No counts of other organisations, ever.
Every card is checked by cards.py before it is returned. The person's own words (their role, what they
said and their titles) are shown as they wrote them. Standard library only.
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
LIBRARY_PLACES = (HERE.parent / "references" / "library.json",
                  HERE.parent.parent / "launchpad-cookbook" / "references" / "library.json")
THEIRS_FILE = Path("working/launchpad/theirs.json")
FS = {"Banking", "CapitalMarkets", "DigitalFintech", "InsuranceCurrent", "InsuranceLifeAnnuity", "InsuranceBrokers",
      "SovereignInvestment"}
CODES_FOR = {"Banking": {"banking"}, "CapitalMarkets": {"capital-markets", "asset-wealth"}, "DigitalFintech": {"payments"},
             "InsuranceCurrent": {"insurance"}, "InsuranceLifeAnnuity": {"insurance"}, "InsuranceBrokers": {"insurance"},
             "SovereignInvestment": {"asset-wealth"}}
EXEC_KINDS = {"board-paper", "executive-brief", "business-review", "business-case", "forecast-budget", "programme-status"}
STOP = {"with", "from", "that", "this", "your", "their", "into", "each", "every", "monthly", "weekly", "quarterly", "annual",
        "daily", "draft", "drafts", "pack", "packs", "report", "reports", "review", "reviews", "summary", "note", "notes",
        "update", "updates", "brief", "memo", "file", "files", "list", "plan", "the", "and", "for", "our", "new"}
# single words too general to prove that a piece of the person's work matches an entry
GENERIC = {"audit", "controls", "strategy", "status", "exceptions", "consultant", "scheme", "bid", "matter", "claim",
           "claims", "proposal", "supervisor", "regulator", "renewal", "board", "forecast", "register", "timeline",
           "tender", "dispute", "disputes", "litigation", "pursuit", "payables", "complaints", "complaint", "exco",
           "breaks", "bundle", "tracker", "submissions", "regulation", "fund update", "evidence", "check-in", "stand-up",
           "performance", "business", "management", "project", "programme", "program", "customer", "client", "team",
           "meeting", "risk", "data", "finance", "financial", "quality", "service", "operations"}
KIND_BADGE = {"skill": "Skill", "app": "App", "routine": "Routine"}


# ------------------------------------------------------------------ loading
def load() -> tuple[dict, dict]:
    cat = json.loads(CAT.read_text(encoding="utf-8"))
    lib = {"entries": [], "kinds": {}, "industries": {}, "families": {}, "regions": {}, "region_fallback": {},
           "functions": {}, "seniority": [], "sector_codes": {}}
    for place in LIBRARY_PLACES:
        if place.exists():
            lib = expand(json.loads(place.read_text(encoding="utf-8")))
            break
    return cat, lib


def expand(lib: dict) -> dict:
    """The library is stored compactly (one array per piece of work, shared role lists stored once)."""
    if "entry_fields" not in lib:
        return lib
    f = {name: i for i, name in enumerate(lib["entry_fields"])}
    ik, rk, kk = lib["industry_keys"], lib["region_keys"], lib["kind_keys"]
    groups, phrases = lib["groups"], lib["starts_phrases"]
    out = []
    for row in lib["entries"]:
        roles, fns = groups[row[f["group"]]]
        e = {"i": ik[row[f["industry"]]], "r": rk[row[f["region"]]], "k": kk[row[f["kind"]]], "ro": roles, "fn": fns,
             "t": row[f["title"]], "w": row[f["weight"]], "sw": phrases[row[f["starts"]]]}
        e["id"] = f"{e['r']}.{e['i']}.{row[f['wid']]}".lower()
        e["in"] = row[f["inputs"]].split("; ") if row[f["inputs"]] else []
        for key, name in (("dc", "decides"), ("mk", "makes"), ("how", "steps")):
            if row[f[name]]:
                e[key] = row[f[name]]
        if row[f["local_to"]]:
            e["loc"] = row[f["local_to"]]
        out.append(e)
    lib["entries"] = out
    return lib


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9&+' ]", " ", (text or "").lower())).strip()


def has_word(word: str, text: str) -> bool:
    return bool(re.search(r"(?<![a-z0-9])" + re.escape(word) + r"(?![a-z0-9])", text))


def resolve_industry(lib: dict, text: str | None, sector: str | None) -> list:
    keys = []
    codes = lib.get("sector_codes", {})
    if sector:
        keys += codes.get(sector.strip().lower(), [])
    t = norm(text or "")
    if t:
        inds = lib.get("industries", {})
        exact = [k for k, v in inds.items() if t in (k.lower(), norm(v["label"]))]
        family = [k for k, v in inds.items() if t in (v["family"], norm(lib.get("families", {}).get(v["family"], "")))]
        if exact:
            keys += exact
        elif family:
            keys += family
        elif t in codes:
            keys += codes[t]
        else:
            best, best_len = [], 0
            for k, v in inds.items():
                for w in v["words"] + [v["label"]]:
                    wn = norm(w)
                    if wn and has_word(wn, t):
                        if len(wn) > best_len:
                            best, best_len = [k], len(wn)
                        elif len(wn) == best_len and k not in best:
                            best.append(k)
            keys += best
    out = []
    for k in keys:
        if k not in out:
            out.append(k)
    return out


def resolve_region(lib: dict, text: str | None):
    t = norm(text or "")
    if not t:
        return None
    regions = lib.get("regions", {})
    for code, v in regions.items():
        if t in (code.lower(), norm(v["label"])):
            return code
    best, best_len = None, 0
    for code, v in regions.items():
        for w in v["words"]:
            if has_word(w, t) and len(w) > best_len:
                best, best_len = code, len(w)
    return best


def functions_of(lib: dict, text: str) -> set:
    t = " " + re.sub(r"[^a-z0-9&+\- ]", " ", (text or "").lower()) + " "
    found = set()
    for fn, v in lib.get("functions", {}).items():
        for w in v["words"]:
            if re.search(r"(?<![a-z])" + re.escape(w) + r"(?![a-z])", t):
                found.add(fn)
                break
    return found


def tokens(lib: dict, text: str) -> set:
    sen = set(lib.get("seniority", []))
    return {w for w in re.findall(r"[a-z][a-z&+'-]+", (text or "").lower()) if len(w) > 2 and w not in sen and w not in STOP}


def hits(phrases, text: str) -> list:
    return [p for p in phrases if re.search(r"\b" + re.escape(p) + r"\b", text)]


def read_items(patterns_path, signals_path) -> tuple[list, list]:
    items, theirs = [], []
    for path, key in ((patterns_path, "patterns"), (signals_path, "signals")):
        if not path:
            continue
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        theirs += [x for x in data.get("theirs", []) if isinstance(x, str)]
        for it in data.get(key, []):
            work = str(it.get("work", "")).strip()
            if work:
                text = (work + " " + str(it.get("text", ""))).lower()
                items.append((work, str(it.get("evidence", "")).strip(), text))
                theirs.append(work)
    return items, theirs


def entry_phrases(lib: dict, title: str) -> list:
    """Phrases from a library title that would show the person's own work matches it."""
    words = [w for w in re.findall(r"[a-z][a-z&+'-]+", title.lower()) if len(w) > 3 and w not in STOP]
    pairs = [f"{a} {b}" for a, b in zip(words, words[1:])]
    singles = [w for w in words if w not in GENERIC and w not in set(lib.get("seniority", []))]
    return pairs + singles


# ------------------------------------------------------------------ the person
class Person:
    def __init__(self, lib: dict, a):
        self.role = (a.role or "").strip()
        self.fns = functions_of(lib, self.role + " " + (a.function or ""))
        self.work_fns = self.fns - {"executive"}
        self.tok = tokens(lib, self.role + " " + (a.function or ""))
        self.exec = ("executive" in self.fns or bool(re.search(r"\b(chief|head|director|vp|vice president|managing)\b",
                                                                   self.role.lower()))) and "executive-support" not in self.fns
        self.industries = resolve_industry(lib, getattr(a, "industry", None), getattr(a, "sector", None))
        self.fs = any(i in FS for i in self.industries)
        self.codes = set().union(*[CODES_FOR.get(i, set()) for i in self.industries]) if self.industries else set()
        self.region = resolve_region(lib, getattr(a, "region", None))
        self.fallback = lib.get("region_fallback", {}).get(self.region, []) if self.region else []
        self.said = (a.said or "").lower()
        self.said_tok = tokens(lib, a.said or "")
        self.items, self.theirs = read_items(getattr(a, "patterns", None), getattr(a, "signals", None))
        self.theirs += [x for x in (self.role, a.said or "") if x]


def match_work(phrases, p: Person):
    best = None
    for work, evidence, text in p.items:
        h = [x for x in hits(phrases, text) if " " in x or x not in GENERIC]
        if h and (best is None or len(h) > best[0]):
            best = (len(h), work, evidence)
    return best


def score_curated(entry: dict, p: Person, lib: dict, a):
    if entry["design"].get("recipe") and not a.all:
        return None  # already offered in "Is this your work?"
    sectors = set(entry["sectors"])
    s = 4 * float(entry.get("weight", 0.5)) + 2
    if p.industries:
        if sectors & p.codes:
            s += 8
        elif "all" in sectors and p.fs:
            s += 6
        elif "any" in sectors:
            s += 3
        else:
            return None
    else:
        s += 2 if "any" in sectors else -3
    # the extra role titles come from financial services studies, so they only widen the match there
    roles_text = " ".join(entry["roles"] + (entry.get("match_roles", []) if p.fs else [])) + " " + entry["function"]
    inter = (functions_of(lib, roles_text) - {"executive"}) & p.work_fns
    if inter:
        s += 10 + min(4, 2 * (len(inter) - 1))
    elif p.work_fns:
        s -= 5
    s += min(9, 3 * len(p.tok & tokens(lib, " ".join(entry["roles"]) + " " + entry["function"])))
    if p.exec and entry.get("lib_kind") in EXEC_KINDS:
        s += 3
    if entry.get("film"):
        s += 1.5
    sig = entry["signals"]
    phrases = sig["file_names"] + sig["meeting_titles"] + sig["email_subjects"]
    why = None
    best = match_work(phrases, p)
    if best:
        s += 10 + best[0]
        why = f"{best[1]}, {best[2]}" if best[2] else best[1]
    if p.said and hits(phrases, p.said):
        s += 6
    return s, why


def score_library(e: dict, p: Person, lib: dict):
    kind = lib["kinds"][e["k"]]
    said_hit = len(p.said_tok & tokens(lib, e["t"])) >= 2
    if kind.get("exclude_people") and not said_hit:
        return None
    s = 4 * float(e.get("w", 0.5)) + 2 * float(kind.get("weight", 0))
    if p.industries:
        if e["i"] not in p.industries:
            return None
        s += 8
    else:
        s -= 2
    if p.region:
        if e["r"] == p.region:
            s += 2
        elif e["r"] in p.fallback:
            s += 0.5
        else:
            s -= 1
        if e.get("loc") and p.region not in e["loc"]:
            s -= 8
    inter = (set(e["fn"]) - {"executive"}) & p.work_fns
    if inter:
        s += 10 + min(4, 2 * (len(inter) - 1))
    elif p.work_fns:
        s -= 5
    s += min(9, 3 * len(p.tok & tokens(lib, " ".join(e["ro"]))))
    if p.exec and e["k"] in EXEC_KINDS:
        s += 3
    if kind.get("film"):
        s += 1.5
    if kind.get("recipe"):
        s += 1
    if e["k"] == "general":
        s -= 2
    why = None
    best = match_work(entry_phrases(lib, e["t"]), p)
    if best and best[0] >= 2:
        s += 10 + best[0]
        why = f"{best[1]}, {best[2]}" if best[2] else best[1]
    if said_hit:
        s += 6
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


def tick_line(t):
    return {"type": "ColumnSet", "spacing": "Small", "columns": [
        {"type": "Column", "width": "auto", "items": [icon("CheckmarkCircle", "Small")]},
        {"type": "Column", "width": "stretch", "items": [text(t, size="Small")]}]}


def film_url(cat: dict, film):
    return cat["film_prefix"] + film if film else None


def short_label(t: str, n: int = 4) -> str:
    words = re.sub(r"[()/,:;]", " ", t).split()
    return " ".join(words[:n])


LEAD = {"and", "or", "of", "the", "a", "an", "for", "with", "to", "in", "on", "by"}


def title_label(title: str) -> str:
    """A choice label of at most four words taken from the title itself, so it always matches the card."""
    t = re.sub(r"\s*/\s*", "/", title)
    head = t
    for sep in (r"\s+(?:with|for|from|against|under|into|after|before|across|per)\s+", r"\s+to\s+", r"\s*\(",
                r"\s*:\s*", r"\s*;\s*", r"\s+[-–]\s+", r"\s*,\s*"):
        part = re.split(sep, head, maxsplit=1)[0].strip()
        if len(part.split()) >= 2:
            head = part
    words = head.split()
    if len(words) > 4:
        first = head.split(" and ")[0]
        fw = first.split()
        if " and " in head and 3 <= len(fw) <= 4 and " or " not in first and "," not in first:
            words = fw
        elif " and " in head and len(fw) > 4:
            words = fw[-4:]
        else:
            words = words[-4:]
    while words and words[0].lower() in LEAD:
        words = words[1:]
    while words and words[-1].lower() in LEAD:
        words = words[:-1]
    while len(" ".join(words)) > 40 and len(words) > 1:
        words = words[1:]
    label = " ".join(words) or short_label(title)
    return label[:1].upper() + label[1:]


def check(card: dict, questions: list, theirs: list) -> dict:
    """Check the card and its questions with the same rules as cards.py, in this process."""
    try:
        sys.dont_write_bytecode = True  # leave no cache files in the skill folder
        spec = importlib.util.spec_from_file_location("launchpad_cards", CARDS)
        cards = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cards)
        extra = []
        if THEIRS_FILE.exists():
            try:
                extra = json.loads(THEIRS_FILE.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                extra = []
        if hasattr(cards, "set_theirs"):
            cards.set_theirs([theirs, extra])
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


# ------------------------------------------------------------------ a common view of both kinds of entry
def view(cat: dict, lib: dict, item: dict, curated: bool) -> dict:
    if curated:
        return {"id": item["id"], "title": item["title"], "icon": item["icon"], "get": item["what_you_get"],
                "roles": item["roles"], "kind": item["kind"], "changes": item["what_changes"], "film": item.get("film"),
                "label": item["short"], "description": item["choice_description"], "work_kind": item.get("lib_kind", item["id"]),
                "measure": item["measure"], "money": item.get("money"), "fit": item["fit"], "design": item["design"],
                "area": "Any organisation" if "any" in item["sectors"] else ", ".join(
                    cat["sectors"].get(s, s) for s in item["sectors"] if s in cat["sectors"]),
                "function": item["function"], "starts": None, "reads": item["design"].get("inputs", []),
                "decides": item["design"].get("who_decides"), "how": None}
    kind = lib["kinds"][item["k"]]
    ind = lib["industries"].get(item["i"], {}).get("label", item["i"])
    return {"id": item["id"], "title": item["t"], "icon": kind["icon"], "get": item.get("mk") or kind["makes"],
            "roles": item["ro"], "kind": kind["kind"], "changes": kind["changes"], "film": kind.get("film"),
            "label": title_label(item["t"]), "description": kind["name"],
            "work_kind": item["k"], "measure": kind["measure"], "money": kind.get("money"), "fit": kind["fit"],
            "area": ind, "function": lib["functions"].get((item["fn"] or ["x"])[0], {}).get("label", ""),
            "starts": item.get("sw"), "reads": item.get("in", []), "decides": item.get("dc"), "how": item.get("how"),
            "design": {"inputs": item.get("in") or [], "outputs": kind["outputs"], "checks": kind["checks"],
                       "who_decides": item.get("dc") or kind["checks"][-1] + ".", "recipe": kind.get("recipe"),
                       "caution": kind.get("caution")}}


def find_item(cat: dict, lib: dict, entry_id: str):
    for e in cat["entries"]:
        if e["id"] == entry_id:
            return view(cat, lib, e, True)
    for e in lib["entries"]:
        if e["id"] == entry_id:
            return view(cat, lib, e, False)
    return None


# ------------------------------------------------------------------ people like you
def subtitle_for(cat: dict, lib: dict, p: Person, a) -> str:
    parts = []
    if p.industries:
        inds = lib.get("industries", {})
        if len(p.codes) == 1 and len(p.industries) > 1:
            parts.append(cat["sectors"].get(next(iter(p.codes)), ""))
        elif len(p.industries) == 1 and p.industries[0] in inds:
            parts.append(inds[p.industries[0]]["label"])
        elif a.sector and a.sector in cat["sectors"]:
            parts.append(cat["sectors"][a.sector])
        else:
            fams = {inds[i]["family"] for i in p.industries if i in inds}
            if len(fams) == 1:
                parts.append(lib["families"][fams.pop()])
    if p.role:
        parts.append(p.role)
    return " · ".join(parts) if parts else "Chosen from the Cowork Cookbook"


def people(cat: dict, lib: dict, a) -> dict:
    p = Person(lib, a)
    exclude = {x.strip() for x in (a.exclude or "").split(",") if x.strip()}
    ranked = []
    for entry in cat["entries"]:
        if entry["id"] in exclude:
            continue
        r = score_curated(entry, p, lib, a)
        if r and r[0] > -5:
            ranked.append((r[0], r[1], entry, True))
    for e in lib.get("entries", []):
        if e["id"] in exclude:
            continue
        r = score_library(e, p, lib)
        if r and r[0] > -5:
            ranked.append((r[0], r[1], e, False))
    ranked.sort(key=lambda r: -r[0])
    limit = max(1, min(4, a.limit))
    picked, kinds_used, titles, labels_used, any_count = [], set(), set(), set(), 0
    for s, why, item, curated in ranked:
        v = view(cat, lib, item, curated)
        if v["work_kind"] in kinds_used or norm(v["title"]) in titles:
            continue
        if curated and "any" in item["sectors"] and not p.fs and any_count >= 2:
            continue
        label = v["label"] if v["label"] not in labels_used else short_label(v["title"])
        if label in labels_used or label.lower() == "keep looking":
            continue
        v["label"] = label
        picked.append((s, why, v))
        kinds_used.add(v["work_kind"])
        titles.add(norm(v["title"]))
        labels_used.add(label)
        any_count += 1 if curated and "any" in item["sectors"] else 0
        if len(picked) == limit:
            break
    body = [header("What people like you do with Cowork", subtitle_for(cat, lib, p, a))]
    for s, why, v in picked:
        why_line = f"Why you: {why}." if why else "For: " + ", ".join(v["roles"][:2]) + "."
        inner = [{"type": "ColumnSet", "columns": [
            {"type": "Column", "width": "auto", "verticalContentAlignment": "Center", "items": [icon(v["icon"])]},
            {"type": "Column", "width": "stretch", "items": [
                text(v["title"], weight="Bolder"),
                text(v["get"], size="Small", spacing="None"),
                text(why_line, isSubtle=True, size="Small", spacing="Small")]},
            {"type": "Column", "width": "auto", "items": [badge(KIND_BADGE[v["kind"]])]}]},
            text("**What changes:** " + v["changes"], size="Small", spacing="Small")]
        url = film_url(cat, v["film"])
        if url:
            inner.append(text(f"[Watch the short film]({url})", size="Small", spacing="Small"))
        body.append({"type": "Container", "showBorder": True, "roundedCorners": True, "spacing": "Medium", "items": inner})
    body.append(text("Pick one below to co-develop it for your own work, or say keep looking.",
                     isSubtle=True, size="Small", spacing="Small"))
    card = {"type": "AdaptiveCard", "version": "1.6", "body": body}
    options = [{"label": v["label"], "description": v["description"]} for _, _, v in picked]
    options.append({"label": "Keep looking", "description": "Show me other things people like me do"})
    questions = [{"header": "Try one", "question": "Which would you like to co-develop for your own work?",
                  "multiSelect": False, "options": options[:5]}]
    return {"card": card, "questions": questions, "picked": [v["id"] for _, _, v in picked],
            "from_your_work": [v["id"] for _, w, v in picked if w],
            "labels": {v["label"]: v["id"] for _, _, v in picked},
            "industry": p.industries, "region": p.region, "left": max(0, len(ranked) - len(picked)),
            "check": check(card, questions, p.theirs)}


# ------------------------------------------------------------------ one entry
def entry_card(cat: dict, lib: dict, entry_id: str) -> dict:
    v = find_item(cat, lib, entry_id)
    if v is None:
        return {"error": f"no entry called {entry_id}", "hint": "use an id from people, find or list", "check": {"exit": 1}}
    body = [header(v["title"], "From the Cowork Cookbook · " + (v["area"] or v["function"]))]
    url = film_url(cat, v["film"])
    if url:
        body.append({"type": "Container", "style": "emphasis", "roundedCorners": True, "spacing": "Medium", "items": [
            {"type": "ColumnSet", "columns": [
                {"type": "Column", "width": "auto", "verticalContentAlignment": "Center", "items": [icon("Eye")]},
                {"type": "Column", "width": "stretch", "items": [
                    text(f"[Watch the short film]({url})", weight="Bolder"),
                    text("See it done on sample data before you decide.", size="Small", isSubtle=True, spacing="None")]}]}]})
    facts = [{"title": "What you get", "value": v["get"]},
             {"title": "Who it is for", "value": ", ".join(v["roles"])}]
    if v["starts"]:
        facts.append({"title": "When it runs", "value": v["starts"]})
    if v["reads"]:
        facts.append({"title": "What it works from", "value": ", ".join(v["reads"][:5])})
    facts += [{"title": "What changes", "value": v["changes"]},
              {"title": "What to measure", "value": v["measure"]}]
    if v.get("money"):
        facts.append({"title": "Where money can come from", "value": v["money"]})
    body.append({"type": "FactSet", "spacing": "Medium", "facts": facts})
    design = v["design"]
    if design.get("caution"):
        body.append(text(design["caution"], isSubtle=True, size="Small"))
    how = ["1. You show me one you have already made, and I read that one file with your OK.",
           "2. I build your skill from the cookbook design: your sections, your sources and a script for every figure.",
           "3. We test it on a past one where you know the answer, and you keep it only if it fits."]
    if v["kind"] == "app":
        how[1] = "2. I build your app from the cookbook design and your own columns, with a script for every figure."
    if v["kind"] == "routine":
        how = ["1. You tell me which mail, chats and meetings it may read.",
               "2. I build the routine and run it once with you.",
               "3. You keep it only if it fits, and it then runs on the schedule you choose."]
    pages = [{"type": "AccordionPage", "headerTitle": "Why this suits Cowork", "headerIconName": "CheckmarkCircle",
              "isExpanded": False, "items": [tick_line(f) for f in v["fit"]] + [tick_line(design["who_decides"])]},
             {"type": "AccordionPage", "headerTitle": "How we would build it together", "headerIconName": "Wrench",
              "isExpanded": False, "items": [text(h, size="Small", spacing="Small") for h in how]}]
    if v.get("how"):
        pages.append({"type": "AccordionPage", "headerTitle": "How the work usually runs", "headerIconName": "TaskListLtr",
                      "isExpanded": False, "items": [text(v["how"], size="Small")]})
    body.append({"type": "Accordion", "spacing": "Medium", "pages": pages})
    body.append(text("Nothing is read, kept or sent without your OK.", isSubtle=True, size="Small", spacing="Small"))
    card = {"type": "AdaptiveCard", "version": "1.6", "body": body}
    first = {"skill": "Co-develop it", "app": "Build it with me", "routine": "Set it up with me"}[v["kind"]]
    questions = [{"header": "Co-develop", "question": "Would you like to co-develop this for your own work?",
                  "multiSelect": False, "options": [
                      {"label": first, "description": "Build it on one of your own examples"},
                      {"label": "Show me another", "description": "Back to what people like me do"},
                      {"label": "Not now", "description": "Leave it here"}]}]
    out_design = dict(design)
    out_design.update({"title": v["title"], "kind": v["kind"], "what_you_get": v["get"], "measure": v["measure"],
                       "money": v.get("money"), "fit": v["fit"], "roles": v["roles"], "starts": v["starts"],
                       "steps": v.get("how"), "area": v["area"]})
    return {"card": card, "questions": questions, "id": v["id"], "design": out_design, "film": url,
            "check": check(card, questions, [])}


# ------------------------------------------------------------------ find, industries, list
def find(cat: dict, lib: dict, a) -> dict:
    p = Person(lib, a)
    want = p.said_tok
    if not want:
        return {"error": "say what the work is with --said", "check": {"exit": 1}}
    out = []
    for e in cat["entries"]:
        if p.industries and not (set(e["sectors"]) & p.codes or "any" in e["sectors"] or ("all" in e["sectors"] and p.fs)):
            continue
        t = tokens(lib, e["title"] + " " + " ".join(e["signals"]["file_names"] + e["signals"]["meeting_titles"]))
        n = len(want & t)
        if n:
            out.append((3 * n + 1 + float(e.get("weight", 0.5)), view(cat, lib, e, True)))
    for e in lib.get("entries", []):
        if p.industries and e["i"] not in p.industries:
            continue
        n = len(want & tokens(lib, e["t"]))
        if not n:
            continue
        s = 3 * n + float(e.get("w", 0.5)) + (3 if (set(e["fn"]) & p.work_fns) else 0)
        if p.region:
            s += 1.5 if e["r"] == p.region else 0.5 if e["r"] in p.fallback else 0
            if e.get("loc") and p.region not in e["loc"]:
                s -= 4
        out.append((s, view(cat, lib, e, False)))
    out.sort(key=lambda x: -x[0])
    seen, rows = set(), []
    for s, v in out:
        if norm(v["title"]) in seen:
            continue
        seen.add(norm(v["title"]))
        rows.append({"id": v["id"], "title": v["title"], "kind": v["work_kind"], "area": v["area"], "roles": v["roles"][:2]})
        if len(rows) == max(1, min(10, a.limit)):
            break
    return {"matches": rows, "industry": p.industries, "region": p.region, "check": {"exit": 0}}


def industries(lib: dict) -> list:
    fams = lib.get("families", {})
    return [{"name": k, "label": v["label"], "family": fams.get(v["family"], v["family"]), "say": v["words"][:6],
             "regions": v.get("regions", [])} for k, v in sorted(lib.get("industries", {}).items(), key=lambda kv: kv[1]["label"])]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="The wider Cowork Cookbook.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("people")
    for flag in ("--role", "--industry", "--sector", "--region", "--function", "--said", "--patterns", "--signals",
                 "--exclude", "--out"):
        p.add_argument(flag)
    p.add_argument("--limit", type=int, default=4)
    p.add_argument("--all", action="store_true", help="include the recipes already offered in Is this your work?")
    en = sub.add_parser("entry")
    en.add_argument("--id", required=True)
    en.add_argument("--out")
    f = sub.add_parser("find")
    for flag in ("--said", "--role", "--industry", "--sector", "--region", "--function", "--out"):
        f.add_argument(flag)
    f.add_argument("--limit", type=int, default=5)
    sub.add_parser("industries")
    sub.add_parser("list")
    a = ap.parse_args(argv)
    cat, lib = load()
    if a.cmd == "industries":
        print(json.dumps(industries(lib), ensure_ascii=False, indent=1))
        return 0
    if a.cmd == "list":
        print(json.dumps({"entries": [{"id": e["id"], "title": e["title"], "area": e["area"], "sectors": e["sectors"],
                                       "function": e["function"], "film": e.get("film")} for e in cat["entries"]],
                          "library": "present" if lib.get("entries") else "not found"}, ensure_ascii=False, indent=1))
        return 0
    if a.cmd == "people":
        result = people(cat, lib, a)
    elif a.cmd == "find":
        result = find(cat, lib, a)
    else:
        result = entry_card(cat, lib, a.id)
    out = json.dumps(result, ensure_ascii=False, indent=1)
    if getattr(a, "out", None):
        Path(a.out).write_text(out + "\n", encoding="utf-8")
    print(out)
    return 0 if result.get("check", {}).get("exit") == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
