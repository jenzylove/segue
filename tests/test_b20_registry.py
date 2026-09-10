from __future__ import annotations

import unittest
from unittest.mock import patch

from backend.segue_api.b20 import B20_REGISTRY, BASE_STOCKS_SOURCE, portfolio_for_wallet


class B20RegistryTests(unittest.TestCase):
    def test_registry_is_official_and_credit_capability_is_explicit(self) -> None:
        self.assertEqual(BASE_STOCKS_SOURCE, "https://brand.base.org/stocks")
        self.assertEqual([asset.ticker for asset in B20_REGISTRY], ["NVDAc", "METAc", "AAPLc", "GOOGLc", "AMZNc"])
        self.assertEqual(sum(asset.credit_supported for asset in B20_REGISTRY), 1)

    def test_live_portfolio_does_not_fabricate_failed_reads(self) -> None:
        def rpc(_rpc: str, method: str, params: list):
            if method == "eth_getCode":
                return "0x6000"
            if method == "eth_call" and str(params[0].get("data", "")).startswith("0x313ce567"):
                return "0x8"
            if method == "eth_call" and str(params[0].get("data", "")).startswith("0x70a08231"):
                if params[0]["to"].lower().endswith("8108c"):
                    return "0x1c"
                raise ValueError("provider read unavailable")
            return "0x"
        def balance(_rpc: str, token: str, _wallet: str) -> int:
            if token.lower().endswith("8108c"):
                return 28
            raise ValueError("provider read unavailable")
        with patch("backend.segue_api.b20.rpc_call", side_effect=rpc), patch("backend.segue_api.b20.erc20_balance", side_effect=balance):
            result = portfolio_for_wallet("rpc", "0x" + "1" * 40)
        self.assertEqual(result["assets"][0]["status"], "LIVE")
        self.assertIsNone(result["assets"][1]["balance_atomic"])
        self.assertIn("error", result["assets"][1])


if __name__ == "__main__":
    unittest.main()
