![Flow ITR](web/logo.svg)

# Flow ITR

**An ITR-3 filing assistant for residents of India**, and one of the **Flow** apps.

![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue) ![No dependencies](https://img.shields.io/badge/dependencies-none-brightgreen) ![Runs locally](https://img.shields.io/badge/runs-locally-informational) [![MIT licence](https://img.shields.io/badge/licence-MIT-lightgrey)](LICENSE)

Flow ITR helps you prepare an Indian income-tax return (form ITR-3) from the
documents you already have. You put the year's papers in a folder; Flow ITR reads
them, works out each schedule of the return, checks the result against what the
Income Tax Department has on record for you, and gives you the figures to type
into the e-filing portal.

It runs on your own computer, in your browser. It **does not file anything**:
what you get is a draft to review and enter yourself.

**Who it is for:** residents of India (resident and ordinarily resident) filing
ITR-3, with any mix of salary, business or professional income, capital gains,
interest and dividends, and foreign shares or income.

---

## Get started in five steps

You do not need to know programming. You will type two or three commands, once.

### 1. Install Python

Flow ITR needs Python 3.10 or newer.

- **Windows:** install "Python 3" from the Microsoft Store, or download it from
  [python.org/downloads](https://www.python.org/downloads/). If the installer
  shows a box saying "Add Python to PATH", tick it.
- **Mac:** download it from [python.org/downloads](https://www.python.org/downloads/).
- **Linux:** it is almost certainly already there.

### 2. Install a reading engine and sign in

Flow ITR reads your documents with an AI assistant. You need **one** of these
three:

| Engine | Costs | Your documents | Install |
|---|---|---|---|
| Claude Code CLI (recommended) | a Claude subscription | sent to Anthropic to be read | install it from [claude.com/claude-code](https://claude.com/claude-code), then run `claude` once in a terminal and sign in |
| Codex CLI | a ChatGPT subscription | sent to OpenAI to be read | install it from [github.com/openai/codex](https://github.com/openai/codex), then run `codex` once in a terminal and sign in |
| An open model through Ollama | free | **never leave your computer** | install [Ollama](https://ollama.com/download), then add a model on the **Reading engines** page inside Flow ITR (see [Using an open model with Ollama](#using-an-open-model-with-ollama)) |

For Claude and Codex, Flow ITR needs the **command-line tool (CLI)**, not the
desktop app: Flow ITR starts the `claude` or `codex` command itself, in the
background. Having only the Claude or ChatGPT desktop app, or only the website,
is not enough. To check it is installed, open a terminal (on Windows:
PowerShell) and type `claude --version` or `codex --version`; if a version
number is printed, Flow ITR will find it. It uses the sign-in you did there and
never asks for a password or a key.

Ollama needs no account and no graphics card; an ordinary laptop with 16 GB of
memory can run it. It is slower than Claude or Codex and less accurate on messy
statements, so it suits the smaller schedules best.

Each engine offers **models**, and the model is what actually reads: Claude
Code offers Opus, Sonnet and Haiku; Codex offers its default and any model you
add; Ollama offers every model you install. You choose the engine and model for
each return under **Returns**, in **Reading engine**, and the default for all
returns on the **Reading engines** page.

Which model does the reading, and how long a reading may take, are set on the
**Reading engines** page (settings menu, top right): Claude reads with Opus
unless you choose Sonnet, Haiku or your Claude Code default; Codex uses its own
default unless you name a model.

### 3. Download Flow ITR

- **Easiest:** on this page press the green **Code** button, choose
  **Download ZIP**, and unzip it anywhere, for example your Documents folder.
- **If you use git:** `git clone https://github.com/vijaykookkal/flow-itr.git`

### 4. Start it

- **Windows:** open the folder and double-click **`flow.cmd`**.
- **Mac or Linux:** open a terminal in the folder and run `./flow.sh`
  (the first time, run `chmod +x flow.sh` before it).

A black window opens and stays open, and your browser opens Flow ITR at
`http://127.0.0.1:8787`. Leave the window open while you work; closing it stops
Flow ITR. The window also tells you where your folders are:

```
  home      C:\Users\you\flow
  documents C:\Users\you\flow\DEFAULT\documents
  results   C:\Users\you\flow\DEFAULT\results
  engine claude   available
```

### 5. Add your documents

Copy the year's documents into the **documents** folder shown above. Sub-folders
are fine, and nothing needs renaming or sorting. A `.zip` is fine too: Flow ITR
opens it and routes it by what is inside (a `.rar` or `.7z` it cannot open, and
says so). Useful ones:

- Form 16 and Form 12BA from your employer
- AIS, TIS and Form 26AS, downloaded from the income-tax portal
- broker statements: capital gains, tax P&L, contract notes, dividend statements
- bank statements and interest certificates
- for a business or profession: the books, invoices, asset purchases
- for foreign shares: the broker's statements and any tax forms such as 1042-S
- proofs for deductions: insurance, NPS, donations, loan interest
- last year's filed return, if you want this year compared against one

Not sure where to get something? In Flow ITR, **Documents › Get documents** has a
card for each usual source (the income-tax portal, your employer, Zerodha, ICICI
Direct, NSDL/CDSL, CAMS, Merrill, INDmoney and the main banks). Each card opens
the site and lists what to download for the year and how. You log in and
download yourself; Flow ITR never sees a password. The cards come from
`config/document_sources.json`, so a new bank or broker can be added there.

The AIS, TIS and Form 26AS are password-protected. Enter your PAN and date of
birth under **Returns** (at the top of the left panel) and Flow ITR opens them for
you, and NSDL/CDSL statements protected with your PAN as well.

---

## Using it

Flow ITR is a set of places you can open in any order. A typical first run:

1. **Documents → "Sort documents again".** Flow ITR looks at every file and decides
   what it is and which part of the return it belongs to.
2. **Schedules → "Read documents" on each card.** The Schedules page lists every
   part of the return (Salary, Capital gains, Other sources and so on) with a
   line on what it is, and a button to read it. This takes a minute or two per
   schedule; "Read the waiting" does them one after another. The tax
   computation updates by itself.
3. **Summary** shows where you stand: the tax payable or refund, your effective
   and marginal tax rates, where the income came from, how it is taxed slab by
   slab, and how much is already paid.
4. **Review** lists what only you can decide: questions the documents do not
   answer, and differences nothing explains. Settle each with a reason.
5. **Reconcile** compares your figures with the department's record (AIS, TIS,
   Form 26AS) so surprises show up before you file, not after.
6. **Hand-off** gives each schedule as a sheet in the form's own line numbers.
   Type them into the e-filing utility and tick them off, or press
   **Export to Excel** to get the whole return as a workbook.

**Planning**, after Hand-off, is for the year that is still running. Add a return
for it in the middle of the year with whatever you have: payslips so far, the
sales already made, and a note of what is coming ("salary Rs 3.5 lakh a month,
bonus Rs 5 lakh in June, selling the 2024 RSUs in January"). Notes go with the
documents (or in a folder called `11_planning`); they are read as expectations
and never into the return. The page projects the year from all of it, and you
can type over any expected figure. Its cards, each opening to the detail:

- **Your year**: read so far, still expected, and the year's tax.
- **Take-home and tax**: how the tax grows with income up to Rs 1.5 crore, where
  the rebate and surcharge thresholds fall, and the stretches just past them
  where earning more leaves you with less.
- **Old or new regime**: the projected tax under each, and how much more in
  deductions the old regime would need.
- **Capital gains**: the tax on the year's gains, what a loss booked before
  31 March would save, how much of the equity exemption is unused, losses
  brought forward and when they expire, and foreign shares (RSUs) with the date
  each lot turns long-term.
- **Advance tax**: what is due by each instalment date against what was paid.

Below them are hints chosen for what is in your return. Everything is worked
out with the same rules as the computation, and nothing changes your return.
For a year whose rates are not built into Flow ITR yet, the plan uses the latest
year's and says so.

**Reading and computing are different.** Reading is done by the AI engine: it
opens your documents and copies out the facts. Computing is done by Flow ITR itself,
with no AI: it applies the tax rules to those facts, instantly, and does so by
itself after every reading or correction. So the only thing you ever ask for is
a reading: once per schedule, and again when you add or replace a document.

Click any figure to see where it came from: the working, the printed line in
your document, and what the department holds against it. If a figure is wrong,
correct it there with a reason; your correction survives every re-read.
Press **Ctrl K** to search every line, amount and document.

The **Getting started** button at the top of the page opens the same steps as a
guide inside Flow ITR, with a button on each step that takes you to the right place.

---

## Using an open model with Ollama

Ollama runs open AI models on your own computer. With it, your documents are
read without ever leaving the machine, and no subscription is needed. No
graphics card is required; a laptop with 16 GB of memory can do it, 32 GB is
comfortable.

1. Install Ollama from [ollama.com/download](https://ollama.com/download). It
   starts by itself and runs quietly in the background.
2. In Flow ITR, open **Reading engines** from the settings menu (top right) and press
   **Download** on a model. The recommended one for a laptop without a graphics
   card is `gpt-oss:20b`. A large model takes a while on a home connection; you
   can leave the page and it carries on. (From a terminal,
   `ollama pull gpt-oss:20b` does the same.)

   | Model | Download | Why |
   |---|---|---|
   | `gpt-oss:20b` (recommended) | about 13 GB | Only a small part of it works on each word, so it is quick on a laptop processor; reliable at filling in a fixed JSON shape; reads long documents (up to 128,000 tokens) |
   | `qwen3:30b-a3b` | about 19 GB | Same quick design; very good with tables and figures; needs more memory |
   | `qwen3:8b` | about 5 GB | For 16 GB machines; slower per word and less accurate |

3. Every installed model appears by itself in **Returns › Reading engine**, as
   "Ollama · gpt-oss:20b (on this computer)". Choose it and press Save. No
   restart is needed; the Reading engines page also lets you remove a model you no longer
   want.

What to expect, honestly:

- **Slower.** A laptop reads perhaps a few hundred words a second, so a large
  schedule can take ten minutes or more. Leave it running.
- **Less accurate on messy statements** than Claude or Codex. Everything Flow ITR
  checks still applies: each answer must fit the schedule exactly, and the
  reconciliation with the AIS, TIS and Form 26AS shows what does not agree.
- **A limit on how much it can read at once.** Flow ITR gives the model 64,000
  tokens by default (the Window setting on the Reading engines page); `gpt-oss:20b` can
  take 131072 on a 32 GB machine. A schedule whose documents do not fit is
  refused with its size, never read halfway. A year of bank statements for
  Other sources or Books is usually too much for a laptop model; read those
  schedules with Claude or Codex, or with fewer documents at a time.
- **Scanned PDFs** (pictures, no text) cannot be read by a local model.
- **Looking up exchange rates** needs Claude or Codex; with Ollama, type the
  rate on the Capital gains page.

## Where your files are, and your privacy

**Nothing personal is stored with the program.** Everything of yours lives in
one folder, called the Flow home, which by default is `Flow\ITR` inside your
user folder (`Flow/ITR` on a Mac or Linux). `Flow` holds each of the Flow apps
in a folder of its own:

```
Flow/ITR/
  profiles.json            your returns and their settings
  fx_rates.json            exchange rates looked up for foreign income
  DEFAULT/
    documents/            your documents go here
    results/               everything Flow ITR produces, and results.xlsx
  .state/                  working files; safe to delete
```

- **Flow ITR itself sends nothing over the internet.** It runs only on your
  computer and cannot be reached from another one.
- **With Ollama, nothing leaves at all**: the model runs on your computer.
- **Otherwise, the reading engine does.** To read a document, Claude Code or Codex sends
  its contents to its maker (Anthropic or OpenAI), under the account you signed
  in with. That is the only place your documents go.
- **Back it up** by copying the `Flow\ITR` folder. To move to a new computer,
  copy that folder across and install Flow ITR there.
- **Before version 0.3.1 the folder was called `flow`.** Flow ITR moves your
  files from it to `Flow\ITR` by itself the first time a newer version starts,
  all at once or not at all: if a file is open (`results.xlsx` in Excel, say),
  nothing moves, the old folder stays in use, and the window says what to
  close. A folder you chose yourself, with `FLOW_HOME` or `flow.local.json`,
  is never moved.
- **Nothing in the `Flow\ITR` folder is encrypted.** `profiles.json` holds each
  return's PAN and date of birth in plain text (they are what opens the AIS and
  TIS), and the `results` folder holds your income and bank details in a form
  that is easy to read, next to the documents themselves. Anyone who can open
  your user folder can read them. Turn on full-disk encryption (BitLocker on
  Windows, FileVault on a Mac), keep the folder out of shared or public cloud
  folders, and treat a copy of it like the documents themselves.

### More than one return

A **return** holds everything for one income-tax return: whose it is and for
which year, its settings, its documents, and everything read and computed from
them (your corrections and decisions, the computation, the reconciliation, the
workbook). Each return keeps its own. Add one under
**Returns** (at the top of the left panel) for a spouse, a parent, or
another year. Each gets its own folder in the Flow home, named after the
return, holding its documents and everything Flow ITR produces from them; the
Returns page shows where it is. Two returns can share one documents folder, for
example to compare the old and new regimes.

### Keeping your files somewhere else

- **A different documents folder for one return:** on the Returns page, under
  Folders, press **Change location** and paste a full path such as
  `D:\Tax\2025-26`. Nothing is moved: the return simply reads from that folder.
  **Move…** instead carries the folder's contents to the new place. Everything
  Flow ITR produces stays in the return's own folder in the Flow home.
- **Renaming a return:** the return's folder follows its name, so a rename
  moves it. Flow ITR warns first and says what will move. Documents kept somewhere
  else stay where they are.
- **Google Drive:** install Google Drive for desktop, then type a Drive path
  such as `G:/My Drive/Flow/ITR/DEFAULT/documents`, or press "Put on Google Drive"
  on the return when Flow ITR finds your Drive. Your documents are then stored in
  your Google account; what Flow ITR produces stays in the Flow home. Let Drive finish syncing
  before opening the same return on another computer.
- **Moving the whole home:** set the `FLOW_HOME` environment variable, or put a
  file called `flow.local.json` next to `flow.cmd` containing
  `{"home": "D:/somewhere"}`, and restart.

### Excel

Press **Export to Excel** on the Hand-off page and Flow ITR writes `results.xlsx`
into the return's results folder: a summary, one sheet per schedule, the
capital gains ledger, the reconciliation, the comparison with a filed return,
and the list of documents. The PAN and account numbers are left out, so it is
safe to send to your accountant. Export again after figures change; or, under
Returns, set "Export results to Excel" to "After every
computation" and Flow ITR keeps the workbook up to date by itself.

---

## Before you file

- **This is a draft, not advice and not a filing.** Check the figures, and have
  a professional check them if the return is not simple.
- **Read the list on the Computation page** of what is not included. In
  particular, interest under sections 234A, 234B and 234C is not computed; the
  e-filing utility adds it.
- The tax rates are those for financial year 2025-26 (assessment year 2026-27)
  as enacted, and have not been checked against the department's released
  utility. Compare the final tax with what the utility shows.
- Non-residents and "not ordinarily resident" taxpayers are not supported.

## If something goes wrong

| What you see | What to do |
|---|---|
| "Python was not found" | Install Python (step 1), then close and reopen the window. |
| The window says `engine … NOT FOUND` | Install an engine and sign in (step 2), then start Flow ITR again. |
| "Port 8787 is already in use" | Flow ITR is already running in another window. Use that one, or close it first. |
| The page says it cannot reach the local agent | The black window was closed. Start Flow ITR again. |
| A schedule shows nothing after reading | Open **Documents** and check the file was sorted to that schedule; press "Sort documents again" after adding files. |
| The AIS or TIS cannot be opened | Enter the PAN and date of birth under **Returns**. |
| A reading or sorting is taking too long, or you started the wrong one | Press **Stop** beside it, or open the Activity menu (top right) and press Stop. Nothing from a stopped run is saved. Each request also has a time limit: 30 minutes for Claude and Codex, 120 for a local model, changeable on the Reading engines page. |
| "The Excel workbook is out of date" | The workbook is open in Excel. Close it and press Export to Excel. |

---

## For developers

Design and rationale: [docs/DESIGN.md](docs/DESIGN.md). The name, logo and
colours shared by the Flow apps: [docs/BRAND.md](docs/BRAND.md). The program is
the Python standard library and plain HTML, CSS and JavaScript: nothing to
install, no build step.

```
python -m server                # what flow.cmd and flow.sh run
python -m server --no-browser
```

The page binds to loopback only. Every request must be addressed to
`127.0.0.1` or `localhost` (which stops DNS rebinding), every API call must
carry a token minted on first start, compared in constant time, and a browser's
`Origin`, where it sends one, must be the page's own. It loads nothing from the
network: the typefaces are in `web/fonts/`.

### Tests

```
python -m unittest discover -s tests -t .
```

Worked cases for the tax rules that are easiest to get wrong, each with its
arithmetic in a comment: slabs in both regimes, the 87A rebate and its marginal
relief, the rebate stopping at capital-gains tax, the 112A exemption, the
surcharge bands with marginal relief and the 15% cap on gains, and loss set-off.
Also the server's refusal of other hosts, other origins and a missing token,
and routing's view inside a zip. They need no documents, no engine and no
network, and never touch your Flow home.

### Layout

```
config/tabs.json     the tabs and what each reads
schemas/  prompts/   the contract with the engine, and its instructions
engine/              deterministic tax computation
server/              local agent: HTTP API, engine drivers, Excel export
web/                 the page: app.js (schedules), charts.js (graphics),
                     pages.js (areas), shell.js (frame)
tests/               worked cases for the tax rules, the server's guard, archive routing
tools/               checks used while developing
fixtures/            invented documents for development
```

Inside a return's results folder:

```
extracted/       AI output              (machine-owned)
overrides/       your corrections       (human-owned, with reasons)
resolved/        the two, merged        (what you file from)
reconciliation/  each schedule against the AIS, TIS and Form 26AS
review/          what you settled, with reasons, and the lines you have entered
_runs/           run manifests and rejected attempts
```

Re-running an extraction rewrites `extracted/` only. Corrections in `overrides/`
are re-applied on top, so re-extracting never discards a judgement already made.
The folder is plain JSON and diffs well; to keep a history of your own return,
make it a private git repository of its own.

### Without the browser

```
python -m server.cli profiles                          # returns, and the home
python -m server.cli status                            # what each tab holds
python -m server.cli run --tab salary --engine claude  # extract one schedule
python -m server.cli run-all --engine claude
python -m server.cli compute                           # derived tabs
python -m server.cli override --tab salary \
    --pointer /data/employers/0/exempt_allowances/1/amount/amount \
    --value 0 --reason "No travel in the 2022-2025 block; not claiming LTA."
```

### Engines

Each return chooses its engine under Returns. Left at "the
default", it uses the default engine set on the Reading engines page, or whichever engine is
installed if that one is not.

| Engine | Billing | Document reading | Reads confined to the tab's folders |
|---|---|---|---|
| `claude` | Claude subscription | Native, no shell | **Yes** — `--add-dir` is the whole world |
| `codex` | ChatGPT subscription | Runs shell commands (`pdftotext`, Python) | **No** — `-s read-only` sandboxes writes, not reads |
| `ollama:<model>` | none: runs locally | Flow ITR sends the text it made of each document; the model opens nothing | **Yes**, the tightest: it sees only what is sent |
| `mock` | none | Text fixtures only | Yes. Not offered in the UI; `--engine mock` for tests |

An engine is anything implementing `run(Request, on_event) -> Reply` and
`available()`, registered in `server/engines/__init__.py`. Everything that makes
a result trustworthy — schema validation, the repair loop, provenance stamping,
the three-layer merge — lives in `runner.py` and applies identically whichever
engine ran. The engine is part of the run fingerprint, so one engine's result
can never satisfy a request for another's, and every output records which engine
produced it. Running a schedule through both and comparing is a genuine check.

### Fixtures

`fixtures/AY2026-27/` holds invented text documents used to develop and test the
pipeline. They never go in a return's documents folder, because a fixture among
real documents is extracted like one and its invented figures then blend into a
return.

```
ITR_SOURCE_ROOT=fixtures python -m server.cli run-all --engine mock
```

### Keeping personal information out of the repository

`tools/check_private.py` refuses a commit that contains a document file, a PAN
other than the specimen ones, or anything that identifies a return on your
machine: each return's name, PAN, date of birth, e-mail, mobile and bank account
numbers, read from your Flow home at the moment you commit. Install it once per
clone:

```
python tools/check_private.py --install   # as a git pre-commit hook
python tools/check_private.py --all       # check everything, any time
```

### After changing the page or the server

```
python -m unittest discover -s tests -t .   # the tax rules and the server's guard
python tools/check_js.py       # the faults that blank a page without an error
python tools/check_page.py     # opens every place in headless Edge or Chrome
python tools/probe_page.py out.png salary "click:.money@0"   # click, then screenshot
python tools/restart_server.py # needed after changing server/ or engine/
```

The two browser tools and the restart tool are written for Windows with Edge or Chrome.

---

## Disclaimer

Flow ITR is a personal tool shared as-is. It is **not tax advice**, not a filing
service, and not affiliated with or endorsed by the Income Tax Department of
India or any bank, broker or other institution named in it. Their names and
websites appear only to tell you where your own documents come from; the names
are the trademarks of their owners. You are responsible for the return you
file: check every figure, and ask a professional when the return is not simple.

## Licence

Copyright (c) 2026 Vijay Kookkal. Released under the [MIT licence](LICENSE):
you may use, change and share it freely, keeping the copyright notice.

The typefaces in `web/fonts/` (Figtree and IBM Plex Mono) are under the SIL Open
Font License; their licence texts are beside them.
