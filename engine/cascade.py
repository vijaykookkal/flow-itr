"""The computation as the return itself runs it, stage by stage, with reasons.

A single "total tax" figure is unreviewable. What a person checking a return
needs is the order the Act works in: losses set off within a head, then across
heads, then brought forward; the heads totalled into Part B-TI; deductions
against the slab-rate pile only; each slice taxed at its own rate; then rebate,
surcharge and cess; then the credits already paid.

So this module produces *stages*. Each stage carries its own table, the ITR
line numbers where the return has them, and a trace: short notes saying what
happened and under which section. The notes are written here, in code, next to
the rule they describe -- they are not an engine's commentary on its own work.

The rules that live here and nowhere else in this project:

  * losses are allocated against the *highest-taxed* gain first, because that
    is worth the most, and long-term losses are placed before short-term ones
    because they have fewer places to go (s.70, s.74);
  * the section 87A rebate does not reach tax on capital gains;
  * unused basic exemption may be set against special-rate gains -- for a
    resident, which is everyone this tool serves;
  * marginal relief, both on the rebate and on surcharge;
  * surcharge on capital gains is capped at 15%.
"""

from __future__ import annotations

from . import fx  # noqa: F401  (kept so rates and conversion travel together)
from . import setoff

SURCHARGE_CAP_ON_CG = 0.15
RUPEE = "Rs"


def pos(n) -> int:
    return max(0, int(n or 0))


def money(n) -> str:
    return f"{RUPEE} {int(n or 0):,}"


def basic_exemption(rates, regime: str, age_band: str) -> int:
    """The first slab band's ceiling: income below it bears no tax."""
    slabs = (rates.SLABS_OLD_BY_AGE.get(age_band, rates.SLABS_OLD)
             if regime == "old" else rates.SLABS_NEW)
    for ceiling, rate in slabs:
        if rate == 0:
            return int(ceiling or 0)
    return 0


def slab_bands(income: int, slabs) -> list[dict]:
    """Each band the income actually reaches, with the tax it bears."""
    out, lower = [], 0
    for ceiling, rate in slabs:
        if income <= lower:
            break
        top = min(income, ceiling if ceiling else income)
        slice_ = top - lower
        if slice_ > 0 and rate > 0:
            out.append({"from": lower, "to": top, "rate": rate,
                        "tax": int(round(slice_ * rate))})
        lower = ceiling if ceiling else top
        if not ceiling:
            break
    return out


def slab_ladder(income: int, slabs) -> list[dict]:
    """Every band the income reaches, the untaxed first one included.

    slab_bands() leaves out a band that bears no tax, which is right for adding
    up the tax and wrong for a picture of where the income sits."""
    out, lower = [], 0
    for ceiling, rate in slabs:
        if income <= lower:
            break
        top = min(income, ceiling if ceiling else income)
        if top > lower:
            out.append({"from": lower, "to": top, "amount": top - lower, "rate": rate,
                        "tax": int(round((top - lower) * rate)),
                        # Where the band itself ends, which the income may not reach.
                        "ceiling": ceiling})
        lower = ceiling if ceiling else top
        if not ceiling:
            break
    return out


def marginal_rate(income: int, slabs) -> float:
    for ceiling, rate in slabs:
        if not ceiling or income < ceiling:
            return rate
    return slabs[-1][1]


# --------------------------------------------------------------------------
# Stage 1 -- set-off within each head (section 70)
# --------------------------------------------------------------------------
def cg_buckets(cg: dict, slab_marginal: float) -> list[dict]:
    """Capital gains grouped as the Act taxes them, gains and losses apart.

    A bucket's net figure hides what matters for set-off: a bucket can hold
    both gains and losses, and only the gains can absorb another bucket's
    loss."""
    buckets: dict[tuple, dict] = {}
    for row in cg.get("rows", []):
        key = (row["section"], row["term"])
        b = buckets.setdefault(key, {
            "key": f"{row['section']}_{row['term']}",
            "section": row["section"], "term": row["term"],
            "rate": row.get("rate"), "gain": 0, "loss": 0, "rows": 0,
            "label": f"{'Long' if row['term'] == 'long' else 'Short'}-term, "
                     + ("slab rate" if row.get("rate") is None else f"section {row['section']}"),
        })
        if row["gain"] >= 0:
            b["gain"] += row["gain"]
        else:
            b["loss"] += -row["gain"]
        b["rows"] += 1
    for b in buckets.values():
        b["effective_rate"] = slab_marginal if b["rate"] is None else b["rate"]
    return sorted(buckets.values(), key=lambda b: (-b["effective_rate"], b["term"]))


def set_off_within_cg(buckets: list[dict], exemption_112a: int) -> dict:
    """Allocate capital losses against capital gains, dearest gain first.

    Long-term losses go first because they may only meet long-term gains;
    short-term losses reach either, so they are spent on whatever is left. A
    rupee of loss placed inside the section 112A exemption saves nothing, so
    that slice is filled last."""
    notes, moves = [], []
    targets = []
    for b in buckets:
        if b["gain"] <= 0:
            continue
        if b["section"] == "112A" and b["term"] == "long" and exemption_112a:
            taxable = max(0, b["gain"] - exemption_112a)
            if taxable:
                targets.append({"b": b, "avail": taxable, "rate": b["effective_rate"], "part": "taxable"})
            free = b["gain"] - taxable
            if free:
                targets.append({"b": b, "avail": free, "rate": 0.0, "part": "exempt"})
        else:
            targets.append({"b": b, "avail": b["gain"], "rate": b["effective_rate"], "part": None})

    long_loss = sum(b["loss"] for b in buckets if b["term"] == "long")
    short_loss = sum(b["loss"] for b in buckets if b["term"] == "short")
    for b in buckets:
        b["set_off"] = 0

    def spend(pool: int, name: str, eligible) -> int:
        left = pool
        for t in sorted([t for t in targets if eligible(t)], key=lambda t: -t["rate"]):
            if left <= 0:
                break
            use = min(left, t["avail"])
            if use <= 0:
                continue
            t["avail"] -= use
            t["b"]["set_off"] += use
            left -= use
            moves.append({"pool": name, "into": t["b"]["label"], "amount": use,
                          "rate": t["rate"], "part": t["part"]})
            if t["rate"] == 0:
                notes.append(
                    f"{money(use)} of {name} had to be set against the section 112A exempt "
                    f"slice, where no tax was due anyway, because no taxed gain was left to "
                    f"absorb it. It saves nothing.")
            else:
                notes.append(
                    f"{money(use)} of {name} set off against {t['b']['label']}, income taxed "
                    f"at {t['rate'] * 100:g}% -- the dearest gain available, so each rupee of "
                    f"loss buys the largest reduction.")
        return left

    long_left = spend(long_loss, "long-term capital loss", lambda t: t["b"]["term"] == "long")
    short_left = spend(short_loss, "short-term capital loss", lambda t: True)

    if long_loss and not long_left:
        notes.insert(0, "Long-term losses were placed before short-term ones: they may only "
                        "meet long-term gains, so they have the fewest options. (s.70(2), s.70(3))")
    if long_left:
        notes.append(f"{money(long_left)} of long-term capital loss found no long-term gain and "
                     f"is carried forward. It can never meet salary or business income. (s.74)")
    if short_left:
        notes.append(f"{money(short_left)} of short-term capital loss found no gain and is "
                     f"carried forward. (s.74)")
    if not long_loss and not short_loss:
        notes.append("No capital losses, so every gain passes through this stage unchanged.")

    return {"moves": moves, "notes": notes,
            "carry_forward": {"stcl": short_left, "ltcl": long_left},
            "net": [{**b, "net": b["gain"] - b["set_off"]} for b in buckets]}


# --------------------------------------------------------------------------
# Stage 2 -- set-off across heads (section 71)
# --------------------------------------------------------------------------
def set_off_across_heads(heads: list[dict], regime: str, rates) -> dict:
    """House-property, business and other-sources losses against other heads.

    Three rules decide this and each one bites: the new regime blocks a
    house-property loss from leaving its head at all; a business loss may not
    touch salary; and a speculative loss may not leave its own head even to
    meet other business income."""
    notes, moves = [], []
    blocked = {}

    pools = []
    for h in heads:
        if h["amount"] >= 0 or h["key"] in ("stcg", "ltcg"):
            continue
        loss = -h["amount"]
        if h["key"] == "house_property":
            if regime == "new":
                blocked["house_property"] = loss
                notes.append(
                    f"The house-property loss of {money(loss)} is blocked: the new regime bars "
                    f"it from being set against any other head. It is not destroyed -- it is "
                    f"carried forward to meet house-property income later. (s.115BAC(2)(i))")
                continue
            cap = 200_000
            usable = min(loss, cap)
            if loss > cap:
                blocked["house_property"] = loss - usable
                notes.append(
                    f"House-property loss is capped at {money(cap)} a year against other heads; "
                    f"{money(loss - usable)} of yours exceeds that and is carried forward. (s.71(3A))")
            pools.append({"key": "house_property", "name": "house-property loss",
                          "amount": usable, "may_touch_salary": True})
        elif h["key"] == "speculative":
            blocked["speculative"] = loss
            notes.append(
                f"The speculative (intraday) loss of {money(loss)} is ring-fenced: it cannot "
                f"meet any other income, not even your other business profit, and is carried "
                f"forward against future speculative profit only. (s.73(1))")
        elif h["key"] == "business":
            pools.append({"key": "business", "name": "business loss", "amount": loss,
                          "may_touch_salary": False})
        elif h["key"] == "other_sources":
            pools.append({"key": "other_sources", "name": "other-sources loss", "amount": loss,
                          "may_touch_salary": True})

    targets = [h for h in heads if h["amount"] > 0]
    for h in targets:
        h["absorbed"] = 0

    for pool in pools:
        left = pool["amount"]
        eligible = [h for h in targets
                    if h["amount"] - h["absorbed"] > 0
                    and (pool["may_touch_salary"] or h["key"] != "salary")]
        for h in sorted(eligible, key=lambda h: -h.get("rate", 0)):
            if left <= 0:
                break
            use = min(left, h["amount"] - h["absorbed"])
            if use <= 0:
                continue
            h["absorbed"] += use
            by = h.setdefault("absorbed_by", {})
            by[pool["key"]] = by.get(pool["key"], 0) + use
            left -= use
            moves.append({"pool": pool["name"], "into": h["label"], "amount": use})
            notes.append(f"{money(use)} of {pool['name']} set off against {h['label']}.")
        if left > 0:
            blocked[pool["key"]] = blocked.get(pool["key"], 0) + left
            notes.append(f"{money(left)} of {pool['name']} found no income to absorb it this "
                         f"year and is carried forward.")
        if pool["key"] == "business" and any(h["key"] == "salary" and h["amount"] > 0 for h in heads):
            notes.append("A business loss may go against any head except salary, so the salary "
                         "above it stays taxable. (s.71(2A))")

    if not pools and not blocked:
        notes.append("No head produced a loss that may travel to another head, so every figure "
                     "passes through unchanged.")
    return {"moves": moves, "notes": notes, "carry_forward": blocked,
            "total_set_off": sum(m["amount"] for m in moves)}


# --------------------------------------------------------------------------
# Stage 6 and 7 -- tax on each slice, then rebate, surcharge and cess
# --------------------------------------------------------------------------
def tax_on_slices(slab_income: int, specials: list[dict], rates, regime: str,
                  age_band: str) -> dict:
    """Slab ladder for ordinary income, own rate for each special slice.

    Any part of the basic exemption the ordinary income does not use may be set
    against special-rate gains. That is a resident's entitlement and it is easy
    to miss, because it never appears as a line anywhere in the return."""
    notes = []
    slabs = (rates.SLABS_OLD_BY_AGE.get(age_band, rates.SLABS_OLD)
             if regime == "old" else rates.SLABS_NEW)
    bands = slab_bands(slab_income, slabs)
    slab_liability = sum(b["tax"] for b in bands)
    for b in bands:
        notes.append(f"{money(b['to'] - b['from'])} between {money(b['from'])} and "
                     f"{money(b['to'])} at {b['rate'] * 100:g}% -> {money(b['tax'])}.")

    exemption = basic_exemption(rates, regime, age_band)
    spare = max(0, exemption - slab_income)
    if spare and specials:
        notes.append(
            f"Ordinary income of {money(slab_income)} leaves {money(spare)} of the "
            f"{money(exemption)} basic exemption unused. A resident may set that against "
            f"special-rate gains, so it is applied to the dearest of them first. "
            f"(proviso to s.111A(1) and s.112A(2))")
    elif spare:
        notes.append(f"{money(spare)} of the basic exemption is unused and there are no "
                     f"special-rate gains to place it against.")

    lines, special_tax = [], 0
    for s in sorted(specials, key=lambda s: -s["rate"]):
        taxable = pos(s["amount"])
        exempt_used = 0
        if s.get("exemption"):
            exempt_used = min(taxable, s["exemption"])
            taxable -= exempt_used
            notes.append(f"The first {money(exempt_used)} of {s['label']} is exempt. "
                         f"(s.112A(1))")
        used_bel = 0
        if spare and taxable:
            used_bel = min(spare, taxable)
            taxable -= used_bel
            spare -= used_bel
            notes.append(f"{money(used_bel)} of unused basic exemption applied to {s['label']}, "
                         f"saving {money(int(round(used_bel * s['rate'])))}.")
        tax = int(round(taxable * s["rate"]))
        special_tax += tax
        lines.append({**s, "exempt": exempt_used, "basic_exemption_used": used_bel,
                      "taxable": taxable, "tax": tax})

    return {"bands": bands, "ladder": slab_ladder(slab_income, slabs),
            "slab_tax": slab_liability, "special": lines,
            "special_tax": special_tax, "basic_exemption_spare": spare, "notes": notes}


def tax_with_income_cut(slab_income: int, specials: list[dict], rates, regime: str,
                        age_band: str, cut: int) -> tuple[int, int]:
    """(slab tax, special tax) had total income been `cut` rupees lower.

    Marginal relief on surcharge compares the tax on the actual income with
    the tax at the threshold, so the tax at the threshold has to be worked out.
    The rupees above the threshold are taken off ordinary income first, the
    slice at the margin, and only then off the cheapest special-rate slice."""
    left = max(0, int(cut))
    slab = max(0, slab_income - left)
    left -= slab_income - slab
    trimmed = []
    for s in sorted(specials, key=lambda s: s["rate"]):
        take = min(left, pos(s["amount"]))
        left -= take
        trimmed.append({**s, "amount": pos(s["amount"]) - take})
    at = tax_on_slices(slab, trimmed, rates, regime, age_band)
    return at["slab_tax"], at["special_tax"]


def rebate_and_surcharge(slab_tax: int, special_tax: int, total_income: int,
                         rates, regime: str, tax_at_threshold=None) -> dict:
    """Rebate (with marginal relief), then surcharge, then cess.

    Two things here are routinely got wrong. The section 87A rebate cannot
    reduce tax on capital gains taxed at a special rate, however low total
    income is. And surcharge on those gains is capped at 15% even when the rest
    of the income attracts a higher band.

    `tax_at_threshold(cut)` gives (slab tax, special tax) on the income less
    `cut`; marginal relief on surcharge needs it (see tax_with_income_cut)."""
    notes = []
    reb = rates.REBATE_87A_OLD if regime == "old" else rates.REBATE_87A_NEW
    rebate, relief = 0, 0
    if total_income <= reb["income_ceiling"]:
        rebate = min(slab_tax, reb["max_rebate"])
        if rebate:
            notes.append(f"Total income of {money(total_income)} is within the "
                         f"{money(reb['income_ceiling'])} limit, so a rebate of {money(rebate)} "
                         f"removes the tax on ordinary income. (s.87A)")
        if special_tax:
            notes.append(f"The rebate stops at your capital gains: {money(special_tax)} of tax "
                         f"on special-rate income survives it, whatever your total income.")
    elif regime == "new":
        over = total_income - reb["income_ceiling"]
        if slab_tax > over:
            relief = slab_tax - over
            rebate = relief
            notes.append(
                f"Total income is {money(over)} above the {money(reb['income_ceiling'])} "
                f"threshold, and without relief the tax would rise by more than the income. "
                f"Marginal relief caps it at {money(over)}, a saving of {money(relief)}. "
                f"(proviso to s.87A)")
        else:
            notes.append(f"Total income of {money(total_income)} is past the rebate threshold "
                         f"and beyond marginal relief. No rebate.")
    else:
        notes.append(f"Total income of {money(total_income)} is above the "
                     f"{money(reb['income_ceiling'])} rebate ceiling. No rebate.")

    after_rebate = max(0, slab_tax + special_tax - rebate)

    bands = rates.SURCHARGE_OLD if regime == "old" else rates.SURCHARGE_NEW
    rate, band_floor, rate_below = 0.0, 0, 0.0
    for floor, band_rate in bands:
        if total_income > floor:
            rate_below = rate
            rate, band_floor = band_rate, floor
    sur, sur_relief = 0, 0
    on_special, on_rest = 0, 0
    if rate:
        cg_rate = min(rate, SURCHARGE_CAP_ON_CG)
        tax_on_rest = max(0, slab_tax - rebate)
        on_special = int(round(special_tax * cg_rate))
        on_rest = int(round(tax_on_rest * rate))
        sur = on_rest + on_special
        notes.append(f"Total income crosses {money(band_floor)}, so surcharge applies at "
                     f"{rate * 100:g}%.")
        if special_tax and cg_rate < rate:
            notes.append(f"Surcharge on capital gains is capped at "
                         f"{SURCHARGE_CAP_ON_CG * 100:g}%, so {money(special_tax)} of "
                         f"capital-gains tax bears {cg_rate * 100:g}% rather than {rate * 100:g}%.")
        # Marginal relief: the tax and surcharge on the actual income may exceed
        # the tax and surcharge on an income of exactly the threshold by no more
        # than the income above the threshold. At the threshold the surcharge
        # is the band below's (nil at the first band). Every threshold is far
        # above the 87A ceiling, so no rebate enters either side.
        over = total_income - band_floor
        if tax_at_threshold is not None:
            slab_at, special_at = tax_at_threshold(over)
        else:                           # no way to recompute: assume the same tax
            slab_at, special_at = max(0, slab_tax - rebate), special_tax
        sur_at = (int(round(slab_at * rate_below))
                  + int(round(special_at * min(rate_below, SURCHARGE_CAP_ON_CG))))
        allowed = slab_at + special_at + sur_at + over
        excess = after_rebate + sur - allowed
        if excess > 0:
            sur_relief = min(sur, int(round(excess)))
            sur -= sur_relief
            notes.append(
                f"Marginal relief on surcharge of {money(sur_relief)}: at exactly "
                f"{money(band_floor)} the tax and surcharge would be "
                f"{money(slab_at + special_at + sur_at)}, and crossing it by {money(over)} "
                f"may not add more than {money(over)}. (proviso to the surcharge rates, "
                f"Finance Act)")

    cess = int(round((after_rebate + sur) * rates.CESS_RATE))
    notes.append(f"Health and education cess at {rates.CESS_RATE * 100:g}% on "
                 f"{money(after_rebate + sur)} -> {money(cess)}. It applies to every rupee of "
                 f"tax, with no threshold.")
    return {"rebate": rebate, "rebate_marginal_relief": relief, "after_rebate": after_rebate,
            "surcharge": sur, "surcharge_rate": rate, "surcharge_marginal_relief": sur_relief,
            "surcharge_on_special": on_special, "surcharge_on_rest": on_rest,
            "cess": cess, "total": after_rebate + sur + cess, "notes": notes}


# --------------------------------------------------------------------------
# the whole computation, stage by stage
# --------------------------------------------------------------------------
def head(key, label, amount, schedule, rate=0.0):
    return {"key": key, "label": label, "amount": int(amount or 0),
            "schedule": schedule, "rate": rate}


def build(docs: dict, rates, regime: str, profile: dict, parts: dict) -> dict:
    """The computation in the order the Act runs it.

    `parts` carries what compute.py has already worked out for this regime --
    the salary head, other sources, Chapter VI-A and the capital gains ledger --
    so the arithmetic is not done twice in two places.
    """
    age_band = (profile or {}).get("age_band", "below_60")
    slabs = (rates.SLABS_OLD_BY_AGE.get(age_band, rates.SLABS_OLD)
             if regime == "old" else rates.SLABS_NEW)
    stages = []

    salary_net = parts["salary"]["net"]
    os_net = parts["other_sources"]["net"]
    hp = _amount(docs.get("house_property"), "total_income_from_hp")
    # Schedule BP's own result, so the cascade and the tab can never disagree.
    schedule_bp = parts.get("business") or {}
    business = schedule_bp.get("ordinary", 0)
    speculative = schedule_bp.get("speculative", 0)
    vda_income = _amount(docs.get("vda"), "total_income")
    cg = parts["capital_gains"]

    rough = pos(salary_net) + pos(hp) + pos(business) + pos(speculative) + pos(os_net)
    slab_marginal = marginal_rate(rough, slabs)

    # ---- Stage 1: within each head -------------------------------------
    buckets = cg_buckets(cg, slab_marginal)
    within = set_off_within_cg(buckets, getattr(rates, "EXEMPTION_112A", 0))
    stages.append({
        "no": 1, "code": "s.70", "title": "Set-off within each head",
        "purpose": "A loss meets a gain of its own kind first, and the dearest gain first.",
        "table": {
            "columns": ["Capital gains bucket", "Gain", "Loss set off", "Net", "Rate"],
            "rows": [[b["label"], b["gain"], -b["set_off"] if b["set_off"] else 0,
                      b["gain"] - b["set_off"],
                      "slab" if b["rate"] is None else f"{b['rate'] * 100:g}%"]
                     for b in within["net"]],
        },
        "notes": within["notes"],
    })

    # ---- Stage 2: across heads -----------------------------------------
    heads = [
        head("salary", "Salaries", salary_net, "Schedule S", slab_marginal),
        head("house_property", "House property", hp, "Schedule HP", slab_marginal),
        head("business", "Business or profession", business, "Schedule BP", slab_marginal),
        head("speculative", "Speculative business", speculative, "Schedule BP", slab_marginal),
        head("other_sources", "Other sources", os_net, "Schedule OS", slab_marginal),
    ]
    cg_slab = sum(b["gain"] - b["set_off"] for b in within["net"] if b["rate"] is None)
    heads.append(head("stcg", "Capital gains at slab rate", cg_slab, "Schedule CG", slab_marginal))
    # Gains taxed at a special rate are still income a loss may be set against
    # -- a business loss or a loss brought forward does not stop at the slab
    # rate -- so each bucket stands as a head of its own, at its own rate.
    for b in within["net"]:
        if b["rate"] is None:
            continue
        special_head = head(f"cg:{b['key']}", b["label"], b["gain"] - b["set_off"],
                            "Schedule CG", b["rate"])
        special_head["term"], special_head["section"] = b["term"], b["section"]
        heads.append(special_head)
    across = set_off_across_heads(heads, regime, rates)
    stages.append({
        "no": 2, "code": "Schedule CYLA", "title": "Set-off across heads, this year",
        "purpose": "A loss that may leave its own head goes against the dearest income left.",
        "table": {
            "columns": ["Head", "Income", "Loss set off", "After set-off"],
            "rows": [[h["label"], h["amount"], -h.get("absorbed", 0) if h.get("absorbed") else 0,
                      h["amount"] - h.get("absorbed", 0) if h["amount"] > 0 else h["amount"]]
                     for h in heads if h["amount"] or h.get("absorbed")],
        },
        "notes": across["notes"],
    })

    # ---- Stage 3: brought forward --------------------------------------
    this_ay = getattr(rates, "AY", "2026-27")
    bf = setoff.apply_brought_forward(heads, parts.get("brought_forward") or [], this_ay, money)
    touched = [h for h in heads if h.get("bf") or h.get("bf_dep")]
    stages.append({
        "no": 3, "code": "Schedule BFLA", "title": "Losses brought forward",
        "purpose": "Losses carried from earlier years, against this year's income.",
        "table": {
            "columns": ["Head", "After this year's set-off", "Loss brought forward",
                        "Depreciation brought forward", "Remaining"],
            "rows": [[h["label"], h["amount"] - h.get("absorbed", 0), -h["bf"], -h["bf_dep"],
                      h["amount"] - h.get("absorbed", 0) - h["bf"] - h["bf_dep"]]
                     for h in touched],
        } if touched else None,
        "notes": bf["notes"],
        "skipped": not bf["entries"],
    })

    # ---- Stage 4: Part B-TI --------------------------------------------
    # `gross` is each head before any loss from another head or another year
    # is set against it: what lines 1 to 5 of Part B-TI print. `after` is what
    # is left once this year's and earlier years' losses have been set off,
    # which is what is actually taxed.
    gross = {h["key"]: pos(h["amount"]) for h in heads}
    after = {h["key"]: (h["amount"] - h.get("absorbed", 0) - h.get("bf", 0) - h.get("bf_dep", 0))
             for h in heads}
    specials = []
    for b in within["net"]:
        if b["rate"] is None:
            continue
        specials.append({"key": b["key"], "label": b["label"], "rate": b["rate"],
                         "section": b["section"], "term": b["term"],
                         "amount": after.get(f"cg:{b['key']}", 0),
                         "exemption": getattr(rates, "EXEMPTION_112A", 0)
                                      if b["section"] == "112A" else 0,
                         "schedule": "Schedule CG"})
    if vda_income:
        specials.append({"key": "vda", "label": "Virtual digital assets",
                         "rate": getattr(rates, "VDA_RATE", 0.30), "amount": vda_income,
                         "section": "115BBH", "term": None,
                         "exemption": 0, "schedule": "Schedule VDA"})

    special_total = sum(pos(s["amount"]) for s in specials)
    # Line 6: every head before set-off, the way lines 1 to 5 print them.
    heads_total = sum(gross.values()) + pos(vda_income)
    via = parts["chapter_via"]["total_allowed"]
    ordinary = (pos(after["salary"]) + pos(after["house_property"]) + pos(after["business"])
                + pos(after["speculative"]) + pos(after["other_sources"]) + pos(after["stcg"]))
    via_usable = min(via, ordinary)
    via_wasted = via - via_usable
    gti = ordinary + special_total
    total_income = int(round((ordinary - via_usable + special_total) / 10.0) * 10)
    slab_income = int(round((ordinary - via_usable) / 10.0) * 10)

    # The form's own lines, in its own words and numbering, taken from a filed
    # ITR-3 for this assessment year rather than from memory. The earlier
    # version of this table was reconstructed and several lines were wrong:
    # business was cited to A38 rather than A37, the capital-gains sub-lines
    # were numbered from item 9 of Schedule CG rather than item 8, and virtual
    # digital assets were put under Other Sources when the form carries them at
    # 4d, inside Capital Gains.
    cg_heads = [h for h in heads if h["key"].startswith("cg:")]
    st_special = sum(gross[h["key"]] for h in cg_heads if h.get("term") == "short")
    lt_special = sum(gross[h["key"]] for h in cg_heads if h.get("term") == "long")
    st_slab = gross["stcg"]
    st_total = st_special + st_slab
    cg_pre_vda = st_total + lt_special
    vda_special = sum(pos(x["amount"]) for x in specials if x.get("term") is None)
    cg_total = cg_pre_vda + vda_special
    os_normal = gross["other_sources"]
    business_total = gross["business"] + gross["speculative"]
    cyla = across["total_set_off"]
    carried = sum(v for v in {**within["carry_forward"],
                              **across["carry_forward"]}.values() if v)

    stages.append({
        "no": 4, "code": "Part B-TI", "title": "Computation of total income",
        "purpose": "Each head, the two rounds of set-off, then deductions -- the order the "
                   "return itself runs, under its own line numbers.",
        "table": {
            "columns": ["Line", "Part B-TI", "Amount"],
            "rows": [
                ["1", "Salaries (6 of Schedule S)", gross["salary"]],
                ["2", "Income from house property (3 of Schedule-HP) (enter nil if loss)",
                 gross["house_property"]],
                ["3i", "Profit and gains from business other than speculative business and "
                       "specified business (A37 of Schedule-BP) (enter nil if loss)",
                 gross["business"]],
                ["3ii", "Profit and gains from speculative business (3(ii) of table E of "
                        "Schedule BP) (enter nil if loss and take the figure to schedule CFL)",
                 gross["speculative"]],
                ["3iii", "Profit and gains from specified business (3(iii) of Table E of "
                         "Schedule BP) (enter nil if loss and take the figure to schedule CFL)", 0],
                ["3iv", "Income chargeable to tax at special rates (3e, 3f & 3g of Schedule BP)", 0],
                ["3v", "Total (3i + 3ii + 3iii + 3iv) (enter nil if 3v is a loss)", business_total],
                ["4ai", "Short-term chargeable @ 20% (8ii of item E of schedule CG)", st_special],
                ["4aii", "Short-term chargeable @ 30% (8iii of item E of schedule CG)", 0],
                ["4aiii", "Short-term chargeable at applicable rate (8iv of item E of schedule CG)",
                 st_slab],
                ["4aiv", "Short Term chargeable at special rates as per DTAA (8v of item E of "
                         "Schedule CG)", 0],
                ["4av", "Total Short-term (ai + aii + aiii + aiv)", st_total],
                ["4bi", "Long-term chargeable @ 12.5% (8vi of item E of schedule CG)", lt_special],
                ["4bii", "Long Term chargeable at special rates in india as per DTAA (8vii of "
                         "item E of Schedule CG)", 0],
                ["4biii", "Total Long-Term (bi + bii) (enter nil if loss)", lt_special],
                ["4c", "Sum of Short-term/Long-term Capital Gains (4av + 4biii) (enter nil if loss)",
                 cg_pre_vda],
                ["4d", "Capital gain chargeable @ 30% u/s 115BBH (C2 of schedule CG)", vda_special],
                ["4e", "Total capital gains (4c + 4d)", cg_total],
                ["5a", "Net Income from Other sources chargeable to tax at Normal Applicable "
                       "rates (6 of Schedule OS) (enter nil if loss)", os_normal],
                ["5b", "Income chargeable to tax at special rate (2 of Schedule OS)", 0],
                ["5c", "Income from the activity of owning & maintaining race horses (8e of "
                       "Schedule OS) (enter nil if loss)", 0],
                ["5d", "Total (5a + 5b + 5c) (enter nil if loss)", os_normal],
                ["6", "Total of Head Wise Income (1 + 2 + 3v + 4e + 5d)", heads_total],
                ["7", "Losses of current year to be set off against 6 (total of 2xvi, 3xvi and "
                      "4xvi of Schedule CYLA)", -cyla],
                ["8", "Balance after set off current year losses (6 - 7)", heads_total - cyla],
                ["9", "Brought forward losses to be set off against 8 (total of 2xv, 3xv and "
                      "4xv of Schedule BFLA)", -bf["total"]],
                ["10", "Gross Total income (8 - 9)", gti],
                ["11", "Income chargeable to tax at special rate under section 111A, 112, 112A "
                       "etc. included in 10", special_total],
                ["12a", "Part-B, CA and D of Chapter VI-A [(1 + 3) of Schedule VI-A]", -via_usable],
                ["12b", "Part-C of Chapter VI-A [2 of Schedule VI-A]", 0],
                ["12c", "Total (12a + 12b) [limited upto (10 - 11)]", -via_usable],
                ["13", "Deduction u/s 10AA (c of Sch. 10AA)", 0],
                ["14", "Total income (10 - 12c - 13)", total_income],
                ["15", "Income which is included in 14 and chargeable to tax at special rates "
                       "(total of (i) of schedule SI)", special_total],
                ["16", "Net agricultural income for rate purpose (2v of Schedule EI)", 0],
                ["17", "'Aggregate income' (14 - 15 + 16) [applicable if (14 - 15) exceeds "
                       "maximum amount not chargeable to tax]", slab_income],
                ["18", "Losses of current year to be carried forward (total of row xix of "
                       "Schedule CFL)", carried],
                ["19", "Deemed income under section 115JC (3 of Schedule AMT)", 0],
            ],
        },
        "notes": [
            "Line 12c is why deductions cannot touch capital gains: the form itself limits "
            "Chapter VI-A to line 10 less line 11 -- gross total income once every "
            "special-rate gain is taken out -- so no arrangement of figures gets around it.",
            f"Line 14 is the figure the section 87A rebate ceiling and every surcharge "
            f"threshold are tested against: {money(total_income)}.",
            "The line numbers and wording here are taken from a filed ITR-3 for this "
            "assessment year, not reconstructed. They still move between years, so check "
            "them against the utility you are filing with.",
        ] + ([f"{money(via_wasted)} of allowable deductions has nowhere to go: deductions bite "
              f"only on ordinary income, and yours has run out."] if via_wasted else []),
    })

    # ---- Stage 5: Chapter VI-A -----------------------------------------
    stages.append({
        "no": 5, "code": "Schedule VI-A", "title": "Deductions",
        "purpose": "Chapter VI-A reduces the ordinary pile, and only that pile.",
        "table": {
            "columns": ["Section", "Claimed", "Allowed", "Why"],
            "rows": [[line.get("section", ""), line.get("claimed", 0), line.get("allowed", 0),
                      line.get("why", "")] for line in parts["chapter_via"]["lines"]],
        } if parts["chapter_via"]["lines"] else None,
        "notes": ([] if parts["chapter_via"]["lines"] else
                  ["Nothing is claimed under Chapter VI-A."])
                 + ([f"The new regime withdraws most of Chapter VI-A; only employer NPS under "
                     f"80CCD(2) and a few niche items survive. Planning therefore happens in the "
                     f"set-off stages above, not here."] if regime == "new" else []),
        "skipped": not parts["chapter_via"]["lines"],
    })

    # ---- Stage 6: tax on each slice ------------------------------------
    sliced = tax_on_slices(slab_income, specials, rates, regime, age_band)
    stages.append({
        "no": 6, "code": "Schedule SI", "title": "Tax on each slice",
        "purpose": "Ordinary income climbs the slab ladder; each special slice pays its own rate.",
        "table": {
            "columns": ["Slice", "Amount", "Exempt", "Basic exemption used", "Taxed", "Rate", "Tax"],
            "rows": [["Ordinary income (slab ladder)", slab_income, 0, 0, slab_income,
                      "slab", sliced["slab_tax"]]]
                    + [[s["label"], s["amount"], s["exempt"], s["basic_exemption_used"],
                        s["taxable"], f"{s['rate'] * 100:g}%", s["tax"]]
                       for s in sliced["special"]],
        },
        # The same ladder band by band, for drawing: where the ordinary income
        # sits and what each band of it bears.
        "ladder": sliced["ladder"],
        "notes": sliced["notes"],
    })

    # ---- Stage 7: rebate, surcharge, cess ------------------------------
    final = rebate_and_surcharge(
        sliced["slab_tax"], sliced["special_tax"], total_income, rates, regime,
        tax_at_threshold=lambda cut: tax_with_income_cut(slab_income, specials, rates, regime,
                                                         age_band, cut))
    sur_before = final["surcharge"] + final["surcharge_marginal_relief"]
    stages.append({
        "no": 7, "code": "Part B-TTI", "title": "Tax payable on total income",
        "purpose": "What the slab and special-rate tax becomes once the rebate, surcharge and "
                   "cess are applied.",
        "table": {
            "columns": ["Line", "Part B-TTI", "Amount"],
            "rows": [
                ["1a", "Tax payable on deemed total income under section 115JC "
                       "(4 of Schedule AMT)", 0],
                ["1b", "Surcharge on (a) (if applicable)", 0],
                ["1c", "Health and Education Cess on (1a + 1b) above", 0],
                ["1d", "Total Tax Payable on deemed total income (1a + 1b + 1c)", 0],
                ["2a", "Tax at normal rates on 17 of Part B-TI", sliced["slab_tax"]],
                ["2b", "Tax at special rates (total of col (ii) of Schedule-SI)",
                 sliced["special_tax"]],
                ["2c", "Rebate on agricultural income [applicable if (14 - 15) of Part B-TI "
                       "exceeds maximum amount not chargeable to tax]", 0],
                ["2d", "Tax Payable on Total Income (2a + 2b - 2c)",
                 sliced["slab_tax"] + sliced["special_tax"]],
                ["2e", "Rebate u/s 87A", -final["rebate"]],
                ["2f", "Tax Payable after Rebate (2d - 2e)", final["after_rebate"]],
                ["Ai", "Surcharge computed before marginal relief: 25% of 16(ii) of "
                         "schedule SI", 0],
                ["Aii", "Surcharge computed before marginal relief: 10% or 15%, as "
                          "applicable, on the balance", sur_before],
                ["Bi", "Surcharge after marginal relief: 25% of 16(ii) of schedule SI", 0],
                ["Bii", "Surcharge after marginal relief: 10% or 15%, as applicable, on the "
                          "balance", final["surcharge"]],
                ["2giv", "Total surcharge", final["surcharge"]],
                ["2h", "Health and Education Cess on (2f + 2giv)", final["cess"]],
                ["2i", "Gross tax liability (2f + 2giv + 2h)", final["total"]],
                ["3", "Gross tax payable (higher of 1d and 2i)", final["total"]],
            ],
        },
        "notes": final["notes"],
    })

    # ---- Stage 8: what is already paid ---------------------------------
    paid = parts.get("taxes_paid", 0)
    split = parts.get("taxes_paid_split") or {
        "advance": 0, "tds": paid, "tcs": 0, "self_assessment": 0, "total": paid}
    # Relief for tax paid abroad (Schedule TR). It can never exceed the tax it
    # is being set against, and it comes off before the credits already paid.
    relief_90 = min(pos(parts.get("relief_90", 0)), final["total"])
    net_liability = final["total"] - relief_90
    balance = net_liability - paid
    carry = {**within["carry_forward"], **across["carry_forward"]}
    stages.append({
        "no": 8, "code": "Part B-TTI", "title": "Taxes paid, and what is left",
        "purpose": "The credits already with the department, and the cheque or the refund.",
        "table": {
            "columns": ["Line", "Part B-TTI", "Amount"],
            "rows": [
                ["3a", "Tax on income without including income on perquisites referred in "
                       "section 17(2)(vi) received from employer, being an eligible start-up "
                       "referred to in section 80-IAC", final["total"]],
                ["3b", "Tax deferred - relatable to income on perquisites referred in section "
                       "17(2)(vi)", 0],
                ["3c", "Tax deferred from earlier years but payable during current AY", 0],
                ["4", "Credit under section 115JD of tax paid in earlier years "
                      "(5 of Schedule AMTC)", 0],
                ["5", "Tax payable after credit under section 115JD (3a + 3c - 4)", final["total"]],
                ["6a", "Section 89 (Please ensure to submit Form 10E to claim this relief)", 0],
                ["6b", "Section 90 / Section 90A (2 of Schedule TR)", relief_90],
                ["6c", "Section 91 (3 of Schedule TR)", 0],
                ["6d", "Total (6a + 6b + 6c)", relief_90],
                ["7", "Net tax liability (5 - 6d) (enter zero if negative)", net_liability],
                ["8a", "Interest for default in furnishing the return (section 234A)", 0],
                ["8b", "Interest for default in payment of advance tax (section 234B)", 0],
                ["8c", "Interest for deferment of advance tax (section 234C)", 0],
                ["8d", "Fee for default in furnishing return of income (section 234F)", 0],
                ["8e", "Total Interest and Fee Payable (8a + 8b + 8c + 8d + 8da)", 0],
                ["9", "Aggregate liability (7 + 8e)", net_liability],
                # The form prints taxes paid as a positive figure and does the
                # subtraction at 11 and 12. Showing it negative here made every
                # comparison against a filed return read as a difference twice
                # the size of the credit.
                ["10a", "Advance Tax (from column 5 of 17A)", split["advance"]],
                ["10b", "TDS (total of column 5 of 17B and column 9 of 17C)", split["tds"]],
                ["10c", "TCS (column 7 of 17D)", split["tcs"]],
                ["10d", "Self Assessment Tax (from column 5 of 17A)",
                 split["self_assessment"]],
                ["10e", "Total Taxes Paid (10a + 10b + 10c + 10d)", paid],
                ["11", "Amount payable (Enter if 9 is greater than 10e, else enter 0)",
                 max(0, balance)],
                ["12", "Refund (If 10e is greater than 9)", max(0, -balance)],
            ],
        },
        "notes": [
            "Lines 10a to 10d come from the Taxes Paid tab, which is where the challan and "
            "certificate details the utility asks for also live. Self-assessment tax paid at "
            "the moment of filing cannot appear in any statement downloaded beforehand, so a "
            "nil at 10d is worth checking against your own bank record rather than trusted.",
            "Lines 8a to 8d are nil because this tool does not compute interest under sections "
            "234A, 234B or 234C, or the fee under section 234F. The e-filing utility works "
            "them out once the return is complete; enter what it says.",
            (f"Line 6b is {money(relief_90)}: the relief Schedule TR works out for tax "
             f"withheld abroad, the lower of that tax and the Indian tax on the same income. "
             f"It stands only if Form 67 was filed before the return."
             if relief_90 else
             "Line 6b is nil because Schedule TR has no relief to bring here: either no tax "
             "withheld abroad is recorded against any foreign receipt, or there is no foreign "
             "income. The Foreign Income tab says which."),
        ] + ([f"{money(sum(carry.values()))} of losses is carried to next year: "
              + "; ".join(f"{k.replace('_', ' ')} {money(v)}" for k, v in carry.items() if v)
              + ". They survive only in a return filed by the due date."]
             if any(carry.values()) else []),
    })

    return {
        "stages": stages,
        "totals": {
            "gross_total_income": gti,
            "total_income": total_income,
            "slab_income": slab_income,
            "special_total": special_total,
            "tax_at_slab": sliced["slab_tax"],
            "tax_at_special": sliced["special_tax"],
            "rebate_87a": final["rebate"],
            "surcharge": final["surcharge"],
            "cess": final["cess"],
            "total_tax_liability": final["total"],
            "relief_90": relief_90,
            "net_tax_liability": net_liability,
            "taxes_paid": paid,
            "payable": max(0, balance),
            "refund": max(0, -balance),
        },
        "carry_forward": carry,
        "setoff": setoff.schedules(heads, within, across, bf, this_ay),
    }


def _amount(doc, field) -> int:
    node = ((doc or {}).get("data") or {}).get(field)
    if isinstance(node, dict):
        return int(node.get("amount") or 0)
    return int(node or 0)
