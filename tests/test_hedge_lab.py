import math
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from build import DEMO_END, DEMO_START, ROOT, make_dashboard
from hedge_lab import hedge_ratio, read_market, summarize, walk_forward


class HedgeLabTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.market = read_market(ROOT / "data" / "demo.csv")

    def test_ols_slope_and_position_limits(self):
        self.assertAlmostEqual(hedge_ratio([9, 11, 13], [2, 6, 10]), 0.5)
        self.assertEqual(hedge_ratio([6, 7, 8], [1, 1, 1]), 0)
        self.assertEqual(hedge_ratio([9, 11, 13], [3, 2, 1]), 0)
        self.assertEqual(hedge_ratio([9, 11, 13], [1, 2, 3]), 1.5)

    def test_position_never_uses_the_current_month_or_later(self):
        first = next(i for i, row in enumerate(self.market.months) if row.date == DEMO_START)
        current = self.market.months[first]
        revised = replace(
            self.market,
            months=self.market.months[:first] + (replace(current, spot=current.spot + 1000),)
            + self.market.months[first + 1:],
        )
        base = walk_forward(self.market, "C1", 24, DEMO_START, DEMO_END, 2)
        edited = walk_forward(revised, "C1", 24, DEMO_START, DEMO_END, 2)
        self.assertEqual(base[0]["ratio"], edited[0]["ratio"])
        self.assertNotEqual(base[0]["rolling"], edited[0]["rolling"])
        self.assertNotEqual(base[1]["ratio"], edited[1]["ratio"])

    def test_short_sign_and_cost_for_each_interval(self):
        gross = walk_forward(self.market, "C1", 24, DEMO_START, DEMO_END, 0)
        net = walk_forward(self.market, "C1", 24, DEMO_START, DEMO_END, 5)
        for before, after in zip(gross, net):
            self.assertAlmostEqual(before["full"], before["spot"] - before["futures"])
            self.assertEqual(after["unhedged"], before["unhedged"])
            self.assertAlmostEqual(before["full"] - after["full"], 5)
            self.assertAlmostEqual(before["rolling"] - after["rolling"], 5 * after["ratio"])

    def test_scenario_comparison_uses_identical_months(self):
        results = make_dashboard(self.market, DEMO_START, DEMO_END, "Synthetic", True)
        self.assertEqual(len(results["cases"]), 24)
        for case in results["cases"].values():
            rows = case["rows"]
            self.assertEqual((rows[0]["month"], rows[-1]["month"], len(rows)), (DEMO_START, DEMO_END, 96))
        base = results["cases"]["C1/24/2"]["metrics"]["rolling"]
        self.assertAlmostEqual(base["effectiveness"], 0.7429441216079309)
        self.assertEqual(base["added_loss"], 32)

    def test_risk_metrics_and_flat_benchmark(self):
        rows = [{"unhedged": -2, "full": -4, "rolling": 0},
                {"unhedged": 2, "full": 4, "rolling": 0}]
        summary = summarize(rows)
        self.assertAlmostEqual(summary["unhedged"]["volatility"], math.sqrt(8))
        self.assertEqual(summary["full"]["effectiveness"], -3)
        self.assertEqual(summary["full"]["tail"], -4)
        self.assertEqual(summary["rolling"]["effectiveness"], 1)
        self.assertIsNone(summarize([rows[0], rows[0]])["rolling"]["effectiveness"])

    def test_rejects_invalid_months_and_numeric_values(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "market.csv"
            for data, error in [
                ("2024-01,2100,\n2024-03,2200,60\n", "consecutive"),
                ("2024-01,2100,\n2024-02,nan,60\n", "finite"),
                ("2024-01,2100,\n2024-02,2200,inf\n", "finite"),
                ("2024-01,2100,5\n2024-02,2200,60\n", "baseline"),
                ("2024-01,2100,\n2024-02,2200,\n", "CSV row 3"),
            ]:
                with self.subTest(data=data):
                    path.write_text("month,spot_myr_t,futures_change_c1\n" + data, encoding="utf-8")
                    with self.assertRaisesRegex(ValueError, error):
                        read_market(path)

    def test_rejects_missing_warmup_or_evaluation_date(self):
        with self.assertRaisesRegex(ValueError, "36 pre-evaluation"):
            walk_forward(self.market, "C1", 36, "2016-01", DEMO_END, 2)
        with self.assertRaisesRegex(ValueError, "endpoints"):
            walk_forward(self.market, "C1", 36, DEMO_START, "2026-01", 2)


if __name__ == "__main__":
    unittest.main()
