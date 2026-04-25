import importlib.util
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "ev" / "sell probablity model.py"


def load_sell_probability_module():
    spec = importlib.util.spec_from_file_location("ev_sell_probability", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def make_row():
    return {
        "live_listing": {
            "price": {
                "listing_price_usd": 850,
                "shipping_price_usd": 20,
            },
        },
        "sold_comparables": [
            {
                "sold_at_unix": 1711500000,
                "price": {
                    "sold_price_usd": 720,
                    "shipping_price_usd": 45,
                },
                "seller": {
                    "posted_at_unix": 1710204000,
                },
            },
            {
                "sold_at_unix": 1712000000,
                "price": {
                    "sold_price_usd": 810,
                    "shipping_price_usd": 35,
                },
                "seller": {
                    "posted_at_unix": 1711395200,
                },
            },
        ],
    }


class EVSellProbabilityContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_sell_probability_module()

    def test_estimate_sell_probability_emits_contract_shape(self):
        result = self.module.estimate_sell_probability(make_row())

        self.assertEqual(
            set(result.keys()),
            {
                "p_sell",
                "horizon_days",
                "median_days_to_sell",
                "adjusted_days_to_sell",
                "pricing_ratio",
                "live_price",
                "q50_comp_price",
                "num_valid_time_comps",
                "num_sold_comps",
            },
        )
        self.assertGreaterEqual(result["p_sell"], 0.05)
        self.assertLessEqual(result["p_sell"], 0.95)

    def test_pricing_ratio_uses_live_price_over_sold_comp_median(self):
        result = self.module.estimate_sell_probability(make_row())

        self.assertEqual(result["live_price"], 870)
        self.assertEqual(result["q50_comp_price"], 805)
        self.assertAlmostEqual(result["pricing_ratio"], 870 / 805)

    def test_defaults_when_no_comps_exist(self):
        row = {
            "live_listing": {
                "price": {
                    "listing_price_usd": 850,
                    "shipping_price_usd": 20,
                },
            },
            "sold_comparables": [],
        }

        result = self.module.estimate_sell_probability(row)

        self.assertEqual(result["median_days_to_sell"], 21.0)
        self.assertEqual(result["pricing_ratio"], 1.0)
        self.assertIsNone(result["q50_comp_price"])
        self.assertEqual(result["num_valid_time_comps"], 0)
        self.assertEqual(result["num_sold_comps"], 0)


if __name__ == "__main__":
    unittest.main()
