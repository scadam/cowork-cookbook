#!/usr/bin/env python3
"""Launchpad for Cowork: build the person's skill folders from a blueprint.

Fills the blueprint for a recipe (../references/skill-blueprints.md) with what
was learned from the person's own example, checks every skill it makes, and
writes the folders only when every check passes. It never publishes: saving
to the person's skills folder is done afterwards with Cowork's own skill saving.

Usage
  python3 make_skill.py --recipe variance-commentary --spec style.json --out working/launchpad/skills
                        [--existing name1,name2] [--as-of 2026-11-11] [--dry-run]

style.json holds what was learned (all optional except document_title):
  document_title, audience, cadence (weekly|monthly|quarterly), sections [..],
  tone, threshold, template, sign_off, owners [..], inputs [..],
  example_lines [..], learned_from, skill_name, example_prompt, standard,
  columns [..] (app recipes), threshold_number.

Output (stdout, JSON): the skills written with their files and checks, the
expected file count for the publish check, and card data for the progress card.
Standard library only.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
REFS = HERE.parent / "references"
ALLOWED_KEYS = {"name", "description", "license", "compatibility", "metadata", "allowed-tools"}
NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september",
          "october", "november", "december"]
MONTH_TOKENS = set(MONTHS) | {m[:3] for m in MONTHS} | {"sept"}
PERIOD_WORD = {"weekly": "week", "monthly": "month", "quarterly": "quarter"}
BANNED = [
    (re.compile(r"!"), "exclamation mark"),
    (re.compile(r"\b(hours?|minutes?|days?|time)\s+(saved|freed|back)\b", re.I), "claim about time given back"),
    (re.compile(r"\bproductiv", re.I), "productivity claim"),
    (re.compile(r"aka\.ms|sharepoint\.com|microsoft-?my", re.I), "internal link"),
    (re.compile(r"\{\{[^}]*\}\}"), "unfilled placeholder"),
]


def slug(text: str) -> str:
    toks = re.sub(r"[^a-z0-9]+", " ", text.lower()).split()
    toks = [t for t in toks if t not in MONTH_TOKENS and not re.fullmatch(r"(19|20)\d\d|v\d+|fy\d+|q[1-4]|final|draft", t)]
    out = "-".join(toks)
    while len(out) > 64 and "-" in out:
        out = out.rsplit("-", 1)[0]
    return out[:64].strip("-")


def sentence_case(title: str) -> str:
    """'Monthly management pack' -> 'monthly management pack'; 'Audit Committee paper' stays."""
    toks = title.split()
    if len(toks) >= 2 and toks[0][:1].isupper() and toks[0][1:].islower() and toks[1][:1].islower():
        return toks[0].lower() + title[len(toks[0]):]
    return title


def parse_blueprints(text: str) -> tuple[dict, dict, str]:
    blueprints = {m.group(1): m.group(2).strip() + "\n" for m in re.finditer(
        r"<!-- blueprint: (\S+) -->\n(.*?)<!-- end blueprint -->", text, re.S)}
    tests = {m.group(1): m.group(2) for m in re.finditer(
        r"<!-- tests: (\S+) -->\n```json\n(.*?)\n```\n<!-- end tests -->", text, re.S)}
    house = re.search(r"<!-- house-style -->\n(.*?)<!-- end house-style -->", text, re.S)
    return blueprints, tests, house.group(1) if house else ""


def fill(template: str, values: dict) -> tuple[str, list[str]]:
    missing = []

    def sub(m: re.Match) -> str:
        key = m.group(1)
        if key not in values:
            missing.append(key)
            return m.group(0)
        return str(values[key])
    return re.sub(r"\{\{([a-z_]+)\}\}", sub, template), missing


def frontmatter(text: str) -> tuple[dict, str, str]:
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
    if not m:
        return {}, "", text
    raw, body = m.group(1), m.group(2)
    keys, desc_lines, current = {}, [], None
    for line in raw.splitlines():
        top = re.match(r"^([A-Za-z][\w-]*):\s*(.*)$", line)
        if top and not line.startswith(" "):
            current = top.group(1)
            keys[current] = top.group(2)
            continue
        if current == "description":
            desc_lines.append(line.strip())
    desc = keys.get("description", "")
    if desc.strip() in (">-", ">", "|", "|-"):
        joiner = " " if desc.strip().startswith(">") else "\n"
        desc = joiner.join(l for l in desc_lines if l)
    return keys, desc.strip(), body


def check_skill(name: str, text: str, companions: int) -> list[str]:
    problems = []
    keys, desc, body = frontmatter(text)
    if not keys:
        return ["no frontmatter"]
    extra = set(keys) - ALLOWED_KEYS
    if extra:
        problems.append(f"frontmatter keys not allowed: {sorted(extra)}")
    fm_name = keys.get("name", "").strip()
    if fm_name != name or not NAME_RE.match(name) or len(name) > 64:
        problems.append(f"name {fm_name!r} must be kebab-case, at most 64 characters and match its folder {name!r}")
    units = len(desc.encode("utf-16-le")) // 2
    if not 1 <= units <= 1024:
        problems.append(f"description is {units} characters; it must be 1 to 1024")
    if len(re.findall(r'"[^"]{2,}"', desc)) < 3:
        problems.append("description needs at least three quoted trigger phrases")
    if "Do not use" not in desc:
        problems.append("description needs a 'Do not use' line")
    for heading in ("## When NOT to use", "## Inputs", "## Steps", "## Output", "## Decisions kept with people",
                    "## Guardrails"):
        if heading not in body:
            problems.append(f"missing section {heading}")
    if not re.search(r"(?m)^1\. ", body):
        problems.append("steps must be numbered")
    if not re.search(r"(?i)never send", text):
        problems.append("must say it never sends")
    if not re.search(r"scripts/\w+\.py", body):
        problems.append("figures must come from a script")
    tokens = len(text) / 4
    if tokens > 5000:
        problems.append(f"about {int(tokens)} tokens; keep under about 5,000")
    if companions > 19:
        problems.append(f"{companions} companion files; at most 19")
    for pattern, why in BANNED:
        m = pattern.search(desc + "\n" + body)  # metadata values such as category: productivity are not claims
        if m:
            problems.append(f"{why}: {m.group(0)!r}")
    return problems


def short(text: str, limit: int = 90) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[:limit - 1].rsplit(" ", 1)[0] + "\u2026"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Build the person's skill folders from a blueprint.")
    parser.add_argument("--recipe", required=True, help="recipe id, or generic")
    parser.add_argument("--spec", required=True, help="what was learned from the person's example (JSON)")
    parser.add_argument("--out", required=True, help="folder to write the skill folders into")
    parser.add_argument("--existing", default="", help="names of skills the person already has")
    parser.add_argument("--as-of", default=date.today().isoformat())
    parser.add_argument("--dry-run", action="store_true", help="check only; write nothing")
    args = parser.parse_args(argv)

    try:
        index = json.loads((REFS / "recipes.json").read_text(encoding="utf-8"))
        blueprints, tests, house_tpl = parse_blueprints((REFS / "skill-blueprints.md").read_text(encoding="utf-8"))
        spec = json.loads(Path(args.spec).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"errors": [f"cannot read input: {exc}"]}))
        return 1

    if args.recipe == "generic":
        recipe = dict(index["generic_blueprint"])
        bp = {"main": recipe["main"], "helpers": recipe["helpers"], "run_prompt": recipe["run_prompt"],
              "cadence": spec.get("cadence", "monthly")}
        rinputs, routputs = [], []
    else:
        recipe = next((r for r in index["recipes"] if r["id"] == args.recipe), None)
        if recipe is None:
            print(json.dumps({"errors": [f"unknown recipe {args.recipe}"]}))
            return 1
        bp = recipe["blueprint"]
        rinputs = recipe.get("inputs", [])

    try:
        as_of = date.fromisoformat(args.as_of)
    except ValueError:
        as_of = date.today()
    cadence = str(spec.get("cadence") or bp.get("cadence") or "monthly").lower()
    period_word = PERIOD_WORD.get(cadence, "month")
    next_period = {"weekly": "this week's", "quarterly": f"Q{(as_of.month - 1) // 3 + 1}"}.get(
        cadence, MONTHS[as_of.month - 1].capitalize())
    document_title = str(spec.get("document_title") or recipe.get("title", "the document")).strip()
    existing = {x.strip() for x in args.existing.split(",") if x.strip()}

    def unique(name: str, taken: set) -> str:
        base, n = name, 2
        while name in taken or name in existing:
            name = f"{base}-{n}"
            n += 1
        return name

    suffix = bp["main"].get("suffix", "")
    if spec.get("skill_name"):
        main_name = re.sub(r"[^a-z0-9]+", "-", str(spec["skill_name"]).lower()).strip("-")
    else:
        base = slug(document_title)
        main_name = base + (f"-{suffix}" if base and suffix and not base.endswith(suffix) else "")
    while len(main_name) > 64 and "-" in main_name:
        main_name = main_name.rsplit("-", 1)[0]
    if not main_name or not NAME_RE.match(main_name):
        main_name = bp["main"]["default_name"]
    taken: set = set()
    main_name = unique(main_name, taken)
    taken.add(main_name)
    roles = {}
    for helper in bp.get("helpers", []):
        roles[helper["role"]] = unique(helper["name"], taken)
        taken.add(roles[helper["role"]])

    sections = spec.get("sections") or ["Not stated in the example; ask before the first run."]
    owners = spec.get("owners") or []
    inputs = spec.get("inputs") or rinputs or ["The files the person names for the period"]
    threshold = spec.get("threshold") or "Not stated in the example; ask before the first run."
    number = spec.get("threshold_number")
    if number is None:
        found = re.search(r"\d+(\.\d+)?", str(threshold))
        number = float(found.group(0)) if found else 0
    doc = sentence_case(document_title)
    template = bp["run_prompt"]
    if cadence == "weekly":
        template = template.replace("the {next_period}", "this week's")
    run_prompt = spec.get("example_prompt") or template.replace("{next_period}", next_period) \
        .replace("{document_title}", doc)
    values = {
        "name": main_name, "document_title": document_title, "doc": doc,
        "audience": spec.get("audience") or "the people who read it",
        "cadence": cadence, "period_word": period_word, "next_period": next_period,
        "run_prompt": run_prompt,
        "inputs_list": "\n".join(f"- {x}" for x in inputs),
        "sections_list": "\n".join(f"- {x}" for x in sections),
        "sections_inline": ", ".join(sections),
        "tone": spec.get("tone") or "Not stated in the example; ask before the first run.",
        "threshold": threshold, "threshold_number": f"{float(number):g}",
        "template": spec.get("template") or "Not stated in the example; ask before the first run.",
        "sign_off": spec.get("sign_off") or "Not stated in the example; ask before the first run.",
        "owners_inline": ", ".join(owners) if owners else "the owners named in the inputs",
        "learned_from": spec.get("learned_from") or "the person's example",
        "as_of": as_of.isoformat(),
        "example_lines": "\n".join(f"- {x}" for x in spec.get("example_lines", [])) or "None recorded.",
        "standard": spec.get("standard") or "the paper standard the author names",
        "columns_inline": ", ".join(spec.get("columns") or recipe.get("app_brief", {}).get("columns", [])
                                    or ["the tracker's own columns"]),
        "helper_inputs": roles.get("helper_inputs", ""), "helper_questions": roles.get("helper_questions", ""),
        "helper_review": roles.get("helper_review", ""),
    }

    plan = [(main_name, bp["main"])] + [(roles[h["role"]], h) for h in bp.get("helpers", [])]
    built, errors, files_total = [], [], 0
    out_root = Path(args.out)
    staged = {}
    for name, part in plan:
        template = blueprints.get(part["template"])
        if template is None:
            errors.append(f"{name}: no blueprint {part['template']}")
            continue
        text, missing = fill(template, values)
        test_text, missing_t = fill(tests.get(part["template"], "[]"), values)
        house, missing_h = fill(house_tpl, values)
        for key in set(missing + missing_t + missing_h):
            errors.append(f"{name}: no value for {{{{{key}}}}}")
        try:
            cases = json.loads(test_text)
        except json.JSONDecodeError as exc:
            errors.append(f"{name}: test cases are not valid JSON ({exc})")
            cases = []
        if len(cases) < 3:
            errors.append(f"{name}: needs three or more test cases")
        files = {"SKILL.md": text, "references/test-cases.json": json.dumps(cases, ensure_ascii=False, indent=1) + "\n"}
        if name == main_name:
            files["references/house-style.md"] = house
        for script in part.get("scripts", []):
            files[f"scripts/{script}"] = (HERE / script).read_text(encoding="utf-8")
        problems = check_skill(name, text, len(files) - 1)
        errors.extend(f"{name}: {p}" for p in problems)
        staged[name] = files
        files_total += len(files)
        built.append({"name": name, "role": "main" if name == main_name else "helper",
                      "files": sorted(files), "checks": "passed" if not problems else problems})

    if "user-config" in str(out_root.resolve()) or "/skills/launchpad-" in str(out_root.resolve()):
        errors.append("write the folders to the workspace (for example working/launchpad/skills); "
                      "saving to the person's skills folder is done with Cowork's own skill saving")
    result = {"recipe": args.recipe, "main": main_name, "helpers": [n for n, _ in plan[1:]],
              "skills": built, "files_expected": files_total, "out": str(out_root), "run_prompt": run_prompt}
    if errors:
        result["errors"] = errors
        print(json.dumps(result, ensure_ascii=False, indent=1))
        return 1
    if not args.dry_run:
        for name, files in staged.items():
            folder = out_root / name
            if folder.exists():
                shutil.rmtree(folder)
            for rel, content in files.items():
                path = folder / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
    test_count = sum(len(json.loads(fill(tests.get(p["template"], "[]"), values)[0])) for _, p in plan)
    helpers = [n for n, _ in plan[1:]]
    result["card"] = {
        "skill_title": document_title,
        "progress": {"done": 5, "total": 6},
        "steps": [
            {"text": f"Read your example: {short(values['learned_from'], 70)}", "icon": "CheckmarkCircle"},
            {"text": f"Wrote the main skill: {main_name}", "icon": "CheckmarkCircle"},
            {"text": (f"Wrote {len(helpers)} helper skill{'s' if len(helpers) != 1 else ''}: {', '.join(helpers)}"
                      if helpers else "No helper skills needed"), "icon": "CheckmarkCircle"},
            {"text": "Added a script for every figure", "icon": "CheckmarkCircle"},
            {"text": f"Wrote {test_count} test cases", "icon": "CheckmarkCircle"},
            {"text": "Next: test it on a past period", "icon": "ArrowRight"},
        ],
        "learned": [
            {"title": "Sections", "value": short(values["sections_inline"])},
            {"title": "Tone", "value": short(values["tone"])},
            {"title": "Threshold", "value": short(values["threshold"])},
            {"title": "Template", "value": short(values["template"])},
            {"title": "Sign-off", "value": short(values["sign_off"])},
        ],
        "built": [
            {"title": "Main skill", "value": main_name},
            {"title": "Helper skills", "value": ", ".join(helpers) if helpers else "None"},
            {"title": "Figures", "value": "Worked out by a script, never typed by hand"},
            {"title": "Test cases", "value": str(test_count)},
            {"title": "Sends", "value": "Nothing"},
        ],
    }
    result["written"] = not args.dry_run
    print(json.dumps(result, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
