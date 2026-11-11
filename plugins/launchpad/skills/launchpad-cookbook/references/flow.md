# launchpad-cookbook: flow details

Read this when you need a data shape or a detail. SKILL.md has the steps.

## Working files (conversation workspace)
| File | Written by | Holds |
|---|---|---|
| working/launchpad/choices.json | launchpad-start or you | what the person chose, the sample flag, the queue |
| working/launchpad/signals.json | launchpad-start | the person's recurring-work signals (titles only) |
| working/launchpad/ranked.json, offers.json | rank.py | offers and suggestions |
| working/launchpad/recipe.json | rank.py --recipe | data for "Would you like this?" |
| working/launchpad/style.json | you | what good looks like, learned from one example |
| working/launchpad/skills/<name>/ | make_skill.py | the built skill folders, until kept |
| working/launchpad/test/ | you and the scripts | draft, approved version, table, result |

choices.json may hold `"queue": ["committee-paper"]` for picks still to show, and
`"shown": ["variance-commentary"]` for "Keep looking".

## style.json (what good looks like)
```json
{
  "document_title": "Monthly management pack",
  "audience": "the Chief Financial Officer and the executive committee",
  "cadence": "monthly",
  "sections": ["Headline", "Revenue", "Costs", "Lines not commented", "Sign-off"],
  "tone": "One entry per material line: the line, the figure against budget, the driver, then the source.",
  "threshold": "Comment on lines at or above US$3m against budget.",
  "template": "A headline paragraph, then Revenue and Costs, then the sign-off.",
  "sign_off": "Prepared by FP&A. Reviewed by the Financial Controller.",
  "owners": ["Distribution finance partner"],
  "inputs": ["Locked-period ledger extract", "Approved budget", "Explanations from budget owners"],
  "example_lines": ["One short line copied from the example, if the person is happy to keep it"],
  "learned_from": "October 2026 pack, version 3"
}
```
Optional: `skill_name` (to override the name), `example_prompt`, `standard` (committee papers),
`columns` (app recipe), `threshold_number`. Record only what the example shows; anything else is
"Not stated". The person's name, colleagues' names and private details never go in.

## Period file (variance recipe)
```json
{"entity": "", "period": "October 2026", "unit": "US$m", "threshold": 3.0,
 "control_totals": {"income_actual": 0, "income_budget": 0, "cost_actual": 0, "cost_budget": 0},
 "lines": [{"line": "Base fees", "type": "income", "actual": 412.6, "budget": 405.0,
            "owner": "Distribution finance partner",
            "explanation": {"text": "", "status": "Supported", "evidence": "", "gap": "", "asked_on": ""}}]}
```
`scripts/variance_table.py` subcommands: `table` (variance, materiality and rank), `tieout`
(against control totals), `questions` (one per gap, grouped by owner), `figures` (draft against
table). Favourable variances are positive.

## Test files
draft.json and approved.json:
```json
{"period": "September 2026",
 "lines": [{"line": "Base fees", "figure": 6.1, "text": "Base fees: 6.1 above budget. ...", "status": "Supported"}],
 "questions": [{"owner": "Investment finance partner", "question": "..."}]}
```
table.json is the script output for the same period. For recipes that are not line-based, use one
"line" per section (committee paper) or per question and movement (MBR brief), with `figure` only
where there is a number.

| Recipe | What "the period with a known answer" is | What to compare |
|---|---|---|
| variance-commentary | last month's inputs and the commentary that was sent | material lines, statuses, figures |
| budget-round-app | last week's tracker and the status email that was sent | the four figures and the overdue owners |
| mbr-brief | last month's packs and notes from that review | movements, questions, open actions |
| committee-paper | the evidence for last cycle's paper and the paper that went | front sheet parts, figures and sources |

## Sample route
references/sample-data.json is invented (Contoso Asset Management, US$m) and labelled so.
- Step 2: `rank.py --recipe variance-commentary --sample`, `"sample": true` in the card data.
- Step 3: `house_style` in the sample is the example; the card's file option is
  "Use the September commentary" (description: "Invented sample: the commentary that was sent").
- Step 4: `make_skill.py --recipe variance-commentary --spec <house_style as a file>`.
- Step 5: September 2026 is the test period; `approved_commentary` is what was sent; run
  `variance_table.py table --period "September 2026"` for the table.
- October 2026 matches the example picture: Base fees +7.6 Supported, Performance fees -6.8
  Partly supported, Compensation -5.4 Awaiting owner, General and administration +3.1 Not
  supported; two questions drafted for owners, not sent.
Always say the sample is invented. Never mix sample figures with the person's own.

## App recipe with the person's own tracker
1. Ask to read that one tracker (a question card naming it). Picking "Read it" is the OK.
2. Write the rows as `{"name", "unit", "columns": [...], "rows": [{"cost_centre", "owner",
   "status", "submitted_date", "value", "target", "due"}]}` and run
   `scripts/tracker_summary.py --tracker <file> --today <date> --out working/launchpad/tracker.json`.
3. Build `app_mockup` with: `tracker_name`; `columns` (the tracker's real column names, up to
   five); `rows` (the first rows as lists of cell text, up to five); `noticed` (two or three lines
   from the look, each `{"icon", "text"}`); `tiles` and `progress` from the script; `changes`
   (three lines on what changes for them); `build_facts` (Built from, Who can use it, Also set up,
   Your spreadsheet: left exactly as it is).
4. On "Build it", fill references/app-brief.md and hand it to Cowork's App skill.

## Keep: saving with Cowork's own skill saving
- One `CopyArtifact` call per skill folder: `surface` "user", `source`
  "working/launchpad/skills/<name>", `destination` "skills/<name>", `recursive` true. Cowork shows
  its approval card. Do not pass `overwrite` unless the person agreed to replace a skill of the
  same name.
- Compare `copied` with the file count make_skill.py reported for that skill. If it is lower, the
  save is incomplete: say so plainly, and do not call the skill ready.
- If the person declines the approval, nothing was saved; say so.
- Kept skills appear in the person's Cowork folder under skills and are ready from their next
  conversation. They can change or share them from Customize, Skills.

## Generic blueprint
For the person's own recurring document with no matching recipe: `make_skill.py --recipe generic`.
It builds one main skill (named after the document plus "draft") with `scripts/figures_check.py`
and three test cases.
