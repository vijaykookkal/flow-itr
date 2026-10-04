# What's new

Changes worth knowing about, newest first. Flow is a draft-preparing tool:
check every figure against the e-filing utility before you file.

## 0.3.0 (4 October 2026)

**Planning.** A new page after Hand-off, for the year that is still running.
Add a return in the middle of the year with what you have (payslips so far, the
sales already made) and a note of what is coming: "₹3.5 lakh a month, a ₹5 lakh
bonus in June, selling the 2024 RSUs in January". The page projects the year
from all of it, with the same rules as the return, and you can type over any
expected figure. Its cards, each opening to the detail:

- **Your year**: what has been read, what is still expected and where each
  expected figure came from, and the year's tax.
- **Take-home and tax**: how the tax grows with income up to ₹1.5 crore, as
  shares of income or in rupees, with income tax, surcharge and cess shown
  apart; where the rebate and each surcharge threshold fall; and the stretches
  just past them where earning more leaves you with less.
- **Old or new regime**: the projected tax under each, and how much more in
  deductions the old regime would need to match the new.
- **Capital gains**: the tax on the year's gains, what a loss booked before
  31 March would save, how much of the ₹1.25 lakh equity exemption is still
  unused, losses brought forward and the year each expires, and foreign shares
  such as RSUs with the date each lot turns long-term.
- **Advance tax**: what is due by each instalment date, against what was paid
  by then.

Below them are hints chosen for what is in your return. Those that call for
acting before 31 March are shown only while the year is running.

**Planning notes.** A note about the year ahead is read as an expectation, never
into the return. Put it with the documents and press **Sort documents again**,
or put it in a folder called `11_planning`, then read it from the Planning page.

**A plan for a year without its rates.** For a year whose Finance Act is not
built into Flow yet, the plan uses the latest year's rates and says so at the
top of the page. A return is never computed this way.

**Returns, redesigned.** The return's name, its year and its folder sit together
at the top. The folder is shown, not chosen, because it is named after the
return. Then come the person (PAN, date of birth, age and sex), how the tax is
worked out, reading and export, and the documents folder.

**Results follow the return's name.** There is no results folder to choose any
more: everything Flow produces is kept in the return's own folder. Renaming a
return moves that folder, with the documents when they are in it, after a
warning; if any part of the move fails, all of it is undone. Results that an
earlier version kept elsewhere can be moved in from the Returns page.

**Restart reminder.** When Flow's own program has changed since it was started,
after an update for instance, the page says so and asks for a restart, instead
of failing in ways that look like bugs.


**Zip archives are read.** A `.zip` in the documents folder is now opened when
documents are sorted, and routed by what is inside it: an archive of expense
invoices goes to Books like the loose invoices would, and a download of the
whole folder is recognised as a duplicate. Before, an archive was routed by its
name alone, and usually to nothing. Sort the documents again to pick this up.

**Surcharge marginal relief corrected.** Relief is now measured, as the Act
requires, from the tax and surcharge on an income of exactly the threshold.
Before, it capped the surcharge alone at the income above the threshold, which
charged a little too much just above ₹50 lakh and much too little just above
₹1 crore, ₹2 crore and ₹5 crore. Returns away from those thresholds are
unchanged.

**One computation.** An older, simpler tax calculation that the staged
computation had replaced is gone, so nothing can show its figures by mistake.

**Tests.** Worked cases for the slabs, the 87A rebate and its marginal relief,
surcharge, the 15% cap on capital gains, loss set-off, the server's guard,
archive routing, the planning projection and its take-home curve, results that
follow the return's name, and a check that the page's scripts never declare the
same name twice: `python -m unittest discover -s tests -t .`

**The local server answers only to itself.** Every request must be addressed
to 127.0.0.1 or localhost, which stops a web page elsewhere from reaching it by
DNS rebinding; the token is compared in constant time; and another site's
origin is refused on reads as well as writes.

**Documentation.** The design document now says what is built and what is
planned. The README says plainly that nothing in the Flow folder is encrypted
and recommends full-disk encryption.

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
