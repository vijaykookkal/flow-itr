"""Computed against filed, line by line.

The tool's Part B-TI and Part B-TTI are a claim about what the return should
say. A filed return is a fact about what it does say. Setting them side by side
is the strongest check available here, because it is the only one whose other
side was produced by something other than this tool.

Matching is on the line number as both sides print it, which is also why this
module is worth having: where the tool's numbering and the filed return's
numbering disagree, that disagreement shows up as lines that failed to pair,
and a line the tool invented is then plain to see. A comparison that quietly
aligned them by amount instead would hide exactly that.
"""

from __future__ import annotations

import re

# Two figures for the same line can differ by a rupee or two and mean nothing:
# the return rounds to the nearest ten, and a transcription may round paise.
TOLERANCE = 10


def _amount(node) -> int:
    if isinstance(node, dict):
        return int(node.get("amount") or 0)
    try:
        return int(node or 0)
    except (TypeError, ValueError):
        return 0


def normalise(item: str) -> str:
    """'4(a)(i)' and '4ai' are the same line printed two ways."""
    return re.sub(r"[^a-z0-9]", "", str(item or "").lower())


# Capital gains is printed as item 4 with a and b nested under it, and the
# innermost rows carry only their own roman numeral. So the same line is "4ai"
# to something reading the outline and "ai" to something reading the row, and
# the two must still pair. Only these forms are aliased: stripping the number
# off "10a" or "12a" would leave "a" and collide with everything else.
NESTED = re.compile(r"^\d+([ab](?:i{1,3}|iv|v))$")


def nested_alias(item: str) -> str | None:
    m = NESTED.match(normalise(item))
    return m.group(1) if m else None


def _computed_rows(stages: list[dict], code: str) -> list[dict]:
    out = []
    for stage in stages or []:
        if stage.get("code") != code or not stage.get("table"):
            continue
        for row in stage["table"]["rows"]:
            if len(row) >= 3 and isinstance(row[2], (int, float)):
                out.append({"item": str(row[0]), "label": str(row[1]), "amount": int(row[2])})
    return out


def compare_part(computed: list[dict], filed: list[dict]) -> dict:
    """One part, paired on line number, with everything that did not pair."""
    by_item: dict[str, dict] = {}
    for row in filed:
        by_item.setdefault(normalise(row.get("item")), {
            "item": row.get("item"), "label": row.get("label") or "",
            "amount": _amount(row.get("amount"))})

    # A second index on the bare nested form, used only when the exact line
    # number misses, so a difference in how deeply the two sides number a row
    # never reads as a missing line.
    by_alias = {nested_alias(k) or k: v for k, v in by_item.items()}

    rows, seen = [], set()
    agreed = differing = 0
    for c in computed:
        key = normalise(c["item"])
        f = by_item.get(key)
        if f is None:
            alias = nested_alias(c["item"])
            if alias and alias in by_item:
                key, f = alias, by_item[alias]
            elif alias and alias in by_alias:
                f = by_alias[alias]
        if f is None:
            rows.append({"item": c["item"], "label": c["label"], "computed": c["amount"],
                         "filed": None, "difference": None, "state": "not_in_filed"})
            continue
        seen.add(key)
        # A sign convention differs between the two: the tool shows a deduction
        # as negative because it is subtracting it, the return prints the
        # amount being deducted. Compare on size, and say so when only the
        # sign differs.
        diff = c["amount"] - f["amount"]
        if abs(diff) <= TOLERANCE:
            state = "agrees"
            agreed += 1
        elif abs(abs(c["amount"]) - abs(f["amount"])) <= TOLERANCE:
            # The same figure with the opposite sign: this tool shows a
            # deduction as negative because it is subtracting it, the return
            # prints the amount being deducted. Nothing is in dispute, so the
            # difference column must not shout a number twice the size of the
            # line and contradict the verdict beside it.
            state, diff = "sign_only", 0
            agreed += 1
        else:
            state = "differs"
            differing += 1
        rows.append({"item": c["item"], "label": c["label"], "computed": c["amount"],
                     "filed": f["amount"], "filed_label": f["label"],
                     "difference": diff, "state": state})

    extra = [{"item": f["item"], "label": f["label"], "computed": None,
              "filed": f["amount"], "difference": None, "state": "not_in_computed"}
             for key, f in by_item.items() if key not in seen]

    return {
        "rows": rows + extra,
        "counts": {
            "agrees": agreed,
            "differs": differing,
            "not_in_filed": sum(1 for r in rows if r["state"] == "not_in_filed"),
            "not_in_computed": len(extra),
        },
    }


# The final position is the form's own arithmetic: tax, less relief, plus
# interest and fee, less what is already paid. So the difference between two
# returns' final positions is the sum of the differences on those four lines,
# and nothing else. Each is given with the lines under it that moved, which is
# where a person starts looking.
#
#   (key, heading, the line that carries it, its effect on what is payable,
#    the lines beneath it, the part those lines sit on)
CAUSES = (
    ("tax", "Tax on total income", "5", +1,
     ("1", "2", "3v", "4e", "5d", "12c"), "Part B-TI"),
    ("relief", "Relief under sections 89, 90, 90A and 91", "6d", -1,
     ("6a", "6b", "6c"), "Part B-TTI"),
    ("interest", "Interest and fee", "8e", +1,
     ("8a", "8b", "8c", "8d"), "Part B-TTI"),
    ("paid", "Taxes already paid", "10e", -1,
     ("10a", "10b", "10c", "10d"), "Part B-TTI"),
)


def _paired(part: dict) -> dict[str, dict]:
    return {normalise(r["item"]): r for r in (part or {}).get("rows") or []
            if r.get("computed") is not None and r.get("filed") is not None}


def _gap(row: dict) -> int:
    """Computed less filed, on size: a deduction shown negative here and
    positive on the form is the same figure, not twice the figure apart."""
    return abs(row["computed"]) - abs(row["filed"])


def causes(parts: dict) -> dict | None:
    """Why the two final positions differ, as arithmetic that adds up.

    Returns None when either side lacks the lines the sum is built from: a
    partial explanation of a difference reads as a complete one.
    """
    tti, ti = _paired(parts.get("Part B-TTI")), _paired(parts.get("Part B-TI"))
    payable, refund = tti.get("11"), tti.get("12")
    if not payable or not refund:
        return None

    def position(side):
        return payable[side] - refund[side]

    difference = position("computed") - position("filed")
    out, explained = [], 0
    for key, label, line, sign, under, part in CAUSES:
        row = tti.get(normalise(line))
        if row is None:
            return None
        effect = sign * _gap(row)
        explained += effect
        index = ti if part == "Part B-TI" else tti
        detail = [{"item": r["item"], "label": r["label"], "computed": abs(r["computed"]),
                   "filed": abs(r["filed"]), "difference": _gap(r)}
                  for r in (index.get(normalise(i)) for i in under)
                  if r and abs(_gap(r)) > TOLERANCE]
        out.append({
            "key": key, "label": label, "line": row["item"], "part": part,
            "computed": abs(row["computed"]), "filed": abs(row["filed"]),
            "effect": effect, "detail": detail,
            # Said only where it is a fact about this tool rather than a
            # reading of the figures.
            "note": ("This tool does not compute interest under sections 234A, 234B and "
                     "234C or the fee under section 234F. The utility works them out, so "
                     "the filed return has them and this computation does not."
                     if key == "interest" and not row["computed"] and row["filed"] else ""),
        })

    return {
        "position": {
            "computed": position("computed"), "filed": position("filed"),
            "difference": difference,
        },
        "causes": out,
        # What the four lines do not account for: rounding to the nearest ten
        # under section 288B, or a line outside the four.
        "residual": difference - explained,
    }


def build(filed_doc: dict | None, cascade: dict, profile: dict | None = None) -> dict | None:
    """The whole comparison, or None when no filed return has been supplied."""
    data = (filed_doc or {}).get("data") or {}
    if not data.get("part_b_ti") and not data.get("part_b_tti"):
        return None

    stages = (cascade or {}).get("stages") or []
    # Part B-TTI includes line 10e, Total Taxes Paid, so this compares the
    # requested income, tax and paid-tax figures against the filed return.
    COMPARED = ("Part B-TI", "Part B-TTI")
    sources = {"Part B-TI": data.get("part_b_ti") or [],
               "Part B-TTI": data.get("part_b_tti") or []}
    parts = {name: compare_part(_computed_rows(stages, name), sources[name])
             for name in COMPARED}

    # Taxes paid, on its own. These lines are inside Part B-TTI above, but they
    # answer a different question from the rest of it -- not "is the tax right"
    # but "is the credit for what you have already paid right" -- and a credit
    # that is quietly missing is the one error that turns a refund into a
    # demand. It is worth its own heading rather than four rows among forty.
    def paid_lines(rows):
        return [r for r in rows if str(r.get("item") or "").lower().startswith("10")]

    tti_computed = _computed_rows(stages, "Part B-TTI")
    parts["Taxes paid"] = compare_part(paid_lines(tti_computed),
                                       paid_lines(sources["Part B-TTI"]))

    identity = data.get("identity") or {}
    warnings = []
    want_ay = str((profile or {}).get("ay") or "")
    got_ay = str(identity.get("assessment_year") or "")
    if want_ay and got_ay and normalise(got_ay) != normalise(want_ay):
        warnings.append(
            f"This filed return is for assessment year {got_ay}, and the profile is "
            f"{want_ay}. The comparison below sets two different years beside each other, "
            f"which is worth nothing until the right document is supplied.")
    if not identity.get("acknowledgement_number"):
        warnings.append(
            "The document carries no acknowledgement number, so there is nothing to show it "
            "was submitted. It may be a draft or a pre-filled JSON rather than a filed return.")
    if identity.get("revised"):
        warnings.append(
            "This is a revised return, which replaces the original entirely. Make sure it is "
            "the latest one filed for the year.")

    totals = sum(p["counts"]["differs"] for p in parts.values())
    unpaired = sum(p["counts"]["not_in_filed"] + p["counts"]["not_in_computed"]
                   for p in parts.values())
    return {
        "identity": identity,
        "warnings": warnings,
        "parts": parts,
        "differences": totals,
        "unpaired": unpaired,
        "causes": causes(parts),
        "schedules": data.get("schedules") or [],
        "note": ("Lines are paired on the number each side prints. A line that did not pair is "
                 "shown too: either the return has a line this tool does not produce, or this "
                 "tool produced a line the return does not have -- and the second is how a "
                 "wrong line number gets found."),
    }
