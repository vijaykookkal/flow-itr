"""A deterministic stand-in for the AI engine.

This is NOT a general extractor. It is a set of hand-written parsers tuned to
the demo fixtures in source_data/, and it exists so the pipeline -- scan,
fingerprint, validate, repair, merge, derive, render -- can be exercised and
tested without spending subscription quota or waiting on a model.

It returns the same thing the real engine returns: a JSON document as text,
which runner.py then validates and writes. Every output is stamped
model: "mock" so no mock result can ever be mistaken for an extraction.

Set ITR_MOCK_FAULT=1 to make it emit a schema-invalid document, which is how
the validation-repair loop gets exercised.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from . import EngineError, Reply, Request


LABEL = "mock (fixtures only)"
NOTE = "Development stub. Parses the text fixtures in fixtures/ and nothing else."
SELECTABLE = False
CONFINES_READS = True


def available() -> bool:
    return True


def _rs(text: str) -> int:
    return int(re.sub(r"[^\d]", "", text)) if text else 0


def _money(amount: int, cite: str, basis: str) -> dict:
    return {"amount": amount, "cite": cite, "basis": basis}


def _find(pattern: str, text: str, group: int = 1) -> str | None:
    m = re.search(pattern, text, re.MULTILINE)
    return m.group(group) if m else None


READABLE = (".txt", ".csv", ".md", ".json")


def _read_all(files: list[dict]) -> list[tuple[str, str]]:
    """Read the plain-text fixtures, and refuse the job if anything else is here.

    The mock cannot read PDFs. Skipping them quietly is the worst thing this
    system could do: it yields an empty document that still passes its schema,
    so the tab renders zeros that look like a real extraction of a real Form 16.
    Refusing is the only safe behaviour.
    """
    unreadable = [f["path"] for f in files if Path(f["abs"]).suffix.lower() not in READABLE]
    if unreadable:
        raise EngineError(
            "the mock engine reads only plain text "
            f"({', '.join(READABLE)}) and cannot read: {', '.join(unreadable)}. "
            "These are real documents - switch the engine to 'claude'. "
            "The mock exists only for the text fixtures used in development."
        )
    return [(Path(f["path"]).name, Path(f["abs"]).read_text("utf-8", errors="replace")) for f in files]


# --------------------------------------------------------------------------
# Schedule S
# --------------------------------------------------------------------------
def _salary(docs) -> dict:
    employers, unmapped, questions = [], [], []

    for name, text in docs:
        if "FORM NO. 16" not in text:
            questions.append(f"{name} is in the salary folder but is not a Form 16. Confirm what it is.")
            continue

        emp_name = (_find(r"Name and address of the Employer\s*:\s*(.+)", text) or "").strip()
        s171 = _rs(_find(r"section 17\(1\)\s+([\d,]+)", text) or "")
        s172 = _rs(_find(r"section 17\(2\)\s+([\d,]+)", text) or "")
        s173 = _rs(_find(r"section 17\(3\)\s+([\d,]+)", text) or "")
        gross = _rs(_find(r"\(d\) Total\s+([\d,]+)", text) or "")

        exempt = []
        hra = _find(r"House Rent Allowance - section 10\(13A\)\s+([\d,]+)", text)
        if hra:
            exempt.append({
                "section": "10(13A)", "description": "House Rent Allowance",
                "amount": _money(_rs(hra), f"{name}#2(i)", "Form 16 Part B, item 2(i)"),
            })
        lta = _find(r"Leave Travel Allowance - section 10\(5\)\s+([\d,]+)", text)
        if lta:
            exempt.append({
                "section": "10(5)", "description": "Leave Travel Allowance",
                "amount": _money(_rs(lta), f"{name}#2(ii)", "Form 16 Part B, item 2(ii)"),
            })

        employers.append({
            "name": emp_name,
            "tan": (_find(r"TAN of the Deductor\s*:\s*(\S+)", text) or None),
            "period": (_find(r"Period with the Employer\s*:\s*(.+)", text) or "").strip() or None,
            "salary_17_1": _money(s171, f"{name}#1(a)", "Form 16 Part B, item 1(a)"),
            "perquisites_17_2": _money(s172, f"{name}#1(b)", "Form 16 Part B, item 1(b)"),
            "profits_in_lieu_17_3": _money(s173, f"{name}#1(c)", "Form 16 Part B, item 1(c)"),
            "gross_salary": _money(gross, f"{name}#1(d)", "Form 16 Part B, item 1(d)"),
            "exempt_allowances": exempt,
            "net_salary": _money(
                _rs(_find(r"Total amount of salary received from current employer\s+([\d,]+)", text) or ""),
                f"{name}#3", "Form 16 Part B, item 3"),
        })

        relief = _find(r"Relief under section 89.*?([\d,]{4,})", text)
        if relief:
            unmapped.append({
                "source": f"{name}#7",
                "text": f"Relief under section 89 - Rs {relief}",
                "why": "Schedule S has no field for section 89 relief; it belongs in Part B-TTI and needs Form 10E filed separately.",
            })

    text0 = docs[0][1] if docs else ""
    name0 = docs[0][0] if docs else "unknown"
    return {
        "data": {
            "employers": employers,
            "deductions_16": {
                "standard_16_ia": _money(
                    _rs(_find(r"Standard deduction under section 16\(ia\)\s+([\d,]+)", text0) or ""),
                    f"{name0}#4(a)", "Form 16 Part B, item 4(a)"),
                "entertainment_16_ii": _money(
                    _rs(_find(r"Entertainment allowance under section 16\(ii\)\s+([\d,]+)", text0) or ""),
                    f"{name0}#4(b)", "Form 16 Part B, item 4(b)"),
                "professional_tax_16_iii": _money(
                    _rs(_find(r"Tax on employment under section 16\(iii\)\s+([\d,]+)", text0) or ""),
                    f"{name0}#4(c)", "Form 16 Part B, item 4(c)"),
            },
            "income_chargeable": _money(
                _rs(_find(r'Income chargeable under the head "Salaries".*?([\d,]{4,})', text0) or ""),
                f"{name0}#6", "Form 16 Part B, item 6"),
        },
        "unmapped": unmapped,
        "questions": questions + [
            "Form 16 item 4(c) claims professional tax of Rs 2,400 under section 16(iii). "
            "That deduction is not available under the section 115BAC default regime - confirm the regime on the General tab."
        ],
    }


# --------------------------------------------------------------------------
# Schedule OS
# --------------------------------------------------------------------------
def _other_sources(docs) -> dict:
    items, questions = [], []

    for name, text in docs:
        if "INTEREST CERTIFICATE" in text:
            payer = (_find(r"^([A-Z][A-Z &.]+(?:LIMITED|LTD|BANK))", text) or "Bank").strip()
            sav = _find(r"Interest credited during FY 2025-26\s+Rs\s+([\d,]+)", text)
            if sav:
                items.append({
                    "payer": payer,
                    "account_ref": _find(r"Account Number\s+(\S+)", text),
                    "category": "interest_savings",
                    "amount": _money(_rs(sav), f"{name}#savings", "Savings account interest certificate"),
                    "tds_deducted": _money(0, f"{name}#savings", "Stated as nil"),
                })
            fd = _find(r"Interest accrued / credited during FY 2025-26\s+Rs\s+([\d,]+)", text)
            if fd:
                items.append({
                    "payer": payer,
                    "account_ref": _find(r"Deposit Number\s+(\S+)", text),
                    "category": "interest_deposits",
                    "amount": _money(_rs(fd), f"{name}#fd", "Fixed deposit interest certificate"),
                    "tds_deducted": _money(
                        _rs(_find(r"section 194A\s+Rs\s+([\d,]+)", text) or ""),
                        f"{name}#fd", "TDS under section 194A"),
                })

        if "DIVIDEND STATEMENT" in text:
            for m in re.finditer(r"^\d{2}-\d{2}-\d{4}\s+(.+?)\s{2,}([\d,]+)\s+([\d,]+)\s*$", text, re.M):
                items.append({
                    "payer": m.group(1).strip(),
                    "account_ref": None,
                    "category": "dividend",
                    "amount": _money(_rs(m.group(2)), f"{name}#dividends", "Consolidated dividend statement"),
                    "tds_deducted": _money(_rs(m.group(3)), f"{name}#dividends", "TDS under section 194"),
                })
            refund = _find(r"(?s)interest credit of Rs ([\d,]+).*?income-tax refund", text)
            if refund:
                items.append({
                    "payer": "Income Tax Department",
                    "account_ref": None,
                    "category": "interest_income_tax_refund",
                    "amount": _money(_rs(refund), f"{name}#note", "Note on the dividend statement"),
                    "tds_deducted": _money(0, f"{name}#note", "No TDS stated"),
                })
                questions.append(
                    "Interest of Rs 3,120 on the AY 2024-25 refund was found in a note on the dividend "
                    "statement, not on a certificate. Confirm it against Form 26AS before filing."
                )

    totals: dict = {}
    for it in items:
        c = it["category"]
        totals[c] = totals.get(c, 0) + it["amount"]["amount"]

    return {
        "data": {
            "items": items,
            "totals_by_category": {
                k: _money(v, "derived", "Sum of items[] in this category") for k, v in totals.items()
            },
            "deductions_57": _money(0, None, "No section 57 expenses found"),
            "gross_income_from_os": _money(
                sum(i["amount"]["amount"] for i in items), "derived", "Sum of items[]"),
        },
        "unmapped": [],
        "questions": questions,
    }


# --------------------------------------------------------------------------
# Schedule VI-A
# --------------------------------------------------------------------------
def _deductions(docs) -> dict:
    claims, unmapped = [], []

    for name, text in docs:
        blocks = re.split(r"^-+$\n^SECTION ", text, flags=re.M)
        for block in blocks[1:]:
            header = block.split("\n", 1)[0]
            section = header.split(" ")[0].strip()
            lines = block.split("\n")
            for idx, line in enumerate(lines):
                m = re.match(r"^\s*(.+?)\s+Rs\s+([\d,]+)\s*$", line)
                if not m:
                    continue
                # An amount line is usually a continuation ("Premium paid ...,
                # mode: net banking   Rs 46,000"); the line above it carries who
                # and what, which is what decides the 80D ceiling. Losing that
                # context silently halves the deduction, so pull it in.
                desc = m.group(1).strip()
                if idx > 0:
                    prev = lines[idx - 1].strip()
                    if prev and not re.search(r"Rs\s+[\d,]+\s*$", prev) and not prev.startswith("-"):
                        desc = f"{prev} - {desc}"
                donee = _find(r"Donee\s*:\s*(.+)", block)
                if donee and re.match(r"^(Mode|Amount|ARN|PAN)\b", desc):
                    desc = f"Donation to {donee.strip()}"
                claims.append({
                    "section": section,
                    "description": re.sub(r"\s+", " ", desc),
                    "payee": _find(r"Donee\s*:\s*(.+)", block),
                    "payee_pan": _find(r"PAN\s*:\s*([A-Z]{5}\d{4}[A-Z])", block),
                    "donation_arn": _find(r"ARN\s*:\s*(\S+)", block),
                    "mode": _find(r"[Mm]ode\s*[:,]\s*(\w+)", block),
                    "amount": _money(_rs(m.group(2)), f"{name}#{section}", f"Proof under section {section}"),
                })
        if "Employer PF contribution" in text:
            unmapped.append({
                "source": f"{name}#note",
                "text": "Employer PF contribution of Rs 1,04,000",
                "why": "Employer contribution is not a VI-A claim by the employee; it is already inside Form 16 gross salary.",
            })

    return {
        "data": {
            "claims": claims,
            "total_claimed": _money(
                sum(c["amount"]["amount"] for c in claims), "derived",
                "Sum of claims[] before statutory ceilings, which engine/ applies"),
        },
        "unmapped": unmapped,
        "questions": [],
    }


# --------------------------------------------------------------------------
# Schedules TDS1 / TDS2 / IT
# --------------------------------------------------------------------------
def _taxes_paid(docs) -> dict:
    tds_salary, tds_other, challans = [], [], []

    for name, text in docs:
        part1 = re.search(r"PART I -.*?\n=+\n(.*?)\n-{10,}", text, re.S)
        if part1:
            for m in re.finditer(r"^(.+?)\s{2,}([A-Z]{4}\d{5}[A-Z])\s+([\d,]+)\s+([\d,]+)\s*$", part1.group(1), re.M):
                tds_salary.append({
                    "deductor": m.group(1).strip(),
                    "tan": m.group(2),
                    "income_paid": _money(_rs(m.group(3)), f"{name}#PartI", "Form 26AS Part I"),
                    "tds": _money(_rs(m.group(4)), f"{name}#PartI", "Form 26AS Part I"),
                })

        part2 = re.search(r"PART II -.*?\n=+\n(.*?)\n-{10,}", text, re.S)
        if part2:
            for m in re.finditer(
                r"^(.+?)\s{2,}([A-Z]{4}\d{5}[A-Z])\s+(\S+)\s+([\d,]+)\s+([\d,]+)\s*$", part2.group(1), re.M
            ):
                tds_other.append({
                    "deductor": m.group(1).strip(),
                    "tan_or_pan": m.group(2),
                    "section": m.group(3),
                    "gross_amount": _money(_rs(m.group(4)), f"{name}#PartII", "Form 26AS Part II"),
                    "head": "other_sources",
                    "tds": _money(_rs(m.group(5)), f"{name}#PartII", "Form 26AS Part II"),
                })

        part3 = re.search(r"PART III -.*?\n=+\n(.*?)\n-{10,}", text, re.S)
        if part3:
            for m in re.finditer(
                r"^(\d{7})\s+(\d{2})-(\d{2})-(\d{4})\s+(\d+)\s+(Advance Tax|Self Assessment)\s+([\d,]+)\s*$",
                part3.group(1), re.M
            ):
                challans.append({
                    "bsr_code": m.group(1),
                    "date_of_deposit": f"{m.group(4)}-{m.group(3)}-{m.group(2)}",
                    "challan_no": m.group(5),
                    "kind": "advance_tax" if m.group(6) == "Advance Tax" else "self_assessment",
                    "amount": _money(_rs(m.group(7)), f"{name}#PartIII", "Form 26AS Part III"),
                })

    total = (
        sum(r["tds"]["amount"] for r in tds_salary)
        + sum(r["tds"]["amount"] for r in tds_other)
        + sum(c["amount"]["amount"] for c in challans)
    )
    return {
        "data": {
            "tds_salary": tds_salary,
            "tds_other": tds_other,
            "tcs": [],
            "taxes_paid_challans": challans,
            "total_taxes_paid": _money(total, "derived", "Sum of TDS, TCS and challans"),
        },
        "unmapped": [],
        "questions": [],
    }


_PARSERS = {
    "salary": _salary,
    "other_sources": _other_sources,
    "deductions": _deductions,
    "taxes_paid": _taxes_paid,
}


def run(req: Request, on_event, **_) -> Reply:
    schedule, ay, files, attempt = req.schedule, req.ay, req.files, req.attempt
    on_event({"phase": "spawn", "detail": f"mock parser for {schedule}"})
    parser = _PARSERS.get(schedule)
    if parser is None:
        raise EngineError(f"mock engine has no parser for schedule {schedule!r}")

    docs = _read_all(files)
    for n, _text in docs:
        on_event({"phase": "tool", "detail": f"Read {n}"})

    result = parser(docs)
    payload = {
        "schema_version": "1.0.0",
        "ay": ay,
        "schedule": schedule,
        "status": "needs_review" if result.get("questions") else "ok",
        "sources": [{"path": f["path"], "sha256": f["sha256"], "bytes": f["bytes"]} for f in files],
        **result,
    }

    fault = os.environ.get("ITR_MOCK_FAULT")
    # "1" fails only the first attempt, so the repair loop is seen recovering.
    # "always" never recovers, so the give-up path is seen refusing to write.
    if fault == "always" or (fault and attempt == 1):
        on_event({"phase": "note", "detail": "injecting a schema fault"})
        payload["data"].pop("income_chargeable", None)
        payload["status"] = "fine"  # not a member of the status enum
        if payload["data"].get("employers"):
            payload["data"]["employers"][0]["gross_salary"]["amount"] = "26,44,500"

    return Reply(text=json.dumps(payload, indent=2), session_id=None, model="mock")
