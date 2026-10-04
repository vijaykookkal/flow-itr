"""Worked cases for loss set-off in engine/cascade.py (sections 70, 71, 73, 74)."""

from __future__ import annotations

import unittest

from engine import cascade
from engine.rates import ay2026_27 as R


def row(section, term, gain, rate):
    return {"section": section, "term": term, "gain": gain, "rate": rate}


def within_cg(rows):
    buckets = cascade.cg_buckets({"rows": rows}, slab_marginal=0.30)
    out = cascade.set_off_within_cg(buckets, R.EXEMPTION_112A)
    return out, {b["key"]: b["net"] for b in out["net"]}


def head(key, amount):
    return cascade.head(key, key.replace("_", " "), amount, "", rate=0.30)


class WithinCapitalGains(unittest.TestCase):
    def test_losses_go_to_the_dearest_gain_long_term_first(self):
        # LTCL 50,000 may meet only long-term gains: it goes into the taxed part
        # of the 112A gain (2L less the 1.25L exemption = 75,000 at 12.5%).
        # STCL 30,000 may meet anything: the dearest is 111A at 20%.
        out, net = within_cg([row("111A", "short", 1_00_000, 0.20),
                              row("112A", "long", 2_00_000, 0.125),
                              row("112A", "long", -50_000, 0.125),
                              row("slab", "short", -30_000, None)])
        self.assertEqual(net["111A_short"], 70_000)
        self.assertEqual(net["112A_long"], 1_50_000)
        self.assertEqual(out["carry_forward"], {"stcl": 0, "ltcl": 0})

    def test_long_term_loss_never_meets_short_term_gain(self):
        out, net = within_cg([row("111A", "short", 1_00_000, 0.20),
                              row("112A", "long", -40_000, 0.125)])
        self.assertEqual(net["111A_short"], 1_00_000)
        self.assertEqual(out["carry_forward"]["ltcl"], 40_000)


class AcrossHeads(unittest.TestCase):
    def test_speculative_loss_is_ring_fenced(self):
        out = cascade.set_off_across_heads(
            [head("salary", 10_00_000), head("business", 2_00_000), head("speculative", -50_000)], "new", R)
        self.assertEqual(out["moves"], [])
        self.assertEqual(out["carry_forward"], {"speculative": 50_000})

    def test_business_loss_never_meets_salary(self):
        out = cascade.set_off_across_heads(
            [head("salary", 10_00_000), head("business", -3_00_000), head("other_sources", 1_00_000)], "new", R)
        self.assertEqual([(m["into"], m["amount"]) for m in out["moves"]], [("other sources", 1_00_000)])
        self.assertEqual(out["carry_forward"], {"business": 2_00_000})

    def test_house_property_loss(self):
        heads = lambda: [head("salary", 10_00_000), head("house_property", -2_50_000)]  # noqa: E731
        # New regime: blocked from leaving its head at all.
        new = cascade.set_off_across_heads(heads(), "new", R)
        self.assertEqual(new["carry_forward"], {"house_property": 2_50_000})
        self.assertEqual(new["total_set_off"], 0)
        # Old regime: up to 2L a year against other heads, the rest carried.
        old = cascade.set_off_across_heads(heads(), "old", R)
        self.assertEqual(old["total_set_off"], 2_00_000)
        self.assertEqual(old["carry_forward"], {"house_property": 50_000})


if __name__ == "__main__":
    unittest.main()
