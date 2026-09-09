import unittest

from scripts.equityline_morpho_preflight import select_market


class MorphoPreflightTests(unittest.TestCase):
    def test_selects_verified_borrowable_market(self):
        loan = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
        collateral = "0xb20000000000000000000078ee7ce2fE4908108C"
        result = select_market({"items": [{
            "marketId": "0xabc", "loanAsset": {"address": loan}, "collateralAsset": {"address": collateral},
            "oracle": {"address": "0x0000000000000000000000000000000000000001"},
            "irmAddress": "0x0000000000000000000000000000000000000002", "lltv": "0.86",
            "state": {"borrowAssets": "1000", "borrowRate": "0.05"},
        }]}, loan, collateral)
        self.assertEqual(result["marketId"], "0xabc")
        self.assertEqual(result["_borrow_assets"], 1000)

    def test_fails_when_no_borrow_liquidity(self):
        with self.assertRaises(ValueError):
            select_market({"items": [{"marketId": "0xabc", "loanAsset": {"address": "0x1"}, "collateralAsset": {"address": "0x2"}}]}, "0x1", "0x2")


if __name__ == "__main__":
    unittest.main()
