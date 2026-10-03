"""Schedules CYLA, BFLA, CFL and UD: where every loss went.

A loss is worth exactly what it is allowed to meet, and the Act is particular
about that. This module does two things the rest of the computation needs and
then lays the result out the way the return prints it:

  * it sets losses brought forward from earlier years against this year's
    income, each kind only against what the Act lets it touch, oldest year
    first, and refuses a loss whose time has run out (sections 71B, 72, 73,
    73A, 74, 74A; unabsorbed depreciation under section 32(2));
  * it works out what is carried to next year: what is left of the earlier
    losses that have not lapsed, plus this year's own.

The opening figures are the one input a person supplies -- last year's
Schedule CFL, or the intimation for that year. With none supplied every line
here is nil, and the schedule says that rather than leaving a gap.
"""

from __future__ import annotations

# Assessment years a loss may be carried for, counted from the year after it
# arose. None means no limit.
YEARS = {
    "house_property": 8,                 # s.71B
    "business_non_speculative": 8,       # s.72
    "business_speculative": 4,           # s.73
    "specified_business_35AD": None,     # s.73A
    "short_term_capital": 8,             # s.74
    "long_term_capital": 8,              # s.74
    "other_sources_race_horses": 4,      # s.74A
    "unabsorbed_depreciation": None,     # s.32(2)
}

LOSS_COLUMNS = ["house_property", "business_non_speculative", "business_speculative",
                "specified_business_35AD", "short_term_capital", "long_term_capital",
                "other_sources_race_horses"]

COLUMN_LABELS = {
    "house_property": "House property loss",
    "business_non_speculative": "Loss from business other than speculative and specified",
    "business_speculative": "Loss from speculative business",
    "specified_business_35AD": "Loss from specified business",
    "short_term_capital": "Short-term capital loss",
    "long_term_capital": "Long-term capital loss",
    "other_sources_race_horses": "Loss from owning and maintaining race horses",
}

# (row key, number in CYLA, number in BFLA, the form's wording)
ROWS = [
    ("salary", "ii", "i", "Salaries"),
    ("house_property", "iii", "ii", "House property"),
    ("business", "iv", "iii", "Income from Business (excluding speculation profit and income "
                              "from specified business) or profession"),
    ("speculative", "v", "iv", "Speculative Income"),
    ("specified", "vi", "v", "Specified Business Income"),
    ("stcg_20", "vii", "vi", "Short-term capital gain taxable @ 20%"),
    ("stcg_30", "viii", "vii", "Short-term capital gain taxable @ 30%"),
    ("stcg_applicable", "ix", "viii", "Short-term capital gain taxable at applicable rates"),
    ("stcg_dtaa", "x", "ix", "Short-term capital gain taxable at Special Rates in India as "
                             "per DTAA"),
    ("ltcg_125", "xi", "x", "Long term capital gain taxable @ 12.5%"),
    ("ltcg_dtaa", "xii", "xi", "Long term capital gains taxable at Special Rates in India as "
                               "per DTAA"),
    ("other_sources", "xiii", "xii", "Net Income from other sources chargeable at normal "
                                     "applicable rates"),
    ("race_horses", "xiv", "xiii", "Profit from the activity of owning and maintaining race "
                                   "horses"),
    ("os_dtaa", "xv", "xiv", "Income from other sources taxable at special rates in India as "
                             "per DTAA rates"),
]


def _amt(node) -> int:
    if isinstance(node, dict):
        return int(node.get("amount") or 0)
    try:
        return int(node or 0)
    except (TypeError, ValueError):
        return 0


def row_of(h: dict) -> str:
    key = h["key"]
    if key == "stcg":
        return "stcg_applicable"
    if key.startswith("cg:"):
        if h.get("term") == "long":
            return "ltcg_125"
        return "stcg_30" if abs((h.get("rate") or 0) - 0.30) < 1e-9 else "stcg_20"
    return key


def _may_meet(kind: str, h: dict) -> bool:
    key = h["key"]
    if kind == "house_property":
        return key == "house_property"
    if kind == "business_non_speculative":
        return key in ("business", "speculative")
    if kind == "business_speculative":
        return key == "speculative"
    if kind == "short_term_capital":
        return key == "stcg" or key.startswith("cg:")
    if kind == "long_term_capital":
        return key.startswith("cg:") and h.get("term") == "long"
    if kind == "unabsorbed_depreciation":
        return key != "salary"
    return False        # specified business and race horses: no such income is modelled


def apply_brought_forward(heads: list[dict], losses: list[dict], ay: str, money) -> dict:
    """Set earlier years' losses against what is left after this year's set-off."""
    current = int(str(ay)[:4])
    for h in heads:
        h["bf"], h["bf_dep"] = 0, 0

    def left_in(h) -> int:
        if h["amount"] <= 0:
            return 0
        return h["amount"] - h.get("absorbed", 0) - h["bf"] - h["bf_dep"]

    notes, entries = [], []
    for item in losses or []:
        origin, kind = str(item.get("ay_of_origin") or ""), item.get("kind")
        amount = _amt(item.get("amount"))
        if kind not in YEARS or not origin[:4].isdigit() or amount <= 0:
            continue
        age = current - int(origin[:4])
        limit = YEARS[kind]
        entry = {"ay": origin, "kind": kind, "brought_forward": amount, "set_off": 0,
                 "expired": limit is not None and age > limit,
                 "last_year": limit is not None and age == limit,
                 "not_earlier": age <= 0}
        if entry["not_earlier"]:
            notes.append(f"A loss stated for {origin} is not from an earlier year and is ignored.")
        elif entry["expired"]:
            notes.append(
                f"{money(amount)} of {COLUMN_LABELS.get(kind, kind).lower()} from {origin} can "
                f"no longer be used: it could be carried for {limit} assessment years and "
                f"that ended with {int(origin[:4]) + limit}-{str(int(origin[:4]) + limit + 1)[-2:]}.")
        entries.append(entry)

    # Losses before depreciation, oldest first: a loss has a clock running and
    # depreciation does not, so the one that can expire is spent first.
    usable = [e for e in entries if not e["expired"] and not e["not_earlier"]]
    for entry in sorted(usable, key=lambda e: (e["kind"] == "unabsorbed_depreciation", e["ay"])):
        slot = "bf_dep" if entry["kind"] == "unabsorbed_depreciation" else "bf"
        left = entry["brought_forward"]
        targets = sorted((h for h in heads if _may_meet(entry["kind"], h) and left_in(h) > 0),
                         key=lambda h: -h.get("rate", 0))
        for h in targets:
            use = min(left, left_in(h))
            if use <= 0:
                continue
            h[slot] += use
            entry["set_off"] += use
            left -= use
            notes.append(f"{money(use)} of {COLUMN_LABELS.get(entry['kind'], 'unabsorbed depreciation').lower()} "
                         f"from {entry['ay']} set off against {h['label']}.")
            if left <= 0:
                break
        if left > 0 and entry["last_year"]:
            notes.append(f"{money(left)} from {entry['ay']} found nothing to meet and this was "
                         f"its last year: it lapses and is not carried further.")

    if not entries:
        notes.append("No losses brought forward from earlier years have been supplied, so "
                     "nothing is set off here. If you carried a loss into this year, add last "
                     "year's return or intimation on the Set-off & Carry Forward tab; until "
                     "then it is not in these figures.")
    return {"entries": entries, "notes": notes,
            "total": sum(e["set_off"] for e in entries)}


def schedules(heads: list[dict], within: dict, across: dict, bf: dict, ay: str) -> dict:
    """CYLA, BFLA, CFL and UD in the form's own rows."""
    by_row: dict[str, list[dict]] = {}
    for h in heads:
        by_row.setdefault(row_of(h), []).append(h)

    def total(key, fn) -> int:
        return sum(fn(h) for h in by_row.get(key, []))

    loss = {k: sum(-h["amount"] for h in heads if h["key"] == k and h["amount"] < 0)
            for k in ("house_property", "business", "other_sources")}

    cyla, bfla = [], []
    for key, cyla_no, bfla_no, label in ROWS:
        income = total(key, lambda h: max(0, h["amount"]))
        hp = total(key, lambda h: (h.get("absorbed_by") or {}).get("house_property", 0))
        biz = total(key, lambda h: (h.get("absorbed_by") or {}).get("business", 0))
        os_ = total(key, lambda h: (h.get("absorbed_by") or {}).get("other_sources", 0))
        remaining = income - hp - biz - os_
        cyla.append({"no": cyla_no, "label": label, "income": income, "hp_loss": hp,
                     "business_loss": biz, "os_loss": os_, "remaining": remaining})
        b_loss = total(key, lambda h: h.get("bf", 0))
        b_dep = total(key, lambda h: h.get("bf_dep", 0))
        bfla.append({"no": bfla_no, "label": label, "income": remaining, "bf_loss": b_loss,
                     "bf_depreciation": b_dep, "bf_allowance_35_4": 0,
                     "remaining": remaining - b_loss - b_dep})

    set_off = {"hp_loss": sum(r["hp_loss"] for r in cyla),
               "business_loss": sum(r["business_loss"] for r in cyla),
               "os_loss": sum(r["os_loss"] for r in cyla)}
    cyla_summary = {
        "loss": {"hp_loss": loss["house_property"], "business_loss": loss["business"],
                 "os_loss": loss["other_sources"]},
        "set_off": set_off,
        "remaining": {"hp_loss": loss["house_property"] - set_off["hp_loss"],
                      "business_loss": loss["business"] - set_off["business_loss"],
                      "os_loss": loss["other_sources"] - set_off["os_loss"]},
    }

    # ---- CFL ---------------------------------------------------------------
    current = int(str(ay)[:4])
    entries = [e for e in bf["entries"] if not e["not_earlier"]]
    years = sorted({f"{y}-{str(y + 1)[-2:]}" for y in range(current - 8, current)}
                   | {e["ay"] for e in entries if e["kind"] != "unabsorbed_depreciation"})
    cfl_rows = []
    for year in years:
        row = {"ay": year}
        for col in LOSS_COLUMNS:
            row[col] = sum(e["brought_forward"] for e in entries
                           if e["ay"] == year and e["kind"] == col and not e["expired"])
        cfl_rows.append(row)

    def col_sum(fn) -> dict:
        return {col: sum(fn(e) for e in entries if e["kind"] == col) for col in LOSS_COLUMNS}

    brought = col_sum(lambda e: 0 if e["expired"] else e["brought_forward"])
    adjusted = col_sum(lambda e: e["set_off"])
    lapsing = col_sum(lambda e: (e["brought_forward"] - e["set_off"])
                      if (e["last_year"] and not e["expired"]) else 0)
    carry_now = {**within.get("carry_forward", {}), **across.get("carry_forward", {})}
    this_year = {
        "house_property": carry_now.get("house_property", 0),
        "business_non_speculative": carry_now.get("business", 0),
        "business_speculative": carry_now.get("speculative", 0),
        "specified_business_35AD": 0,
        "short_term_capital": carry_now.get("stcl", 0),
        "long_term_capital": carry_now.get("ltcl", 0),
        "other_sources_race_horses": 0,
    }
    forward = {col: brought[col] - adjusted[col] - lapsing[col] + this_year[col]
               for col in LOSS_COLUMNS}

    notes = list(bf["notes"])
    if carry_now.get("other_sources"):
        notes.append("A loss under other sources (other than from race horses) that finds no "
                     "income this year cannot be carried forward; it lapses.")
    if any(this_year.values()):
        notes.append("This year's losses are carried forward only if the return is filed by "
                     "the due date (section 80). A house-property loss is the exception.")

    dep = [e for e in entries if e["kind"] == "unabsorbed_depreciation"]
    ud = [{"ay": e["ay"], "brought_forward": e["brought_forward"], "set_off": e["set_off"],
           "balance": e["brought_forward"] - e["set_off"]} for e in sorted(dep, key=lambda e: e["ay"])]

    return {
        "cyla": {"rows": cyla, **cyla_summary},
        "bfla": {"rows": bfla,
                 "total_set_off": sum(r["bf_loss"] + r["bf_depreciation"] for r in bfla),
                 "total_remaining": sum(r["remaining"] for r in bfla)},
        "cfl": {"columns": [{"key": c, "label": COLUMN_LABELS[c]} for c in LOSS_COLUMNS],
                "rows": cfl_rows, "brought_forward": brought, "adjusted_in_bfla": adjusted,
                "lapsing": lapsing, "current_year": this_year, "carried_forward": forward,
                "current_ay": f"{current}-{str(current + 1)[-2:]}"},
        "ud": ud,
        "supplied": bool(bf["entries"]),
        "notes": notes,
    }
