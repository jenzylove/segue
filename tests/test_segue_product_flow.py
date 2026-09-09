from __future__ import annotations

import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.segue_api.evm import selector
from backend.segue_api.main import app
from backend.segue_api.mission import Mission, MissionState, MissionStore
from backend.segue_api.morpho_plans import full_repay_plan
from backend.segue_api.worker import reconcile_receipt


MARKET = {
    "market_id": "0x" + "1" * 64,
    "loan_token": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
    "collateral_token": "0xb20000000000000000000078ee7ce2fE4908108C",
    "oracle_address": "0x39712F36c013C09Cf4D62D0F695DD74eBe67FD19",
    "irm_address": "0x46415998764C29aB2a25CbeA6254146D50D22687",
    "lltv_wad": "770000000000000000",
}
WALLET = "0x48C8B4D40dE216C652ED4D67f6466CeBA90054CA"


class ProductFlowTests(unittest.TestCase):
    def test_eth_selectors_match_canonical_abi(self):
        self.assertEqual(selector("transfer(address,uint256)"), "0xa9059cbb")
        self.assertEqual(selector("price()"), "0xa035b1fe")

    def test_full_repay_is_share_based(self):
        plan = full_repay_plan("0xBBBBBbbBBb9cC5e90e3b3Af64bdAF62C37EEFFCb", MARKET["market_id"], wallet=WALLET, market=MARKET, borrow_shares=1_000_000_000_000, approval_amount=1_010_000)
        repay = plan["actions"][1]["calldata"]
        self.assertTrue(repay.startswith("0x20b76e81"))
        # Morpho repay has assets=0 and the fresh share balance as the next word.
        self.assertEqual(int(repay[10 + 5 * 64:10 + 6 * 64], 16), 0)
        self.assertEqual(int(repay[10 + 6 * 64:10 + 7 * 64], 16), 1_000_000_000_000)

    def test_action_idempotency_survives_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            path = f"{directory}/missions.sqlite3"
            first = MissionStore(path)
            first.save(Mission("m", WALLET, MissionState.BORROWED, MARKET["market_id"], {}, {"market": MARKET}))
            one = first.action("m:borrow:1", "m", "borrow", {"actions": []})
            again = first.action("m:borrow:1", "m", "borrow", {"actions": [{"different": True}]})
            self.assertEqual(one["plan"], again["plan"])
            first.close()
            second = MissionStore(path)
            self.assertEqual(second.get_action("m:borrow:1")["status"], "READY")
            second.close()

    def test_plan_endpoint_never_accepts_calldata(self):
        client = TestClient(app)
        with patch("backend.segue_api.main._missions.get", return_value=Mission("m", WALLET, MissionState.BORROWED, MARKET["market_id"], {}, {"market": MARKET})):
            response = client.post("/v1/missions/m/plan/borrow", json={"amount": 1, "calldata": "0xdeadbeef"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("calldata", response.json()["detail"])

    def test_receipt_reconciliation_requires_verified_postcondition(self):
        with tempfile.TemporaryDirectory() as directory:
            store = MissionStore(f"{directory}/missions.sqlite3")
            mission = Mission("m", WALLET, MissionState.BORROWED, MARKET["market_id"], {}, {"position": {"borrow_shares": 1}})
            store.save(mission)
            plan = {"flow": "full-repay", "actions": [{"target": "0x" + "1" * 40, "calldata": "0x095ea7b3"}, {"target": "0x" + "2" * 40, "calldata": "0x20b76e81"}], "pre_position": {"borrow_shares": 1}}
            store.action("close", "m", "full-repay", plan)
            confirmed = Mission("m", WALLET, MissionState.BORROWED, MARKET["market_id"], {}, {"position": {"borrow_shares": 0}})
            def fake_rpc(_rpc, method, _params):
                if method == "eth_getTransactionByHash": return {"to": "0x" + "2" * 40, "input": "0x20b76e81"}
                if method == "eth_getTransactionReceipt": return {"status": "0x1", "transactionHash": "0x" + "a" * 64}
                raise AssertionError(method)
            with patch("backend.segue_api.worker.rpc_call", side_effect=fake_rpc), patch("backend.segue_api.worker.reconcile_live", return_value=confirmed):
                result = reconcile_receipt(store, "m", "0x" + "a" * 64, "rpc", "close")
            self.assertEqual(store.get_action("close")["status"], "CONFIRMED")
            self.assertEqual(result.state, MissionState.REPAID)
            store.close()

    def test_receipt_reconciliation_checks_target_selector_pair(self):
        with tempfile.TemporaryDirectory() as directory:
            store = MissionStore(f"{directory}/missions.sqlite3")
            mission = Mission("m", WALLET, MissionState.BORROWED, MARKET["market_id"], {}, {"position": {"borrow_shares": 1}})
            store.save(mission)
            plan = {"flow": "full-repay", "actions": [{"target": "0x" + "1" * 40, "calldata": "0x095ea7b3"}, {"target": "0x" + "2" * 40, "calldata": "0x20b76e81"}], "pre_position": {"borrow_shares": 1}}
            store.action("close", "m", "full-repay", plan)
            with patch("backend.segue_api.worker.rpc_call", side_effect=lambda _rpc, method, _params: {"to": "0x" + "1" * 40, "input": "0x20b76e81"} if method == "eth_getTransactionByHash" else {"status": "0x1"}):
                result = reconcile_receipt(store, "m", "0x" + "a" * 64, "rpc", "close")
            self.assertEqual(store.get_action("close")["status"], "FAILED")
            self.assertEqual(result.state, MissionState.ERROR)
            store.close()


if __name__ == "__main__":
    unittest.main()
