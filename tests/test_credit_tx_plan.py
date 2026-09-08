from __future__ import annotations

import unittest
from decimal import Decimal

from backend.segue_api.models import AaveMarket, CreditPolicy, TokenRef
from backend.segue_api.tx_plan import TxKind, build_close_credit_plan, build_open_credit_plan


USDC = TokenRef("USDC", "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913", 6, "official")
NVDAC = TokenRef("NVDAc", "0xb20000000000000000000078ee7ce2fE4908108C", 18, "official")
USER = "0x9999999999999999999999999999999999999999"


def market(**overrides: object) -> AaveMarket:
    data = dict(
        collateral=NVDAC,
        debt_asset=USDC,
        pool="0xA238Dd80C259a72e81d7e4664a9801593F98d1c5",
        protocol_data_provider="0x0F43731EB8d45A581f4a36DD74F5f358bc90C73A",
        ltv_bps=5_000,
        liquidation_threshold_bps=6_500,
        liquidation_bonus_bps=10_500,
        borrow_apr_bps=350,
        available_liquidity_atomic=100_000_000,
        collateral_price_usd=Decimal("100"),
        debt_price_usd=Decimal("1"),
        active=True,
        frozen=False,
        paused=False,
        borrowing_enabled=True,
        collateral_enabled=True,
        provenance={"fixture": "unit-test"},
    )
    data.update(overrides)
    return AaveMarket(**data)


class CreditTxPlanTests(unittest.TestCase):
    def test_open_credit_plan_prepares_unsigned_aave_transactions(self) -> None:
        plan = build_open_credit_plan(
            market(),
            CreditPolicy(20_000_000, 4_000, 15_000, 2_000, 1_000),
            collateral_balance_atomic=10**18,
            collateral_to_supply_atomic=10**18,
            borrower=USER,
        )

        self.assertEqual([tx.kind for tx in plan.unsigned_transactions],
                         [TxKind.APPROVE_COLLATERAL, TxKind.AAVE_SUPPLY, TxKind.AAVE_BORROW])
        self.assertEqual(plan.unsigned_transactions[0].to, NVDAC.address)
        self.assertTrue(plan.unsigned_transactions[1].data.startswith("0x617ba037"))
        self.assertTrue(plan.unsigned_transactions[2].data.startswith("0xa415bcad"))
        self.assertIn("sign", plan.human_boundary)

    def test_open_credit_plan_rejects_blocked_policy(self) -> None:
        with self.assertRaisesRegex(ValueError, "blocked proposal"):
            build_open_credit_plan(
                market(paused=True),
                CreditPolicy(20_000_000, 4_000, 15_000, 2_000, 1_000),
                collateral_balance_atomic=10**18,
                collateral_to_supply_atomic=10**18,
                borrower=USER,
            )

    def test_open_credit_plan_rejects_insufficient_collateral_supply(self) -> None:
        with self.assertRaisesRegex(ValueError, "below the proposal requirement"):
            build_open_credit_plan(
                market(),
                CreditPolicy(20_000_000, 4_000, 15_000, 2_000, 1_000),
                collateral_balance_atomic=10**18,
                collateral_to_supply_atomic=1,
                borrower=USER,
            )

    def test_close_credit_plan_prepares_repay_and_withdraw(self) -> None:
        plan = build_close_credit_plan(
            market(),
            debt_to_repay_atomic=20_000_000,
            collateral_to_withdraw_atomic=10**18,
            borrower=USER,
        )

        self.assertEqual([tx.kind for tx in plan.unsigned_transactions],
                         [TxKind.APPROVE_DEBT_REPAY, TxKind.AAVE_REPAY, TxKind.AAVE_WITHDRAW])
        self.assertTrue(plan.unsigned_transactions[1].data.startswith("0x573ade81"))
        self.assertTrue(plan.unsigned_transactions[2].data.startswith("0x69328dec"))


if __name__ == "__main__":
    unittest.main()

