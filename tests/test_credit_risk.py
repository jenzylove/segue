from __future__ import annotations

import unittest
from decimal import Decimal

from backend.segue_api.models import AaveMarket, CreditPolicy, MissionStatus, PolicyAction, TokenRef
from backend.segue_api.risk import build_credit_proposal, keeper_action


USDC = TokenRef(
    symbol="USDC",
    address="0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
    decimals=6,
    source="test fixture",
)
NVDAC = TokenRef(
    symbol="NVDAc",
    address="0xb20000000000000000000078ee7ce2fE4908108C",
    decimals=18,
    source="test fixture",
)


def market(**overrides: object) -> AaveMarket:
    data = dict(
        collateral=NVDAC,
        debt_asset=USDC,
        pool="0x1111111111111111111111111111111111111111",
        protocol_data_provider="0x2222222222222222222222222222222222222222",
        ltv_bps=5_000,
        liquidation_threshold_bps=6_500,
        liquidation_bonus_bps=500,
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


def policy(**overrides: object) -> CreditPolicy:
    data = dict(
        requested_debt_atomic=20_000_000,
        max_ltv_bps=4_000,
        min_health_factor_bps=15_000,
        reserve_bps=2_000,
        max_borrow_apr_bps=1_000,
    )
    data.update(overrides)
    return CreditPolicy(**data)


class CreditRiskTests(unittest.TestCase):
    def test_builds_proposal_inside_aave_and_policy_limits(self) -> None:
        proposal = build_credit_proposal(market(), policy(), collateral_balance_atomic=10**18)

        self.assertEqual(proposal.status, MissionStatus.PROPOSED)
        self.assertEqual(proposal.action, PolicyAction.HOLD)
        self.assertEqual(proposal.requested_debt_atomic, 20_000_000)
        self.assertEqual(proposal.max_safe_debt_atomic, 40_000_000)
        self.assertEqual(proposal.projected_ltv_bps, 2_000)
        self.assertEqual(proposal.projected_health_factor_bps, 32_500)
        self.assertEqual(proposal.reserve_required_atomic, 4_000_000)

    def test_blocks_when_requested_debt_exceeds_safe_limit(self) -> None:
        proposal = build_credit_proposal(
            market(),
            policy(requested_debt_atomic=60_000_000),
            collateral_balance_atomic=10**18,
        )

        self.assertEqual(proposal.status, MissionStatus.BLOCKED)
        self.assertIn("requested borrow exceeds safe or available liquidity", proposal.reasons)

    def test_blocks_when_market_is_paused(self) -> None:
        proposal = build_credit_proposal(
            market(paused=True),
            policy(),
            collateral_balance_atomic=10**18,
        )

        self.assertEqual(proposal.status, MissionStatus.BLOCKED)
        self.assertIn("Aave market is not usable for collateralized borrowing", proposal.reasons)

    def test_blocks_when_borrow_apr_exceeds_policy(self) -> None:
        proposal = build_credit_proposal(
            market(borrow_apr_bps=1_250),
            policy(max_borrow_apr_bps=1_000),
            collateral_balance_atomic=10**18,
        )

        self.assertEqual(proposal.status, MissionStatus.BLOCKED)
        self.assertIn("borrow APR exceeds policy limit", proposal.reasons)

    def test_keeper_uses_sequence_policy_for_de_risking(self) -> None:
        self.assertEqual(
            keeper_action(
                health_factor_bps=14_500,
                reserve_atomic=1_000_000,
                repay_threshold_bps=15_000,
                approval_threshold_bps=12_500,
                emergency_repay_enabled=True,
            ),
            PolicyAction.REPAY_FROM_RESERVE,
        )
        self.assertEqual(
            keeper_action(
                health_factor_bps=12_000,
                reserve_atomic=1_000_000,
                repay_threshold_bps=15_000,
                approval_threshold_bps=12_500,
                emergency_repay_enabled=True,
            ),
            PolicyAction.NEEDS_APPROVAL,
        )


if __name__ == "__main__":
    unittest.main()

