from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
DEMO_WALLET = "0x48C8B4D40dE216C652ED4D67f6466CeBA90054CA"


class FrontendWalletFlowTests(unittest.TestCase):
    def test_landing_is_wallet_neutral_with_explicit_demo_route(self):
        html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
        self.assertIn('href="app.html?demo=1"', html)
        self.assertIn("const wallet = demoMode ? DEMO_WALLET : null;", html)
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


if __name__ == "__main__":
    unittest.main()
