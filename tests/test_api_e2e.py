from __future__ import annotations

import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.segue_api import main as api
from backend.segue_api.mission import MissionStore
from backend.segue_api.morpho import LOCKED_MARKET_ID, MORPHO_BLUE_BASE, USDC_BASE, CANONICAL_COLLATERAL


WALLET = "0x48C8B4D40dE216C652ED4D67f6466CeBA90054CA"
MARKET = {
    "market_id": LOCKED_MARKET_ID,
    "loan_token": USDC_BASE,
    "collateral_token": CANONICAL_COLLATERAL,
    "oracle_address": "0xE0AE3137a30393410B595E1C1d572a1449A969ea",
    "irm_address": "0x46415998764C29aB2a25CbeA6254146D50D22687",
    "lltv_wad": "770000000000000000",
    "available_liquidity": 97_000_001,
    "direct_oracle_price": 2_235_755_667_163_822_400_022_578_076_957_299_301,
    "provenance": {"market_source": "test", "onchain_params": "test", "deployment_source": "test"},
}
POSITION = {
    "wallet": WALLET,
    "collateral_balance_atomic": 0,
    "collateral_position_atomic": 2_323_053,
    "supply_shares": 0,
    "borrow_shares": 1_000_000_000_000,
    "debt_assets_atomic": 1_000_004,
}


class ApiJourneyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.previous_store = api._missions
        api._missions = MissionStore(f"{self.directory.name}/missions.sqlite3")
        self.client = TestClient(api.app)

    def tearDown(self) -> None:
        api._missions.close()
        api._missions = self.previous_store
        self.directory.cleanup()

    def _mission(self) -> str:
        with patch.object(api, "_market", return_value=MARKET), patch.object(api, "_snapshot", return_value=POSITION):
            response = self.client.post("/v1/missions", json={"wallet": WALLET, "policy": {"reserve_bps": 2_000}})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["id"]

    def test_live_proposal_uses_provider_market_and_risk(self) -> None:
        with patch.object(api, "_market", return_value=MARKET), patch.object(api, "_snapshot", return_value=POSITION):
            response = self.client.post("/v1/credit/proposal", json={"wallet": WALLET, "desired_usdc_atomic": 1_000_000})
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["market"]["market_id"], LOCKED_MARKET_ID)
        self.assertEqual(payload["risk"]["oracle_price_1e36"], MARKET["direct_oracle_price"])
        self.assertEqual(payload["risk"]["available_executable_borrow_atomic"], 3_199_367)
        self.assertNotIn("collateral_price_usd", payload)

    def test_empty_wallet_position_returns_onboarding_state(self) -> None:
        empty = {**POSITION, "collateral_position_atomic": 0, "borrow_shares": 0, "debt_assets_atomic": 0}
        with patch.object(api, "_market", return_value=MARKET), patch.object(api, "_snapshot", return_value=empty):
            response = self.client.get("/v1/credit/position", params={"wallet": "0x" + "2" * 40})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["risk"]["state"], "NO_COLLATERAL")
        self.assertEqual(response.json()["mission_state"], "NO_COLLATERAL")

    def test_protocol_fields_are_rejected_on_proposal_and_lender_plan(self) -> None:
        proposal = self.client.post("/v1/credit/proposal", json={"wallet": WALLET, "desired_usdc_atomic": 1, "calldata": "0xdeadbeef"})
        self.assertEqual(proposal.status_code, 400)
        lender = self.client.post("/v1/morpho/lender-plan", json={"wallet": WALLET, "amount": 1, "market_id": LOCKED_MARKET_ID})
        self.assertEqual(lender.status_code, 400)

    def test_product_workspace_is_served_by_unified_api(self) -> None:
        response = self.client.get("/app.html")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Live position workspace", response.text)
        self.assertIn("/v1/credit/position", response.text)

    def test_mission_recovery_plan_idempotency_and_close_gate(self) -> None:
        mission_id = self._mission()
        with patch.object(api, "_market", return_value=MARKET), patch.object(api, "_snapshot", return_value=POSITION):
            first = self.client.post(f"/v1/missions/{mission_id}/plan/borrow", json={"amount": 1_000_000, "idempotency_key": "borrow-demo"})
            second = self.client.post(f"/v1/missions/{mission_id}/plan/borrow", json={"amount": 9_000_000, "idempotency_key": "borrow-demo"})
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(second.status_code, 200, second.text)
        self.assertEqual(first.json()["plan"], second.json()["plan"])
        recovered = self.client.get(f"/v1/missions/{mission_id}")
        self.assertEqual(recovered.status_code, 200)
        self.assertEqual(recovered.json()["actions"][0]["status"], "READY")
        requirements = self.client.get(f"/v1/missions/{mission_id}/action-requirements")
        self.assertFalse(requirements.json()["requirements"]["withdrawal_allowed"])
        with patch.object(api, "_market", return_value=MARKET), patch.object(api, "_snapshot", return_value=POSITION):
            close = self.client.post(f"/v1/missions/{mission_id}/repay-close")
        self.assertEqual(close.status_code, 200, close.text)
        self.assertEqual(close.json()["plan"]["borrow_shares"], POSITION["borrow_shares"])
        self.assertEqual(close.json()["plan"]["actions"][1]["calldata"][:10], "0x20b76e81")

    def test_idempotency_key_cannot_cross_bind_actions(self) -> None:
        mission_id = self._mission()
        with patch.object(api, "_market", return_value=MARKET), patch.object(api, "_snapshot", return_value=POSITION):
            first = self.client.post(f"/v1/missions/{mission_id}/plan/borrow", json={"amount": 1_000_000, "idempotency_key": "shared-key"})
            conflicting = self.client.post(f"/v1/missions/{mission_id}/plan/repay", json={"amount": 1_000_000, "idempotency_key": "shared-key"})
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(conflicting.status_code, 409, conflicting.text)

    def test_repay_close_rejects_caller_calldata(self) -> None:
        mission_id = self._mission()
        response = self.client.post(f"/v1/missions/{mission_id}/repay-close", json={"calldata": "0xdeadbeef"})
        self.assertEqual(response.status_code, 400)

    def test_submit_preserves_pre_position_evidence(self) -> None:
        mission_id = self._mission()
        with patch.object(api, "_market", return_value=MARKET), patch.object(api, "_snapshot", return_value=POSITION):
            planned = self.client.post(f"/v1/missions/{mission_id}/plan/borrow", json={"amount": 1_000_000, "idempotency_key": "submit-evidence"})
        self.assertEqual(planned.status_code, 200, planned.text)
        submitted = self.client.post(f"/v1/missions/{mission_id}/actions/submit-evidence/submit", json={"tx_hash": "0x" + "a" * 64})
        self.assertEqual(submitted.status_code, 200, submitted.text)
        self.assertEqual(submitted.json()["evidence"]["pre_position"]["borrow_shares"], POSITION["borrow_shares"])

    def test_list_and_reconcile_routes_are_persistent(self) -> None:
        mission_id = self._mission()
        listed = self.client.get("/v1/missions", params={"wallet": WALLET})
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.json()["missions"][0]["id"], mission_id)
        mission = api._missions.get(mission_id)
        with patch.object(api, "reconcile_receipt", return_value=mission), patch.object(api, "_rpc", return_value="http://rpc.invalid"):
            reconciled = self.client.post(f"/v1/missions/{mission_id}/reconcile", json={"tx_hash": "0x" + "a" * 64})
        self.assertEqual(reconciled.status_code, 200, reconciled.text)

    def test_portfolio_is_registry_driven_and_capability_explicit(self) -> None:
        fixture = {
            "wallet": WALLET,
            "chain_id": 8453,
            "assets": [
                {"ticker": "NVDAc", "company": "NVIDIA", "address": CANONICAL_COLLATERAL, "balance_atomic": 2323053, "balance": "0.02323053", "status": "LIVE", "sequence_supported": True, "credit_supported": True},
                {"ticker": "AAPLc", "company": "Apple", "address": "0x" + "a" * 40, "balance_atomic": 0, "balance": "0", "status": "LIVE", "sequence_supported": False, "credit_supported": False},
            ],
            "registry_source": "https://brand.base.org/stocks",
        }
        with patch.object(api, "_rpc", return_value="rpc"), patch.object(api, "portfolio_for_wallet", return_value=fixture):
            response = self.client.get("/v1/portfolio", params={"wallet": WALLET})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual([item["ticker"] for item in response.json()["assets"]], ["NVDAc", "AAPLc"])
        self.assertTrue(response.json()["assets"][0]["credit_supported"])
        self.assertFalse(response.json()["assets"][1]["credit_supported"])

    def test_sequence_create_recover_and_validate_contract_semantics(self) -> None:
        body = {
            "wallet": WALLET,
            "max_capital_atomic": 20_000_000,
            "steps": [{
                "condition_type": "DOWN_BPS_FROM_REFERENCE",
                "delta_bps": 500,
                "action": "BUY",
                "sell_token": USDC_BASE,
                "buy_token": CANONICAL_COLLATERAL,
                "amount_mode": "PERCENT_BALANCE",
                "amount": 5000,
                "max_deviation_bps": 100,
            }],
        }
        created = self.client.post("/v1/sequences", json=body)
        self.assertEqual(created.status_code, 200, created.text)
        sequence = created.json()
        self.assertEqual(sequence["status"], "DRAFT")
        self.assertEqual(sequence["steps"][0]["status"], "ACTIVE")
        self.assertEqual(self.client.get("/v1/sequences", params={"wallet": WALLET}).json()["sequences"][0]["id"], sequence["id"])
        self.assertEqual(self.client.get(f"/v1/sequences/{sequence['id']}").json()["events"][0]["kind"], "SEQUENCE_CREATED")
        invalid = self.client.post("/v1/sequences", json={**body, "steps": body["steps"] * 9})
        self.assertEqual(invalid.status_code, 400)

    def test_activity_aggregates_credit_and_sequence_events(self) -> None:
        created = self.client.post("/v1/sequences", json={"wallet": WALLET, "max_capital_atomic": 1, "steps": [{"condition_type": "PRICE_ABOVE", "threshold": 1, "action": "BUY", "sell_token": USDC_BASE, "buy_token": CANONICAL_COLLATERAL, "amount": 1}]})
        self.assertEqual(created.status_code, 200, created.text)
        activity = self.client.get("/v1/activity", params={"wallet": WALLET})
        self.assertEqual(activity.status_code, 200, activity.text)
        self.assertEqual(activity.json()["events"][0]["source"], "sequence")


if __name__ == "__main__":
    unittest.main()
