from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
DEMO_WALLET = "0x48C8B4D40dE216C652ED4D67f6466CeBA90054CA"


class FrontendWalletFlowTests(unittest.TestCase):
    def test_landing_is_wallet_neutral_with_explicit_demo_route(self):
        html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
        self.assertIn('href="app.html?demo=1"', html)
        self.assertIn('class="button button-indigo js-connect-wallet"', html)
        self.assertIn("eth_requestAccounts", html)
        self.assertIn("Live Segue demo · Base mainnet", html)
        self.assertNotIn("CONNECT WALLET TO VIEW", html)
        self.assertNotIn("Unavailable", html)
        self.assertEqual(html.count(DEMO_WALLET), 1)
        self.assertIn('rel="icon"', html)
        self.assertTrue((ROOT / "frontend" / "favicon.svg").exists())

    def test_workspace_uses_eip1193_and_base_switch(self):
        html = (ROOT / "frontend" / "app.html").read_text(encoding="utf-8")
        self.assertIn("eth_accounts", html)
        self.assertIn("eth_requestAccounts", html)
        self.assertIn("wallet_switchEthereumChain", html)
        self.assertIn("wallet_addEthereumChain", html)
        self.assertIn("accountsChanged", html)
        self.assertIn("chainChanged", html)
        self.assertIn("const DEMO_WALLET", html)
        self.assertIn('href="favicon.svg"', html)
        self.assertNotIn("params.get('wallet')", html)

    def test_workspace_exposes_product_areas_and_real_api_wiring(self):
        html = (ROOT / "frontend" / "app.html").read_text(encoding="utf-8")
        for label in ("Portfolio", "Sequences", "Credit", "Activity", "/v1/portfolio", "/v1/sequences", "/v1/activity"):
            self.assertIn(label, html)
        self.assertIn("Save sequence draft", html)
        self.assertIn("Official Coinbase Tokenized Stocks on Base", html)
        self.assertIn('id="summary-holdings"', html)
        self.assertIn('id="market-asset-selector"', html)
        self.assertIn("No supported tokenized stocks found in this wallet.", html)
        self.assertIn("Coinbase Tokenized Stocks are available only in eligible jurisdictions.", html)

    def test_sequence_builder_keeps_condition_and_action_amounts_separate(self):
        html = (ROOT / "frontend" / "app.html").read_text(encoding="utf-8")
        for field in (
            "sequence-asset",
            "sequence-condition-value",
            "sequence-destination",
            "sequence-amount-mode",
            "sequence-amount",
            "sequence-deviation",
            "sequence-expiry",
        ):
            self.assertIn(field, html)
        self.assertIn("rows.children.length >= 8", html)
        self.assertIn("PERCENT_BALANCE", html)
        self.assertNotIn("amount_mode: condition.includes('BPS')", html)

    def test_catalogue_uses_official_acquisition_provenance(self):
        from backend.segue_api.b20 import BASE_STOCKS_SOURCE, B20_REGISTRY, registry_public

        self.assertEqual(len(B20_REGISTRY), 5)
        self.assertTrue(all(asset.provenance == BASE_STOCKS_SOURCE for asset in B20_REGISTRY))
        self.assertTrue(all(asset.acquisition_url == BASE_STOCKS_SOURCE for asset in B20_REGISTRY))
        self.assertTrue(all(item["acquisition_url"] == BASE_STOCKS_SOURCE for item in registry_public()))


if __name__ == "__main__":
    unittest.main()
