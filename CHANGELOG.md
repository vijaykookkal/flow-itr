# What's new

Changes worth knowing about, newest first. Flow is a draft-preparing tool:
check every figure against the e-filing utility before you file.

## 0.2.0 (3 October 2026)

**Read with an open model on your own computer.** Flow can now read documents
with an open model through Ollama, so no document leaves your computer and no
subscription is needed. It runs on an ordinary laptop with no graphics card.
Install and remove models on the **Reading engines** page; each one appears as
a reading engine on the Returns page.

**A Home page.** Flow now opens on a Home page: what Flow does, the return you
are working on, how it works, and the Getting started guide as a section of it.

**Returns, one at a time.** The Returns page lists your returns on the left and
shows one on the right, with a single Save. Each folder can be **opened**,
**changed** to another location without moving anything, or **moved**.

**Schedules page.** Every schedule as a card: what it is about, what it reads,
where it stands, and its button. It also explains the difference between
reading (done by the AI engine) and computing (done by Flow itself).

**Get documents.** A tab on the Documents page with a card for each usual
source (the income-tax portal, your employer, brokers, mutual funds, foreign
stock plans, banks): it opens the site and lists what to download for the year.

**Help.** The user guide, these notes and an About page, inside Flow.

**Reading engines page.** One place for all three engines (settings menu, top
right). Each engine lists its models, and a return reads with an engine and
one of its models: Claude Code's Opus, Sonnet or Haiku; Codex's default or a
model you add; any model installed in Ollama, each with its own window and
reasoning level. The page also sets the default reader and each engine's time
limit. These choices are kept in `settings.json` in your Flow
folder, so updating Flow never changes them.

**Stop, and time limits.** Any reading, comparison or sorting can be stopped
from its own Stop button or from the Activity menu (top right), which also has
Stop everything. Each request to a reading engine now has a time limit that is
enforced while it runs: 30 minutes for Claude and Codex, 120 for a local model,
adjustable on the Reading engines page. A stopped run saves nothing, and a stopped
reading leaves the schedule as it was.

**Smaller changes**
- Each return's document folder is now called `documents` (was `input-docs`).
- The Overview is now called **Summary**.
- Excel export writes `results.xlsx` when you ask for it (the default), or
  after every computation if you choose.
- Flow opens Form 26AS and NSDL/CDSL statements protected with your date of
  birth or PAN, as well as the AIS and TIS.

## 0.1.0 (3 October 2026)

The first public release: documents sorted and read schedule by schedule, the
ITR-3 computed in the form's own line numbers for both regimes, reconciliation
with the AIS, TIS and Form 26AS, comparison with a filed return, hand-off sheets
and an Excel workbook. Everything personal is kept in a folder outside the
program.
