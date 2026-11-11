#!/usr/bin/env python3
"""Launchpad for Cowork: turn title-only lists into recurring-work signals.

Input is the discovery file the model writes after the person says
"Have a look": calendar titles and attendee counts, subjects of sent mail,
and names of files. No bodies, attachments or contents, ever.

Usage
  python3 signals.py --input discovery.json [--out signals.json]
  python3 signals.py --stated stated.json [--out signals.json]   (Ask-me route)

Every number shown in the "Is this your work?" card comes from this output.
Private, confidential, personal, HR and medical items are dropped before
anything is counted or shown; only the number left out is reported.
Standard library only.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta

MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august",
          "september", "october", "november", "december"]
MONTH_TOKENS = set(MONTHS) | {m[:3] for m in MONTHS} | {"sept"}
DAYS = {"monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
        "mon", "tue", "tues", "wed", "thu", "thur", "thurs", "fri", "sat", "sun"}
STOP = {"the", "a", "an", "and", "of", "for", "to", "on", "in", "at", "by", "with", "from",
        "re", "fw", "fwd", "aw", "sv", "tr", "our", "your", "my", "is", "are", "this", "that",
        "please", "pls", "due", "today", "tomorrow", "week", "next", "last", "all", "any",
        "team", "call", "meeting", "sync", "it", "be", "we", "you", "i", "will", "can", "new"}
VERSION_TOKEN = re.compile(r"^(v\d+(\.\d+)*|version|ver|rev\d*|r\d+|final|finalv?\d*|draft\d*|updated|"
                           r"latest|clean|tracked|copy|\d+|fy\d{2,4}|q[1-4]|h[12]|\d{4}|wk\d+)$")
TRAILING_VERSION = re.compile(r"[\s_\-]*(\(?v\d+(\.\d+)*\)?|version\s*\d+|final|draft\s*\d*|rev\s*\d+|"
                              r"updated|latest|clean|tracked|copy|\(\d+\)|wk\s?\d+|week\s?\d+)\s*$", re.I)
SENSITIVE_WORDS = re.compile(
    r"\b(private|personal|confidential|strictly confidential|hr|human resources|medical|doctor|dentist|"
    r"hospital|clinic|gp appointment|sick|sickness|illness|maternity|paternity|parental leave|"
    r"salary|salaries|pay review|bonus|bonuses|remuneration|payroll|appraisal|performance review|"
    r"disciplinary|grievance|redundancy|redundancies|resignation|termination|offer letter|"
    r"candidate|interview|recruitment|background check|1:1|1-1|one to one|one-on-one|therapy|"
    r"counselling|counseling|pregnancy|occupational health|fit note|wellbeing check|legal privilege)\b",
    re.I)
SENSITIVE_LABEL = re.compile(r"confidential|private|restricted|secret|personal|highly", re.I)
NOISE_TITLE = re.compile(
    r"^(canceled|cancelled|declined|accepted|tentative|updated invitation|automatic reply|"
    r"out of office|ooo)\b|\b(lunch|focus time|focus|hold|block|commute|travel|gym|school run|"
    r"out of office|ooo|busy|do not book|holiday|annual leave|vacation)\b", re.I)
STATUS_WORDS = re.compile(
    r"\b(status|update|updates|chaser|chasing|chase|reminder|remind|overdue|outstanding|follow up|"
    r"follow-up|followup|nudge|deadline|action required|please send|please submit|submission|"
    r"submissions|progress|still waiting|where are we)\b", re.I)
STATUS_TOKENS = {"status", "update", "updates", "chaser", "chasing", "chase", "reminder", "remind",
                 "overdue", "outstanding", "follow", "up", "followup", "nudge", "deadline", "action",
                 "required", "send", "submit", "progress", "still", "waiting", "where"}
PACK_WORDS = re.compile(
    r"\b(review|committee|board|mbr|qbr|forecast|close|steering|exco|results|readout|governance|"
    r"council|pack|business review|operating|monthly|quarterly|budget|investment|audit|risk|"
    r"leadership|executive)\b", re.I)
SPREADSHEET = (".xlsx", ".xlsm", ".xls", ".csv")
DOCUMENT = (".docx", ".doc", ".pptx", ".ppt", ".pdf", ".xlsx", ".xlsm")


# ----------------------------------------------------------------- helpers
def parse_when(value) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    text = value.strip().replace("Z", "")
    text = re.sub(r"(\.\d{6})\d+", r"\1", text)
    text = re.sub(r"[+-]\d{2}:\d{2}$", "", text)
    for candidate in (text, text[:19], text[:10]):
        try:
            return datetime.fromisoformat(candidate)
        except ValueError:
            continue
    return None


def day_text(d: date | datetime | None, with_year: bool = False) -> str:
    if d is None:
        return "date not shown"
    names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    text = f"{names[d.weekday()]} {d.day} {months[d.month - 1]}"
    return f"{text} {d.year}" if with_year else text


def words(text: str) -> list[str]:
    text = text.lower().replace("&", " & ")
    text = re.sub(r"\.[a-z0-9]{2,4}$", "", text)
    text = re.sub(r"[_\-\u2013\u2014.,;:!?()\[\]{}/\\+\"'|#*]", " ", text)
    return [w for w in text.split() if w]


def norm(text: str) -> str:
    return " ".join(words(text))


def stem(token: str) -> str:
    return token[:-1] if len(token) > 4 and token.endswith("s") and not token.endswith("ss") else token


def strip_prefixes(subject: str) -> str:
    prev = None
    s = subject.strip()
    while prev != s:
        prev = s
        s = re.sub(r"^\s*(re|fw|fwd|aw|sv|tr|wg)\s*:\s*", "", s, flags=re.I)
    return s


def display_name(filename: str) -> str:
    base = re.sub(r"\.[A-Za-z0-9]{2,4}$", "", filename.strip())
    prev = None
    while prev != base:
        prev = base
        base = TRAILING_VERSION.sub("", base)
    base = re.sub(r"[_]+", " ", base)
    base = re.sub(r"\s{2,}", " ", base).strip(" -")
    return base[:1].upper() + base[1:] if base else filename


def series_title(work: str) -> str:
    """'October management pack' -> 'Management pack': the recurring deliverable, without the period."""
    toks = [t for t in work.split() if t.lower().strip(",.") not in MONTH_TOKENS
            and not re.fullmatch(r"(19|20)\d\d|fy\d{2,4}|q[1-4]|wk\d+", t.lower())]
    text = " ".join(toks).strip(" -")
    return (text[:1].upper() + text[1:]) if text else work


def series_key(filename: str) -> str:
    toks = [t for t in words(filename) if not VERSION_TOKEN.match(t) and t not in MONTH_TOKENS]
    return " ".join(stem(t) for t in toks)


def clean_meeting_title(title: str) -> str:
    t = re.sub(r"^\s*(canceled|cancelled|updated|fw|fwd|re)\s*:\s*", "", title.strip(), flags=re.I)
    t = re.sub(r"\b\d{1,2}(st|nd|rd|th)?\s+(of\s+)?(" + "|".join(sorted(MONTH_TOKENS)) + r")\b", "", t, flags=re.I)
    t = re.sub(r"\b(" + "|".join(sorted(MONTH_TOKENS)) + r")\s+\d{2,4}\b", "", t, flags=re.I)
    t = re.sub(r"\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}/\d{1,2}(/\d{2,4})?\b", "", t)
    t = re.sub(r"\s*[-\u2013\u2014|:]\s*$", "", t)
    return re.sub(r"\s{2,}", " ", t).strip(" -\u2013\u2014|:") or title.strip()


def meeting_key(title: str) -> str:
    toks = [t for t in words(clean_meeting_title(title))
            if t not in MONTH_TOKENS and not re.fullmatch(r"\d+(st|nd|rd|th)?", t)]
    return " ".join(toks)


def first(item: dict, *keys, default=None):
    for key in keys:
        if key in item and item[key] not in (None, ""):
            return item[key]
    return default


def is_sensitive(title: str, labels: list[str]) -> bool:
    if any(SENSITIVE_LABEL.search(str(lbl)) for lbl in labels if lbl):
        return True
    return bool(SENSITIVE_WORDS.search(title or ""))


def cadence_from(title: str, starts: list[datetime], recurring: bool = True) -> str:
    t = title.lower()
    if re.search(r"\b(monthly|mbr|month|month-end|month end)\b", t):
        return "Monthly"
    if re.search(r"\b(quarterly|qbr|quarter)\b", t):
        return "Quarterly"
    if re.search(r"\b(weekly|week)\b", t):
        return "Weekly"
    if re.search(r"\b(daily|stand-?up)\b", t):
        return "Daily"
    if len(starts) >= 2:
        gaps = sorted((b - a).days for a, b in zip(sorted(starts), sorted(starts)[1:]))
        gap = gaps[len(gaps) // 2]
        if 6 <= gap <= 8:
            return "Weekly"
        if 13 <= gap <= 15:
            return "Fortnightly"
        if 26 <= gap <= 35:
            return "Monthly"
        if gap <= 1:
            return "Daily"
    return "Recurring" if recurring else ""


def how_often_from_names(names: list[str]) -> str:
    joined = " ".join(names).lower()
    if re.search(r"\bweekly|\bweek\b|\bwk\d", joined):
        return "Weekly"
    if re.search(r"\bquarter|\bq[1-4]\b|\bqbr\b", joined):
        return "Quarterly"
    if re.search(r"\bmonthly|month-end|month end|mbr\b", joined) or \
            any(re.search(r"\b" + m + r"\b", joined) for m in MONTHS):
        return "Monthly"
    return "Not found yet"


def plural(n: int, one: str, many: str | None = None) -> str:
    return f"{n} {one if n == 1 else (many or one + 's')}"


# -------------------------------------------------------------- the work
def build_signals(disc: dict) -> dict:
    as_of = parse_when(disc.get("as_of")) or datetime.combine(date.today(), datetime.min.time())
    sample = bool(disc.get("sample"))
    skipped_sensitive = 0
    skipped_noise = 0
    titles = {"file_names": [], "meeting_titles": [], "email_subjects": []}

    # Calendar -------------------------------------------------------
    meetings = []
    for raw in disc.get("calendar", []) or []:
        title = str(first(raw, "title", "subject", default="")).strip()
        if not title:
            continue
        sensitivity = str(first(raw, "sensitivity", default="normal")).lower()
        labels = list(first(raw, "categories", default=[]) or [])
        if sensitivity in {"private", "personal", "confidential"} or is_sensitive(title, labels):
            skipped_sensitive += 1
            continue
        if first(raw, "cancelled", "isCancelled", default=False) or first(raw, "all_day", "isAllDay", default=False) \
                or str(first(raw, "show_as", "showAs", default="busy")).lower() in {"free", "oof"} \
                or NOISE_TITLE.search(title):
            skipped_noise += 1
            continue
        meetings.append({
            "title": title,
            "start": parse_when(first(raw, "start", "startDateTime")),
            "attendees": int(first(raw, "attendees", "attendeeCount", default=0) or 0),
            "recurring": bool(first(raw, "recurring", "isRecurring", default=False)),
            "series": first(raw, "series", "seriesMasterId"),
        })
        titles["meeting_titles"].append(norm(title))

    # Sent mail ------------------------------------------------------
    subjects = []
    for raw in disc.get("sent_mail", []) or []:
        subject = str(first(raw, "subject", default="")).strip()
        if not subject:
            continue
        labels = list(first(raw, "categories", default=[]) or [])
        if is_sensitive(subject, labels) or str(first(raw, "sensitivity", default="")).lower() in {
                "private", "personal", "confidential"}:
            skipped_sensitive += 1
            continue
        if NOISE_TITLE.search(subject):
            skipped_noise += 1
            continue
        subjects.append({"subject": subject, "sent": parse_when(first(raw, "sent", "sentDateTime"))})
        titles["email_subjects"].append(norm(strip_prefixes(subject)))

    # Files ----------------------------------------------------------
    files = []
    for raw in disc.get("files", []) or []:
        name = str(first(raw, "name", default="")).strip()
        if not name:
            continue
        label = first(raw, "label", "sensitivityLabel", default="") or ""
        if is_sensitive(name, [label]):
            skipped_sensitive += 1
            continue
        files.append({
            "name": name,
            "modified": parse_when(first(raw, "modified", "lastModifiedDateTime")),
            "editors": int(first(raw, "editors", "editorCount", default=0) or 0),
            "shared": bool(first(raw, "shared", default=False)),
            "location": first(raw, "location", default=""),
        })
        titles["file_names"].append(norm(name))

    signals = []

    # Documents made in several versions --------------------------------
    by_series = defaultdict(list)
    for f in files:
        if f["name"].lower().endswith(DOCUMENT) and series_key(f["name"]):
            by_series[series_key(f["name"])].append(f)
    for key, group in by_series.items():
        if len(group) < 2:
            continue
        group.sort(key=lambda f: f["modified"] or datetime.min, reverse=True)
        latest = group[0]
        mailed = sum(1 for s in subjects if key and key in " ".join(stem(t) for t in words(s["subject"])))
        evidence = f"{plural(len(group), 'version')} in the last 30 days, latest {day_text(latest['modified'])}"
        if mailed:
            evidence += f", {plural(mailed, 'email')} you sent about it"
        signals.append({
            "type": "versioned_document", "group": "documents", "icon": "DocumentText", "kind": "skill",
            "work": display_name(latest["name"]), "evidence": evidence, "count": len(group),
            "latest": latest["modified"].date().isoformat() if latest["modified"] else None,
            "text": norm(" ".join(f["name"] for f in group)),
            "items": [f["name"] for f in group[:5]],
            "how_often": how_often_from_names([f["name"] for f in group]),
            "location": latest["location"] or "Not found yet",
        })

    # Status emails and chasers -----------------------------------------
    status_groups = defaultdict(list)
    for s in subjects:
        subject = strip_prefixes(s["subject"])
        if not STATUS_WORDS.search(subject):
            continue
        sig = [stem(t) for t in words(subject)
               if t not in STOP and t not in MONTH_TOKENS and t not in DAYS
               and stem(t) not in STATUS_TOKENS and t not in STATUS_TOKENS and not t.isdigit()]
        key = sig[0] if sig else "general"
        status_groups[key].append((subject, sig))
    status_signals = {}
    for key, group in status_groups.items():
        if len(group) < 3 or key == "general":
            continue
        pairs = Counter(" ".join(sig[:2]) for _, sig in group if sig)
        topic = pairs.most_common(1)[0][0] if pairs else key
        sig = {
            "type": "status_emails", "group": "running", "icon": "Mail", "kind": "app",
            "work": topic[:1].upper() + topic[1:] + " status",
            "evidence": f"{plural(len(group), 'status email and chaser', 'status emails and chasers')} you sent in the last two weeks",
            "count": len(group), "latest": None, "key": key,
            "text": norm(" ".join(subject for subject, _ in group)),
            "items": [subject for subject, _ in group[:5]],
        }
        status_signals[key] = sig

    # Shared trackers ----------------------------------------------------
    linked = set()
    for f in files:
        if not f["name"].lower().endswith(SPREADSHEET):
            continue
        if f["editors"] < 3 and not f["shared"]:
            continue
        toks = {stem(t) for t in words(f["name"])}
        evidence = f"Edited by {f['editors']} people" if f["editors"] >= 3 else "Shared with your team"
        types = ["shared_tracker"]
        for key, ssig in status_signals.items():
            if key in toks:
                evidence += f"; {ssig['count']} status emails and chasers you sent about it"
                linked.add(key)
                types.append("status_emails")
        signals.append({
            "type": "shared_tracker", "types": types, "group": "running", "icon": "Table", "kind": "app",
            "work": display_name(f["name"]), "evidence": evidence, "count": f["editors"],
            "latest": f["modified"].date().isoformat() if f["modified"] else None,
            "text": norm(f["name"] + " " + " ".join(
                s["text"] for k, s in status_signals.items() if k in toks)),
            "items": [f["name"]], "location": f["location"] or "Not found yet",
        })
    for key, ssig in status_signals.items():
        if key not in linked:
            signals.append(ssig)

    # Meetings that need a pack ------------------------------------------
    by_meeting = defaultdict(list)
    for m in meetings:
        key = meeting_key(m["title"])
        if key:
            by_meeting[key].append(m)
    for key, group in by_meeting.items():
        attendees = max(m["attendees"] for m in group)
        recurring = any(m["recurring"] for m in group) or len(group) >= 2
        title = clean_meeting_title(group[0]["title"])
        if attendees < 3:
            continue
        if not (PACK_WORDS.search(title) or attendees >= 6):
            continue
        if not (recurring or PACK_WORDS.search(title)):
            continue
        starts = [m["start"] for m in group if m["start"]]
        future = sorted(s for s in starts if s >= as_of)
        past = sorted(s for s in starts if s < as_of)
        when = f"next on {day_text(future[0])}" if future else (f"last on {day_text(past[-1])}" if past else "")
        cadence = cadence_from(title, starts, any(m["recurring"] for m in group))
        evidence = ", ".join(x for x in [cadence, f"{attendees} people", when] if x)
        signals.append({
            "type": "recurring_meeting", "group": "meetings", "icon": "CalendarLtr", "kind": "routine",
            "work": title, "evidence": evidence, "count": len(group),
            "latest": (future[0] if future else (past[-1] if past else as_of)).date().isoformat(),
            "text": norm(title), "items": [title], "cadence": cadence, "attendees": attendees,
            "weekday": day_text(starts[0]).split()[0] if starts else "",
        })

    return finish(signals, titles, as_of, sample, {
        "meetings": len(meetings), "subjects": len(subjects), "files": len(files)},
        skipped_sensitive, skipped_noise)


def finish(signals, titles, as_of, sample, counts, skipped_sensitive, skipped_noise, stated=False):
    order = {"documents": 0, "running": 1, "meetings": 2}
    signals.sort(key=lambda s: (order[s["group"]], -s.get("attendees", s["count"]), -s["count"],
                                s["work"].lower()))
    groups = {"documents": [], "running": [], "meetings": []}
    for i, s in enumerate(signals, 1):
        s["id"] = f"s{i}"
        kind = s["kind"]
        badge = {"skill": ("Skill", "Default"), "app": ("App", "Default"), "routine": ("Routine", "Default")}[kind]
        groups[s["group"]].append({"signal": s["id"], "work": s["work"], "evidence": s["evidence"],
                                   "icon": s["icon"], "badge": badge[0], "badge_style": badge[1]})
    as_of_text = day_text(as_of, with_year=True)
    if stated:
        source_line = "From what you told me. Nothing of yours was read."
    else:
        source_line = (f"From {plural(counts['meetings'], 'meeting title')}, "
                       f"{plural(counts['subjects'], 'subject')} of mail you sent and "
                       f"{plural(counts['files'], 'file name')}, as of {as_of_text}.")
    if sample:
        source_line = "Invented sample data. " + source_line
    deliverables = []
    for s in signals:
        if s["type"] == "versioned_document" and len(deliverables) < 5:
            deliverables.append({"what": series_title(s["work"]), "how_often": s.get("how_often", "Not found yet"),
                                 "for_whom": "Not found yet", "inputs": s.get("location", "Not found yet")})
        elif s["type"] == "shared_tracker" and len(deliverables) < 5:
            deliverables.append({"what": s["work"], "how_often": "Not found yet",
                                 "for_whom": "Not found yet", "inputs": s.get("location", "Not found yet")})
    rhythms = [f"{s['work']}: {s['evidence']}" for s in signals if s["type"] == "recurring_meeting"][:5]
    out = {
        "as_of": as_of.date().isoformat(),
        "as_of_text": as_of_text,
        "sample": sample,
        "stated": stated,
        "counts": counts,
        "skipped": {"sensitive": skipped_sensitive, "noise": skipped_noise},
        "source_line": source_line,
        "signals": signals,
        "groups": groups,
        "titles": titles,
        "profile_draft": {"as_of_text": as_of_text, "deliverables": deliverables, "rhythms": rhythms},
    }
    if skipped_sensitive:
        out["skipped_line"] = (f"I left out {plural(skipped_sensitive, 'item')} that looked private, "
                               "confidential or personal.")
    theirs = set()
    for s in signals:
        theirs.add(s["work"])
        theirs.add(series_title(s["work"]))
        theirs.update(str(x) for x in s.get("items", []) if x)
    theirs.update(d["what"] for d in deliverables)
    out["theirs"] = sorted(t for t in theirs if t)
    return out


def build_from_stated(stated: dict) -> dict:
    as_of = parse_when(stated.get("as_of")) or datetime.combine(date.today(), datetime.min.time())
    signals = []
    document = str(stated.get("document", "")).strip()
    meeting = str(stated.get("meeting", "")).strip()
    role = str(stated.get("role", "")).strip()
    if document and not is_sensitive(document, []):
        signals.append({"type": "stated_document", "group": "documents", "icon": "DocumentText", "kind": "skill",
                        "work": document[:1].upper() + document[1:], "evidence": "You told me you make this",
                        "count": 1, "latest": None, "text": norm(document), "items": [document],
                        "how_often": how_often_from_names([document])})
    if meeting and not is_sensitive(meeting, []):
        signals.append({"type": "stated_meeting", "group": "meetings", "icon": "CalendarLtr", "kind": "routine",
                        "work": meeting[:1].upper() + meeting[1:], "evidence": "You told me you prepare for this",
                        "count": 1, "latest": None, "text": norm(meeting), "items": [meeting]})
    titles = {"file_names": [], "meeting_titles": [norm(meeting)] if meeting else [],
              "email_subjects": [], "stated": [norm(x) for x in (role, document, meeting) if x]}
    out = finish(signals, titles, as_of, bool(stated.get("sample")), {"meetings": 0, "subjects": 0, "files": 0},
                 0, 0, stated=True)
    out["profile_draft"]["role"] = role or "Not found yet"
    out["profile_draft"]["deliverables"] = [
        {"what": s["work"], "how_often": s.get("how_often", "Not found yet"), "for_whom": "Not found yet",
         "inputs": "Not found yet"} for s in signals if s["type"] == "stated_document"]
    out["profile_draft"]["rhythms"] = [s["work"] for s in signals if s["type"] == "stated_meeting"]
    out["theirs"] = sorted(set(out.get("theirs", [])) | {x for x in (role, document, meeting) if x})
    return out


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
    parser = argparse.ArgumentParser(description="Turn title-only lists into recurring-work signals.")
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--input", help="discovery JSON (calendar, sent_mail, files)")
    src.add_argument("--stated", help="Ask-me answers JSON (role, document, meeting)")
    parser.add_argument("--out", help="also write the result to this file")
    args = parser.parse_args(argv)
    try:
        with open(args.input or args.stated, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"errors": [f"cannot read input: {exc}"]}))
        return 1
    result = build_signals(data) if args.input else build_from_stated(data)
    text = json.dumps(result, ensure_ascii=False, indent=1)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
        save_theirs(args.out, result.get("theirs", []))
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
