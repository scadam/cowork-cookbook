---
name: launchpad-routines
description: >-
  Sets up Launchpad routines that keep the person on top of their priorities and their day: a
  Monday priorities view, a morning brief, meeting preparation the evening before, a kept skill on
  a schedule, or a kept skill when a matching email arrives, using Cowork's own scheduled prompts
  and event triggers. Use when someone says "Help me stay on top of my priorities", "Help me stay
  on top of my day", "Set up my week", "Brief me every morning", "Prepare me for my meetings", "Put
  this on a schedule", "Run this when the ... email arrives" or "Show my routines". Do not use for a
  one-off briefing or daily brief right now (use daily-briefing or meeting-intel instead), for
  building a new skill (use launchpad-cookbook instead) or for how-to questions (use
  launchpad-how-do-i instead).
metadata:
  category: productivity
  icon: CalendarLtr
  version: "2.2.0"
---

# Launchpad: my priorities and my day

> Owner note: this half of Launchpad is Nirali Desai's to refine. Keep it simple and well
> structured: one offer, one set-up at a time, Cowork's own approval cards, nothing sent.

Sets up routines that run by themselves and draft for the person: what matters this week, a
morning brief, and preparation for meetings that need a pack. It can also run a skill they kept
on a schedule, or when a matching email arrives.

## When to use
- "Help me stay on top of my priorities", "Help me stay on top of my day", "Set up my week".
- "Brief me every morning", "Prepare me for my meetings".
- "Put this on a schedule", "Run this when the ... email arrives".
- "Show my routines".
- A hand-over from launchpad-start (My priorities, My day) or launchpad-cookbook (Put it on a rhythm).

## When NOT to Use
- A one-off brief or meeting preparation right now: use daily-briefing or meeting-intel instead
  (Cowork's Daily Briefing and Meetings skills).
- Building a new skill: use launchpad-cookbook instead.
- "How do I...?" about schedules: use launchpad-how-do-i instead.

## Rules
1. **Set up only with approval.** Every routine is set up with Cowork's own tools, and Cowork
   shows its own approval card ("Set up trigger?" for triggers). Never describe a routine as set
   up until the tool returns success.
2. **Drafts, never sends.** Every routine's instructions say: draft only; do not send, post or
   share anything. Never request standing permission to send.
3. **One schedule per conversation.** Cowork keeps one scheduled prompt per conversation, and
   setting another replaces it. Set up the first chosen schedule here; for each other one, give a
   one-line starter to say in a new conversation. Never replace an existing schedule silently.
4. **Up to 25 schedules.** If the person is at the limit, say so and suggest pausing one.
5. **Privacy.** Routines leave out private, confidential, personal, HR and medical items. A saved
   Launchpad profile does not give permission for new reads; each routine reads only what it says.
6. Plain business English, British spelling, no tool names, file paths, IDs or error codes in
   what the person sees, no hype, no exclamation marks.
7. One card per reply, built by scripts/cards.py and shown unchanged, with every choice in one
   question card in the same reply.

## Run this skill's scripts
```bash
ls -d /mnt/shared/plugins/*/*/skills/launchpad-routines 2>/dev/null | sort -t/ -k6,6V | tail -1
# if nothing prints:
find / -path '*/skills/launchpad-routines/scripts/cards.py' -not -path '/proc/*' 2>/dev/null | head -1
mkdir -p working/launchpad
```
To show a card: write the data to a file, run
`python3 <skill>/scripts/cards.py build <template> --data <file>`, then call `render_ui` with the
returned card exactly and, in the same reply, `AskUserQuestion` with its `questions` (`preview`
has none: Cowork's own approval card follows it). Templates: `offer`, `preview`, `done`, `list`.

## Workflow

### 1. Offer
Read references/routines.json. If you can, check existing schedules first with
`GetScheduledPrompts` and count them for `used_text` (for example "You have 3 of 25 schedules.").
Build `offer` with `{"routines": <the five routines>, "used_text": "..."}`. Question (several):
Monday priorities, Morning brief, Meeting preparation, Schedule a kept skill, Start a skill from
email.

### 2. Set up the first chosen schedule
1. Check this conversation's own schedule with `GetScheduledPrompts`. If it already has one, do not
   replace it: give the starter line instead (step 4).
2. For a kept skill, ask which skill and when (a day of the month, or a weekday such as the first
   Wednesday). Use the routine's `prompt_template`.
3. Build `preview` with `name` and `facts`: When, What it reads, What you get, Where it appears
   ("In a new conversation, ready for you"), Sends ("Nothing").
4. In the same reply, call `SetupScheduledPrompt` with: `name`; `description` = the routine's
   `prompt` (what to do each run, with no times and no tool names); the routine's `schedule`
   fields (`frequency`, `interval`, `weekDays`, `hours`, `minutes`, or `monthDays`);
   `execution_mode` "separate"; and `required_tools` for the reads it needs (calendar and mail
   reads, for example). Pass `timezone` only if the person names one. Cowork shows its approval
   card.

### 3. Set up an email trigger ("Start a skill from email", "Run this when the ... email arrives")
1. Ask which skill, the words the subject contains, and who sends it.
2. Resolve the sender to an email address with Cowork's people lookup; never pass a name.
3. Build `preview`, then call `SetupEventTrigger` with `name`, `prompt` from the routine's
   `prompt_template`, `event_type` "email_received", `filter` with `subject_contains` and `from`,
   `execution_mode` "separate", and `required_tools`. Cowork shows its own "Set up trigger?" card.
   Do not request standing permission to send.

### 4. List what was set up, and the starters for the rest
Build `done` with `set_up` (name, when, state as returned) and `starters` (each other chosen
routine's `starter` line, with any `{skill}` or `{subject}` filled in). Say how to pause or stop:
the Automations page. Question: Help with my work (launchpad-cookbook), Show my routines,
Done for now.

### Show my routines
Call `GetScheduledPrompts` and `GetEventTriggers`. Build `list` with `items` (name, when, state)
and `count_text` (for example "3 of 25 schedules used."). Other conversations' schedules may show
only a title; never guess what they do.

## Output
- Every reply: at most one short line, one card, one question card under it.
- Each routine: a scheduled prompt or trigger that drafts for the person, visible on the
  Automations page, where they can edit, pause, resume or delete it.

## Guardrails
- Never set up, change or delete a routine without the person's approval on Cowork's own card.
- Never replace this conversation's existing schedule; give a starter line instead.
- Never send, post or share; every routine drafts only.
- Never ask for standing permission to send or post.
- Never pass a person's name as a sender; resolve it to an email address first, and confirm it.
- If a tool is unavailable or refuses, say plainly what could not be set up and give the starter
  line so the person can set it up later.

## Recovery
| Situation | What to do |
|---|---|
| The approval is declined | Say nothing was set up |
| This conversation already has a schedule | Give the starter line for a new conversation |
| 25 schedules already | Say so; suggest pausing or deleting one on the Automations page |
| Set-up is refused for a missing capability | Name what is missing in plain words; give the starter line |
| The sender cannot be resolved | Ask for their email address |
| The skill to schedule does not exist | Offer launchpad-cookbook to build it first |
