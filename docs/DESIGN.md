# ITR-3 Filing Assistant — System Design

**Status:** design · **Target:** AY 2026-27 (FY 2025-26) · **Mode:** local-first, single user

---

## 1. What this system is

A local web application that turns a folder of tax documents into a reviewed,
schedule-by-schedule ITR-3 dataset.

It is deliberately **not** a filing bot. It does extraction, arithmetic and
record-keeping; you make the judgement calls. The design goal that outranks
convenience is this: **three years from now, when a notice arrives asking why
line X of Schedule CG says what it says, you can answer in under a minute.**
Every number traces to a file; every change to a number is in git.

## 2. Decisions at a glance

| Area | Decision | Why |
|---|---|---|
| Source repository | A profile's documents folder: a plain local folder outside the project, `<home>/<profile>/documents` by convention (§15) | Drive adds OAuth and a network hop for no benefit. A Drive synced by Drive for desktop is an ordinary folder, so using one is a path, not a feature |
| AI engine | Pluggable, chosen per return: Claude Code headless (`claude -p`), Codex, or an open model run locally through Ollama (§16) | Use a subscription the person already has, or keep every document on the machine with a local model. Whichever reads, the server validates and stores the answer the same way |
| AI write access | **None.** Claude's tools are restricted to `Read`, `Glob`, `Grep`; a local model has no tools at all and sees only the text it is sent | The model proposes JSON; the *server* validates and writes it. The model can never touch your files |
| Persistence | JSON per schedule in the profile's results folder, outside the project (§15). The repository holds the program only | The extracted data is the asset, and it is one person's; a repository other people clone must not contain it |
| Web UI | Static HTML/CSS/JS, no framework, no build step, served by the local agent | A tax form is a form. This must still run in 2031 without an `npm install` |
| Server | Python 3.10+ standard library only | Clone and run: nothing to install, no toolchain to rot |
| Money | Integer rupees everywhere. No floats, ever | Floats and tax arithmetic do not mix, and ITR schedules are rupee-rounded anyway |
| Git role | The repository versions the program. A results folder may be made a private repository of its own, where every AI run is a reviewable commit and a `filed/AY20xx-yy` tag marks what was submitted (§10) | The two have different audiences: the program is shared, the return is not |
| GitHub Actions | Deferred. Layout is CI-ready (§10) | Source control now, automation when it earns its keep |

## 3. Repository layout

```
<home>/                              yours, outside the repository (§15)
├── profiles.json                    profiles, their settings and folders
├── fx_rates.json                    SBI TT buying rates looked up or entered
├── <profile>/documents/…           raw documents
├── <profile>/results/
│   ├── extracted/<schedule>.json    AI output. Machine-owned, never hand-edited
│   ├── overrides/<schedule>.json    your corrections, with reasons. Human-owned
│   ├── resolved/<schedule>.json     extracted + overrides merged. What you file from
│   ├── reconciliation/              each schedule against the department's records
│   ├── review/                      what you settled, with reasons; what you have entered
│   ├── _runs/<run_id>.json          run manifest: prompt, model, inputs, hashes
│   └── results.xlsx               the return as a workbook (server/export.py)
└── .state/                          token, log, document conversions. Disposable

income-tax-automation/               the program, and nothing personal
├── config/tabs.json                 the tabs and what each reads
├── schemas/<schedule>.schema.json   JSON Schema — the contract between AI and UI
├── prompts/<schedule>.md            versioned extraction prompt, one per schedule
├── engine/                          deterministic tax computation (derived tabs)
├── server/                          local agent: HTTP API + claude subprocess driver
├── web/                             the page: index.html, styles.css, app.js (schedules),
│                                    pages.js (areas), shell.js (frame), fonts/
└── docs/DESIGN.md                   this file
```

## 4. The three-layer data model

This is the load-bearing idea, and it answers the question the brief does not:
*what happens to my corrections when I re-run the extraction?*

```
  extracted/salary.json     ← written only by an AI run
          +
  overrides/salary.json     ← written only by you, through the UI
          ↓  merge
  resolved/salary.json      ← what the UI renders and the engine consumes
```

An override is addressed by JSON Pointer and carries a reason:

```json
{
  "schedule": "salary",
  "overrides": [
    {
      "pointer": "/employers/0/perquisites/value",
      "value": 184500,
      "was": 0,
      "reason": "Form 16 Part B omits the ESPP discount; added from the broker statement dated 2025-11-30 per s.17(2)(vi)",
      "by": "you",
      "at": "2026-07-14T10:22:11+05:30"
    }
  ]
}
```

Consequences worth having:

- Re-running extraction is **safe and cheap** — it only rewrites `extracted/`.
- `git log overrides/` becomes a standing list of every place you disagreed with
  the machine, and why. That is the most useful artefact in the repo.
- If a re-run makes an override redundant (the AI now agrees), the merge marks it
  `stale` in the UI rather than deleting it.
- A field present only in `overrides/` with no `extracted/` counterpart is marked
  `manual` — expected on the General tab, a red flag on Schedule CG.

## 5. The JSON contract

Every schedule file shares one envelope; only `data` differs.

```json
{
  "schema_version": "1.0.0",
  "ay": "2026-27",
  "schedule": "salary",
  "run_id": "2026-07-14T10-02-33Z-salary-a91c",
  "engine": { "model": "claude-opus-5", "prompt_version": "salary@3" },
  "input_fingerprint": "sha256:9f2c...",
  "sources": [
    { "path": "01_salary/Form16_Acme_AY2026-27.pdf", "sha256": "e3b0...", "pages": 4 }
  ],
  "status": "ok",
  "data": { "...schedule-specific...": null },
  "unmapped": [
    {
      "source": "Form16_Acme_AY2026-27.pdf#p3",
      "text": "Relief u/s 89 - Rs. 42,000",
      "why": "No matching field in Schedule S; belongs in Part B-TTI"
    }
  ],
  "questions": [
    "Two Form 16s cover overlapping months (Apr-Jun 2025). Confirm whether the Acme one is a superseded draft."
  ]
}
```

Three rules make this trustworthy:

**1. Every monetary leaf cites its source** — not just the file, the spot in it:

```json
"gross_salary": {
  "amount": 4820000,
  "cite": "Form16_Acme.pdf#p2",
  "basis": "Part B, item 1(d)"
}
```

**2. Nothing is silently dropped.** Anything the model read but could not place
goes into `unmapped[]`. An empty `unmapped[]` on a messy broker statement is
itself a smell worth clicking into.

**3. Uncertainty is a first-class output.** The model writes `questions[]` and
sets `status: "needs_review"` instead of guessing. The UI will not let a tab go
green until every question is answered into an override.

`schemas/<schedule>.schema.json` enforces the envelope and the schedule shape.
The server validates *before* writing. On failure it feeds the validator errors
back into the same Claude session (`--resume`) for up to two repair attempts,
then gives up and parks the raw output under `_runs/` for you to inspect.

## 6. Tabs: three kinds, not one

The brief gives every tab an "ask the AI" button. That is right for most tabs and
wrong for two categories, because asking a language model to compute
carry-forward set-off is strictly worse than computing it:

- **Extract** — AI reads the folder, emits JSON. Button: *Extract from documents*.
- **Derive** — `engine/` computes it from other tabs. Button: *Recompute*. No AI.
- **Declare** — you type it; there is no document to read. No button. (No tab
  is of this kind now: General was, until it turned out that the documents do
  state the identity and the bank accounts. It is read like any other, and the
  filing choices in it, which no document states, come back as questions.)

| # | Tab | ITR-3 schedules | Kind | Source folder |
|---|---|---|---|---|
| 1 | General | Part A-GEN, bank accounts, 115BAC regime option | Extract | `00_general` |
| 2 | Salary | Schedule S | Extract | `01_salary` |
| 3 | House Property | Schedule HP | Extract | `02_house_property` |
| 4 | Books | Part A-BS, Part A-P&L, Part A-OI, Part A-QD | Extract | `03_business/books` |
| 5 | Business Computation | Schedule BP, ICDS, ESR | Derive + Declare | `03_business` |
| 6 | Depreciation | DPM, DOA, DEP, DCG | Derive | `03_business/assets` |
| 7 | Capital Gains | Schedule CG | Extract | `04_capital_gains` |
| 8 | Schedule 112A | Schedule 112A | Derive | none: built from the Capital Gains ledger |
| 9 | VDA | Schedule VDA | Extract | `04_capital_gains/vda` |
| 10 | Other Sources | Schedule OS | Extract | `05_other_sources` |
| 11 | Deductions | Schedule VI-A, 80G, 80GGA, 80GGC, 80D | Extract | `06_deductions` |
| 12 | Taxes Paid | TDS1, TDS2, TDS3, TCS, IT | Extract | `07_taxes_paid` |
| 13 | Set-off & Carry Forward | CYLA, BFLA, CFL, UD | Derive | prior-year `data/` |
| 14 | Foreign & Special | FSI, TR, FA, SI, EI, PTI, SPI, IF, 5A | Extract + Derive | `09_foreign_assets` |
| 15 | Assets & Liabilities | Schedule AL | Extract | `08_assets_liabilities` |
| 16 | Summary | Part B-TI, Part B-TTI, AMT, AMTC, 234A/B/C | Derive | — |

### A tab owns source specs, not a folder

The table above names one folder per tab for readability, but a tab actually
owns a **list of specs** in `config/tabs.json`, each either a directory or a
glob, resolved against the active profile's documents folder. Long export paths are named once
under `roots` and referenced as `drive:Some/Folder/*.pdf`.

This exists because real document folders are not organised by ITR schedule. A
drive export puts capital gains, dividends and bank statements in one folder,
and those belong to three different schedules. Globs let each tab take exactly
its own files without anyone reorganising their documents — which also keeps
the `--add-dir` scoping guarantee tight, since a tab that points at a whole
mixed folder can see everything in it.

Two consequences fall out:

- **Documents are deduplicated by content hash.** People copy a Form 16 into a
  curated folder and leave it in the export too. Without dedup the model sees
  the same employer twice and has every reason to report two.
- **Archives are reported, not skipped.** Nothing can read inside a `.zip`, and
  "no business expenses found" must never be the way you learn that.

### Formats the engine cannot read are converted server-side

The engine has no shell, so it cannot open a spreadsheet — and broker tax P&L
reports, bank statements and consolidated foreign-income reports are almost
always `.xlsx`. Rather than hand the model a shell and lose the read-only
guarantee, `server/convert.py` turns `.xlsx` into one CSV per sheet and `.docx`
into text, using only the standard library (both are zip archives of XML).

Conversions are cached by the original's content hash, written to
`<home>/.state/cache/`, and granted to the engine alongside the originals. The run
fingerprint stays keyed to the **originals**, so a cold conversion cache never
looks like changed input. Excel date serials become ISO dates, because the
capital-gains rate split turns on transaction dates. The prompt tells the model
to cite the original document, never the derived CSV.

Tabs 9, 15 and parts of 14 are conditional — VDA only if you traded crypto, AL
only above ₹50 lakh total income, FA only with foreign assets. The General tab's
answers switch them on. A switched-off tab is **greyed, not hidden**, so you can
see that you considered it and why it does not apply.

Each tab renders in ITR-3's own row-and-column order using the department's item
labels (`1(a)`, `2(iii)`, …), so cross-checking against the official utility is a
visual scan rather than an archaeological dig.

## 7. What happens when you press the button

```
 [Extract from documents]  (Capital Gains tab)
        │
        │  POST /api/run  {ay: "2026-27", schedule: "capital_gains"}
        ▼
 ┌─ local agent (127.0.0.1:8787) ──────────────────────────────────────┐
 │ 1. Scan the documents routed to capital gains → file list + sha256  │
 │ 2. input_fingerprint = sha256(file hashes + prompt_version)         │
 │    unchanged since last run and not --force? → return cached, done  │
 │ 3. Compose prompt = prompts/capital_gains.md                        │
 │                   + schemas/capital_gains.schema.json               │
 │                   + the file manifest                               │
 │ 4. spawn: claude -p --output-format stream-json --verbose           │
 │           --allowedTools Read,Glob,Grep                             │
 │           --add-dir <that folder only>                              │
 │ 5. relay stream to the browser over SSE (live progress in the tab)  │
 │ 6. parse final JSON → validate against schema                       │
 │       invalid → --resume with the validator errors (max 2 retries)  │
 │ 7. write extracted/capital_gains.json + _runs/<run_id>.json         │
 │ 8. re-merge overrides → resolved/capital_gains.json                 │
 │ 9. invalidate derived tabs that depend on it (13, 16)               │
 └─────────────────────────────────────────────────────────────────────┘
        │
        ▼
  tab re-renders: new values, diff vs previous run, questions[] as a
  review queue, unmapped[] in a drawer
```

Two properties fall out of this and are worth protecting:

- **Idempotent.** Same documents plus same prompt version equals no AI call. You
  can mash the button without burning subscription quota.
- **Scoped.** `--add-dir` points at one folder. The Salary extraction physically
  cannot read your broker statements, so it cannot hallucinate from them.

## 8. Local agent API

Binds `127.0.0.1` only. A random token is minted at startup and injected into
`index.html`; every mutating request must carry it, and the `Origin` header is
checked. That is enough to stop a random web page in another tab from driving
your tax return.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/state?ay=` | All resolved schedules, tab statuses, last-run metadata |
| `GET` | `/api/sources?ay=&schedule=` | File manifest for a tab — shows what *will* be read |
| `POST` | `/api/run` | Start an extraction. Returns `run_id` |
| `GET` | `/api/run/{id}/events` | SSE stream of live progress |
| `POST` | `/api/override` | Record a correction (pointer, value, reason) |
| `POST` | `/api/compute?ay=` | Run the deterministic engine over the derived tabs |
| `GET` | `/api/diff?schedule=&run=` | This run versus the previous one |
| `POST` | `/api/commit` | Stage and commit the AY's `data/` with a run-linked message |
| `GET` | `/api/export?ay=` | ITR-3 JSON in the department's utility schema |

## 9. The deterministic engine

Everything the tax code defines as arithmetic lives in `engine/` as plain Python
with unit tests, never in a prompt:

- Head-wise aggregation, and the Chapter VI-A ceilings (80C, 80D age slabs, 80G
  qualifying-limit maths, the 10% / 20% of adjusted GTI caps).
- The set-off chain in its statutory order: CYLA, then BFLA, then CFL, with
  per-head restrictions (house-property loss capped at ₹2 lakh against other
  heads, speculative losses only against speculative income, the 8-year and
  4-year carry-forward clocks).
- Capital-gains rate buckets by transaction date. FY 2025-26 sits entirely after
  the 23-Jul-2024 changeover, so 111A STCG is at 20%, 112A LTCG at 12.5% with the
  ₹1.25 lakh exemption, and long-term property gains at 12.5% without indexation
  — with the pre-changeover branches kept in code for prior-year re-filings.
- Old regime versus 115BAC(1A), computed both ways and shown side by side, since
  the new regime is now the default and the choice is a real decision for ITR-3.
- Surcharge with marginal relief, cess, and 234A/234B/234C interest.

The engine is also the **audit of the AI**: where a schedule is both extracted and
computable (Part B-TI totals, Schedule BP against the P&L, TDS totals against
26AS), it recomputes and flags any disagreement instead of trusting the model.

Rates, slabs and limits live in `engine/rates/AY2026-27.py` — one file per year,
never hardcoded inline, because next year you change one file.

## 10. Git, and the GitOps story

This section is about a **results folder kept as its own private repository**,
which is optional. The program's repository holds no return (§15).

Working now, without CI:

- The results folder is the desired state; the UI is a view over it. Nothing is
  authoritative unless it is committed.
- Each extraction run commits on its own branch — `run/capital_gains/20260714-1` —
  with the run manifest in the commit message. You read the diff, then merge. The
  diff of a re-run against last week's is the review, and the review is the point.
- `overrides/` commits separately from `extracted/` so the two histories stay
  legible.
- When you actually submit, tag `filed/AY2026-27` and attach the exported utility
  JSON and the acknowledgement. That tag is what you reconstruct from if the
  department ever asks.
- In the program's repository, a `pre-commit` hook that greps staged files for
  PAN, Aadhaar and full account-number patterns is the right guard: nothing of
  that kind has any business there.

**A results repository must be private.** It holds your income, PAN and bank
details in clean machine-readable form — considerably easier to harvest than the
PDFs it came from.

When Actions are worth adding, these drop in unchanged, and none of them need
your documents or an API key:

1. Validate every results JSON against its schema on push.
2. Re-run `engine/` and fail the PR if any total disagrees with the committed one.
3. Build the redacted GitHub Pages viewer (§11).

## 11. Designed-for, not built-now

- **Google Drive through its API.** Built now is the simple half: a Drive synced
  by Drive for desktop is a folder, and a profile is pointed at it (§15). Reading
  a Drive without the desktop app would be a second resolver in
  `server/sources.py` that syncs into a local cache first; nothing above it
  changes, and it is not built because it brings OAuth and credentials into a
  program that otherwise has neither.
- **GitHub Pages viewer.** The same `web/` assets, built against a **redacted**
  snapshot: PAN masked, account numbers truncated, per-field citations stripped.
  Gated behind an explicit `make publish` so it can never happen by accident.
- **Multi-year.** Every path is keyed by AY from day one, because carry-forward
  losses, unabsorbed depreciation and the depreciation block WDVs genuinely need
  last year's numbers as this year's input. Last year's results are a read-only
  input to tab 13, not an archive.

## 12. Known risks

| Risk | Mitigation |
|---|---|
| AI misreads a number and it looks plausible | Per-field citations; the engine recomputes what it can; `git diff` between runs surfaces drift |
| The model quietly omits a transaction | `unmapped[]` plus a count reconciliation — number of broker rows in versus rows out |
| Schema drift when the department releases the AY 2026-27 ITR-3 utility | `schema_version` on every file, plus a mapping layer between our shape and the utility's shape, isolated in `engine/export/` |
| Prompt changes silently alter past results | `prompt_version` is recorded in every output and feeds the fingerprint |
| Large PDFs blow the context window | Per-file extraction with a merge step for bank statements and broker reports; the run manifest records the split |
| Tax rules in this document are my reading, not a filing | The engine has tests keyed to sections; verify against the released utility before filing. **This system produces a draft for your review, never a filing.** |

## 13. Build order

1. **Skeleton + contract** — schemas and the envelope for two tabs (Salary, Taxes
   Paid), the three-layer merge, and git wiring. Nothing else matters if this is wrong.
2. **Local agent + one real extraction** — prove `claude -p` against a real Form 16
   end to end, including the validation-repair loop.
3. **The UI shell** — tab chrome, run button, SSE progress, review queue, override editor.
4. **Remaining extract tabs**, hardest first: Capital Gains and 112A scrip-wise
   will take longer than the other twelve combined.
5. **The engine** — set-off chain, both regimes, Part B-TI/TTI.
6. **Export** to the department's utility JSON, and the `filed/` tagging ritual.

## 14. The page

The page is a workspace of places, not a sequence of steps. A return is not
built in a straight line -- a document arrives late, a schedule is read again, a
decision moves a figure -- so nothing is numbered, nothing is locked until
something else is finished, and each place says what it needs as a status.

| Place | What it is for |
|---|---|
| Home | The page Flow opens on: what Flow is, the return in use, how it works, and the getting-started guide as a section |
| Returns | One return at a time: whose it is, the year, how the tax is worked out, the reading engine, its folders |
| Schedules | Every schedule as a card: what it is about, what it reads, where it stands, and its Read or Recompute button |
| Summary | What is owed, key ratios and graphics, the income and tax statements, what is waiting on a person, and how each schedule reconciles |
| Documents | Every file: what it was recognised as, which schedules it feeds, whether each has read it, the figures taken from it. A second tab, Get documents, opens each usual source's website and says what to download (`config/document_sources.json`) |
| A schedule | The form in the return's own numbering, with tabs for its ledger, reconciliation, documents, decisions and history |
| Review | Everything only a person can settle, from every schedule, each settled with a reason |
| Reconcile | Your documents against the department's record, and against a filed return if one is supplied |
| Hand-off | Each schedule as a sheet to copy into the utility, ticked off line by line |

Four things stay in view whatever is open: which return this is, search over
every line, amount and document (Ctrl K), whether the computation is current,
and a way back to Getting started.

**The Summary page draws the return as well as stating it** (`web/charts.js`): the
effective and marginal rates, income after tax, the share already paid, what
deductions kept out of tax and what the other regime would have cost; then the
income by head, the slab ladder (each band as wide as the income in it and as
tall as its rate), what the tax is made of, and payments against the liability.
Every graphic restates lines of Part B-TI and Part B-TTI that are printed as a
table beside it, each value is printed next to its mark, and the same details
appear on hover and on keyboard focus. One blue measures, a neutral takes away,
and the page's status colours mean agree or differ; the colours are checked for
contrast and colour-blind separation in both themes. The engine supplies the
slab ladder as data (`ladder` on the Schedule SI stage) so the page parses no
prose.

**Evidence beside every figure.** A figure opens a panel instead of an editor:
how it was reached, the printed line it came from (found in the same converted
text the engine read, `server/excerpt.py`), what the department holds against
it, and where it is carried. Correcting it is offered there, beside the
evidence.

**Reconciliation is shown wherever a figure is.** On the Summary page by schedule,
on each schedule under its heading, in a figure's evidence, and in Review as an
open decision when nothing accounts for a difference. A filed return is set
beside the computation and feeds none of it.

**Nothing a person decides is written by a run.** Corrections live in
`overrides/`, decisions and entered-marks in `review/` (`server/notes.py`). A
decision is identified by what the item says, so a re-run that words a question
differently brings it back as open: the safe direction to fail in. The log is
append-only; reopening adds an entry.

**Hand-off flags drift.** Each ticked line remembers what it said. If the figure
moves afterwards, the line is flagged with what it was when it was entered.

The scripts are plain files loaded in order (`app.js`, `pages.js`, `shell.js`)
into one scope. `tools/check_js.py` catches the faults that blank a page with no
error -- a broken string, a name declared in two files -- and
`tools/check_page.py` opens every place in a real browser and reports console
errors, failed layouts and blank pages.

## 15. Portability: the program here, the return elsewhere

The test is one sentence: **someone clones the repository, runs
`python -m server`, and is working on their own return, with nobody else's
anywhere on their disk.** Everything below follows from it.

**One folder holds everything personal: the Flow home.** `server/paths.py` is
the only module that knows where it is, and resolves it in this order:

1. the `FLOW_HOME` environment variable;
2. `flow.local.json` beside the program, `{"home": "..."}`, ignored by git;
3. a folder called `flow` in the user's home directory.

The default is under the user's own folder because that exists on every
operating system and needs no rights a normal account lacks. A fixed path such
as `C:\Users\flow` reads well but cannot be created without administrator
rights on Windows and means nothing elsewhere; anyone who wants it sets it with
(1) or (2).

**Profiles are externalised too.** The profile list holds a PAN and a date of
birth, so it cannot ship with the program, and it is not per-clone either: two
clones on one machine should see the same returns. It is `profiles.json` in the
home. First run writes one profile, DEFAULT, and makes its folders, which is
what makes "clone and go" true. What stays in the repository under `config/` is
configuration of the *program*: the tabs and what each reads.

**The convention.** A profile called X reads `<home>/X/documents` and writes
`<home>/X/results`. Folders inside the home are stored relative to it, so
the home moves between machines as one piece; a folder anywhere else is stored
as an absolute path. Two profiles may share a documents folder (one set of
papers, two regimes); no two may share a results folder.

**Cloud folders are folders.** Pointing a profile at a synced Drive, OneDrive or
Dropbox folder needs no code, because nothing below `paths.py` cares where a
folder is, and the engine is granted folders by absolute path. The page offers
"Put on Google Drive" when it finds a Drive for desktop mount
(`paths.cloud_roots()`), and otherwise says what path to type. Nothing here
calls a cloud API or holds a credential. The costs are the user's to accept and
are stated where the choice is made: the documents are then held by the cloud
provider, and two machines must not work on one profile before syncing settles.

**Working files are disposable and local.** The session token, the server log,
the conversion cache and downloaded rate archives are in `<home>/.state/`. They
are rebuilt as needed and should not be synced: a profile on Drive keeps its
`.state` on the machine, because the home stays local unless `FLOW_HOME` itself
is put on Drive.

**Exchange rates.** Rates looked up or typed in are written to
`<home>/fx_rates.json`: which dates were needed says when someone bought and
sold. `config/fx_rates.json`, if a repository chooses to ship one, is read as a
seed and never written.

**The workbook.** `server/xlsx.py` writes Excel files with the standard library
(an .xlsx is a zip of XML), so export adds nothing to install.
`server/export.py` lays out what is already computed; it computes nothing. It
is always `results.xlsx` in the results folder, written when asked for (the
default) or after every computation when the profile asks for that, and a workbook
locked by Excel is reported on the Hand-off page and never fails a computation.

**What keeps it true.** `.gitignore` lists the places personal files used to
live, and `tools/check_private.py`, installed as a pre-commit hook, refuses any
commit that contains a document file, a non-specimen PAN, or any return's name,
PAN, date of birth, e-mail, mobile or account numbers, read from the Flow home at
commit time rather than kept in the repository. Fixtures use invented names and
specimen PANs. Prompts and schemas describe kinds of document, never a
particular person's.

## 16. Reading engines, including a local model

**Engines and models.** An engine is how Flow reaches a reader: the Claude Code
command-line tool, the Codex command-line tool, or Ollama's API on this
computer. Every engine offers models, and the model is the reader: Claude
Code's Opus, Sonnet and Haiku; Codex's default and any model names the person
adds; each model installed in Ollama. Each engine module declares
`model_list()` and `default_model()`, and a return names what it reads with as
`engine:model` (`claude:opus`, `ollama:gpt-oss:20b`); a bare `claude` means that
engine's default model. Settings sit at the level they belong to: a time limit
and an address per engine, a window and a reasoning level per Ollama model.
Every list of readers in the page groups models under their engine.

An engine is anything that turns a prompt and a set of documents into a JSON
answer (`server/engines/`). Everything that makes the answer trustworthy --
schema validation, the repair loop, provenance, the three-layer merge -- is in
`runner.py` and is the same whichever engine read. Each return chooses its
engine under Returns; the engine and model are part of every run's fingerprint
and are recorded on every output.

| Engine | How it reads | What leaves the computer |
|---|---|---|
| Claude Code | An agent: opens the documents itself, read-only tools, confined to the schedule's folders | The documents it reads, to Anthropic, under the user's account |
| Codex | An agent with a sandboxed shell | The documents it reads, to OpenAI, under the user's account |
| Ollama (`ollama:<model>`) | No tools: Flow sends the text it already makes of each document (`server/convert.py`) | Nothing |

**The local engine** (`server/engines/ollama_local.py`) talks to Ollama's HTTP
API on the same machine. Three decisions shape it:

* **Send text, never cut it short.** A model behind Ollama cannot open a file,
  so each document's text is sent under its original name, with the runs of
  spaces a PDF uses for layout squeezed to two. Ollama gives a model only the
  window it is asked for (the Window setting on the Reading engines page, 64k by
  default). If a schedule's documents do not fit, the run is refused with their
  size: a dropped page is a dropped transaction, and a silent one. Sorting is
  the exception, since it needs only the start of each document.
* **Table plans stay table plans.** For a tabular schedule the model sees the
  heads of the spreadsheets, as any engine does, and code reads the rows; only
  the PDFs that must be read whole are sent in full.
* **The schema is enforced by the server when it can be.** Ollama constrains
  the reply to the schedule's JSON schema; if a schema is beyond it, plain JSON
  mode is used and the runner's validation and repair do the rest. A repair
  continues the same conversation.

Each installed model is offered as its own choice, so a return names the model
it reads with. The default prefers light mixture-of-experts models
(`gpt-oss:20b`, `qwen3:30b-a3b`), which run on a laptop processor with no
graphics card because only a few billion parameters work per token.

**Limits, measured on a real year's documents.** Deductions, Taxes paid and
General information fit a 64k window; Salary, Capital gains and Foreign income
need about 128k; a year of bank statements for Other sources or Books is around
300k tokens, beyond a laptop model. Scanned PDFs without text cannot be read,
and the exchange-rate lookup, which reads a large rate archive, needs Claude or
Codex. Reading a large schedule document by document and merging the answers
would lift the size limit. It is not built, because a generic merge of partial
schedules is exactly where silent double-counting would creep in.

**Where engine settings live.** `config/tabs.json` holds the program's
defaults: the default engine, the time limits, Ollama's address, window and
reasoning level. What a person changes on the Reading engines page is kept in
`settings.json` in the Flow home and laid over those defaults
(`server/settings.py`). A `git pull` then never overwrites a choice, and a push
never publishes one; deleting the file returns everything to the defaults.
