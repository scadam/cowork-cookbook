#!/usr/bin/env python3
"""Launchpad for Cowork: is it worth it? Every sum, worked out by a script.

Works out, for a recipe and the person's four answers:
  - the measure that moves (from the recipe and what goes wrong today),
  - cash that can stop: only real outside spend (contractors or temporary
    support, overtime, outside advisers) that the person selected and gave an
    amount for; otherwise "not sized",
  - Cowork running cost: the recipe's credits-per-run planning range x runs a
    year x a price per credit (a stated setting, default US$0.01),
  - net a year, only when both sides are sized in the same currency.
Time is never turned into money. Every assumption is listed.

Usage
  python3 case.py --data answers.json [--recipes ../references/recipes.json]

answers.json:
  {"recipe": "variance-commentary", "work_title": "optional, for your own work",
   "frequency": "Weekly|Monthly|Quarterly", "people": "1 to 2|3 to 5|6 or more",
   "late_or_wrong": ["Rework rounds", "Contractors or overtime", ...],
   "outside_spend": "free text, for example US$48,000 a year on contractors",
   "price_per_credit": 0.01, "credit_currency": "USD",
   "credits_per_run": {"low": 1000, "high": 2000},   (optional: your own measured runs)
   "share_that_can_stop": 1.0}                         (optional, 0 to 1)
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
FREQUENCIES = {"Weekly": 52, "Monthly": 12, "Quarterly": 4}
PEOPLE = {"1 to 2", "3 to 5", "6 or more"}
CONSEQUENCES = ["Rework rounds", "Contractors or overtime", "Missed deadlines",
                "Questions from the board or a regulator"]
SYMBOL = {"USD": "US$", "GBP": "\u00a3", "EUR": "\u20ac", "AUD": "A$", "CAD": "C$"}
CURRENCY_RE = r"(US\$|USD|\$|\u00a3|GBP|\u20ac|EUR|A\$|AUD|C\$|CAD)"
AMOUNT_RE = re.compile(CURRENCY_RE + r"?\s?(\d[\d,]*(?:\.\d+)?)\s?(k|m|bn|thousand|million)?\s?" + CURRENCY_RE + "?",
                       re.I)
PER_WORDS = [
    ("year", r"\b(a|per|each)\s+(year|annum)\b|\bannual(ly)?\b|\byearly\b|\bp\.?a\.?\b|/\s?(yr|year)"),
    ("month", r"\b(a|per|each)\s+month\b|\bmonthly\b|/\s?(mo|month)"),
    ("quarter", r"\b(a|per|each)\s+quarter\b|\bquarterly\b"),
    ("week", r"\b(a|per|each)\s+week\b|\bweekly\b"),
    ("run", r"\b(a|per|each)\s+(run|time|pack|paper|round|cycle|close)\b"),
]
PER_YEAR = {"year": 1, "month": 12, "quarter": 4, "week": 52}


def money(amount: float, currency: str) -> str:
    sign = "-" if amount < 0 else ""
    return f"{sign}{SYMBOL.get(currency, currency + ' ')}{abs(amount):,.0f}"


def money_range(low: float, high: float, currency: str) -> str:
    if round(low) == round(high):
        return money(low, currency)
    return f"{money(low, currency)} to {money(high, currency)}"


def currency_of(token: str | None, default: str) -> str:
    if not token:
        return default
    t = token.upper()
    return {"US$": "USD", "$": "USD", "\u00a3": "GBP", "\u20ac": "EUR", "A$": "AUD", "C$": "CAD"}.get(t, t)


def parse_spend(text: str, index: dict, default_currency: str) -> tuple[list[dict], list[str]]:
    """Find amounts in the person's free text and what kind of spend each is."""
    found, notes = [], []
    if not text or not text.strip():
        return found, notes
    segments = [s for s in re.split(r";|\band\b|\n", text) if s.strip()]
    for seg in segments:
        low = seg.lower()
        if any(re.search(r"\b" + re.escape(w) + r"\b", low) for w in index["not_money_words"]) and \
                not any(re.search(r"\b" + re.escape(w) + r"\b", low)
                        for k in index["spend_kinds"].values() for w in k["words"]):
            notes.append(f"Not counted: \u201c{seg.strip()}\u201d is about time or people, and time is never turned into money here.")
            continue
        m = AMOUNT_RE.search(seg)
        names_kind = any(re.search(r"\b" + re.escape(w) + r"\b", low)
                         for k in index["spend_kinds"].values() for w in k["words"])
        if not m or not (m.group(1) or m.group(4) or m.group(3) or names_kind):
            if re.search(r"\d", seg):
                notes.append(f"Not counted: no amount of money found in \u201c{seg.strip()}\u201d.")
            continue
        value = float(m.group(2).replace(",", ""))
        scale = (m.group(3) or "").lower()
        value *= {"k": 1e3, "thousand": 1e3, "m": 1e6, "million": 1e6, "bn": 1e9}.get(scale, 1)
        currency = currency_of(m.group(1) or m.group(4), default_currency)
        per = next((p for p, pat in PER_WORDS if re.search(pat, low)), None)
        kind = next((k for k, d in index["spend_kinds"].items()
                     if any(re.search(r"\b" + re.escape(w) + r"\b", low) for w in d["words"])), None)
        found.append({"amount": value, "currency": currency, "per": per, "kind": kind,
                      "currency_given": bool(m.group(1) or m.group(4)), "text": seg.strip()})
    return found, notes


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Is it worth it? Every sum by script.")
    parser.add_argument("--data", required=True)
    parser.add_argument("--recipes", default=str(RECIPES))
    parser.add_argument("--out", help="also write the result to this file")
    args = parser.parse_args(argv)
    try:
        answers = json.loads(Path(args.data).read_text(encoding="utf-8"))
        index = json.loads(Path(args.recipes).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"errors": [f"cannot read input: {exc}"]}))
        return 1

    errors = []
    rid = answers.get("recipe", "generic")
    if rid == "generic":
        recipe = dict(index["generic_blueprint"])
        recipe.setdefault("title", answers.get("work_title") or "Your own recurring document")
        title = answers.get("work_title") or recipe["title"]
    else:
        recipe = next((r for r in index["recipes"] if r["id"] == rid), None)
        if recipe is None:
            errors.append(f"unknown recipe {rid}")
        title = recipe["title"] if recipe else rid
    frequency = answers.get("frequency")
    if frequency not in FREQUENCIES:
        errors.append("frequency must be Weekly, Monthly or Quarterly")
    people = answers.get("people")
    if people not in PEOPLE:
        errors.append("people must be 1 to 2, 3 to 5 or 6 or more")
    late = [c for c in answers.get("late_or_wrong", []) if c in CONSEQUENCES]
    unknown = [c for c in answers.get("late_or_wrong", []) if c not in CONSEQUENCES]
    if unknown:
        errors.append(f"unknown answers: {unknown}")
    if errors:
        print(json.dumps({"errors": errors}))
        return 1

    sizing = recipe["sizing"]
    runs = FREQUENCIES[frequency]
    credit_currency = answers.get("credit_currency", index.get("price_currency_default", "USD"))
    price = float(answers.get("price_per_credit", index.get("price_per_credit_default", 0.01)))
    share = float(answers.get("share_that_can_stop", 1.0))
    share = min(max(share, 0.0), 1.0)
    assumptions, working = [], []

    # The measure that moves -------------------------------------------------
    measure_map = sizing.get("measure_map", {})
    measures = []
    for c in late:
        m = measure_map.get(c)
        if m and m not in measures:
            measures.append(m)
    for m in recipe.get("measures", []):
        if m not in measures:
            measures.append(m)
    headline = measures[0]
    also = measures[1:3]
    why = f"You said: {', '.join(c.lower() for c in late)}." if late else "From what this work is for."
    why = why[:1].upper() + why[1:] if why else why

    # Cash that can stop -------------------------------------------------------
    spend, notes = parse_spend(str(answers.get("outside_spend", "")), index, credit_currency)
    counted, cash_lines = [], []
    allowed = set(sizing.get("spend_that_can_stop", []))
    for s in spend:
        label = index["spend_kinds"].get(s["kind"], {}).get("label", "Unnamed spend")
        if s["kind"] is None:
            notes.append(f"Not counted: \u201c{s['text']}\u201d does not say what the spend is "
                         "(contractors, overtime or outside advisers).")
            continue
        if s["kind"] not in allowed:
            notes.append(f"Not counted: {label.lower()} does not usually stop because of this work.")
            continue
        if s["kind"] in ("contractors", "overtime") and "Contractors or overtime" not in late:
            notes.append(f"Not counted: {label.lower()} was named, but not chosen as what happens when "
                         "it is late or wrong.")
            continue
        per = s["per"]
        if per is None:
            per = "year"
            assumptions.append(f"\u201c{s['text']}\u201d did not say how often, so it is taken as a year.")
        if not s["currency_given"]:
            assumptions.append(f"\u201c{s['text']}\u201d did not give a currency, so it is taken as "
                               f"{SYMBOL.get(s['currency'], s['currency'])}.")
        yearly = s["amount"] * (runs if per == "run" else PER_YEAR[per]) * share
        counted.append({"kind": s["kind"], "label": label, "currency": s["currency"], "per_year": yearly})
        times = f"{runs} runs a year" if per == "run" else {"year": "1", "month": "12 months", "quarter": "4 quarters",
                                                            "week": "52 weeks"}[per]
        line = f"{label}: {money(s['amount'], s['currency'])} a {per}"
        if per != "year":
            line += f" \u00d7 {times}"
        if share < 1:
            line += f" \u00d7 {share:.0%} that can stop"
        if per != "year" or share < 1:
            line += f" = {money(yearly, s['currency'])} a year"
        working.append(line)
        cash_lines.append(line)
    currencies = {c["currency"] for c in counted}
    if counted and len(currencies) == 1:
        cash_currency = currencies.pop()
        cash = sum(c["per_year"] for c in counted)
        cash_status, cash_text = "sized", f"{money(cash, cash_currency)} a year"
        assumptions.append("Count this cash only when the spend actually stops: a contract not renewed, "
                           "overtime not approved, an adviser not engaged.")
        if share == 1:
            assumptions.append("All of the spend you named can stop. If only part can, tell me the share.")
    elif counted:
        cash_status, cash_text, cash, cash_currency = "not sized", "Not sized: more than one currency", None, None
        notes.append("Not added up: the spend is in more than one currency.")
    else:
        cash_status, cash_text, cash, cash_currency = "not sized", "Not sized", None, None
        if not spend and not notes:
            notes.append("No outside spend was named, so no cash is counted. The case rests on the measure that moves.")

    # Cowork running cost -------------------------------------------------------
    credits = answers.get("credits_per_run") or sizing.get("credits_per_run")
    if credits:
        low_c, high_c = float(credits["low"]), float(credits["high"])
        basis = "your own measured runs" if answers.get("credits_per_run") else "a planning range"
        cost_low, cost_high = low_c * runs * price, high_c * runs * price
        price_text = f"{SYMBOL.get(credit_currency, credit_currency + ' ')}{price:g}"
        working.append(f"Cowork running cost: {low_c:,.0f} to {high_c:,.0f} credits a run ({basis}) \u00d7 "
                       f"{runs} runs a year \u00d7 {price_text} a credit = "
                       f"{money_range(cost_low, cost_high, credit_currency)} a year")
        cost_status, cost_text = "sized", f"{money_range(cost_low, cost_high, credit_currency)} a year"
        if answers.get("credits_per_run"):
            assumptions.append(f"{low_c:,.0f} to {high_c:,.0f} credits a run come from your own measured runs.")
        else:
            assumptions.append(f"{low_c:,.0f} to {high_c:,.0f} credits a run is a planning range, not a quote. "
                               "Replace it with your own measured runs.")
        assumptions.append(f"Price per credit is a setting: {SYMBOL.get(credit_currency, credit_currency)}{price:g}. "
                           "Use your own agreed price if you have one.")
    else:
        cost_low = cost_high = None
        cost_status, cost_text = "not sized", "Not sized yet"
        notes.append(sizing.get("credits_basis", "No planning range yet. Measure a few runs first."))
    assumptions.append(f"{frequency} means {runs} runs a year.")

    # Net a year ------------------------------------------------------------------
    if cash_status == "sized" and cost_status == "sized" and cash_currency == credit_currency:
        net_low, net_high = cash - cost_high, cash - cost_low
        net_status = "sized"
        net_text = f"{money_range(net_low, net_high, cash_currency)} a year"
        working.append(f"Net a year: {money(cash, cash_currency)} \u2212 "
                       f"({money_range(cost_low, cost_high, credit_currency)}) = {money_range(net_low, net_high, cash_currency)}")
    else:
        net_low = net_high = None
        net_status = "not sized"
        if cash_status == "sized" and cost_status == "sized":
            net_text = "Not sized: the spend and the running cost are in different currencies"
        elif cash_status != "sized":
            net_text = "Not sized: no cash that can stop"
        else:
            net_text = "Not sized: no running cost yet"
    assumptions.append("Time is never turned into money here.")

    told = [{"title": "How often", "value": frequency},
            {"title": "People who touch it", "value": people},
            {"title": "When it is late or wrong", "value": ", ".join(late) if late else "Nothing chosen"},
            {"title": "Outside spend", "value": str(answers.get("outside_spend") or "None named")}]
    out = {
        "recipe": rid, "recipe_title": title, "frequency": frequency, "runs_per_year": runs,
        "measure_headline": headline, "measure_also": ", ".join(also), "measure_why": why,
        "cash": {"status": cash_status, "per_year": cash, "currency": cash_currency, "lines": cash_lines},
        "running_cost": {"status": cost_status, "low": cost_low, "high": cost_high, "currency": credit_currency},
        "net": {"status": net_status, "low": net_low, "high": net_high},
        "cash_text": cash_text, "cost_text": cost_text, "net_text": net_text,
        "cost_badge": "Planning range" if cost_status == "sized" and not answers.get("credits_per_run") else (
            "Your measured runs" if cost_status == "sized" else "Not sized yet"),
        "told": told, "working": working or ["Nothing to add up yet."], "assumptions": assumptions,
        "notes": notes,
    }
    text = json.dumps(out, ensure_ascii=False, indent=1)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
