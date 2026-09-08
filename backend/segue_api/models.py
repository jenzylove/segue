from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Mapping


class MissionStatus(str, Enum):
    PROPOSED = "PROPOSED"
    APPROVED = "APPROVED"
    BORROWED = "BORROWED"
    MANAGED = "MANAGED"
    DE_RISKING = "DE_RISKING"
    NEEDS_APPROVAL = "NEEDS_APPROVAL"
    REPAID = "REPAID"
    CLOSED = "CLOSED"
    BLOCKED = "BLOCKED"


class PolicyAction(str, Enum):
    HOLD = "HOLD"
    REPAY_FROM_RESERVE = "REPAY_FROM_RESERVE"
    UNWIND_ALLOCATION = "UNWIND_ALLOCATION"
    NEEDS_APPROVAL = "NEEDS_APPROVAL"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class TokenRef:
    symbol: str
    address: str
    decimals: int
    source: str

    def validate(self) -> None:
        if not self.symbol:
            raise ValueError("token symbol is required")
        if not is_address(self.address):
            raise ValueError(f"{self.symbol} address is not a valid EVM address")
        if self.decimals < 0 or self.decimals > 36:
            raise ValueError(f"{self.symbol} decimals are outside the supported range")
        if not self.source:
            raise ValueError(f"{self.symbol} provenance source is required")


@dataclass(frozen=True)
class AaveMarket:
    collateral: TokenRef
    debt_asset: TokenRef
    pool: str
    protocol_data_provider: str
    ltv_bps: int
    liquidation_threshold_bps: int
    liquidation_bonus_bps: int
    borrow_apr_bps: int
    available_liquidity_atomic: int
    collateral_price_usd: Decimal
    debt_price_usd: Decimal
    active: bool
    frozen: bool
    paused: bool
    borrowing_enabled: bool
    collateral_enabled: bool
    provenance: Mapping[str, str] = field(default_factory=dict)

    def validate(self) -> None:
        self.collateral.validate()
        self.debt_asset.validate()
        if not is_address(self.pool):
            raise ValueError("Aave pool address is not valid")
        if not is_address(self.protocol_data_provider):
            raise ValueError("Aave data provider address is not valid")
        for name, value in (
            ("ltv_bps", self.ltv_bps),
            ("liquidation_threshold_bps", self.liquidation_threshold_bps),
            ("liquidation_bonus_bps", self.liquidation_bonus_bps),
            ("borrow_apr_bps", self.borrow_apr_bps),
        ):
            if value < 0:
                raise ValueError(f"{name} cannot be negative")
        if self.ltv_bps > self.liquidation_threshold_bps:
            raise ValueError("Aave LTV cannot exceed liquidation threshold")
        if self.liquidation_threshold_bps > 10_000:
            raise ValueError("liquidation threshold cannot exceed 100%")
        if self.available_liquidity_atomic < 0:
            raise ValueError("available liquidity cannot be negative")
        if self.collateral_price_usd <= 0 or self.debt_price_usd <= 0:
            raise ValueError("market prices must be positive")

    @property
    def is_usable(self) -> bool:
        return (
            self.active
            and not self.frozen
            and not self.paused
            and self.borrowing_enabled
            and self.collateral_enabled
            and self.ltv_bps > 0
            and self.available_liquidity_atomic > 0
        )


@dataclass(frozen=True)
class CreditPolicy:
    requested_debt_atomic: int
    max_ltv_bps: int
    min_health_factor_bps: int
    reserve_bps: int
    max_borrow_apr_bps: int
    allow_productive_liquidity: bool = False
    emergency_repay_enabled: bool = True

    def validate(self) -> None:
        if self.requested_debt_atomic <= 0:
            raise ValueError("requested debt must be positive")
        if self.max_ltv_bps <= 0 or self.max_ltv_bps > 10_000:
            raise ValueError("max LTV must be between 0 and 100%")
        if self.min_health_factor_bps < 10_000:
            raise ValueError("minimum health factor must be at least 1.0")
        if self.reserve_bps < 0 or self.reserve_bps > 10_000:
            raise ValueError("reserve must be between 0 and 100%")
        if self.max_borrow_apr_bps < 0:
            raise ValueError("max borrow APR cannot be negative")


@dataclass(frozen=True)
class CreditProposal:
    status: MissionStatus
    action: PolicyAction
    collateral_required_atomic: int
    requested_debt_atomic: int
    max_safe_debt_atomic: int
    projected_ltv_bps: int
    projected_health_factor_bps: int
    reserve_required_atomic: int
    reasons: tuple[str, ...]
    evidence: Mapping[str, str]


def is_address(value: str) -> bool:
    if not isinstance(value, str):
        return False
    if len(value) != 42 or not value.startswith("0x"):
        return False
    try:
        int(value[2:], 16)
    except ValueError:
        return False
    return int(value[2:], 16) != 0

