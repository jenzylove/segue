from __future__ import annotations

import unittest

from backend.segue_api.b20 import CANONICAL_COLLATERAL
from backend.segue_api.evm import selector
from backend.segue_api.morpho import USDC_BASE
from backend.segue_api.sequence_chain import (
    build_activation_plan,
    create_policy_calldata,
    create_vault_calldata,
    execute_step_calldata,
)


WALLET = "0x1111111111111111111111111111111111111111"
EXECUTOR = "0x2222222222222222222222222222222222222222"
FACTORY = "0x3333333333333333333333333333333333333333"
VAULT = "0x4444444444444444444444444444444444444444"


def steps() -> list[dict]:
    return [
        {
            "condition_asset": CANONICAL_COLLATERAL,
            "condition_type": "DOWN_BPS_FROM_REFERENCE",
            "delta_bps": 500,
            "action": "BUY",
            "sell_token": USDC_BASE,
            "buy_token": CANONICAL_COLLATERAL,
            "amount_mode": "FIXED",
            "amount": 1_000_000,
            "max_deviation_bps": 100,
        },
        {
            "condition_asset": CANONICAL_COLLATERAL,
            "condition_type": "UP_BPS_FROM_REFERENCE",
            "delta_bps": 800,
            "action": "SELL",
            "sell_token": CANONICAL_COLLATERAL,
            "buy_token": USDC_BASE,
            "amount_mode": "PERCENT_BALANCE",
            "amount": 5000,
            "max_deviation_bps": 100,
        },
    ]


class SequenceChainTests(unittest.TestCase):
    def test_create_policy_calldata_is_the_stock_policy_vault_abi(self) -> None:
        calldata = create_policy_calldata(steps(), 1_000_000)
        self.assertTrue(calldata.startswith(selector("createPolicy((address,uint8,uint256,uint16,address,address,uint8,uint256,uint16,uint40)[],uint256)")))
        self.assertEqual((len(calldata) - 2) // 2, 4 + 32 + 32 + 32 + 2 * 10 * 32)
        # Dynamic-array head points to the tuple array at byte offset 64.
        self.assertEqual(calldata[10:74], f"{64:064x}")
        self.assertEqual(int(calldata[74:138], 16), 1_000_000)
        self.assertEqual(int(calldata[138:202], 16), 2)

    def test_create_vault_and_execute_step_calls_are_generated(self) -> None:
        vault = create_vault_calldata(EXECUTOR, 1_000_000)
        self.assertTrue(vault.startswith(selector("createVault(address,uint256)")))
        route = "0x12345678" + "00" * 32
        execute = execute_step_calldata(1, route)
        self.assertTrue(execute.startswith(selector("executeStep(uint256,bytes)")))
        self.assertEqual(int(execute[10:74], 16), 1)
        self.assertEqual(int(execute[74:138], 16), 64)

    def test_activation_plan_uses_persisted_steps_and_owner_boundary(self) -> None:
        sequence = {"id": "seq-1", "wallet": WALLET, "max_capital_atomic": 1_000_000, "steps": steps()}
        waiting = build_activation_plan(sequence, factory=FACTORY, executor=EXECUTOR)
        self.assertEqual(waiting["status"], "AWAITING_VAULT")
        self.assertEqual(waiting["actions"][0]["operation"], "createVault")
        ready = build_activation_plan(sequence, factory=FACTORY, executor=EXECUTOR, vault=VAULT)
        self.assertEqual(ready["status"], "SIGNATURE_READY")
        self.assertEqual([action["operation"] for action in ready["actions"]], ["approveSettlement", "depositSettlement", "createPolicy"])
        self.assertTrue(ready["actions"][-1]["calldata"].startswith("0x"))


if __name__ == "__main__":
    unittest.main()
