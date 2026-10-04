"""The Planning page's projection: the year read so far, plus what is expected,
computed by the return's own engine."""

from __future__ import annotations

import copy
import unittest
from datetime import date

from engine import planning, projection

AY = "2026-27"                       # FY 2025-26, whose rates are built in
MID_YEAR = date(2025, 10, 4)         # six months gone


def m(n):
    return {"amount": n}


def scenario():
    """Six months of salary, two sales, TDS and one advance-tax challan, RSU
    lots in Schedule FA and a short-term loss from AY 2018-19 (whose last
    year of set-off is this one)."""
    return {
        "salary": {"data": {"employers": [{
            "name": "Acme", "tan": "BLRA00000A", "period": "01-04-2025 to 30-09-2025",
            "gross_salary": m(2_100_000)}]}},
        "capital_gains": {"data": {"disposals": [
            {"asset_class": "foreign_shares", "description": "RSU sale", "acquired_on": "2024-08-15",
             "transferred_on": "2025-08-20", "full_value": m(900_000), "cost_of_acquisition": m(600_000)},
            {"asset_class": "equity_stt", "description": "Index fund", "acquired_on": "2022-01-10",
             "transferred_on": "2025-07-01", "full_value": m(450_000), "cost_of_acquisition": m(400_000)}]}},
        "taxes_paid": {"data": {
            "tds_salary": [{"tds": m(350_000)}],
            "taxes_paid_challans": [{"bsr_code": "1", "challan_no": "1", "kind": "advance_tax",
                                     "date_of_deposit": "2025-09-10", "amount": m(100_000)}]}},
        "foreign_special": {"data": {"schedule_fa": {"a3_equity_and_debt": [{
            "country_code": "US", "country": "United States", "entity_name": "Example Corp",
            "acquisitions": [{"on": "2023-12-15", "quantity": 100}, {"on": "2024-06-15", "quantity": 80},
                             {"on": "2024-08-15", "quantity": 90}],
            "sales": [{"on": "2025-08-20", "quantity": 90, "lot_acquired_on": "2024-08-15"}]}]}}},
        "setoff_cfl": {"data": {"brought_forward": [
            {"ay_of_origin": "2018-19", "kind": "short_term_capital", "amount": m(80_000)}]}},
    }


NOTES = {"data": {"expectations": [
    {"kind": "salary", "description": "Monthly gross", "amount": {"amount": 350_000, "cite": "note.txt"},
     "per": "month", "from_month": "2025-04", "to_month": "2026-03"},
    {"kind": "bonus", "description": "Bonus", "amount": {"amount": 500_000, "cite": "note.txt"}, "per": "once"},
]}}


def build(docs=None, notes=NOTES, inputs=None, today=MID_YEAR, profile=None):
    return projection.build(AY, scenario() if docs is None else docs, notes, inputs,
                            profile or {"age_band": "below_60", "regime": "compare"}, today=today)


class MidYear(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p = build()

    def test_the_year_is_projected_from_the_notes(self):
        salary = self.p["inputs"]["salary_year"]
        self.assertEqual((salary["source"], salary["year"], salary["more"]), ("notes", 4_700_000, 2_600_000))
        self.assertEqual((self.p["year_state"], self.p["months_gone"], self.p["salary_months"]), ("current", 6, 6))
        self.assertFalse(self.p["rates"]["assumed"])

    def test_the_projected_tax_is_the_engines(self):
        # Salary 47L less the 75k standard deduction, plus 3L of short-term
        # foreign gain less the 80k loss brought forward: 48.45L at slab rates
        # is 10,33,500; the 50k equity gain is inside the exemption; no
        # surcharge below 50L; 4% cess.
        new = self.p["regimes"]["new"]["projected"]
        self.assertEqual(new["total_income"], 4_895_000)
        self.assertEqual(new["net_tax_liability"], 1_074_840)
        self.assertEqual(self.p["chosen"], "new")

    def test_regime_break_even_is_enough_and_not_much_more(self):
        r = self.p["regime"]
        self.assertEqual((r["new"], r["old"], r["difference"]), (1_074_840, 1_324_440, 249_600))
        self.assertTrue(r["break_even_possible"])
        self.assertEqual(r["break_even"], 801_000)

    def test_capital_gains_card(self):
        g = self.p["gains"]
        self.assertEqual(g["tax_on_gains"], 68_640)                 # 2.2L at 31.2%
        self.assertEqual(g["exemption_unused"], 75_000)
        self.assertEqual(g["saving_per_lakh"], {"short": 31_200, "long": 0})
        self.assertEqual(g["short_term_foreign"], 300_000)
        self.assertTrue(g["brought_forward"][0]["last_year_now"])

    def test_advance_tax_by_instalment(self):
        a = self.p["advance_tax"]
        self.assertEqual((a["liability"], a["credits"], a["due"]), (1_074_840, 783_333, 291_507))
        june, september, december, march = a["instalments"]
        self.assertEqual((june["shortfall"], june["interest_234c"]), (43_726, 1_312))
        # 1,00,000 paid by 15 September is under 36% of 2,91,507, so interest runs.
        self.assertEqual((september["paid"], september["interest_234c"]), (100_000, 935))
        self.assertEqual((a["next"]["date"], a["next"]["to_pay"]), ("2025-12-15", 118_630))

    def test_foreign_lots(self):
        lots = self.p["lots"]
        self.assertEqual([(lot["acquired_on"], lot["quantity"], lot["long_term_after"], lot["status"])
                          for lot in lots],
                         [("2023-12-15", 100.0, "2025-12-15", "soon"), ("2024-06-15", 80.0, "2026-06-15", "later")])

    def test_hints_fit_the_return(self):
        ids = {h["id"] for h in self.p["hints"]}
        for expected in ("advance", "foreign-24", "lots-soon", "harvest-112a", "harvest-loss",
                         "expiring", "schedule-fa", "threshold", "nps"):
            self.assertIn(expected, ids)
        self.assertNotIn("rates", ids)
        self.assertNotIn("debt-funds", ids)
        self.assertNotIn("form-67", ids)


class Sources(unittest.TestCase):
    def test_without_notes_salary_is_scaled_from_the_months_covered(self):
        p = build(notes=None)
        salary = p["inputs"]["salary_year"]
        self.assertEqual((salary["source"], salary["year"]), ("scaled", 4_200_000))
        # Salary TDS carries on in step with the salary still to come.
        self.assertEqual(p["inputs"]["tds_year"]["year"], 700_000)

    def test_typed_figures_win(self):
        p = build(inputs={"salary_year": 5_200_000, "gains": {"equity_short": -100_000}})
        self.assertEqual(p["inputs"]["salary_year"]["source"], "typed")
        self.assertEqual(p["inputs"]["gains"]["equity_short"]["amount"], -100_000)
        self.assertEqual(p["heads"][0]["projected"], 5_200_000)

    def test_a_finished_year_is_taken_as_read(self):
        p = build(notes=None, today=date(2026, 10, 4))
        self.assertEqual(p["year_state"], "past")
        self.assertEqual(p["inputs"]["salary_year"]["source"], "documents")
        self.assertFalse([h for h in p["hints"] if h["kind"] == "act"])

    def test_the_documents_are_never_altered(self):
        docs = scenario()
        before = copy.deepcopy(docs)
        build(docs=docs, inputs={"gains": {"other_long": 200_000}})
        self.assertEqual(docs, before)

    def test_a_planned_sale_gets_its_term_from_its_dates(self):
        notes = {"data": {"expectations": [
            {"kind": "capital_gain", "description": "Sell the 2023 RSUs", "per": "once",
             "asset_class": "foreign_shares", "direction": "gain", "acquired_on": "2023-12-15",
             "on": "2026-01-20", "amount": m(400_000)},
            {"kind": "capital_gain", "description": "Trim the fund", "per": "once",
             "asset_class": "equity_stt", "direction": "loss", "acquired_on": "2025-06-01",
             "on": "2026-02-01", "amount": m(60_000)}]}}
        gains = build(notes=notes)["inputs"]["gains"]
        self.assertEqual(gains["other_long"]["amount"], 400_000)
        self.assertEqual(gains["equity_short"]["amount"], -60_000)

    def test_with_nothing_at_all(self):
        p = build(docs={}, notes=None)
        self.assertEqual(p["regimes"]["new"]["projected"]["total_income"], 0)
        self.assertFalse(p["advance_tax"]["needed"])


class Helpers(unittest.TestCase):
    def test_indian_grouping(self):
        self.assertEqual([projection.inr(n) for n in (999, 1_000, 118_630, 5_000_000, -80_000)],
                         ["₹999", "₹1,000", "₹1,18,630", "₹50,00,000", "-₹80,000"])

    def test_salary_months_from_periods(self):
        start, end = projection.fy_bounds(AY)
        doc = lambda *periods: {"data": {"employers": [{"period": p} for p in periods]}}  # noqa: E731
        self.assertEqual(projection.salary_months(doc("Apr 2025 to Sep 2025"), start, end), 6)
        self.assertEqual(projection.salary_months(doc("2025-04-01 to 2025-06-30", "01/06/2025 - 31/08/2025"),
                                                  start, end), 5)
        self.assertIsNone(projection.salary_months(doc("the year"), start, end))

    def test_a_year_without_rates_borrows_the_latest(self):
        rates, assumed = planning.planning_rates("2099-00")
        self.assertTrue(assumed)
        self.assertEqual(rates.AY, assumed)


class NotesSchema(unittest.TestCase):
    """What a reading of planning notes must look like."""

    def doc(self, *expectations):
        return {"schema_version": "1.0.0", "ay": AY, "schedule": "plan", "status": "ok",
                "data": {"as_of": "2025-09-30", "expectations": list(expectations)}}

    def test_a_good_reading_passes(self):
        from server import jsonschema_lite as jsl
        schema = jsl.compose("plan")
        good = self.doc(*NOTES["data"]["expectations"],
                        {"kind": "capital_gain", "description": "RSUs", "per": "once", "amount": m(400_000),
                         "direction": "gain", "asset_class": "foreign_shares", "acquired_on": "2023-12-15",
                         "on": "2026-01", "term": None},
                        {"kind": "deduction", "description": "PPF", "per": "once", "amount": m(150_000),
                         "section": "80C"})
        self.assertEqual(jsl.validate(good, schema), [])

    def test_a_bad_reading_is_refused(self):
        from server import jsonschema_lite as jsl
        schema = jsl.compose("plan")
        for bad in ({"kind": "salary", "description": "x", "per": "fortnight", "amount": m(1)},
                    {"kind": "lottery", "description": "x", "per": "once", "amount": m(1)},
                    {"kind": "salary", "description": "x", "per": "month", "amount": m(1), "from_month": "April"},
                    {"kind": "salary", "description": "x", "per": "year", "amount": m(1), "guess": True}):
            self.assertTrue(jsl.validate(self.doc(bad), schema), bad)

    def test_the_tab_is_kept_out_of_the_return(self):
        from server import paths
        tab = paths.tab("plan")
        self.assertEqual(tab["kind"], "plan")
        self.assertTrue((paths.PROMPTS / "plan.md").read_text("utf-8").startswith("version: plan@"))


class Inputs(unittest.TestCase):
    def test_what_may_be_typed(self):
        from server.app import planning_inputs
        out = planning_inputs({"salary_year": "52,00,000", "gains": {"equity_long": "-25000"}})
        self.assertEqual(out["salary_year"], 5_200_000)
        self.assertEqual(out["gains"]["equity_long"], -25_000)
        self.assertIsNone(out["tds_year"])
        with self.assertRaisesRegex(ValueError, "cannot be negative"):
            planning_inputs({"salary_year": "-5"})
        with self.assertRaisesRegex(ValueError, "must be an amount"):
            planning_inputs({"tds_year": "lots"})


if __name__ == "__main__":
    unittest.main()
