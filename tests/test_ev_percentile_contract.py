import importlib.util
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "ev" / "percentile calc v1.py"

try:
    from shared.models import EVDistribution
except ModuleNotFoundError:
    EVDistribution = None


def load_percentile_module():
    spec = importlib.util.spec_from_file_location("ev_percentile_calc_v1", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def make_row():
    return {
        "live_listing": {
            "id": "live-1",
            "name": "788Z Back Zip Boots",
            "designer": "Guidi",
            "size": "43",
            "condition_raw": "Gently Used",
            "price": {
                "listing_price_usd": 850,
                "shipping_price_usd": 20,
            },
        },
        "sold_comparables": [
            {
                "designer": "Guidi",
                "size": "43",
                "condition_raw": "Used",
                "sold_at_unix": 1711500000,
                "price": {
                    "sold_price_usd": 720,
                    "shipping_price_usd": 45,
                },
                "seller": {
                    "reviews_count": 89,
                    "transactions_count": 94,
                    "posted_at_unix": 1710204000,
                    "badges": {
                        "verified": True,
                        "trusted_seller": False,
                    },
                },
            },
            {
                "designer": "Guidi",
                "size": "44",
                "condition_raw": "Gently Used",
                "sold_at_unix": 1712000000,
                "price": {
                    "sold_price_usd": 810,
                    "shipping_price_usd": 35,
                },
                "seller": {
                    "reviews_count": 50,
                    "transactions_count": 60,
                    "posted_at_unix": 1711395200,
                    "badges": {
                        "verified": False,
                        "trusted_seller": True,
                    },
                },
            },
        ],
    }


class EVPercentileContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_percentile_module()

    def test_value_listing_uses_shared_distribution_keys(self):
        result = self.module.value_listing(make_row(), scraped_at=1713995645)

        self.assertEqual(set(result["dist"].keys()), {"q10", "q50", "q90"})

    def test_value_listing_does_not_emit_legacy_distribution_keys(self):
        result = self.module.value_listing(make_row(), scraped_at=1713995645)

        self.assertNotIn("p10_floor", result["dist"])
        self.assertNotIn("p50_fair", result["dist"])
        self.assertNotIn("p90_max", result["dist"])

    @unittest.skipIf(EVDistribution is None, "pydantic is not installed in the local test environment")
    def test_distribution_validates_against_shared_model_without_translation(self):
        result = self.module.value_listing(make_row(), scraped_at=1713995645)

        dist = EVDistribution(**result["dist"])

        self.assertEqual(dist.q10, result["dist"]["q10"])
        self.assertEqual(dist.q50, result["dist"]["q50"])
        self.assertEqual(dist.q90, result["dist"]["q90"])

    def test_percentile_values_use_seller_and_recency_weights(self):
        row = make_row()
        scraped_at = 1713995645
        expected_weights = [
            self.module.get_recency_weight(1711500000, scraped_at)
            * self.module.get_seller_score(
                {
                    "reviews_count": 89,
                    "transactions_count": 94,
                    "posted_at_unix": 1710204000,
                    "badges": {
                        "verified": True,
                        "trusted_seller": False,
                    },
                }
            ),
            self.module.get_recency_weight(1712000000, scraped_at)
            * self.module.get_seller_score(
                {
                    "reviews_count": 50,
                    "transactions_count": 60,
                    "posted_at_unix": 1711395200,
                    "badges": {
                        "verified": False,
                        "trusted_seller": True,
                    },
                }
            ),
        ]
        expected_q10 = round(
            self.module.weighted_percentile(
                [765, 845],
                expected_weights,
                10,
            ),
            2,
        )
        expected_q50 = round(
            self.module.weighted_percentile(
                [765, 845],
                expected_weights,
                50,
            ),
            2,
        )
        expected_q90 = round(
            self.module.weighted_percentile(
                [765, 845],
                expected_weights,
                90,
            ),
            2,
        )

        result = self.module.value_listing(row, scraped_at=scraped_at)

        self.assertEqual(result["dist"]["q10"], expected_q10)
        self.assertEqual(result["dist"]["q50"], expected_q50)
        self.assertEqual(result["dist"]["q90"], expected_q90)

    def test_metrics_emit_confidence_percentage_not_legacy_label(self):
        result = self.module.value_listing(make_row(), scraped_at=1713995645)

        self.assertIn("confidence_percentage", result["metrics"])
        self.assertNotIn("confidence", result["metrics"])

    def test_calculate_buy_cost_applies_tax_only_to_listing_price(self):
        result = self.module.calculate_buy_cost(
            listing_price=850,
            shipping_cost=20,
        )

        self.assertEqual(result["listing_price"], 850)
        self.assertEqual(result["shipping_cost"], 20)
        self.assertEqual(result["sales_tax_rate"], 0.08875)
        self.assertAlmostEqual(result["tax_amount"], 850 * 0.08875)
        self.assertAlmostEqual(result["buy_cost"], 850 * 1.08875 + 20)

    def test_calculate_grailed_net_payout_uses_domestic_fee_formula(self):
        result = self.module.calculate_grailed_net_payout(
            item_price=845,
            shipping_charged=0,
            region="domestic",
        )

        self.assertAlmostEqual(result["total_transaction"], 845)
        self.assertAlmostEqual(result["commission_fee"], 845 * 0.09)
        self.assertAlmostEqual(result["processing_fee"], 845 * 0.0349 + 0.49)
        self.assertAlmostEqual(
            result["total_fees"],
            (845 * 0.09) + (845 * 0.0349 + 0.49),
        )
        self.assertAlmostEqual(result["net_payout"], 845 - result["total_fees"])

    def test_value_listing_emits_fee_adjusted_profit_fields(self):
        result = self.module.value_listing(make_row(), scraped_at=1713995645)
        metrics = result["metrics"]
        q50 = result["dist"]["q50"]
        expected_buy_cost = 850 * 1.08875 + 20
        expected_grailed_fees = (q50 * 0.09) + (q50 * 0.0349 + 0.49)
        expected_grailed_payout = q50 - expected_grailed_fees
        expected_profit_grailed = expected_grailed_payout - expected_buy_cost
        expected_profit_off_grailed = q50 - expected_buy_cost

        self.assertEqual(result["cost"], 870)
        self.assertEqual(metrics["edge_usd"], round(q50 - 870, 2))
        self.assertEqual(metrics["percent_under"], round(((q50 - 870) / q50) * 100, 1))
        self.assertEqual(result["listing_price"], 850)
        self.assertEqual(result["buy_shipping_cost"], 20)
        self.assertEqual(result["tax_amount"], round(850 * 0.08875, 2))
        self.assertEqual(result["buy_cost"], round(expected_buy_cost, 2))
        self.assertEqual(metrics["grailed_total_fees"], round(expected_grailed_fees, 2))
        self.assertEqual(metrics["grailed_net_payout"], round(expected_grailed_payout, 2))
        self.assertEqual(
            metrics["expected_profit_off_grailed"],
            round(expected_profit_off_grailed, 2),
        )
        self.assertEqual(
            metrics["expected_profit_grailed"],
            round(expected_profit_grailed, 2),
        )
        self.assertEqual(
            metrics["expected_profit_off_grailed_pct"],
            round(expected_profit_off_grailed / expected_buy_cost, 4),
        )
        self.assertEqual(
            metrics["expected_profit_grailed_pct"],
            round(expected_profit_grailed / expected_buy_cost, 4),
        )

    def test_one_comp_market_caps_confidence_percentage_at_35(self):
        row = make_row()
        row["sold_comparables"] = row["sold_comparables"][:1]

        result = self.module.value_listing(row, scraped_at=1713995645)

        self.assertLessEqual(result["metrics"]["confidence_percentage"], 35)

    def test_tight_spread_has_higher_confidence_than_wide_spread(self):
        tight = self.module.get_confidence_percentage(
            effective_n=4,
            q10=180,
            q50=220,
            q90=260,
            num_valid_time_comps=4,
        )
        wide = self.module.get_confidence_percentage(
            effective_n=4,
            q10=100,
            q50=220,
            q90=500,
            num_valid_time_comps=4,
        )

        self.assertGreater(tight, wide)

    def test_num_valid_time_comps_counts_only_valid_timestamp_pairs(self):
        row = make_row()
        row["sold_comparables"] = [
            {
                **row["sold_comparables"][0],
                "sold_at_unix": 1711500000,
                "seller": {
                    **row["sold_comparables"][0]["seller"],
                    "posted_at_unix": 1710204000,
                },
            },
            {
                **row["sold_comparables"][1],
                "sold_at_unix": 1712000000,
                "seller": {
                    **row["sold_comparables"][1]["seller"],
                    "posted_at_unix": 1712000000,
                },
            },
            {
                **row["sold_comparables"][1],
                "sold_at_unix": 1712000000,
                "seller": {
                    **row["sold_comparables"][1]["seller"],
                    "posted_at_unix": 1679000000,
                },
            },
            {
                **row["sold_comparables"][1],
                "sold_at_unix": 1712000000,
                "seller": {
                    **row["sold_comparables"][1]["seller"],
                    "posted_at_unix": None,
                },
            },
        ]

        result = self.module.value_listing(row, scraped_at=1713995645)

        self.assertEqual(result["metrics"]["num_valid_time_comps"], 1)


if __name__ == "__main__":
    unittest.main()
