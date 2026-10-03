# Flow: an ITR-3 filing assistant

![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue) ![No dependencies](https://img.shields.io/badge/dependencies-none-brightgreen) ![Runs locally](https://img.shields.io/badge/runs-locally-informational) [![MIT licence](https://img.shields.io/badge/licence-MIT-lightgrey)](LICENSE)

Flow helps you prepare an Indian income-tax return (form ITR-3) from the
documents you already have. You put the year's papers in a folder; Flow reads
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

Flow needs Python 3.10 or newer.

- **Windows:** install "Python 3" from the Microsoft Store, or download it from
  [python.org/downloads](https://www.python.org/downloads/). If the installer
  shows a box saying "Add Python to PATH", tick it.
- **Mac:** download it from [python.org/downloads](https://www.python.org/downloads/).
- **Linux:** it is almost certainly already there.

### 2. Install a reading engine and sign in

Flow reads your documents with an AI assistant. It needs the assistant's
**command-line tool (CLI)**, not the desktop app: Flow starts the `claude` or
`codex` command itself, in the background. Having only the Claude or ChatGPT
desktop app, or only the website, is not enough.

You need **one** of these, and a paid plan with its maker:

| Engine | Needs | Install and sign in |
|---|---|---|
| Claude Code CLI (recommended) | a Claude subscription | install it from [claude.com/claude-code](https://claude.com/claude-code), then run `claude` once in a terminal and sign in |
| Codex CLI | a ChatGPT subscription | install it from [github.com/openai/codex](https://github.com/openai/codex), then run `codex` once in a terminal and sign in |

To check it is installed, open a terminal (on Windows: PowerShell) and type
`claude --version` or `codex --version`. If a version number is printed, Flow
will find it.

Flow uses the sign-in you did there. It never asks for a password or a key.

Which model does the reading: with Claude, Flow always asks for Opus; the
effort level is whatever your Claude Code is set to. With Codex, both the model
and the effort are whatever your Codex is set to.

### 3. Download Flow

- **Easiest:** on this page press the green **Code** button, choose
  **Download ZIP**, and unzip it anywhere, for example your Documents folder.
- **If you use git:** `git clone https://github.com/vijaykookkal/flow-itr.git`

### 4. Start it

- **Windows:** open the folder and double-click **`flow.cmd`**.
- **Mac or Linux:** open a terminal in the folder and run `./flow.sh`
  (the first time, run `chmod +x flow.sh` before it).

A black window opens and stays open, and your browser opens Flow at
`http://127.0.0.1:8787`. Leave the window open while you work; closing it stops
Flow. The window also tells you where your folders are:

```
  home      C:\Users\you\flow
  documents C:\Users\you\flow\DEFAULT\input-docs
  results   C:\Users\you\flow\DEFAULT\results
  engine claude   available
```

### 5. Add your documents

Copy the year's documents into the **documents** folder shown above. Sub-folders
are fine, and nothing needs renaming or sorting. Useful ones:

- Form 16 and Form 12BA from your employer
- AIS, TIS and Form 26AS, downloaded from the income-tax portal
- broker statements: capital gains, tax P&L, contract notes, dividend statements
- bank statements and interest certificates
- for a business or profession: the books, invoices, asset purchases
- for foreign shares: the broker's statements and any tax forms such as 1042-S
- proofs for deductions: insurance, NPS, donations, loan interest
- last year's filed return, if you want this year compared against one

Not sure where to get something? In Flow, **Documents › Get documents** has a
card for each usual source (the income-tax portal, your employer, Zerodha, ICICI
Direct, NSDL/CDSL, CAMS, Merrill, INDmoney and the main banks). Each card opens
the site and lists what to download for the year and how. You log in and
download yourself; Flow never sees a password. The cards come from
`config/document_sources.json`, so a new bank or broker can be added there.

The AIS, TIS and Form 26AS are password-protected. Enter your PAN and date of
birth under **Returns** (at the top of the left panel) and Flow opens them for
you, and NSDL/CDSL statements protected with your PAN as well.

---

## Using it

Flow is a set of places you can open in any order. A typical first run:

1. **Documents → "Sort documents again".** Flow looks at every file and decides
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

**Reading and computing are different.** Reading is done by the AI engine: it
opens your documents and copies out the facts. Computing is done by Flow itself,
with no AI: it applies the tax rules to those facts, instantly, and does so by
itself after every reading or correction. So the only thing you ever ask for is
a reading: once per schedule, and again when you add or replace a document.

Click any figure to see where it came from: the working, the printed line in
your document, and what the department holds against it. If a figure is wrong,
correct it there with a reason; your correction survives every re-read.
Press **Ctrl K** to search every line, amount and document.

The **Getting started** button at the top of the page opens the same steps as a
guide inside Flow, with a button on each step that takes you to the right place.

---

## Where your files are, and your privacy

**Nothing personal is stored with the program.** Everything of yours lives in
one folder, called the Flow home, which by default is a folder named `flow`
inside your user folder:

```
flow/
  profiles.json            your returns and their settings
  fx_rates.json            exchange rates looked up for foreign income
  DEFAULT/
    input-docs/            your documents go here
    results/               everything Flow produces, and results.xlsx
  .state/                  working files; safe to delete
```

- **Flow itself sends nothing over the internet.** It runs only on your
  computer and cannot be reached from another one.
- **The reading engine does.** To read a document, Claude Code or Codex sends
  its contents to its maker (Anthropic or OpenAI), under the account you signed
  in with. That is the only place your documents go.
- **Back it up** by copying the `flow` folder. To move to a new computer, copy
  that folder across and install Flow there.
- The `results` folder holds your income, PAN and bank details in a form that is
  easy to read. Treat it like the documents themselves.

### More than one return

A **return** is one person and one year, with its settings and folders. Add one under
**Returns** (at the top of the left panel) for a spouse, a parent, or
another year. Each gets its own `input-docs` and `results` folders. Two returns
can share one documents folder, for example to compare the old and new regimes.

### Keeping your files somewhere else

- **A different folder for one return:** type a full path, such as
  `D:\Tax\2025-26\papers`, as its documents or results folder. A path that is
  not a full path is taken from the Flow home.
- **Google Drive:** install Google Drive for desktop, then type a Drive path
  such as `G:/My Drive/Flow/DEFAULT/input-docs`, or press "Put on Google Drive"
  on the return when Flow finds your Drive. Your documents are then stored in
  your Google account. Let Drive finish syncing before opening the same return
  on another computer.
- **Moving the whole home:** set the `FLOW_HOME` environment variable, or put a
  file called `flow.local.json` next to `flow.cmd` containing
  `{"home": "D:/somewhere"}`, and restart.

### Excel

Press **Export to Excel** on the Hand-off page and Flow writes `results.xlsx`
into the return's results folder: a summary, one sheet per schedule, the
capital gains ledger, the reconciliation, the comparison with a filed return,
and the list of documents. The PAN and account numbers are left out, so it is
safe to send to your accountant. Export again after figures change; or, under
Returns, set "Export results to Excel" to "After every
computation" and Flow keeps the workbook up to date by itself.

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
| The window says `engine … NOT FOUND` | Install an engine and sign in (step 2), then start Flow again. |
| "Port 8787 is already in use" | Flow is already running in another window. Use that one, or close it first. |
| The page says it cannot reach the local agent | The black window was closed. Start Flow again. |
| A schedule shows nothing after reading | Open **Documents** and check the file was sorted to that schedule; press "Sort documents again" after adding files. |
| The AIS or TIS cannot be opened | Enter the PAN and date of birth under **Returns**. |
| "The Excel workbook is out of date" | The workbook is open in Excel. Close it and press Export to Excel. |

---

## For developers

Design and rationale: [docs/DESIGN.md](docs/DESIGN.md). The program is the
Python standard library and plain HTML, CSS and JavaScript: nothing to install,
no build step.

```
python -m server                # what flow.cmd and flow.sh run
python -m server --no-browser
```

The page binds to loopback only and authenticates with a token minted on first
start. It loads nothing from the network: the typefaces are in `web/fonts/`.

### Layout

```
config/tabs.json     the tabs and what each reads
schemas/  prompts/   the contract with the engine, and its instructions
engine/              deterministic tax computation
server/              local agent: HTTP API, engine drivers, Excel export
web/                 the page: app.js (schedules), charts.js (graphics),
                     pages.js (areas), shell.js (frame)
tools/               checks used while developing
fixtures/            invented documents for tests
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
default", it uses `default_engine` from `config/tabs.json`, or whichever engine is
installed if that one is not.

| Engine | Billing | Document reading | Reads confined to the tab's folders |
|---|---|---|---|
| `claude` | Claude subscription | Native, no shell | **Yes** — `--add-dir` is the whole world |
| `codex` | ChatGPT subscription | Runs shell commands (`pdftotext`, Python) | **No** — `-s read-only` sandboxes writes, not reads |
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
python tools/check_js.py       # the faults that blank a page without an error
python tools/check_page.py     # opens every place in headless Edge or Chrome
python tools/probe_page.py out.png salary "click:.money@0"   # click, then screenshot
python tools/restart_server.py # needed after changing server/ or engine/
```

The two browser tools and the restart tool are written for Windows with Edge or Chrome.

---

## Disclaimer

Flow is a personal tool shared as-is. It is **not tax advice**, not a filing
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

