#!/usr/bin/env python3
"""Launchpad for Cowork: build cards and question cards from templates.

The model fills the data, this script returns the JSON, and the model shows it
unchanged: the card with render_ui (type, version, body and any actions) and
the questions with AskUserQuestion, in the same reply.

Usage
  python3 cards.py list
  python3 cards.py build TEMPLATE --data DATA.json [--merge MORE.json ...]
  python3 cards.py build TEMPLATE < DATA.json
  python3 cards.py check CARD.json [--questions QUESTIONS.json]

Output of build (stdout, JSON):
  {"template": NAME, "card": {...} or null, "questions": [...],
   "markdown": "..." (markdown templates only), "warnings": [...]}
Exit 0 when everything is valid. Exit 1 with {"errors": [...]} when not.

Templates live in ../references/cards.json next to this script. Standard
library only; nothing is fetched, sent or written.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TEMPLATE_FILE = HERE.parent / "references" / "cards.json"

# ---------------------------------------------------------------- the rules
ALLOWED = {
    "TextBlock", "RichTextBlock", "TextRun", "ColumnSet", "Column", "Container",
    "Image", "ImageSet", "FactSet", "Table", "TableRow", "TableCell", "Badge",
    "Icon", "Accordion", "AccordionPage", "TabSet", "TabPage", "Carousel",
    "CarouselPage", "ProgressBar",
}
NESTED_ONLY = {"Column", "TableRow", "TableCell", "AccordionPage", "TabPage",
               "CarouselPage", "TextRun"}
ELEMENT = "element"
CHILD_RULES = {
    "Container": {"items": ELEMENT},
    "Column": {"items": ELEMENT},
    "TableCell": {"items": ELEMENT},
    "AccordionPage": {"items": ELEMENT},
    "TabPage": {"items": ELEMENT},
    "CarouselPage": {"items": ELEMENT},
    "ColumnSet": {"columns": {"Column"}},
    "Table": {"rows": {"TableRow"}},
    "TableRow": {"cells": {"TableCell"}},
    "Accordion": {"pages": {"AccordionPage"}},
    "TabSet": {"pages": {"TabPage"}},
    "Carousel": {"pages": {"CarouselPage"}},
    "ImageSet": {"images": {"Image"}},
    "RichTextBlock": {"inlines": {"TextRun"}},
}
ENUMS = {
    "size_text": {"Small", "Default", "Medium", "Large", "ExtraLarge"},
    "weight": {"Lighter", "Default", "Bolder"},
    "mono_color": {"Default"},
    "spacing": {"None", "ExtraSmall", "Small", "Default", "Medium", "Large",
                "ExtraLarge", "Padding"},
    "image_size": {"Auto", "Stretch", "Small", "Medium", "Large"},
    "icon_size": {"xxSmall", "xSmall", "Small", "Standard", "Medium", "Large",
                  "xLarge", "xxLarge"},
    "icon_style": {"Regular", "Filled"},
    "badge_style": {"Default", "Subtle", "Informative", "Accent", "Good",
                    "Attention", "Warning"},
    "badge_size": {"Medium", "Large", "ExtraLarge"},
    "badge_shape": {"Square", "Rounded", "Circular"},
    "container_style": {"default", "emphasis"},
    "halign": {"Left", "Center", "Right"},
    "valign": {"Top", "Center", "Bottom"},
    "accordion_header": {"Small", "Medium", "Large", "XLarge"},
}
# Mono theme. Icons and text use the Default colour, never Accent. Every badge is
# tinted. A badge whose colour carries meaning keeps it (STATUS_BADGES: the invented
# sample flag, test results, Kept and the evidence statuses); every other badge is a
# label, such as the kinds Skill, App, Routine, Schedule and Trigger, and uses the
# Default style. No badge uses Accent.
MEANING_STYLES = {"Default", "Subtle", "Informative", "Good", "Attention", "Warning"}
STATUS_BADGES = {
    "invented sample data": {"Warning"},
    "different": MEANING_STYLES, "same": MEANING_STYLES, "kept": MEANING_STYLES,
    "supported": MEANING_STYLES, "partly supported": MEANING_STYLES,
    "not supported": MEANING_STYLES, "awaiting owner": MEANING_STYLES,
}
KIND_LABELS = {"skill", "app", "routine", "schedule", "trigger"}
LINK_HOSTS = ("learn.microsoft.com", "support.microsoft.com", "scott-adams.ai",
              "scadam.github.io", "github.com")
BANNED_TYPES_RE = re.compile(r"^(Input\.|Action\.(Submit|Execute|ToggleVisibility|ShowCard)|ActionSet$)")
VISIBLE_KEYS = {"text", "headerTitle", "altText", "tooltip", "title", "value"}

# Text hygiene for everything the person sees. Patterns are written as
# regular expressions on purpose.
HYGIENE = [
    (re.compile(r"!"), "no exclamation marks"),
    (re.compile(r"[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\uFE0F\U0001F1E6-\U0001F1FF]"),
     "no emoji or pictographs"),
    (re.compile(r"\{\{|\{[A-Za-z_$][\w.$|]*\}"), "unfilled placeholder"),
    (re.compile(r"\b(hours?|minutes?|days?|weeks?|time)\s+(saved|freed)\b", re.I),
     "no claims about time given back; name the outcome instead"),
    (re.compile(r"\b(give|gives|giving|get|gets|getting)\s+(you\s+)?(\w+\s+){0,3}(hours?|minutes?|time)\s+back\b", re.I),
     "no claims about time given back; name the outcome instead"),
    (re.compile(r"\bsav(e|es|ed|ing)\s+(you\s+)?(\d+|an?|hours?|minutes?|days?|time)\b", re.I),
     "no claims about time given back; name the outcome instead"),
    (re.compile(r"\bproductiv", re.I), "no productivity claims"),
    (re.compile(r"\d+\s*%\s*(faster|quicker|less\s+time|more\s+efficient)", re.I),
     "no speed or efficiency percentages"),
    (re.compile(r"\b\d[\d,]*\s+(other\s+)?(customers|clients|organi[sz]ations|companies|firms|enterprises)\b", re.I),
     "never count other organisations"),
    (re.compile(r"\b(customers|organi[sz]ations|companies|clients)\s+(like\s+you|did\s+this|use\s+this|have\s+done)", re.I),
     "never mention other organisations"),
    (re.compile(r"aka\.ms|sharepoint\.com|microsoft-?my|\.corp\.microsoft", re.I),
     "no internal links"),
    (re.compile(r"\bGB{2}\b|re-?imagin", re.I), "never mention where recipes came from"),
    (re.compile(r"\b(render_ui|AskUserQuestion|ExecuteSql|SearchM365|ReadFileContent|"
                r"CopyArtifact|CreateArtifact|EditArtifact|DeleteArtifact|"
                r"SetupScheduledPrompt|SetupEventTrigger|GetScheduledPrompts|"
                r"GetEventTriggers|microsoft_docs_search|microsoft_docs_fetch)\b"),
     "no tool names"),
    (re.compile(r"\b[\w-]+\.(py|json)\b|/mnt/|\bworking/|[A-Za-z]:\\"), "no file paths"),
    (re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I),
     "no IDs"),
    (re.compile(r"\bHTTP\s?[45]\d\d\b|\b0x[0-9A-Fa-f]{6,}\b|-32\d{3}\b"), "no error codes"),
    (re.compile(r"\b(amazing|awesome|incredible|revolutionary|revolutioni[sz]e|game[- ]changer|"
                r"supercharge|seamless(ly)?|magic(al)?|effortless(ly)?|10x)\b", re.I),
     "no hype"),
]
CATCH_ALL = {"other", "something else", "none of these", "none of the above",
             "anything else", "other option", "others"}


class Problems:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def err(self, where: str, msg: str) -> None:
        self.errors.append(f"{where}: {msg}")

    def warn(self, where: str, msg: str) -> None:
        self.warnings.append(f"{where}: {msg}")


# ---------------------------------------------------------- template engine
PLACEHOLDER = re.compile(r"\{([A-Za-z_$][\w.$]*)(\|[a-z]+)?\}")
MISSING = object()


def resolve(ctx: dict, path: str):
    cur = ctx
    for part in path.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        elif isinstance(cur, list) and part.isdigit() and int(part) < len(cur):
            cur = cur[int(part)]
        else:
            return MISSING
    return cur


def to_text(value) -> str:
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, list):
        return ", ".join(to_text(v) for v in value)
    return str(value)


def apply_filter(text: str, flt: str | None) -> str:
    if flt == "|cell":
        return text.replace("|", "/").replace("\n", " ").strip()
    if flt == "|lower":
        return text.lower()
    return text


def truthy(ctx: dict, cond: str) -> bool:
    cond = cond.strip()
    for op in ("==", "!=", ">"):
        if op in cond:
            left, right = (s.strip() for s in cond.split(op, 1))
            value = resolve(ctx, left)
            value = None if value is MISSING else value
            if op == ">":
                try:
                    return float(value or 0) > float(right)
                except (TypeError, ValueError):
                    return False
            right_v = right.strip("'\"")
            equal = to_text(value) == right_v if value is not None else right_v in ("", "null")
            return equal if op == "==" else not equal
    negate = cond.startswith("!")
    value = resolve(ctx, cond.lstrip("!"))
    result = value is not MISSING and bool(value)
    return not result if negate else result


def expand(node, ctx: dict, where: str, probs: Problems):
    if isinstance(node, str):
        def sub(m: re.Match) -> str:
            value = resolve(ctx, m.group(1))
            if value is MISSING or value is None:
                probs.err(where, f"missing value for {{{m.group(1)}}}")
                return m.group(0)
            return apply_filter(to_text(value), m.group(2))
        return PLACEHOLDER.sub(sub, node)
    if isinstance(node, list):
        out = []
        for i, item in enumerate(node):
            w = f"{where}[{i}]"
            if isinstance(item, dict) and "$for" in item:
                seq = resolve(ctx, item["$for"])
                if seq is MISSING or seq is None:
                    seq = []
                if not isinstance(seq, list):
                    probs.err(w, f"{item['$for']} is not a list")
                    continue
                limit = item.get("$limit")
                if isinstance(limit, int):
                    seq = seq[:limit]
                name = item.get("as", "item")
                for n, element in enumerate(seq):
                    sub_ctx = dict(ctx)
                    sub_ctx[name] = element
                    sub_ctx["$index"] = n + 1
                    sub_ctx["$first"] = n == 0
                    sub_ctx["$last"] = n == len(seq) - 1
                    for part in item.get("do", []):
                        result = expand(part, sub_ctx, f"{w}.{name}[{n}]", probs)
                        if isinstance(part, dict) and ("$if" in part or "$for" in part):
                            out.extend(result if isinstance(result, list) else [result])
                        else:
                            out.append(result)
                continue
            if isinstance(item, dict) and "$if" in item:
                branch = item.get("do", []) if truthy(ctx, item["$if"]) else item.get("else", [])
                out.extend(expand(list(branch), ctx, w, probs))
                continue
            out.append(expand(item, ctx, w, probs))
        return out
    if isinstance(node, dict):
        if set(node) <= {"$value", "$default"} and "$value" in node:
            value = resolve(ctx, node["$value"])
            if value is MISSING or value is None:
                if "$default" in node:
                    return node["$default"]
                probs.err(where, f"missing value for {node['$value']}")
                return None
            return value
        if "$if" in node or "$for" in node:
            return expand([node], ctx, where, probs)
        out = {}
        for key, value in node.items():
            if isinstance(value, dict) and "$value" in value and value.get("$default") == "$omit":
                resolved = resolve(ctx, value["$value"])
                if resolved is MISSING or resolved is None or resolved == "":
                    continue
            out[key] = expand(value, ctx, f"{where}.{key}", probs)
        return out
    return node


# ---------------------------------------------------------------- checking
# ---------------------------------------------------------------- the person's own words
# Titles, file names, the role the person gave and what they typed are shown as they wrote them.
# The wording rules are for what Launchpad writes, so the person's own words are set aside first.
THEIRS: list = []
THEIRS_FILE = Path("working/launchpad/theirs.json")
THEIR_KEYS = ("theirs", "role", "industry", "their_words")


def set_theirs(values) -> None:
    """Remember the person's own words (strings, lists or dicts of them, nested)."""
    global THEIRS
    found = set()

    def walk(v):
        if isinstance(v, str):
            v = re.sub(r"\s+", " ", v).strip()
            if len(v) >= 3 and re.search(r"[A-Za-z0-9]", v):
                found.add(v)
        elif isinstance(v, (list, tuple, set)):
            for x in v:
                walk(x)
        elif isinstance(v, dict):
            for x in v.values():
                walk(x)
    walk(values)
    THEIRS = sorted(found, key=len, reverse=True)


def theirs_in(data) -> list:
    """The parts of card data that are the person's own words."""
    out = []
    if isinstance(data, dict):
        for key in THEIR_KEYS:
            if key in data:
                out.append(data[key])
        draft = data.get("profile_draft")
        if isinstance(draft, dict):
            out.append(draft.get("role"))
    return out


def saved_theirs() -> list:
    try:
        return [json.loads(THEIRS_FILE.read_text(encoding="utf-8"))] if THEIRS_FILE.exists() else []
    except (OSError, ValueError):
        return []


def without_theirs(text: str) -> str:
    low = text.lower()
    for v in THEIRS:
        if v.lower() in low:
            text = re.sub(re.escape(v), " ", text, flags=re.I)
            low = text.lower()
    return text


def check_text(where: str, text: str, probs: Problems) -> None:
    text = without_theirs(text)
    for pattern, why in HYGIENE:
        m = pattern.search(text)
        if m:
            probs.err(where, f"{why} (found {m.group(0)!r})")


def check_url(where: str, url, prefix: str, probs: Problems, kind: str) -> None:
    if not isinstance(url, str) or not url.startswith("https://"):
        probs.err(where, f"{kind} must be an https address")
        return
    if kind == "picture" and not url.startswith(prefix):
        probs.err(where, f"pictures may only come from {prefix}")
    if kind == "link":
        host = url.split("/")[2].lower()
        if not any(host == h or host.endswith("." + h) for h in LINK_HOSTS):
            probs.err(where, f"link host {host} is not on the allowed list")
        if re.search(r"aka\.ms|sharepoint\.com|microsoft-?my", url, re.I):
            probs.err(where, "no internal links")


def enum(where, obj, key, allowed, probs) -> None:
    if key in obj and obj[key] not in allowed:
        probs.err(where, f"{key}={obj[key]!r} is not one of {sorted(allowed)}")


def mono_colour(where: str, el: dict, what: str, probs: Problems) -> None:
    colour = el.get("color", "Default")
    if colour != "Default":
        probs.err(where, f"{what} use the Default colour in the mono theme, not {colour!r}")


def check_badge_style(where: str, el: dict, probs: Problems) -> None:
    if el.get("appearance") != "Tint":
        probs.err(where, "badges say appearance Tint in the mono theme (left out, a badge can draw filled)")
    label = str(el.get("text", "")).strip()
    style = el.get("style", "Default")
    allowed = STATUS_BADGES.get(label.lower())
    if style == "Accent":
        probs.err(where, f"badge {label!r} uses Accent; the mono theme never does")
    elif allowed is None and style != "Default":
        kind = "a kind badge" if label.lower() in KIND_LABELS else "a label"
        probs.err(where, f"badge {label!r} is {kind}: style Default in the mono theme, not {style!r}")
    elif allowed is not None and style not in allowed:
        probs.err(where, f"badge {label!r} keeps its meaning colour: style {' or '.join(sorted(allowed))}, "
                         f"not {style!r}")


def check_action(where: str, action, probs: Problems) -> None:
    if not isinstance(action, dict) or action.get("type") != "Action.OpenUrl":
        probs.err(where, "only Action.OpenUrl is allowed, and only in selectAction or top-level actions")
        return
    check_url(where, action.get("url"), "", probs, "link")
    if "title" in action:
        check_text(where + ".title", str(action["title"]), probs)


def check_element(el, where: str, allowed_here, cfg: dict, probs: Problems, depth: int = 0) -> None:
    if depth > 12:
        probs.err(where, "nested too deeply")
        return
    if not isinstance(el, dict):
        probs.err(where, "element must be an object")
        return
    etype = el.get("type")
    if not isinstance(etype, str):
        probs.err(where, "missing type")
        return
    if BANNED_TYPES_RE.match(etype) or etype not in ALLOWED:
        probs.err(where, f"{etype} is not allowed in Launchpad cards")
        return
    if allowed_here == ELEMENT and etype in NESTED_ONLY:
        probs.err(where, f"{etype} may only appear inside its parent")
    elif isinstance(allowed_here, set) and etype not in allowed_here:
        probs.err(where, f"{etype} cannot appear here (expected {sorted(allowed_here)})")
    for key in el:
        if key.startswith("$"):
            probs.err(where, f"template key {key} left in the card")
    if "selectAction" in el:
        check_action(where + ".selectAction", el["selectAction"], probs)
    enum(where, el, "spacing", ENUMS["spacing"], probs)
    enum(where, el, "horizontalAlignment", ENUMS["halign"], probs)
    enum(where, el, "verticalContentAlignment", ENUMS["valign"], probs)

    if etype == "TextBlock":
        if el.get("wrap") is not True:
            probs.err(where, "TextBlock needs wrap true")
        text = el.get("text")
        if not isinstance(text, str) or not text.strip():
            probs.err(where, "TextBlock needs text")
        else:
            check_text(where, text, probs)
        enum(where, el, "size", ENUMS["size_text"], probs)
        enum(where, el, "weight", ENUMS["weight"], probs)
        mono_colour(where, el, "text blocks", probs)
    elif etype == "TextRun":
        text = el.get("text")
        if not isinstance(text, str) or not text.strip():
            probs.err(where, "TextRun needs text")
        else:
            check_text(where, text, probs)
        mono_colour(where, el, "text runs", probs)
    elif etype == "Image":
        check_url(where, el.get("url"), cfg["picture_prefix"], probs, "picture")
        alt = el.get("altText")
        if not isinstance(alt, str) or not alt.strip():
            probs.err(where, "every picture needs altText")
        else:
            check_text(where + ".altText", alt, probs)
        enum(where, el, "size", ENUMS["image_size"], probs)
    elif etype == "Icon":
        if el.get("name") not in cfg["icons"]:
            probs.err(where, f"icon {el.get('name')!r} is not on the icon list")
        mono_colour(where, el, "icons", probs)
        enum(where, el, "size", ENUMS["icon_size"], probs)
        enum(where, el, "style", ENUMS["icon_style"], probs)
    elif etype == "Badge":
        check_badge_style(where, el, probs)
        text = el.get("text")
        if not isinstance(text, str) or not text.strip():
            probs.err(where, "Badge needs text")
        else:
            check_text(where, text, probs)
        if "tooltip" in el:
            check_text(where + ".tooltip", str(el["tooltip"]), probs)
        if "icon" in el and el["icon"] not in cfg["icons"]:
            probs.err(where, f"badge icon {el['icon']!r} is not on the icon list")
        enum(where, el, "style", ENUMS["badge_style"], probs)
        enum(where, el, "size", ENUMS["badge_size"], probs)
        enum(where, el, "shape", ENUMS["badge_shape"], probs)
    elif etype == "FactSet":
        facts = el.get("facts")
        if not isinstance(facts, list) or not facts:
            probs.err(where, "FactSet needs facts")
        else:
            for i, fact in enumerate(facts):
                if not isinstance(fact, dict) or not fact.get("title") or not fact.get("value"):
                    probs.err(f"{where}.facts[{i}]", "each fact needs title and value")
                    continue
                check_text(f"{where}.facts[{i}].title", str(fact["title"]), probs)
                check_text(f"{where}.facts[{i}].value", str(fact["value"]), probs)
    elif etype == "Container":
        enum(where, el, "style", ENUMS["container_style"], probs)
    elif etype == "ProgressBar":
        value, maximum = el.get("value"), el.get("max", 100)
        if not isinstance(value, (int, float)) or not isinstance(maximum, (int, float)) or maximum <= 0 \
                or value < 0 or value > maximum:
            probs.err(where, "ProgressBar needs 0 <= value <= max")
        if "color" in el:
            probs.err(where, "ProgressBar sets no colour (there is no Default colour for progress bars)")
    elif etype == "AccordionPage":
        if not str(el.get("headerTitle", "")).strip():
            probs.err(where, "AccordionPage needs headerTitle")
        else:
            check_text(where + ".headerTitle", el["headerTitle"], probs)
        if "headerIconName" in el and el["headerIconName"] not in cfg["icons"]:
            probs.err(where, f"header icon {el['headerIconName']!r} is not on the icon list")
        enum(where, el, "headerSize", ENUMS["accordion_header"], probs)
    elif etype == "TabPage":
        if not str(el.get("title", "")).strip():
            probs.err(where, "TabPage needs title")
        else:
            check_text(where + ".title", el["title"], probs)
        if "iconName" in el and el["iconName"] not in cfg["icons"]:
            probs.err(where, f"tab icon {el['iconName']!r} is not on the icon list")
    elif etype == "Table":
        cols = el.get("columns", [])
        if not isinstance(cols, list) or not cols:
            probs.err(where, "Table needs column widths")
        rows = el.get("rows", [])
        for r, row in enumerate(rows if isinstance(rows, list) else []):
            cells = row.get("cells", []) if isinstance(row, dict) else []
            if isinstance(cols, list) and len(cells) != len(cols):
                probs.err(f"{where}.rows[{r}]", f"{len(cells)} cells for {len(cols)} columns")
    elif etype == "Column":
        width = el.get("width", "stretch")
        if not (width in ("auto", "stretch") or isinstance(width, (int, float))
                or (isinstance(width, str) and re.fullmatch(r"\d+px", width))):
            probs.err(where, f"column width {width!r} is not valid")

    for key, rule in CHILD_RULES.get(etype, {}).items():
        children = el.get(key)
        if children is None:
            if etype in ("ColumnSet", "Table", "Accordion", "TabSet", "Carousel", "ImageSet",
                         "Container", "TableCell", "AccordionPage", "TabPage", "CarouselPage"):
                probs.err(where, f"{etype} needs {key}")
            continue
        if not isinstance(children, list) or not children:
            probs.err(where, f"{etype}.{key} must be a non-empty list")
            continue
        for i, child in enumerate(children):
            check_element(child, f"{where}.{key}[{i}]", rule, cfg, probs, depth + 1)


def check_card(card, cfg: dict, probs: Problems) -> None:
    if not isinstance(card, dict):
        probs.err("card", "must be an object")
        return
    if card.get("type") != "AdaptiveCard" or card.get("version") != "1.6":
        probs.err("card", "must be type AdaptiveCard, version 1.6")
    body = card.get("body")
    if not isinstance(body, list) or not body:
        probs.err("card.body", "must be a non-empty list")
        return
    extra = set(card) - {"type", "version", "body", "actions", "$schema"}
    if extra:
        probs.err("card", f"unexpected top-level keys {sorted(extra)}")
    for i, el in enumerate(body):
        check_element(el, f"body[{i}]", ELEMENT, cfg, probs)
    for i, action in enumerate(card.get("actions", []) or []):
        check_action(f"actions[{i}]", action, probs)
    size = len(json.dumps(card, ensure_ascii=False).encode("utf-8"))
    if size > 60000:
        probs.err("card", f"{size} bytes is too large")
    elif size > 24000:
        probs.warn("card", f"{size} bytes; keep cards under about 24 KB")
    pictures = sum(1 for _ in iter_type(card, "Image"))
    if pictures > 6:
        probs.warn("card", f"{pictures} pictures; keep to a few")


def iter_type(node, etype):
    if isinstance(node, dict):
        if node.get("type") == etype:
            yield node
        for value in node.values():
            yield from iter_type(value, etype)
    elif isinstance(node, list):
        for value in node:
            yield from iter_type(value, etype)


def check_questions(questions, probs: Problems) -> None:
    if questions in (None, []):
        return
    if not isinstance(questions, list) or not 1 <= len(questions) <= 4:
        probs.err("questions", "one to four questions per question card")
        return
    for i, q in enumerate(questions):
        w = f"questions[{i}]"
        if not isinstance(q, dict):
            probs.err(w, "must be an object")
            continue
        header = q.get("header", "")
        if not isinstance(header, str) or not 1 <= len(header) <= 12:
            probs.err(w, "header must be 1 to 12 characters")
        text = q.get("question", "")
        if not isinstance(text, str) or not text.strip().endswith("?") and "?" not in text:
            probs.err(w, "question must ask something (with a question mark)")
        check_text(w + ".question", str(text), probs)
        check_text(w + ".header", str(header), probs)
        if "multiSelect" in q and not isinstance(q["multiSelect"], bool):
            probs.err(w, "multiSelect must be true or false")
        options = q.get("options")
        if not isinstance(options, list):
            probs.err(w, "options must be a list ([] for free text)")
            continue
        if options and not 2 <= len(options) <= 5:
            probs.err(w, f"{len(options)} options; use two to five")
        seen = set()
        for j, opt in enumerate(options):
            ow = f"{w}.options[{j}]"
            label = opt.get("label", "") if isinstance(opt, dict) else ""
            desc = opt.get("description", "") if isinstance(opt, dict) else ""
            if not isinstance(label, str) or not label.strip():
                probs.err(ow, "label needed")
                continue
            words = len(label.split())
            if words > 7 or len(label) > 48:
                probs.err(ow, f"label too long ({words} words)")
            elif words > 5:
                probs.warn(ow, f"label has {words} words; aim for five or fewer")
            if label.strip().lower().rstrip(".") in CATCH_ALL:
                probs.err(ow, "no catch-all option; free text is always possible")
            if label.lower() in seen:
                probs.err(ow, "duplicate label")
            seen.add(label.lower())
            if not isinstance(desc, str) or not desc.strip():
                probs.err(ow, "each option needs a one-line description")
            elif "\n" in desc or len(desc) > 100:
                probs.err(ow, "description must be one short line")
            check_text(ow + ".label", label, probs)
            check_text(ow + ".description", str(desc), probs)


# ------------------------------------------------------------------- main
def load_templates() -> dict:
    with TEMPLATE_FILE.open(encoding="utf-8") as fh:
        return json.load(fh)


def config(templates: dict) -> dict:
    return {"icons": set(templates.get("icons", [])),
            "picture_prefix": templates.get("picture_prefix", "https://")}


def read_json(path: str | None) -> dict:
    if path in (None, "-"):
        raw = sys.stdin.read()
        return json.loads(raw) if raw.strip() else {}
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def emit(obj: dict, code: int) -> int:
    print(json.dumps(obj, ensure_ascii=False, indent=1))
    return code


def build(name: str, data: dict, templates: dict) -> tuple[dict, Problems]:
    probs = Problems()
    tdefs = templates.get("templates", {})
    if name not in tdefs:
        probs.err("template", f"unknown template {name!r}; try: {', '.join(sorted(tdefs))}")
        return {}, probs
    tdef = tdefs[name]
    for field in tdef.get("required", []):
        if resolve(data, field) is MISSING:
            probs.err("data", f"{field} is required for {name}")
    if probs.errors:
        return {}, probs
    ctx = dict(data)
    ctx["pictures"] = templates.get("pictures", {})
    ctx["fixed"] = templates.get("fixed", {})
    cfg = config(templates)
    result = {"template": name, "card": None, "questions": [], "warnings": []}
    if tdef.get("kind") == "markdown":
        lines = expand(tdef.get("lines", []), ctx, "markdown", probs)
        text = "\n".join(str(line) for line in lines).rstrip() + "\n"
        for i, line in enumerate(text.splitlines()):
            check_text(f"markdown line {i + 1}", line, probs)
        must_end = tdef.get("must_end_with")
        if must_end and text.strip().splitlines()[-1].strip() != must_end:
            probs.err("markdown", f"must end with: {must_end}")
        result["markdown"] = text
    if "card" in tdef:
        card = expand(tdef["card"], ctx, "card", probs)
        check_card(card, cfg, probs)
        result["card"] = card
    if "questions" in tdef:
        questions = expand(tdef["questions"], ctx, "questions", probs)
        questions = [q for q in questions if q]
        check_questions(questions, probs)
        result["questions"] = questions
    result["warnings"] = probs.warnings
    return result, probs


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Build and check Launchpad cards.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="list templates and the data each needs")
    b = sub.add_parser("build", help="fill a template and check the result")
    b.add_argument("template")
    b.add_argument("--data", help="JSON data file (default: stdin)")
    b.add_argument("--merge", action="append", default=[],
                   help="more JSON files merged on top, in order (for script outputs)")
    b.add_argument("--theirs", action="append", default=[],
                   help="JSON file of the person's own words, shown as they wrote them")
    c = sub.add_parser("check", help="check a card (and questions) built elsewhere")
    c.add_argument("card")
    c.add_argument("--questions")
    c.add_argument("--theirs", action="append", default=[],
                   help="JSON file of the person's own words, shown as they wrote them")
    args = parser.parse_args(argv)

    try:
        templates = load_templates()
    except (OSError, json.JSONDecodeError) as exc:
        return emit({"errors": [f"cannot read templates: {exc}"]}, 1)

    if args.cmd == "list":
        listing = {k: {"required": v.get("required", []), "about": v.get("about", "")}
                   for k, v in sorted(templates.get("templates", {}).items())}
        return emit({"templates": listing}, 0)

    if args.cmd == "check":
        probs = Problems()
        try:
            set_theirs(saved_theirs() + [read_json(f) for f in args.theirs])
            card = read_json(args.card)
            check_card(card, config(templates), probs)
            if args.questions:
                check_questions(read_json(args.questions), probs)
        except (OSError, json.JSONDecodeError) as exc:
            probs.err("input", str(exc))
        if probs.errors:
            return emit({"errors": probs.errors, "warnings": probs.warnings}, 1)
        return emit({"valid": True, "warnings": probs.warnings}, 0)

    try:
        data = read_json(args.data)
        for extra in args.merge:
            more = read_json(extra)
            if not isinstance(more, dict):
                raise ValueError(f"{extra} must hold a JSON object")
            data.update(more)
        set_theirs(saved_theirs() + [read_json(f) for f in args.theirs] + theirs_in(data))
    except (OSError, ValueError) as exc:
        return emit({"errors": [f"cannot read data: {exc}"]}, 1)
    result, probs = build(args.template, data, templates)
    if probs.errors:
        return emit({"errors": probs.errors, "warnings": probs.warnings}, 1)
    return emit(result, 0)


if __name__ == "__main__":
    sys.exit(main())
