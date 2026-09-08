from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping

from .models import AaveMarket, CreditPolicy, is_address
from .risk import build_credit_proposal


class TxKind(str, Enum):
    APPROVE_COLLATERAL = "APPROVE_COLLATERAL"
    AAVE_SUPPLY = "AAVE_SUPPLY"
    AAVE_BORROW = "AAVE_BORROW"
    APPROVE_DEBT_REPAY = "APPROVE_DEBT_REPAY"
    AAVE_REPAY = "AAVE_REPAY"
    AAVE_WITHDRAW = "AAVE_WITHDRAW"


@dataclass(frozen=True)
class UnsignedTx:
    kind: TxKind
    to: str
    data: str
    value: int = 0
    note: str = ""

    def validate(self) -> None:
        if not is_address(self.to):
            raise ValueError("transaction target must be a verified nonzero address")
        if self.value != 0:
            raise ValueError("Aave credit transactions must not send native value")
        if not isinstance(self.data, str) or not self.data.startswith("0x") or len(self.data) < 10:
            raise ValueError("transaction calldata is malformed")
        int(self.data[2:], 16)


@dataclass(frozen=True)
class MissionTxPlan:
    title: str
    unsigned_transactions: tuple[UnsignedTx, ...]
    human_boundary: str
    evidence: Mapping[str, str] = field(default_factory=dict)

    def validate(self) -> None:
        if not self.title:
            raise ValueError("plan title is required")
        if not self.unsigned_transactions:
            raise ValueError("plan must contain at least one transaction")
        for tx in self.unsigned_transactions:
            tx.validate()
        if not self.human_boundary:
            raise ValueError("human boundary is required")


def build_open_credit_plan(
    market: AaveMarket,
    policy: CreditPolicy,
    collateral_balance_atomic: int,
    collateral_to_supply_atomic: int,
    borrower: str,
    referral_code: int = 0,
) -> MissionTxPlan:
    if not is_address(borrower):
        raise ValueError("borrower must be a verified nonzero address")
    if collateral_to_supply_atomic <= 0:
        raise ValueError("collateral to supply must be positive")
    proposal = build_credit_proposal(market, policy, collateral_balance_atomic)
    if proposal.status.value != "PROPOSED":
        raise ValueError("cannot build open-credit transactions for a blocked proposal")
    if collateral_to_supply_atomic < proposal.collateral_required_atomic:
        raise ValueError("collateral to supply is below the proposal requirement")

    txs = (
        UnsignedTx(
            TxKind.APPROVE_COLLATERAL,
            market.collateral.address,
            encode_call("0x095ea7b3", [address_word(market.pool), uint_word(collateral_to_supply_atomic)]),
            note="Approve Aave Pool to transfer the exact B20 collateral amount.",
        ),
        UnsignedTx(
            TxKind.AAVE_SUPPLY,
            market.pool,
            encode_call(
                "0x617ba037",
                [
                    address_word(market.collateral.address),
                    uint_word(collateral_to_supply_atomic),
                    address_word(borrower),
                    uint_word(referral_code),
                ],
            ),
            note="Supply B20 collateral to Aave on behalf of the user.",
        ),
        UnsignedTx(
            TxKind.AAVE_BORROW,
            market.pool,
            encode_call(
                "0xa415bcad",
                [
                    address_word(market.debt_asset.address),
                    uint_word(policy.requested_debt_atomic),
                    uint_word(2),
                    uint_word(referral_code),
                    address_word(borrower),
                ],
            ),
            note="Borrow variable-rate USDC inside the approved credit policy.",
        ),
    )
    plan = MissionTxPlan(
        title="Open Segue credit mission",
        unsigned_transactions=txs,
        human_boundary="User wallet must review and sign these transactions locally.",
        evidence=proposal.evidence,
    )
    plan.validate()
    return plan


def build_close_credit_plan(
    market: AaveMarket,
    debt_to_repay_atomic: int,
    collateral_to_withdraw_atomic: int,
    borrower: str,
) -> MissionTxPlan:
    if not is_address(borrower):
        raise ValueError("borrower must be a verified nonzero address")
    if debt_to_repay_atomic <= 0:
        raise ValueError("debt to repay must be positive")
    if collateral_to_withdraw_atomic <= 0:
        raise ValueError("collateral to withdraw must be positive")
    market.validate()

    txs = (
        UnsignedTx(
            TxKind.APPROVE_DEBT_REPAY,
            market.debt_asset.address,
            encode_call("0x095ea7b3", [address_word(market.pool), uint_word(debt_to_repay_atomic)]),
            note="Approve Aave Pool to pull the exact USDC repayment amount.",
        ),
        UnsignedTx(
            TxKind.AAVE_REPAY,
            market.pool,
            encode_call(
                "0x573ade81",
                [
                    address_word(market.debt_asset.address),
                    uint_word(debt_to_repay_atomic),
                    uint_word(2),
                    address_word(borrower),
                ],
            ),
            note="Repay variable-rate USDC debt for the user.",
        ),
        UnsignedTx(
            TxKind.AAVE_WITHDRAW,
            market.pool,
            encode_call(
                "0x69328dec",
                [
                    address_word(market.collateral.address),
                    uint_word(collateral_to_withdraw_atomic),
                    address_word(borrower),
                ],
            ),
            note="Withdraw B20 collateral back to the user.",
        ),
    )
    plan = MissionTxPlan(
        title="Close Segue credit mission",
        unsigned_transactions=txs,
        human_boundary="User wallet must review and sign these transactions locally.",
        evidence=market.provenance,
    )
    plan.validate()
    return plan


def encode_call(selector: str, words: list[str]) -> str:
    if not selector.startswith("0x") or len(selector) != 10:
        raise ValueError("selector must be four bytes")
    return selector + "".join(word.removeprefix("0x") for word in words)


def address_word(address: str) -> str:
    if not is_address(address):
        raise ValueError("cannot encode invalid address")
    return "0x" + address.lower().removeprefix("0x").rjust(64, "0")


def uint_word(value: int) -> str:
    if value < 0:
        raise ValueError("cannot encode negative uint")
    return "0x" + f"{value:064x}"

