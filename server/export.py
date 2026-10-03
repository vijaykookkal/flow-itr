"""The return as an Excel workbook.

The page is where the work is done; a workbook is what gets kept, sent to a
chartered accountant, or opened next year to see what was filed. This writes
one from the figures already computed -- it computes nothing itself, for the
same reason the hand-off sheets do not: there is one place a number comes
from.

What goes in:

  * **Summary** -- the return in a dozen lines, the checks, and what is not
    covered.
  * **One sheet per schedule**, the same sheets the Hand-off page shows, in the
    form's own line numbers.
  * **Capital gains ledger** -- every sale, with its cost, charges and gain.
  * **Reconciliation** -- each comparison with the department's records.
  * **Filed return** -- line by line against a return already filed, when one
    was supplied.
  * **Decisions** and **Documents** -- what was settled and why, and which
    papers were read for which schedule.

What stays out: the PAN, account numbers and the filed return's acknowledgement
number. A workbook gets attached to emails; the figures are what it is for.

The workbook is always `results.xlsx` in the profile's results folder. It is
written when asked for, or after every computation if the profile says so. A
workbook that is open in Excel cannot be rewritten on Windows; that is
reported, and never stops a computation.
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from pathlib import Path

from . import classify, notes, paths, profiles
from . import reconcile as reconciler
from .xlsx import Workbook

LOCK = threading.Lock()
# The last attempt per workbook, so the page can say "could not be written,
# it is open in Excel" long after the request that tried has gone.
LAST: dict[str, dict] = {}

STATUS_WORDS = {
    "matches": "Agrees", "rounding": "Agrees, to rounding", "explained": "Accounted for",
    "not_comparable": "Not comparable", "differs": "Differs", "unexplained": "Not accounted for",
    "missing": "Not in this return",
}
STATE_WORDS = {"agrees": "Agrees", "differs": "Differs", "not_in_filed": "Not in the filed return",
               "not_in_computed": "Not computed here"}


WORKBOOK = "results.xlsx"


def workbook_path(profile: dict | None = None, ay: str | None = None) -> Path:
    """Where the workbook goes. By convention, not by setting: results.xlsx in
    the profile's results folder, so it is always found in the same place."""
    profile = profile or profiles.active() or {}
    return paths.data_root(ay or profile.get("ay") or profiles.active_ay()) / WORKBOOK


def status(ay: str) -> dict:
    """What the page shows: where the workbook is, and how the last write went."""
    profile = profiles.active() or {}
    path = workbook_path(profile, ay)
    out = {
        "path": str(path),
        "mode": (profile.get("settings") or {}).get("excel_export") or "manual",
        "exists": path.is_file(),
        "written_at": None,
    }
    if out["exists"]:
        out["written_at"] = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(timespec="seconds")
    last = LAST.get(str(path))
    if last and not last.get("ok"):
        out["error"] = last["error"]
    return out


# --------------------------------------------------------------------------
# reading what is already computed
# --------------------------------------------------------------------------
def _collect(ay: str) -> dict:
    docs = {}
    recon = {}
    for tab in paths.load_tabs()["tabs"]:
        docs[tab["id"]] = paths.read_json(paths.resolved(ay, tab["id"]))
        recon[tab["id"]] = paths.read_json(reconciler.stored(ay, tab["id"]))
    docs["summary"] = paths.read_json(paths.data_root(ay) / "resolved" / "summary.json")
    titles = {tab["id"]: tab.get("title") or tab["id"] for tab in paths.load_tabs()["tabs"]}
    return {"docs": docs, "recon": recon, "titles": titles}


def _short(title: str) -> str:
    """'Schedule CG: capital gains' -> 'Schedule CG', for a sheet's name."""
    return title.split(":")[0].strip()


# --------------------------------------------------------------------------
# sheets
# --------------------------------------------------------------------------
def _summary_sheet(book: Workbook, profile: dict, ay: str, summary: dict | None, sheets: list[dict],
                   listing: list[tuple[str, str]]) -> None:
    sheet = book.sheet("Summary", widths=[46, 20, 70])
    sheet.row([f"{profile.get('name') or 'Return'}: income-tax return, ITR-3"], style="title")
    sheet.row([f"Financial year {profile.get('fy', '')}, assessment year {ay}. Resident and ordinarily resident."],
              style="muted")
    sheet.blank()
    if not summary:
        sheet.row(["Nothing has been computed yet. Read the documents on the page, then export again."])
        return

    regime = summary.get("recommended_regime") or ""
    chosen = (summary.get("regimes") or {}).get(regime) or {}
    balance = summary.get("balance") or {}
    by_id = {s["id"]: s for s in sheets}

    def line(sheet_id: str, starts: str):
        for row in (by_id.get(sheet_id) or {}).get("rows") or []:
            if row["label"].lower().startswith(starts.lower()) and row["values"]:
                return row["values"][0]
        return None

    sheet.row(["The return", "Amount"], styles=["head", "headr"])
    figures = [
        ("Regime computed", "New, section 115BAC(1A)" if regime == "new" else "Old" if regime == "old" else regime),
        ("Gross total income", line("part_b_ti", "Gross Total income")),
        ("Deductions under Chapter VI-A", (chosen.get("chapter_via") or {}).get("total_allowed")),
        ("Total income", line("part_b_ti", "Total income")),
        # From Part B-TTI as the form adds it up, not from a figure part-way
        # through the computation: these are the lines a reader will look for.
        ("Gross tax liability, with surcharge and cess", line("part_b_tti", "Gross tax liability")),
        ("Net tax liability, after reliefs", line("part_b_tti", "Net tax liability")),
        ("Aggregate liability, with interest and fee", line("part_b_tti", "Aggregate liability")),
        ("Taxes already paid", line("part_b_tti", "Total Taxes Paid") or summary.get("taxes_already_paid")),
    ]
    for label, value in figures:
        if value is not None:
            sheet.row([label, value])
    if balance.get("refund"):
        sheet.row(["Refund due", balance["refund"]], style="bold")
    else:
        sheet.row(["Balance payable", balance.get("payable") or 0], style="bold")
    if summary.get("saving_versus_other"):
        other = "old" if regime == "new" else "new"
        sheet.row([f"Tax saved against the {other} regime", summary["saving_versus_other"]])
    sheet.blank()

    if summary.get("checks"):
        sheet.row(["Checks", "Result", "Detail"], style="head")
        for check in summary["checks"]:
            sheet.row([check.get("check"), "Holds" if check.get("ok") else "Does not hold", check.get("detail")])
        sheet.blank()
    notes_ = [summary.get("warning")] + list(summary.get("not_implemented") or [])
    notes_ = [n for n in notes_ if n]
    if notes_:
        sheet.row(["Not covered, or to check before filing"], style="head")
        for n in notes_:
            sheet.row([n])
        sheet.blank()

    sheet.row(["In this workbook", "", "What it holds"], style="head")
    for name, what in listing:
        sheet.row([name, "", what])
    sheet.blank()
    computed = summary.get("computed_at") or ""
    sheet.row([f"Computed {computed}. Written {datetime.now(timezone.utc).isoformat(timespec='seconds')}. "
               f"Figures are the tool's computation from the documents supplied; check them against the "
               f"utility you file with."], style="muted")


def _schedule_sheet(book: Workbook, data: dict) -> str:
    columns = data.get("columns") or []
    widths = [9, 58] + [max(16, min(30, len(c["t"]) + 4)) for c in columns]
    sheet = book.sheet(_short(data["title"]), widths=widths, freeze=0)
    sheet.row([data["title"]], style="title")
    if data.get("note"):
        sheet.row(["", data["note"]], style="muted")
    sheet.blank()
    sheet.row(["Line", "As the form words it"] + [c["t"] for c in columns],
              styles=["head", "head"] + ["headr" if c.get("num") else "head" for c in columns])
    for row in data.get("rows") or []:
        kind = row.get("kind") or ""
        label = ("    " + row["label"]) if kind == "sub" else row["label"]
        sheet.row([row["item"], label] + list(row["values"]),
                  style="bold" if kind == "total" else None)
    return sheet.name


def _ledger_sheet(book: Workbook, cg: dict | None) -> str | None:
    rows = (cg or {}).get("rows") or []
    if not rows:
        return None
    sheet = book.sheet("Capital gains ledger", freeze=1,
                       widths=[5, 44, 16, 12, 12, 8, 9, 15, 15, 12, 15, 12, 10, 15, 34])
    sheet.row(["#", "Asset", "Class", "Acquired", "Transferred", "Term", "Section", "Sale value",
               "Cost as stated", "Charges on purchase", "Cost of acquisition", "Charges on sale",
               "STT, not deducted", "Gain", "Why this cost"],
              styles=["head"] * 7 + ["headr"] * 7 + ["head"])
    keys = ("proceeds", "cost_stated", "purchase_expenses", "cost", "expenses", "stt", "gain")
    for i, r in enumerate(rows, 1):
        sheet.row([i, r.get("description"), r.get("asset_class"), r.get("acquired_on"),
                   r.get("transferred_on"), r.get("term"), r.get("section")]
                  + [r.get(k) if r.get(k) is not None else (r.get("cost") if k == "cost_stated" else 0)
                     for k in keys]
                  + [r.get("cost_reason")],
                  styles=["text"] * 7 + [None] * 7 + ["sub"])
    sheet.row(["", "Total", "", "", "", "", ""]
              + [sum((r.get(k) if r.get(k) is not None else (r.get("cost") if k == "cost_stated" else 0)) or 0
                     for r in rows) for k in keys],
              style="bold")
    return sheet.name


def _recon_sheet(book: Workbook, recon: dict, titles: dict) -> str | None:
    present = {tab: doc for tab, doc in recon.items() if doc and (doc.get("groups") or doc.get("lines"))}
    if not present:
        return None
    sheet = book.sheet("Reconciliation", freeze=1, widths=[24, 44, 16, 16, 14, 16, 22, 70])
    sheet.row(["Schedule", "What is compared", "This return", "Their record", "Difference",
               "Not accounted for", "Result", "What accounts for it"],
              styles=["head", "head", "headr", "headr", "headr", "headr", "head", "head"])
    for tab, doc in present.items():
        for g in doc.get("groups") or []:
            accounted = "; ".join(f"{a.get('what')}: {a.get('amount'):,}" if isinstance(a.get("amount"), (int, float))
                                  else str(a.get("what")) for a in g.get("accounted_by") or [])
            sheet.row([titles.get(tab, tab), g.get("label"), g.get("ours"), g.get("reported"),
                       g.get("difference") or 0, g.get("unaccounted") or 0,
                       STATUS_WORDS.get(g.get("status"), g.get("status")), accounted],
                      styles=["text", "text", None, None, None, None, "text", "sub"])
    sheet.blank()
    sheet.row(["Schedule", "Reported line", "This return", "Reported", "Difference", "Not accounted for",
               "Result", "Reported by, and why it is compared this way"],
              styles=["head", "head", "headr", "headr", "headr", "headr", "head", "head"])
    for tab, doc in present.items():
        for ln in doc.get("lines") or []:
            reported = (ln.get("reported") or {}).get("amount")
            sheet.row([titles.get(tab, tab), ln.get("category") or ln.get("measure_label"), ln.get("ours"),
                       reported, ln.get("difference") or 0, ln.get("unaccounted") or 0,
                       STATUS_WORDS.get(ln.get("status"), ln.get("status")),
                       " ".join(x for x in (ln.get("source"), ln.get("why")) if x)],
                      styles=["text", "text", None, None, None, None, "text", "sub"])
        for u in doc.get("unreported") or []:
            sheet.row([titles.get(tab, tab), u.get("label"), u.get("amount"), None, None, None,
                       "In this return, in none of their records", ""],
                      styles=["text", "text", None, None, None, None, "text", "sub"])
    return sheet.name


def _filed_sheet(book: Workbook, comparison: dict | None) -> str | None:
    parts = (comparison or {}).get("parts") or {}
    if not any((p.get("rows") for p in parts.values())):
        return None
    sheet = book.sheet("Filed return", freeze=1, widths=[18, 9, 58, 16, 16, 14, 24])
    sheet.row(["Part", "Line", "As the form words it", "Computed here", "As filed", "Difference", "Result"],
              styles=["head", "head", "head", "headr", "headr", "headr", "head"])
    for name, part in parts.items():
        for r in part.get("rows") or []:
            sheet.row([name, r.get("item"), r.get("label"), r.get("computed"), r.get("filed"),
                       r.get("difference") if r.get("state") == "differs" else None,
                       STATE_WORDS.get(r.get("state"), r.get("state"))],
                      style="bold" if r.get("state") == "differs" else None,
                      styles=None)
    causes = (comparison.get("causes") or {})
    if causes.get("causes"):
        sheet.blank()
        sheet.row(["Why the two differ", "Line", "Cause", "Computed here", "As filed", "Effect on tax", "Detail"],
                  styles=["head", "head", "head", "headr", "headr", "headr", "head"])
        for c in causes["causes"]:
            sheet.row([c.get("part"), c.get("line"), c.get("label"), c.get("computed"), c.get("filed"),
                       c.get("effect"), c.get("detail") or c.get("note")],
                      styles=["text", "text", "text", None, None, None, "sub"])
        if causes.get("residual"):
            sheet.row(["", "", "Not traced to a cause", None, None, causes["residual"], ""], style="bold")
    return sheet.name


def _decisions_sheet(book: Workbook, decisions: dict, titles: dict) -> str | None:
    log = (decisions or {}).get("log") or []
    if not log:
        return None
    sheet = book.sheet("Decisions", freeze=1, widths=[22, 24, 70, 16, 26, 60])
    sheet.row(["When", "Schedule", "What was raised", "Amount", "Decided", "Reason"],
              styles=["head", "head", "head", "headr", "head", "head"])
    for e in log:
        decided = "Reopened" if e.get("action") == "reopen" else e.get("choice_label") or e.get("choice")
        amount = e.get("amount") if isinstance(e.get("amount"), (int, float)) else None
        sheet.row([e.get("at"), titles.get(e.get("tab"), e.get("tab")), e.get("text"), amount,
                   decided, e.get("reason")])
    return sheet.name


def _documents_sheet(book: Workbook, ay: str, titles: dict) -> str | None:
    documents = (classify.load_map(ay) or {}).get("documents") or []
    if not documents:
        return None
    sheet = book.sheet("Documents", freeze=1, widths=[70, 26, 34, 14, 80])
    sheet.row(["Document", "What it is", "Read for", "Confidence", "Why"], style="head")
    for d in sorted(documents, key=lambda d: d.get("path") or ""):
        sheet.row([d.get("path"), d.get("kind"),
                   ", ".join(titles.get(t, t) for t in d.get("tabs") or []) or "Set aside",
                   d.get("confidence"), d.get("why")],
                  styles=["text", "text", "text", "text", "sub"])
    return sheet.name


# --------------------------------------------------------------------------
# the workbook
# --------------------------------------------------------------------------
def build(ay: str) -> Workbook:
    from engine import handoff

    profile = profiles.active() or {}
    found = _collect(ay)
    docs, titles = found["docs"], found["titles"]
    summary = docs.get("summary")
    regime = ((summary or {}).get("regimes") or {}).get((summary or {}).get("recommended_regime")) or {}
    sheets = handoff.build(summary, docs) if summary else []

    # The summary lists the other sheets, so it is laid out last and put first.
    rest = Workbook()
    listing: list[tuple[str, str]] = []
    for data in sheets:
        if data.get("rows"):
            listing.append((_schedule_sheet(rest, data), data["title"]))
    extras = [
        (_ledger_sheet(rest, regime.get("capital_gains")),
         "Every sale: dates, sale value, cost, charges and the gain"),
        (_recon_sheet(rest, found["recon"], titles),
         "Each schedule against Form 26AS, the AIS and the TIS"),
        (_filed_sheet(rest, regime.get("filed_comparison")),
         "This computation against the return already filed, line by line"),
        (_decisions_sheet(rest, notes.load_decisions(ay), titles),
         "What was settled by hand, and the reason given"),
        (_documents_sheet(rest, ay, titles),
         "The papers supplied and the schedule each was read for"),
    ]
    listing += [(name, what) for name, what in extras if name]

    book = Workbook()
    _summary_sheet(book, profile, ay, summary, sheets, listing)
    book.sheets += rest.sheets
    return book


def write(ay: str) -> dict:
    """Write the workbook. Returns how it went; never raises for a workbook
    that is merely open somewhere, because that is the ordinary failure."""
    path = workbook_path(None, ay)
    with LOCK:
        try:
            book = build(ay)
            book.save(path)
        except PermissionError:
            LAST[str(path)] = {"ok": False, "error": (
                f"{path.name} could not be rewritten. It is probably open in Excel: close it and "
                f"export again.")}
        except OSError as exc:
            LAST[str(path)] = {"ok": False, "error": f"{path} could not be written: {exc.strerror or exc}"}
        else:
            LAST[str(path)] = {"ok": True, "sheets": [s.name for s in book.sheets]}
    return {**status(ay), **{k: v for k, v in LAST[str(path)].items() if k != "error"},
            **({"error": LAST[str(path)]["error"]} if not LAST[str(path)]["ok"] else {})}


def after_compute(ay: str) -> None:
    """Keep the workbook in step with the figures, when the profile asks for it."""
    if ((profiles.active() or {}).get("settings") or {}).get("excel_export", "manual") != "auto":
        return
    try:
        write(ay)
    except Exception as exc:                # a workbook must never fail a computation
        LAST[str(workbook_path(None, ay))] = {"ok": False, "error": f"the workbook was not written: {exc}"}
