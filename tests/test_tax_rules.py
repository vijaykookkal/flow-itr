"""Worked cases for the tax rules in engine/cascade.py, AY 2026-27.

Every expected figure here was worked by hand from the Finance Act 2025
position for FY 2025-26, and the working is in the comment beside it, so a
reader can check the arithmetic without running anything. If a rule changes,
the comment and the number change together.

    python -m unittest discover -s tests
"""

from __future__ import annotations

import unittest

from engine import cascade
from engine.rates import ay2026_27 as R


def slab_tax(income: int, regime: str = "new", age: str = "below_60") -> int:
    return cascade.tax_on_slices(income, [], R, regime, age)["slab_tax"]


def final(slab_income: int, specials: list[dict], regime: str = "new", age: str = "below_60") -> dict:
    """Stage 6 then stage 7, as cascade.build runs them."""
    sliced = cascade.tax_on_slices(slab_income, specials, R, regime, age)
    total = slab_income + sum(s["amount"] for s in specials)
    return cascade.rebate_and_surcharge(
        sliced["slab_tax"], sliced["special_tax"], total, R, regime,
        tax_at_threshold=lambda cut: cascade.tax_with_income_cut(slab_income, specials, R, regime, age, cut))


def ltcg(amount: int) -> dict:
    return {"label": "Long-term, section 112A", "amount": amount, "rate": 0.125, "exemption": R.EXEMPTION_112A}


def stcg(amount: int) -> dict:
    return {"label": "Short-term, section 111A", "amount": amount, "rate": 0.20}


class Slabs(unittest.TestCase):
    def test_new_regime(self):
        # 4L-8L at 5% = 20,000; 8L-12L at 10% = 40,000; 12L-16L at 15% = 60,000
        self.assertEqual(slab_tax(16_00_000), 1_20_000)
        # every band to 24L = 3,00,000; then 1L at 30% = 30,000
        self.assertEqual(slab_tax(25_00_000), 3_30_000)
        self.assertEqual(slab_tax(4_00_000), 0)

    def test_old_regime_by_age(self):
        # 2.5L-5L at 5% = 12,500; 5L-10L at 20% = 1,00,000
        self.assertEqual(slab_tax(10_00_000, "old"), 1_12_500)
        # senior: 3L-5L at 5% = 10,000; then 1,00,000
        self.assertEqual(slab_tax(10_00_000, "old", "senior"), 1_10_000)
        # super senior: nothing to 5L; 5L-10L at 20%
        self.assertEqual(slab_tax(10_00_000, "old", "super_senior"), 1_00_000)


class Rebate87A(unittest.TestCase):
    def test_full_rebate_at_the_ceiling(self):
        # 12L: slab tax 60,000, all of it rebated
        out = final(12_00_000, [])
        self.assertEqual(out["rebate"], 60_000)
        self.assertEqual(out["total"], 0)

    def test_marginal_relief_just_above_the_ceiling(self):
        # 12,10,000: slab tax 60,000 + 10,000 at 15% = 61,500. Income is only
        # 10,000 over the ceiling, so tax is capped at 10,000: rebate 51,500.
        out = final(12_10_000, [])
        self.assertEqual(out["rebate"], 51_500)
        self.assertEqual(out["rebate_marginal_relief"], 51_500)
        self.assertEqual(out["after_rebate"], 10_000)
        self.assertEqual(out["cess"], 400)

    def test_no_relief_once_tax_is_below_the_excess(self):
        # 13L: slab tax 75,000, excess over 12L is 1,00,000 -> no relief at all
        out = final(13_00_000, [])
        self.assertEqual(out["rebate"], 0)
        self.assertEqual(out["after_rebate"], 75_000)

    def test_rebate_never_reaches_capital_gains_tax(self):
        # 8L ordinary (tax 20,000) + 2L under 111A (tax 40,000): total 10L is
        # within the ceiling, but only the 20,000 on ordinary income is rebated.
        out = final(8_00_000, [stcg(2_00_000)])
        self.assertEqual(out["rebate"], 20_000)
        self.assertEqual(out["after_rebate"], 40_000)
        self.assertEqual(out["total"], 41_600)          # + 4% cess

    def test_old_regime_has_no_marginal_relief(self):
        self.assertEqual(final(5_00_000, [], "old")["after_rebate"], 0)
        # ten rupees over 5L: no rebate, and the whole tax of 12,502 is due
        self.assertEqual(final(5_00_010, [], "old")["rebate"], 0)


class SpecialRates(unittest.TestCase):
    def test_unused_basic_exemption_meets_special_gains(self):
        # Ordinary 2L leaves 2L of the 4L exemption unused; it absorbs 2L of the
        # 5L short-term gain, so 3L is taxed at 20% = 60,000.
        out = cascade.tax_on_slices(2_00_000, [stcg(5_00_000)], R, "new", "below_60")
        self.assertEqual(out["slab_tax"], 0)
        self.assertEqual(out["special_tax"], 60_000)

    def test_112a_exemption_once(self):
        # 3L of 112A gains with 20L ordinary income: 1.25L exempt, 1.75L at 12.5%
        out = cascade.tax_on_slices(20_00_000, [ltcg(3_00_000)], R, "new", "below_60")
        self.assertEqual(out["special_tax"], 21_875)


class Surcharge(unittest.TestCase):
    def test_ten_percent_band(self):
        # 60L: 3,00,000 + 36L at 30% = 13,80,000; surcharge 10% = 1,38,000
        out = final(60_00_000, [])
        self.assertEqual(out["surcharge"], 1_38_000)
        self.assertEqual(out["surcharge_marginal_relief"], 0)
        self.assertEqual(out["cess"], 60_720)

    def test_marginal_relief_just_above_50_lakh(self):
        # 50,10,000: tax 10,83,000, surcharge 1,08,300 -> 11,91,300.
        # At exactly 50L: tax 10,80,000 and no surcharge. Crossing by 10,000
        # may add no more than 10,000, so the cap is 10,90,000: relief 1,01,300.
        out = final(50_10_000, [])
        self.assertEqual(out["surcharge_marginal_relief"], 1_01_300)
        self.assertEqual(out["surcharge"], 7_000)
        self.assertEqual(out["after_rebate"] + out["surcharge"], 10_90_000)

    def test_marginal_relief_just_above_one_crore(self):
        # 1.01 Cr: tax 26,10,000, surcharge 15% = 3,91,500 -> 30,01,500.
        # At exactly 1 Cr: tax 25,80,000 plus the 10% band's surcharge 2,58,000
        # = 28,38,000. Cap 28,38,000 + 1,00,000 = 29,38,000: relief 63,500.
        out = final(1_01_00_000, [])
        self.assertEqual(out["surcharge_marginal_relief"], 63_500)
        self.assertEqual(out["surcharge"], 3_28_000)

    def test_surcharge_on_capital_gains_is_capped_at_15_percent(self):
        # 2.2 Cr ordinary: tax 61,80,000 bears 25% = 15,45,000.
        # 50L of 112A gains: 48,75,000 taxable at 12.5% = 6,09,375, which bears
        # 15%, not 25%: 91,406.
        out = final(2_20_00_000, [ltcg(50_00_000)])
        self.assertEqual(out["surcharge_rate"], 0.25)
        self.assertEqual(out["surcharge_on_rest"], 15_45_000)
        self.assertEqual(out["surcharge_on_special"], 91_406)
        self.assertEqual(out["surcharge"], 16_36_406)


if __name__ == "__main__":
    unittest.main()
