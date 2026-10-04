"""The Planning page's curve: the return's own rules, run over a range of incomes."""

from __future__ import annotations

import unittest

from engine import planning
from engine.compute import load_rates

AY = "2026-27"


class Curve(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rates = load_rates(AY)
        cls.curve = planning.curve(AY, "below_60")

    def total(self, income, regime="new"):
        t = planning.tax_at(income, self.rates, regime, "below_60")
        return t["tax"] + t["surcharge"] + t["cess"]

    def test_figures_worked_by_hand(self):
        # New regime, FY 2025-26: nothing to 12L under the rebate; at 12.5L
        # marginal relief caps the tax at the 50,000 above 12L, plus cess.
        self.assertEqual(self.total(1_200_000), 0)
        self.assertEqual(self.total(1_250_000), 52_000)
        # 50L: 1,080,000 at slab rates, no surcharge yet, 4% cess.
        self.assertEqual(self.total(5_000_000), 1_123_200)
        # 51L: surcharge of 111,000 cut to 70,000 by marginal relief.
        t = planning.tax_at(5_100_000, self.rates, "new", "below_60")
        self.assertEqual((t["tax"], t["surcharge"]), (1_110_000, 70_000))
        # 1.5 crore: 15% surcharge in full, cess on both.
        self.assertEqual(self.total(15_000_000), 4_879_680)

    def test_old_regime_has_no_relief_on_the_rebate(self):
        self.assertEqual(self.total(500_000, "old"), 0)
        self.assertEqual(self.total(500_001, "old"), 13_000)
        kinds = [z["kind"] for z in self.curve["regimes"]["old"]["relief_zones"]]
        self.assertNotIn("rebate", kinds)

    def test_relief_zones_end_where_relief_does(self):
        for regime, data in self.curve["regimes"].items():
            for z in data["relief_zones"]:
                key = "rebate_relief" if z["kind"] == "rebate" else "surcharge_relief"
                inside = planning.tax_at(z["to"] - 1, self.rates, regime, "below_60")[key]
                after = planning.tax_at(z["to"], self.rates, regime, "below_60")[key]
                self.assertGreater(inside, 0, (regime, z))
                self.assertEqual(after, 0, (regime, z))

    def test_take_home_recovers_at_the_break_even(self):
        kept = lambda n, r: n - self.total(n, r)  # noqa: E731
        for regime, data in self.curve["regimes"].items():
            for z in data["relief_zones"]:
                floor, even = z["from"], z["keeps_less_until"]
                self.assertLess(kept(z["to"], regime), kept(floor, regime))
                self.assertLess(kept(even - 1, regime), kept(floor, regime))
                self.assertGreaterEqual(kept(even, regime), kept(floor, regime))

    def test_tax_never_falls_as_income_rises(self):
        for regime, data in self.curve["regimes"].items():
            totals = [t + s + c for t, s, c in zip(data["tax"], data["surcharge"], data["cess"])]
            self.assertEqual(data["income"], sorted(data["income"]))
            self.assertTrue(all(a <= b for a, b in zip(totals, totals[1:])), regime)
            self.assertEqual(data["income"][-1], planning.TOP)

    def test_every_threshold_is_a_point(self):
        incomes = set(self.curve["regimes"]["new"]["income"])
        for edge in (1_200_000, 5_000_000, 10_000_000):
            self.assertIn(edge, incomes)
            self.assertIn(edge + 1, incomes)

    def test_position_of_the_return(self):
        summary = {"regimes": {
            "new": {"cascade": {"totals": {"total_income": 2_000_000, "special_total": 150_000,
                                           "total_tax_liability": 230_000}}},
            "old": {"cascade": {"totals": {"total_income": 0}}}}}
        you = planning.position(AY, "below_60", summary)
        self.assertEqual(set(you), {"new"})
        self.assertEqual(you["new"]["income"], 2_000_000)
        self.assertEqual(you["new"]["special_total"], 150_000)
        self.assertEqual(you["new"]["tax"] + you["new"]["surcharge"] + you["new"]["cess"],
                         self.total(2_000_000))
        self.assertEqual(planning.position(AY, "below_60", None), {})


if __name__ == "__main__":
    unittest.main()
