"""Turning an amount stated in a foreign currency into rupees.

The extraction never converts. A foreign statement says USD 6,052.54 and that
is what gets recorded -- `currency` and `amount_foreign` on the money object,
with `amount` left out -- because the rate is a rule of law, not something to
estimate from a document.

The rule applied here is Rule 115 of the Income-tax Rules: the telegraphic
transfer buying rate of the State Bank of India, taken on the date the rule
fixes. For capital gains that is the last day of the month immediately
preceding the month in which the asset was transferred.

Rule 115 converts "income" and says nothing about the cost side. This tool is
for residents, who are taxed on the rupee gain, so the cost is converted at the
rate on the acquisition date (engine/capital_gains.py). For shares from an
employee stock plan, section 49(2AA) makes the cost the perquisite value
already taxed as salary -- a rupee figure from the employer's records, used as
stated when the documents give it.
"""

from __future__ import annotations

import calendar
import json
from datetime import date, timedelta
from pathlib import Path

# Published rates that ship with the program, if any: read, never written.
SEED_FILE = Path(__file__).resolve().parents[1] / "config" / "fx_rates.json"


def rates_file() -> Path:
    """Where looked-up and typed-in rates are kept: the Flow home, not the
    repository. Which dates were needed says when someone bought and sold."""
    from server import paths

    return paths.home() / "fx_rates.json"


def _read(path: Path) -> dict:
    try:
        data = json.loads(path.read_text("utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def load_rates() -> dict:
    """Rates by currency and date. Your own file wins over the shipped one."""
    rates: dict = {}
    for data in (_read(SEED_FILE), _read(rates_file())):
        for currency, by_date in data.items():
            if not currency.startswith("_") and isinstance(by_date, dict):
                rates.setdefault(currency, {}).update(by_date)
    return rates


def rule115_date(transferred: date) -> date:
    """Last day of the month immediately preceding the month of transfer."""
    first = transferred.replace(day=1)
    return first - timedelta(days=1)


def is_foreign(node) -> bool:
    return (isinstance(node, dict) and "amount" not in node
            and node.get("currency") and node.get("amount_foreign") is not None)


def rate_for(currency: str, on: date, rates: dict) -> tuple[float, date] | None:
    """(rate, date it was published for). Rule 115 does not say what to do when
    no rate was published on the date -- a Sunday or bank holiday. Practice is
    the nearest earlier published rate, so up to a week back is accepted, and
    the date actually used is returned so it is always reported."""
    table = rates.get(currency.upper()) or {}
    for back in range(0, 8):
        day = on - timedelta(days=back)
        if day.isoformat() in table:
            return float(table[day.isoformat()]), day
    return None


def convert(node, when: date | None, rates: dict, why: str = "Rule 115"
            ) -> tuple[int | None, str]:
    """(rupees, how) at the rate for `when`, the date the caller's method fixes.
    Rupees is None when the amount cannot be converted."""
    if not is_foreign(node):
        return None, "not a foreign amount"
    currency = str(node["currency"]).upper()
    if when is None:
        return None, f"{currency} amount with no date to fix the rate"
    found = rate_for(currency, when, rates)
    if found is None:
        return None, f"needs the SBI TT buying rate for {currency} on {when.isoformat()}"
    rate, used = found
    rupees = round(float(node["amount_foreign"]) * rate)
    day = used.isoformat() if used == when else f"{used.isoformat()}, nearest to {when.isoformat()}"
    return rupees, (f"{currency} {float(node['amount_foreign']):,.2f} at {rate} "
                    f"(SBI TT buying rate, {day}, {why})")


def working(node, when: date | None, rates: dict, rule: str) -> dict | None:
    """The conversion laid out for display: what was stated, which rate, whose
    date, and under which rule -- so a reviewer can redo the multiplication."""
    rupees, _why = convert(node, when, rates, rule)
    if rupees is None:
        return None
    rate, used = rate_for(str(node["currency"]).upper(), when, rates)
    return {"currency": str(node["currency"]).upper(),
            "amount_foreign": float(node["amount_foreign"]),
            "rate": rate, "rate_date": used.isoformat(),
            "date_wanted": when.isoformat(), "rule": rule, "rupees": rupees}


def find_unconverted(value, pointer: str = "") -> list[str]:
    """Every foreign-only money object in a document, by JSON pointer.

    Used so an amount no schedule knows how to convert is reported, rather
    than read as zero by code that expects rupees."""
    out: list[str] = []
    if is_foreign(value):
        out.append(f"{pointer} ({value['currency']} {value['amount_foreign']})")
    elif isinstance(value, dict):
        for k, v in value.items():
            out.extend(find_unconverted(v, f"{pointer}/{k}"))
    elif isinstance(value, list):
        for i, v in enumerate(value):
            out.extend(find_unconverted(v, f"{pointer}/{i}"))
    return out


def month_end(year: int, month: int) -> date:
    return date(year, month, calendar.monthrange(year, month)[1])


def save_rate(currency: str, on: str, rate: float, source: dict | None = None) -> dict:
    """Record one published rate, with where it came from."""
    import re as _re
    from datetime import date as _date

    currency = str(currency or "").strip().upper()
    if not _re.fullmatch(r"[A-Z]{3}", currency):
        raise ValueError(f"currency must be a three-letter code, got {currency!r}")
    _date.fromisoformat(on)                     # raises on a malformed date
    rate = float(rate)
    if not 0 < rate < 100000:
        raise ValueError(f"rate {rate} is not a plausible rupees-per-unit rate")

    target = rates_file()
    data = _read(target)
    data.setdefault(currency, {})[on] = rate
    data[currency] = dict(sorted(data[currency].items()))
    # Where each rate came from sits beside it: a looked-up rate carries its
    # source row, and one typed on the page says so.
    data.setdefault("_sources", {}).setdefault(currency, {})[on] = source or {"entered_by": "you"}
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n", "utf-8")
    tmp.replace(target)
    return {"currency": currency, "date": on, "rate": rate}
