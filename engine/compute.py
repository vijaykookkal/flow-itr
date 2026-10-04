"""Part B-TI and Part B-TTI, computed rather than extracted.

Two jobs:

  1. Build the summary the Summary tab renders, both regimes side by side.
  2. **Audit the extraction.** Where a figure is both stated in a document and
     derivable from its components, this recomputes it and reports any
     disagreement as a check. The model is not trusted with arithmetic; it is
     trusted only with transcription, and this is what verifies even that.

Nothing here is a filing. Anything not yet implemented is listed explicitly in
`not_implemented` rather than being silently treated as zero.
"""

from __future__ import annotations

import importlib
from datetime import datetime, timezone

from . import capital_gains as cg_engine
from . import bp as bp_engine
from . import depreciation as dep_engine
from . import filed as filed_engine
from . import fsi as fsi_engine
from . import fa as fa_engine
from . import cascade
from . import cg_form
from . import schedule_112a as s112a_engine
from . import os_form
from . import fx


class RatesUnavailable(Exception):
    """No rate table for this assessment year yet."""


def load_rates(ay: str):
    module = f"engine.rates.ay{ay.replace('-', '_')}"
    try:
        return importlib.import_module(module)
    except ModuleNotFoundError as exc:
        # A profile for a year we have not encoded yet is a normal thing to
        # create -- you add next year's profile before anyone has written next
        # year's Finance Act into this repo. It must not crash the page.
        raise RatesUnavailable(
            f"No rate table for AY {ay}. Add engine/rates/ay{ay.replace('-', '_')}.py "
            f"(copy the nearest year and update slabs, ceilings and surcharge)."
        ) from exc


def _amt(node, default: int = 0) -> int:
    """Money objects are {'amount': int, ...}; plain ints are tolerated."""
    if node is None:
        return default
    if isinstance(node, dict):
        return int(node.get("amount") or 0)
    return int(node)


# --------------------------------------------------------------------------
# Head-wise income
# --------------------------------------------------------------------------
def salary_head(salary_doc: dict, rates, regime: str) -> dict:
    """Recomputed from components. Form 16 item 6 is a cross-check, not the input.

    Under the section 115BAC default regime the HRA and LTA exemptions and the
    section 16(ii)/(iii) deductions are unavailable, so lifting 'income
    chargeable' off Form 16 -- which is usually prepared on one regime's basis --
    silently produces the wrong figure for the other.
    """
    if not salary_doc:
        return {"gross": 0, "exempt": 0, "deductions_16": 0, "net": 0, "lines": []}

    data = salary_doc.get("data", {})
    gross = sum(_amt(e.get("gross_salary")) for e in data.get("employers", []))

    exempt, exempt_lines = 0, []
    for e in data.get("employers", []):
        for a in e.get("exempt_allowances", []):
            allowed = regime == "old" or a["section"] in rates.SECTION_10_ALLOWED_IN_NEW_REGIME
            amount = _amt(a.get("amount"))
            exempt_lines.append({
                "section": a["section"], "description": a["description"],
                "amount": amount, "allowed": allowed,
            })
            if allowed:
                exempt += amount

    d16 = data.get("deductions_16", {})
    std = rates.STANDARD_DEDUCTION_OLD if regime == "old" else rates.STANDARD_DEDUCTION_NEW
    others = 0
    if regime == "old" or rates.SECTION_16_OTHERS_IN_NEW_REGIME:
        others = _amt(d16.get("entertainment_16_ii")) + _amt(d16.get("professional_tax_16_iii"))

    net = max(0, gross - exempt - std - others)
    return {
        "gross": gross, "exempt": exempt, "standard_deduction": std,
        "other_16": others, "deductions_16": std + others, "net": net,
        "lines": exempt_lines,
    }


def other_sources_head(os_doc: dict, ay: str = "2026-27") -> dict:
    """The head as Schedule OS computes it, not as the ledger states it.

    Summing the ledger's own amounts looks right and is wrong: a receipt in a
    foreign currency has no rupee amount until Rule 115 converts it, and a
    plain sum reads that as zero. Schedule OS does the conversion, so the head
    is taken from there -- one figure, computed once, in both places.
    """
    if not os_doc:
        return {"gross": 0, "deductions_57": 0, "net": 0, "by_category": {},
                "form": os_form.build(None, ay), "stated_gross": 0, "disagreements": []}

    form = os_form.build(os_doc, ay)
    data = os_doc.get("data", {})

    by_cat: dict[str, int] = {}
    for item in data.get("items", []):
        node = item.get("amount")
        if isinstance(node, dict) and "amount" not in node:
            continue                      # converted through the form instead
        by_cat[item["category"]] = by_cat.get(item["category"], 0) + _amt(node)
    for line in form["normal"]:
        converted = line.get("foreign") or 0
        if converted:
            # the form knows which item number it landed on; credit it back to
            # the category that fed that line
            for category, code in os_form.ITEMS.items():
                if code == line["item"]:
                    by_cat[category] = by_cat.get(category, 0) + converted
                    break

    gross, d57 = form["gross_normal"], form["deductions_57"]
    disagreements = []
    stated = form["stated_gross"]
    if stated and abs(stated - gross) > 1:
        disagreements.append(
            f"The extraction states gross other-sources income of Rs {stated:,}; Schedule OS "
            f"computes Rs {gross:,} from the ledger row by row, a difference of "
            f"Rs {gross - stated:,}. The computed figure is used.")
    if form["pending"]:
        disagreements.append(
            f"{len(form['pending'])} receipt(s) in a foreign currency are in NO figure here: "
            f"they still need a date of receipt or an exchange rate.")

    return {"gross": gross, "deductions_57": d57, "net": gross - d57,
            "by_category": by_cat, "form": form, "stated_gross": stated,
            "disagreements": disagreements}


# --------------------------------------------------------------------------
# Chapter VI-A
# --------------------------------------------------------------------------
def chapter_via(ded_doc: dict, os_head: dict, rates, regime: str, profile: dict) -> dict:
    """Ceilings are applied here, never in extraction.

    The extractor reports what the proofs evidence. This is where the statutory
    cap becomes visible as a line you can read: claimed X, allowed Y, because Z.
    """
    if not ded_doc:
        return {"total_allowed": 0, "lines": []}

    claimed: dict[str, int] = {}
    senior_parent = False
    for c in ded_doc.get("data", {}).get("claims", []):
        claimed[c["section"]] = claimed.get(c["section"], 0) + _amt(c.get("amount"))
        if c["section"] == "80D" and "parent" in (c.get("description", "") + str(c.get("payee"))).lower():
            if any(tok in c.get("description", "").lower() for tok in ("aged 6", "aged 7", "aged 8", "senior")):
                senior_parent = True

    lines = []

    def add(section, claim, allowed, note):
        if claim or allowed:
            lines.append({"section": section, "claimed": claim, "allowed": allowed, "note": note})

    if regime == "new":
        for section, amount in sorted(claimed.items()):
            allowed = amount if section in rates.VIA_ALLOWED_IN_NEW_REGIME else 0
            add(section, amount, allowed,
                "Allowed under 115BAC" if allowed else "Not available under the 115BAC default regime")
        return {"total_allowed": sum(line["allowed"] for line in lines), "lines": lines}

    # --- old regime ---
    agg_80c = sum(claimed.get(s, 0) for s in ("80C", "80CCC", "80CCD(1)"))
    allowed_80c = min(agg_80c, rates.CEILING_80C_AGGREGATE)
    add("80C/80CCC/80CCD(1)", agg_80c, allowed_80c,
        f"Aggregate ceiling Rs {rates.CEILING_80C_AGGREGATE:,}")

    c_1b = claimed.get("80CCD(1B)", 0)
    add("80CCD(1B)", c_1b, min(c_1b, rates.CEILING_80CCD_1B),
        f"Ceiling Rs {rates.CEILING_80CCD_1B:,}, over and above 80C")

    # 80D is split self/parents by the description text the extractor captured.
    d_self = d_parents = 0
    for c in ded_doc.get("data", {}).get("claims", []):
        if c["section"] != "80D":
            continue
        desc = c.get("description", "").lower()
        if "parent" in desc:
            d_parents += _amt(c.get("amount"))
        else:
            d_self += _amt(c.get("amount"))
    cap_parents = rates.CEILING_80D_PARENTS_SENIOR if senior_parent else rates.CEILING_80D_PARENTS
    allowed_80d = min(d_self, rates.CEILING_80D_SELF) + min(d_parents, cap_parents)
    add("80D", d_self + d_parents, allowed_80d,
        f"Self capped at Rs {rates.CEILING_80D_SELF:,}; parents at Rs {cap_parents:,}"
        + (" (senior citizen)" if senior_parent else ""))

    c_80g = claimed.get("80G", 0)
    add("80G", c_80g, c_80g // 2,
        "Taken at 50% without qualifying limit. The donee's category decides "
        "this - verify against the 80G certificate before filing")

    # 80TTB replaces 80TTA at 60 and covers deposit interest as well as savings,
    # which is worth far more to a senior citizen than the 80TTA ceiling.
    savings = os_head["by_category"].get("interest_savings", 0)
    if profile.get("age_band", "below_60") == "below_60":
        add("80TTA", savings, min(savings, rates.CEILING_80TTA),
            f"Savings interest, ceiling Rs {rates.CEILING_80TTA:,}")
    else:
        deposits = os_head["by_category"].get("interest_deposits", 0)
        eligible = savings + deposits
        add("80TTB", eligible, min(eligible, rates.CEILING_80TTB),
            f"Senior citizen: savings and deposit interest, ceiling Rs {rates.CEILING_80TTB:,}")

    for section, amount in sorted(claimed.items()):
        if section not in ("80C", "80CCC", "80CCD(1)", "80CCD(1B)", "80D", "80G"):
            add(section, amount, amount, "Passed through - no ceiling modelled yet")

    return {"total_allowed": sum(line["allowed"] for line in lines), "lines": lines}


# --------------------------------------------------------------------------
# Tax
# --------------------------------------------------------------------------
def taxes_already_paid(docs: dict) -> int:
    """Every credit claimed: TDS, TCS and challans."""
    data = (docs.get("taxes_paid") or {}).get("data") or {}
    stated = data.get("total_taxes_paid")
    if stated is not None:
        return _amt(stated)
    return (sum(_amt(r.get("tds")) for r in data.get("tds_salary", []))
            + sum(_amt(r.get("tds")) for r in data.get("tds_other", []))
            + sum(_amt(r.get("tcs")) for r in data.get("tcs", []))
            + sum(_amt(c.get("amount")) for c in data.get("taxes_paid_challans", [])))


def taxes_paid_split(docs: dict) -> dict:
    """The credits under the four headings Part B-TTI asks for separately.

    The total alone cannot be checked against anything. Split by heading it
    can: advance tax and self-assessment tax come from challans and TDS from
    certificates, and a total that matches while the split does not means two
    errors cancelling.
    """
    data = (docs.get("taxes_paid") or {}).get("data") or {}
    advance = other = 0
    for ch in data.get("taxes_paid_challans", []):
        kind = str(ch.get("kind") or "").lower()
        if "advance" in kind:
            advance += _amt(ch.get("amount"))
        else:
            other += _amt(ch.get("amount"))
    tds = (sum(_amt(r.get("tds")) for r in data.get("tds_salary", []))
           + sum(_amt(r.get("tds")) for r in data.get("tds_other", [])))
    tcs = sum(_amt(r.get("tcs")) for r in data.get("tcs", []))
    return {"advance": advance, "tds": tds, "tcs": tcs, "self_assessment": other,
            "total": advance + tds + tcs + other}


def slabs_for(rates, regime: str, profile: dict):
    band = (profile or {}).get("age_band", "below_60")
    return (rates.SLABS_OLD_BY_AGE.get(band, rates.SLABS_OLD)
            if regime == "old" else rates.SLABS_NEW)


def rates_for_fx(docs: dict) -> dict:
    """The saved SBI TT rates, which conversion needs and nothing else does."""
    return fx.load_rates()


def tax_for_regime(docs: dict, rates, regime: str, profile: dict) -> dict:
    # A filed return is here to be compared against, never to be computed
    # from. It is taken out of what the computation can reach before anything
    # else runs, so no schedule can lean on it even by accident, and it comes
    # back only at the end, for the side-by-side comparison.
    filed_doc = docs.get("filed_return")
    docs = {k: v for k, v in docs.items() if k != "filed_return"}
    sal = salary_head(docs.get("salary"), rates, regime)
    os_h = other_sources_head(docs.get("other_sources"), getattr(rates, "AY", "2026-27"))
    via = chapter_via(docs.get("deductions"), os_h, rates, regime, profile)
    # Section 32 relief is arithmetic on dates and costs, so it is computed
    # here and handed to Schedule BP, rather than being a figure someone typed
    # into the Depreciation tab and nobody could check.
    schedule_dep = dep_engine.build(docs.get("depreciation"), docs.get("books"),
                                    docs.get("_ay") or "2026-27")
    business = bp_engine.build(docs.get("books"), {"data": {"blocks": schedule_dep["blocks"]}})
    business["depreciation_schedule"] = schedule_dep
    cg = cg_engine.summarise(docs.get("capital_gains"), rates)
    # The same gains, laid out the way Schedule CG numbers them.
    cg["form"] = cg_form.build(
        cg, getattr(rates, "AY", "2026-27"),
        (docs.get("capital_gains") or {}).get("data", {}).get("deductions"))

    # The tax itself is worked out once, stage by stage, in cascade.py: the
    # loss set-offs, Chapter VI-A against ordinary income only, each special
    # rate on its own slice, the 87A rebate kept off capital-gains tax, and
    # surcharge with its cap and marginal relief. There is no second, simpler
    # calculation anywhere for a page to read by mistake.
    parts = {
        "salary": sal, "other_sources": os_h, "chapter_via": via,
        "capital_gains": cg, "business": business,
        "taxes_paid": taxes_already_paid(docs),
        "taxes_paid_split": taxes_paid_split(docs),
        # Last year's Schedule CFL: the opening losses, which are an input and
        # not something this return computes.
        "brought_forward": ((docs.get("setoff_cfl") or {}).get("data") or {})
                           .get("brought_forward") or [],
    }
    staged = cascade.build(docs, rates, regime, profile, parts)

    # Relief for foreign tax is capped by the Indian tax on the same income, so
    # it cannot be known until the tax is. The computation therefore runs once
    # to find the rate that income bore -- slab rate, with the surcharge and
    # cess that ride on it -- then Schedules FSI and TR are built at that rate,
    # and it runs again with the relief on line 6b.
    totals = staged["totals"]
    slab_rate = cascade.marginal_rate(totals["slab_income"], slabs_for(rates, regime, profile))
    base = (totals["tax_at_slab"] + totals["tax_at_special"] - totals["rebate_87a"]) or 1
    loading = (1 + totals["surcharge"] / base) * (1 + rates.CESS_RATE)
    foreign = fsi_engine.build(docs, rates_for_fx(docs), slab_rate * loading)
    if foreign and foreign["total_relief"]:
        parts["relief_90"] = foreign["total_relief"]
        staged = cascade.build(docs, rates, regime, profile, parts)

    return {
        "regime": regime,
        "cascade": staged,
        "heads": {"salary": sal, "other_sources": os_h},
        "capital_gains": cg,
        # The section 112A sales again, in that schedule's own columns. Built
        # from the same ledger rows, so it cannot differ from Schedule CG.
        "schedule_112a": s112a_engine.build(cg, docs.get("capital_gains")),
        "business": business,
        # Schedules FSI and TR, computed from the foreign receipts the other
        # schedules already hold. The marginal slab rate is what caps the
        # relief, because section 90(2) allows the lower of the foreign tax and
        # the Indian tax on the same income.
        "foreign": foreign,
        # Schedule FA's rupee columns, each at the rate for its own date.
        "foreign_assets": fa_engine.build(docs.get("foreign_special"), rates_for_fx(docs)),
        # Set beside a return already filed, where one has been supplied. This
        # is the only check in the tool whose other side was not produced by
        # the tool.
        "filed_comparison": filed_engine.build(filed_doc, staged, profile),
        # What one more rupee of ordinary income costs: the slab rate with the
        # surcharge and cess that ride on it. Used to size an open question --
        # "if this credit is income, about this much tax" -- never to compute.
        "marginal_rate": round(slab_rate * loading, 6),
        "chapter_via": via,
    }


# --------------------------------------------------------------------------
# Cross-checks: this is where the extraction gets audited
# --------------------------------------------------------------------------
def checks(docs: dict, old: dict, new: dict) -> list[dict]:
    out = []

    def check(name, ok, detail, severity="warn"):
        out.append({"check": name, "ok": ok, "detail": detail,
                    "severity": "info" if ok else severity})

    sal = docs.get("salary")
    if sal:
        stated = _amt(sal["data"].get("income_chargeable"))
        check(
            "Salary: Form 16 item 6 against recomputed heads",
            stated in (old["heads"]["salary"]["net"], new["heads"]["salary"]["net"]),
            f"Form 16 states Rs {stated:,}. Recomputed from components: "
            f"old regime Rs {old['heads']['salary']['net']:,}, "
            f"new regime Rs {new['heads']['salary']['net']:,}. "
            "A Form 16 is prepared on one regime's basis, so a mismatch with the "
            "other is expected - a mismatch with both is not.",
        )
        for e in sal["data"].get("employers", []):
            parts = (_amt(e.get("salary_17_1")) + _amt(e.get("perquisites_17_2"))
                     + _amt(e.get("profits_in_lieu_17_3")))
            check(
                f"Salary: 17(1)+17(2)+17(3) equals gross for {e['name'][:40]}",
                parts == _amt(e.get("gross_salary")),
                f"Components Rs {parts:,} against stated gross Rs {_amt(e.get('gross_salary')):,}",
                severity="error",
            )

    os_doc, tax_doc = docs.get("other_sources"), docs.get("taxes_paid")
    if os_doc and tax_doc:
        os_tds = sum(_amt(i.get("tds_deducted")) for i in os_doc["data"].get("items", []))
        as_tds = sum(_amt(r.get("tds")) for r in tax_doc["data"].get("tds_other", []))
        check(
            "TDS on other-sources income: certificates against Form 26AS",
            os_tds == as_tds,
            f"Interest and dividend certificates total Rs {os_tds:,}; "
            f"Form 26AS Part II totals Rs {as_tds:,}. These must agree row by row "
            "or a credit is being claimed that the department will not allow.",
            severity="error",
        )

    if tax_doc:
        d = tax_doc["data"]
        computed = (sum(_amt(r.get("tds")) for r in d.get("tds_salary", []))
                    + sum(_amt(r.get("tds")) for r in d.get("tds_other", []))
                    + sum(_amt(r.get("tcs")) for r in d.get("tcs", []))
                    + sum(_amt(c.get("amount")) for c in d.get("taxes_paid_challans", [])))
        stated = _amt(d.get("total_taxes_paid"))
        check("Taxes paid: stated total against the sum of rows", computed == stated,
              f"Rows sum to Rs {computed:,}; document states Rs {stated:,}",
              severity="error")

    return out


CONVERTS_ITS_OWN = {"capital_gains", "other_sources", "foreign_special", "filed_return"}


def _left_unconverted(regime: dict) -> list[str]:
    """What the converting schedules themselves report as still left out."""
    out = []
    cg = regime.get("capital_gains") or {}
    if cg.get("unconverted"):
        out.append(f"Capital gains: {len(cg['unconverted'])} disposal(s) in a foreign currency "
                   f"are in no total until the SBI TT buying rate for the date is known.")
    form = ((regime.get("heads") or {}).get("other_sources") or {}).get("form") or {}
    if form.get("pending"):
        out.append(f"Other sources: {len(form['pending'])} receipt(s) in a foreign currency are "
                   f"in no figure until each has a date of receipt and that day's rate.")
    needed = (regime.get("foreign_assets") or {}).get("rates_needed") or []
    if needed:
        out.append(f"Schedule FA: figures on {len(needed)} date(s) are left out until the SBI TT "
                   f"buying rate is known: "
                   + ", ".join(f"{n['currency']} {n['date']}" for n in needed[:8])
                   + ("…" if len(needed) > 8 else "") + ".")
    return out


def summarise(ay: str, docs: dict, missing_tabs: list[str], profile: dict | None = None) -> dict:
    profile = profile or {}
    try:
        rates = load_rates(ay)
    except RatesUnavailable as exc:
        return {
            "ay": ay,
            "computed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "profile": profile,
            "unavailable": str(exc),
            "regimes": {}, "checks": [], "contributors": [], "fabricated_inputs": [],
            "not_implemented": [str(exc)],
            "warning": f"No computation is possible for AY {ay} until its rate table exists.",
        }
    old = tax_for_regime(docs, rates, "old", profile)
    new = tax_for_regime(docs, rates, "new", profile)

    tax_doc = docs.get("taxes_paid")
    paid = _amt(tax_doc["data"].get("total_taxes_paid")) if tax_doc else 0

    # Everything said at the top of the summary is read off the staged
    # computation, the same one Part B-TTI is drawn from, so the balance can
    # never contradict the line 11 printed further down.
    def totals_of(regime: dict) -> dict:
        return regime["cascade"]["totals"]

    def liability(regime: dict) -> int:
        return totals_of(regime)["net_tax_liability"]

    lower = "new" if liability(new) <= liability(old) else "old"
    # An elected regime is respected even when it costs more -- the election is
    # yours to make, and the cost of making it is exactly what you want shown.
    elected = profile.get("regime", "compare")
    better = lower if elected == "compare" else elected
    chosen = new if better == "new" else old

    # Which extraction produced each contributing head, and when. A summary is
    # an aggregate, and an aggregate hides its inputs: without this, figures
    # from the mock stub or from a stale run last month blend invisibly into
    # figures from a real extraction this morning.
    contributors = [
        {
            "tab": tab_id,
            "engine": (d.get("engine") or {}).get("model"),
            "run_id": d.get("run_id"),
            "generated_at": d.get("generated_at"),
            "sources": [s["path"] for s in d.get("sources", [])],
        }
        # A filed return is set beside the computation and feeds none of it.
        for tab_id, d in sorted(docs.items()) if tab_id != "filed_return"
    ]
    fabricated = [c["tab"] for c in contributors if c["engine"] == "mock"]

    return {
        "ay": ay,
        "computed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "regimes": {"old": old, "new": new},
        "profile": profile,
        "recommended_regime": better,
        "lower_regime": lower,
        "regime_is_elected": elected != "compare",
        "election_costs": liability(chosen) - min(liability(old), liability(new)),
        "saving_versus_other": abs(liability(old) - liability(new)),
        "taxes_already_paid": totals_of(chosen).get("taxes_paid", paid),
        "balance": {
            "payable": totals_of(chosen)["payable"],
            "refund": totals_of(chosen)["refund"],
        },
        "checks": checks(docs, old, new),
        "contributors": contributors,
        "fabricated_inputs": fabricated,
        "not_implemented": [
            f"{tab_id}: an amount stated only in a foreign currency is not counted "
            f"anywhere yet -- {where}"
            # Capital gains, other sources and the foreign schedules convert
            # their own foreign amounts, each at the date its rule fixes, and
            # say for themselves what they could not convert. Listing those
            # amounts here as uncounted would be untrue of every one that was.
            for tab_id, d in sorted(docs.items()) if tab_id not in CONVERTS_ITS_OWN
            for where in fx.find_unconverted((d or {}).get("data"), "")
        ] + _left_unconverted(chosen) + ([
            "SOME FIGURES ABOVE CAME FROM THE MOCK ENGINE, WHICH INVENTS NOTHING "
            "but parses only development fixtures, not your documents: "
            + ", ".join(fabricated)
            + ". Re-extract these tabs with the claude engine before reading any total."
        ] if fabricated else []) + [
            ("No losses brought forward from earlier years have been supplied on the "
             "Set-off & Carry Forward tab, so none are set off."
             if t == "setoff_cfl" else
             f"Nothing has been extracted for this tab, so it adds nothing to the "
             f"computation: {t}")
            for t in missing_tabs
        ] + [
            "Interest under sections 234A, 234B and 234C is not computed.",
        ],
        "warning": (
            "This is a draft for your review, not a return. Business and "
            "professional income is the reason this is an ITR-3 and it is not "
            "included below, so the balance shown is not your real position."
        ) if "books" in missing_tabs else
        "This is a draft for your review, not a return.",
    }
