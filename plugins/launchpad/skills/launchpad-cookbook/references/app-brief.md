# Brief for Cowork's App skill: a round of submissions

Fill every bracket from the person's own tracker and the script's output, then hand the whole
brief to Cowork's App skill. Do not add columns or statuses the tracker does not have, except the
ones marked "add".

## Purpose
An app for [the round, for example the 2027 budget round] so that each owner updates their own
line and [the person] sees who is late without chasing anyone. It replaces passing the
spreadsheet around; the original spreadsheet is left exactly as it is.

## Data, from the tracker's own columns
| Column in the tracker | Field in the app | Type |
|---|---|---|
| [Cost centre column] | Cost centre | text |
| [Owner column] | Owner | person |
| [Status column] | Status | choice: [the statuses used in the tracker]; add Overdue if missing |
| [Submitted date column] | Submitted date | date |
| [Value column] | Value | number, [unit] |
| [Target column] | Target | number, [unit] |
| add | Due date | date, [the round's deadline] |

Load the current [number] rows from the tracker as the starting data.

## Views
- All lines, sorted by status then cost centre.
- Overdue: lines not submitted or in review whose due date has passed.
- By owner.
- My lines: each owner sees and edits only their own lines.

## Summary tiles
Submitted ([x of y]), In review, Overdue, Gap to target ([unit]). Worked out the same way as the
weekly summary script: a line is overdue when it is not submitted or in review and its due date
has passed; gap to target is value minus target over submitted and in-review lines.

## Actions
- Draft a chaser for each overdue owner, naming their lines and the due date. Drafts only; the
  person sends them.
- Every Friday at 16:00, draft a summary for [audience]: the four tiles and the overdue owners.
  Drafts only.

## Access
Only [the person] until they choose to share it. Owners edit their own lines only. Nothing is
sent automatically.
