---
name: launchpad-how-do-i
description: >-
  Answers "How do I...?", "Can Cowork...?" and "Where do I...?" questions about using Cowork
  itself (skills, plugins, schedules, email triggers, sharing, files, apps and admin deployment)
  from Microsoft Learn through the Microsoft Learn connector: plain steps, a link to the exact
  page, and three questions people ask next. Never invents steps. Use for questions such as "How
  do I share a skill?", "Can Cowork run this every month?", "Where do I find my schedules?", "How do
  I upload a plugin?" or "Can Cowork start a task when an email arrives?". Do not use for questions
  about the content of the person's own work (use launchpad-cookbook instead) or for setting up a
  routine now (use launchpad-routines instead).
metadata:
  category: productivity
  icon: QuestionCircle
  version: "2.1.1"
---

# Launchpad: how do I...?

Answers questions about using Cowork from Microsoft Learn, the official public documentation,
in two to four plain steps with a link to the exact page. Where Cowork can do the thing in this
conversation, it offers to.

## When to use
- "How do I ...?", "Can Cowork ...?", "Where do I ...?" about Cowork itself: skills, plugins,
  schedules, email triggers, sharing, files, apps, admin deployment.

## When NOT to Use
- Questions about the person's own work ("Can Cowork do my month-end pack?"): use
  launchpad-cookbook instead.
- Setting up a schedule or trigger now: use launchpad-routines instead.
- General questions that are not about Cowork: answer normally, without this skill.

## Rules
1. **Only Microsoft Learn.** Search with the Microsoft Learn connector first. Write steps only from
   the page; never invent a step, a menu name or a limit. If Learn has no answer, say so.
2. **Link the exact page**, with its section anchor when there is one.
3. **Offer to do it only where Cowork can do it here**: a schedule or an email trigger (hand to
   launchpad-routines), or building a skill from their work (hand to launchpad-cookbook). Never
   offer a step only the person can do in a screen, such as sharing a skill.
4. Plain business English, British spelling, the point first. Menu names exactly as Learn writes
   them (for example Customize, Automations). No tool names, file paths or error codes. No hype,
   no exclamation marks.
5. Read nothing of the person's work to answer a how-to question.
6. One card per reply, built by scripts/cards.py and shown unchanged, with the choices in one
   question card in the same reply.

## Run this skill's scripts
```bash
ls -d /mnt/shared/plugins/*/*/skills/launchpad-how-do-i 2>/dev/null | sort -t/ -k6,6V | tail -1
# if nothing prints:
find / -path '*/skills/launchpad-how-do-i/scripts/cards.py' -not -path '/proc/*' 2>/dev/null | head -1
mkdir -p working/launchpad
```
To show a card: write the data to a file, run
`python3 <skill>/scripts/cards.py build <template> --data <file>`, then call `render_ui` with the
returned card exactly and, in the same reply, `AskUserQuestion` with its `questions`. Templates:
`answer` and `not_found`.

## Workflow
1. **Search.** Call the Microsoft Learn connector's search tool (`microsoft_docs_search`) with the
   question in Cowork's words, for example "Copilot Cowork share a skill".
2. **Fetch when needed.** If the excerpt does not give the full steps, fetch the best page with
   `microsoft_docs_fetch`. Prefer pages under learn.microsoft.com/copilot/cowork/.
3. **Write the answer.** Two to four short steps, from the page only, in the order the page gives
   them. Use the question as the title.
4. **Check against the verified answers.** If the topic is in references/verified-answers.json,
   compare. If the live page differs, the live page wins.
5. **Offer to do it**, only where rule 3 allows: add `can_do` with `text`, `question`, `label`,
   `description` (verified-answers.json has the wording for schedules, triggers and skills).
6. **Three questions people ask next**: `next` as `[{"label", "description"}]`, short labels that
   start with a verb (for example "Share a skill"), each with the full question as the description.
7. **Build and show** `answer` with `question`, `steps`, `learn_url`, `learn_title`, `next`, and
   `can_do` and `note` when needed. If the person picks the offer, hand over to launchpad-routines
   or launchpad-cookbook. If they pick a next question, answer it the same way.

Data example:
```json
{"question": "How do I share a skill?",
 "steps": ["Open Customize, then the skill's detail page.",
           "Select Share, choose Specific users in your organization and add their names.",
           "Select Apply.",
           "When you change the skill later, select Re-share so everyone gets the latest version."],
 "learn_url": "https://learn.microsoft.com/copilot/cowork/cowork-customize#share-skills-and-plugins",
 "learn_title": "Share skills and plugins",
 "next": [{"label": "Upload a plugin", "description": "How do I upload a plugin package?"},
          {"label": "Run it every month", "description": "Can Cowork run this on a schedule?"},
          {"label": "Start it from an email", "description": "Can it run when a matching email arrives?"}]}
```

### When Learn has no answer
Build `not_found` with the question, a link to the closest Learn page (or the Cowork overview,
https://learn.microsoft.com/copilot/cowork/), and three next questions. Say plainly: "Microsoft
Learn does not answer this yet, so I will not guess."

### When the connector is not available
If the topic matches references/verified-answers.json, use that answer and add the `note`
"Checked on Microsoft Learn in November 2026; the page may have changed." Otherwise say Microsoft
Learn cannot be reached right now, and do not guess.

## Output
- The answer card: the question as the title, two to four steps, an offer where Cowork can do it,
  and a "Read on Microsoft Learn" link to the exact page.
- The question card: the offer (if any) and three questions people ask next.

## Guardrails
- Never invent steps, menu names, limits or links; if Learn does not say it, do not say it.
- Never offer to do something Cowork cannot do in this conversation.
- Always show the answer before offering to do anything, and ask before handing over: the offer is
  a choice in the question card, never an action taken for the person.
- Never read the person's mail, calendar or files to answer a how-to question.
- Never link to anything other than public Microsoft Learn or support pages.
- If two Learn pages disagree, show the newer page and say the documentation differs.
- If the connector is unavailable or a page cannot be fetched, say so plainly; use only a matching
  verified answer with its dated note, and never fill the gap from memory.

## Recovery
| Situation | What to do |
|---|---|
| No good search result | Try one rephrased search; then use not_found |
| The page cannot be fetched | Use the search excerpt if it has the steps; otherwise not_found |
| The connector is not available | Use a matching verified answer with its dated note, or say Learn cannot be reached |
| A card is refused when shown | Rebuild once; otherwise give the steps and the link as text, then the question card |
