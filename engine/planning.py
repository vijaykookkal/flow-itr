"""How the tax grows with income: the curve the Planning page draws.

Every point is the return's own computation run on a plain income -- all of
it ordinary income at slab rates, for a resident individual -- with the
rebate, the surcharge, the marginal relief on both, and cess applied exactly
as they are for the return itself (cascade.tax_on_slices and
cascade.rebate_and_surcharge). Nothing here has a tax rule of its own, so the
curve cannot drift from the computation it illustrates.

What the curve leaves out is said on the page: capital gains at special
rates, deductions and set-offs. Income on the axis is taxable income, after
all of those.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from . import cascade
from .compute import RatesUnavailable, load_rates

TOP = 15_000_000          # Rs 1.5 crore: past the first two surcharge thresholds
STEP = 25_000             # a point every Rs 25,000, and more where the tax turns


def planning_rates(ay: str):
    """(rates, assumed_from): the year's own rate table, or -- for a year whose
    Finance Act is not built in yet, which is exactly the year one plans in --
    the latest table there is, with the year it belongs to, so the page can
    say plainly that the plan borrows it. A return is never computed this
    way; only a plan is."""
    try:
        return load_rates(ay), None
    except RatesUnavailable:
        have = sorted(f.stem for f in (Path(__file__).parent / "rates").glob("ay*.py"))
        if not have:
            raise
        latest = have[-1]                       # e.g. "ay2026_27"
        assumed = f"{latest[2:6]}-{latest[7:9]}"
        return load_rates(assumed), assumed


def tax_at(income: int, rates, regime: str, age_band: str) -> dict:
    """Tax on `income`, all of it at slab rates, split the way the page shows it."""
    sliced = cascade.tax_on_slices(income, [], rates, regime, age_band)
    final = cascade.rebate_and_surcharge(
        sliced["slab_tax"], 0, income, rates, regime,
        tax_at_threshold=lambda cut: cascade.tax_with_income_cut(income, [], rates, regime,
                                                                 age_band, cut))
    return {"tax": final["after_rebate"], "surcharge": final["surcharge"], "cess": final["cess"],
            "rebate_relief": final["rebate_marginal_relief"],
            "surcharge_relief": final["surcharge_marginal_relief"]}


def _relief_ends(start: int, kind: str, rates, regime: str, age_band: str) -> int:
    """The first income past `start` where this marginal relief has run out.

    Relief shrinks as income rises (the tax grows by less than the income), so
    a binary search finds the rupee where it reaches nothing."""
    gone = lambda n: tax_at(n, rates, regime, age_band)[kind] == 0  # noqa: E731
    lo, hi = start + 1, start + 2_000_000
    if gone(lo):
        return start
    while not gone(hi):
        hi += 2_000_000
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if gone(mid):
            hi = mid
        else:
            lo = mid
    return hi


def _kept(income: int, rates, regime: str, age_band: str) -> int:
    t = tax_at(income, rates, regime, age_band)
    return income - t["tax"] - t["surcharge"] - t["cess"]


def _keeps_less_until(floor: int, relief_ends: int, rates, regime: str, age_band: str) -> int:
    """The income past `floor` from which you again keep at least what you
    kept at `floor`.

    Inside a relief zone every extra rupee becomes tax, and cess adds 4% on
    top, so what you keep falls. Past the zone it rises again, and this is
    where it has climbed back."""
    target = _kept(floor, rates, regime, age_band)
    lo, hi = relief_ends, relief_ends + 2_000_000
    if _kept(lo, rates, regime, age_band) >= target:
        return lo
    while _kept(hi, rates, regime, age_band) < target:
        hi += 2_000_000
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if _kept(mid, rates, regime, age_band) >= target:
            hi = mid
        else:
            lo = mid
    return hi


def relief_zones(rates, regime: str, age_band: str, top: int = TOP) -> list[dict]:
    """Where crossing a threshold costs every extra rupee until relief runs
    out, and how far past it you keep less than you did at the threshold."""
    zones = []
    rebate = rates.REBATE_87A_NEW if regime == "new" else rates.REBATE_87A_OLD
    # Marginal relief on the 87A rebate exists only in the new regime.
    if regime == "new" and rebate["income_ceiling"] < top:
        floor = rebate["income_ceiling"]
        zones.append({"kind": "rebate", "from": floor,
                      "to": _relief_ends(floor, "rebate_relief", rates, regime, age_band)})
    for floor, rate in (rates.SURCHARGE_NEW if regime == "new" else rates.SURCHARGE_OLD):
        if floor < top:
            zones.append({"kind": "surcharge", "rate": rate, "from": floor,
                          "to": _relief_ends(floor, "surcharge_relief", rates, regime, age_band)})
    for z in zones:
        z["keeps_less_until"] = _keeps_less_until(z["from"], z["to"], rates, regime, age_band)
    return zones


@lru_cache(maxsize=16)
def curve(ay: str, age_band: str = "below_60", top: int = TOP) -> dict:
    """Both regimes' tax at every point from nothing to `top`, as columns.

    Points every STEP rupees, plus each threshold and the rupee past it, and
    a closer run of points through each marginal-relief zone, where the tax
    turns most sharply. Between points the tax is straight enough to draw."""
    rates, assumed = planning_rates(ay)
    start = int(ay[:4]) - 1
    out = {"ay": ay, "fy": f"{start}-{str(start + 1)[-2:]}", "rates_ay": assumed or ay,
           "rates_fy": rates.FY, "rates_assumed": bool(assumed),
           "age_band": age_band, "top": top, "regimes": {}}
    for regime in ("new", "old"):
        zones = relief_zones(rates, regime, age_band, top)
        slabs = (rates.SLABS_OLD_BY_AGE.get(age_band, rates.SLABS_OLD)
                 if regime == "old" else rates.SLABS_NEW)
        rebate = rates.REBATE_87A_NEW if regime == "new" else rates.REBATE_87A_OLD
        surcharge = rates.SURCHARGE_NEW if regime == "new" else rates.SURCHARGE_OLD
        points = set(range(0, top + 1, STEP))
        for edge in [c for c, _ in slabs if c] + [rebate["income_ceiling"]] + [f for f, _ in surcharge]:
            points.update({edge, edge + 1})
        for z in zones:
            points.update(z["from"] + (z["to"] - z["from"]) * i // 12 for i in range(13))
        cols = {"income": [], "tax": [], "surcharge": [], "cess": []}
        for income in sorted(p for p in points if 0 <= p <= top):
            t = tax_at(income, rates, regime, age_band)
            cols["income"].append(income)
            for key in ("tax", "surcharge", "cess"):
                cols[key].append(t[key])
        out["regimes"][regime] = {
            **cols,
            "rebate_ceiling": rebate["income_ceiling"],
            "surcharge_bands": [{"from": f, "rate": r} for f, r in surcharge if f < top],
            "relief_zones": zones,
        }
    return out


def position(ay: str, age_band: str, summary: dict | None) -> dict:
    """Where the return itself sits on each regime's curve.

    The curve taxes every rupee at slab rates; the return may have capital
    gains at special rates too, so its own tax is given beside the curve's."""
    rates, _ = planning_rates(ay)
    out = {}
    for regime, computed in ((summary or {}).get("regimes") or {}).items():
        totals = (computed.get("cascade") or {}).get("totals") or {}
        income = int(totals.get("total_income") or 0)
        if regime not in ("new", "old") or income <= 0:
            continue
        t = tax_at(income, rates, regime, age_band)
        out[regime] = {"income": income, "tax": t["tax"], "surcharge": t["surcharge"], "cess": t["cess"],
                       "special_total": int(totals.get("special_total") or 0),
                       "actual_tax": int(totals.get("total_tax_liability") or 0)}
    return out
