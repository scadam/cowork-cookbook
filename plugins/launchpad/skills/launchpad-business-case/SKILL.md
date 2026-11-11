---
name: launchpad-business-case
description: >-
  Works out whether a skill, app or routine is worth it, outcomes first: the measure that moves,
  any cash that can really stop (contractors, overtime, outside advisers) and Cowork's running
  cost, all from a script with every assumption stated. It never turns time into money, and can
  draft a brief for a manager as a Word document. Use when someone says "Is it worth it?", "What
  is this worth?", "Build the business case", "Size this for my manager" or "What would this cost
  to run?". Do not use for building the skill itself (use launchpad-cookbook instead), for
  schedules and routines (use launchpad-routines instead), for how-to questions about Cowork
  (use launchpad-how-do-i instead) or for any other Word document (use docx instead).
metadata:
  category: analysis
  icon: DataBarVertical
  version: "2.2.0"
---

# Launchpad: is it worth it?

Shows what changes if the work runs well: the measure that moves first, then money only where
real spend can stop, against what Cowork costs to run. A script does every sum and lists every
assumption.

## When to use
- "Is it worth it?", "What is this worth?", "Build the business case", "Size this for my manager",
  "What would this cost to run?"
- After launchpad-cookbook keeps a skill and the person picks "Is it worth it?".

## When NOT to Use
- Building or testing the skill: use launchpad-cookbook instead.
- Putting it on a schedule: use launchpad-routines instead.
- "How do I...?" about Cowork: use launchpad-how-do-i instead.
- A full investment appraisal or headcount plan: this skill does not do those.
- Any other Word document: use docx instead (Cowork's Word skill).

## Rules
1. **Outcomes, not time.** Lead with the measure that moves. Never turn time into money, never
   claim hours or minutes given back, never give productivity or speed percentages.
2. **Money only where real spend can stop**: contractor or temporary support, overtime, outside
   advisers. Only spend the person selected and gave an amount for; otherwise "not sized".
3. **Every sum from scripts/case.py.** Never add, multiply or round anything yourself.
4. **State every assumption**: the price per credit is a stated setting (default US$0.01), the
   credits a run are a planning range, not a quote.
5. **Nothing kept or sent without OK.** The brief is drafted only after "Draft the full brief" and
   is never sent.
6. Plain business English, British spelling, no tool names, file paths or error codes in what the
   person sees, no hype, no exclamation marks. Never mention other organisations, customers or
   counts of them, or where the planning ranges came from.
7. One card per reply, built by scripts/cards.py and shown unchanged, with the choices in one
   question card in the same reply.

## Run this skill's scripts
```bash
ls -d /mnt/shared/plugins/*/*/skills/launchpad-business-case 2>/dev/null | sort -t/ -k6,6V | tail -1
# if nothing prints:
find / -path '*/skills/launchpad-business-case/scripts/case.py' -not -path '/proc/*' 2>/dev/null | head -1
mkdir -p working/launchpad
```
To show a card: write the data to a file, run
`python3 <skill>/scripts/cards.py build <template> --data <file> [--merge <script output>]`, fix
any errors in the data, then call `render_ui` with the returned card exactly and, in the same
reply, `AskUserQuestion` with the returned `questions`. Templates: `sizing_questions`
(question card only) and `case`.

## Workflow

### 1. Which work?
Use the recipe from the conversation: the skill just kept (working/launchpad/choices.json), or the
work the person names. Recipe ids are in references/recipes.json: variance-commentary,
budget-round-app, mbr-brief, committee-paper. For their own work with no recipe, use `generic`
and pass its name as `work_title`. If it is unclear, ask in one line.

### 2. Four questions, one question card
Build `sizing_questions` and show only its question card:
- How often? Weekly, Monthly, Quarterly.
- How many people touch it? 1 to 2, 3 to 5, 6 or more.
- What happens when it is late or wrong? (several) Rework rounds, Contractors or overtime, Missed
  deadlines, Questions from the board or a regulator.
- Any outside spend that could stop? Free text, optional, for example "US$30,000 a year on
  contractors".

### 3. Work it out
Write the answers to `working/launchpad/case-answers.json`:
```json
{"recipe": "variance-commentary", "frequency": "Monthly", "people": "3 to 5",
 "late_or_wrong": ["Rework rounds", "Contractors or overtime"],
 "outside_spend": "US$48,000 a year on month-end contractor support"}
```
Pass the person's spend text exactly as typed; the script reads the amount, currency, period and
kind. Add `"price_per_credit"` only if the person gives their own agreed price, and
`"credits_per_run": {"low": ..., "high": ...}` only from their own measured runs. Then:
```bash
python3 <skill>/scripts/case.py --data working/launchpad/case-answers.json --out working/launchpad/case.json
```
It returns the measure that moves, cash that can stop (or "Not sized"), Cowork running cost (the
recipe's credits-a-run planning range x runs a year x the price per credit, or "Not sized yet"),
net a year (only when both are sized in one currency), the working, the assumptions and notes on
anything it did not count.

### 4. Show the case
Build `case` with `--data` `{}` and `--merge working/launchpad/case.json`. The card leads with the
measure that moves, then a table of cash that can stop, running cost and net a year, what the
person told you, and accordions with the working and the assumptions.
- **Draft the full brief:** step 5.
- **Change an answer:** show the four questions again and work it out again.
- **Not now:** keep nothing.

### 5. Draft the full brief (only after "Draft the full brief")
Use Cowork's Word skill to draft a Word document from references/brief-outline.md, using only the
figures, working and assumptions in working/launchpad/case.json, word for word. Show the working
and list every assumption. Say where the document was saved. Never send it or share it.

## Output
- The case card: the measure that moves, a three-line money table, what you told me, the working
  and the assumptions.
- On request: a Word brief for the person's manager, drafted and not sent.

## Guardrails
- Never turn time into money, and never estimate hours, minutes or percentages of effort.
- Never count spend the person did not select and give an amount for; never invent an amount.
- Never do arithmetic yourself; every figure comes from scripts/case.py.
- Always show the assumptions with the figures; never present a planning range as a quote.
- Never send, post or share the brief; draft it only when asked.
- If an answer is missing or unclear, ask for it rather than guess.

## Recovery
| Situation | What to do |
|---|---|
| case.py prints errors | Fix the answers file (frequency, people and options must match the question card) and run it again |
| The spend is in a different currency from the credit price | Show it as is; net stays "not sized" unless the person gives a price per credit in that currency |
| No planning range for the recipe | Show "Not sized yet" and suggest measuring a few runs first |
| The person names time, salaries or headcount | Say these are not counted, because time is never turned into money here |
| The Word skill is not available | Give the brief as text in the conversation, and say no file was created |

See references/recipes.json for the measures and planning ranges.
