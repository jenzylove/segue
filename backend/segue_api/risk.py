from __future__ import annotations

from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR, getcontext

from .models import AaveMarket, CreditPolicy, CreditProposal, MissionStatus, PolicyAction

getcontext().prec = 80


def build_credit_proposal(
    market: AaveMarket,
    policy: CreditPolicy,
    collateral_balance_atomic: int,
) -> CreditProposal:
    market.validate()
    policy.validate()
    if collateral_balance_atomic <= 0:
        return _blocked(policy, "wallet has no supported B20 collateral")

    reasons: list[str] = []
    if not market.is_usable:
        reasons.append("Aave market is not usable for collateralized borrowing")
    if policy.max_borrow_apr_bps and market.borrow_apr_bps > policy.max_borrow_apr_bps:
        reasons.append("borrow APR exceeds policy limit")

    collateral_value = atomic_to_usd(
        collateral_balance_atomic,
        market.collateral.decimals,
        market.collateral_price_usd,
    )
    requested_debt_value = atomic_to_usd(
        policy.requested_debt_atomic,
        market.debt_asset.decimals,
        market.debt_price_usd,
    )
    effective_ltv_bps = min(market.ltv_bps, policy.max_ltv_bps)
    max_safe_debt_value = collateral_value * Decimal(effective_ltv_bps) / Decimal(10_000)
    max_safe_debt_atomic = usd_to_atomic(
        max_safe_debt_value,
        market.debt_asset.decimals,
        market.debt_price_usd,
        rounding=ROUND_FLOOR,
    )
    available_debt_atomic = min(max_safe_debt_atomic, market.available_liquidity_atomic)
    projected_ltv_bps = ratio_bps(requested_debt_value, collateral_value)
    projected_hf_bps = health_factor_bps(
        collateral_value,
        requested_debt_value,
        market.liquidation_threshold_bps,
    )
    reserve_required_atomic = ceil_mul_div(
        policy.requested_debt_atomic,
        policy.reserve_bps,
        10_000,
    )

    if policy.requested_debt_atomic > available_debt_atomic:
        reasons.append("requested borrow exceeds safe or available liquidity")
    if projected_hf_bps < policy.min_health_factor_bps:
        reasons.append("projected health factor is below policy minimum")

    collateral_required_value = requested_debt_value * Decimal(10_000) / Decimal(effective_ltv_bps)
    collateral_required_atomic = usd_to_atomic(
        collateral_required_value,
        market.collateral.decimals,
        market.collateral_price_usd,
        rounding=ROUND_CEILING,
    )

    if reasons:
        return CreditProposal(
            status=MissionStatus.BLOCKED,
            action=PolicyAction.BLOCKED,
            collateral_required_atomic=collateral_required_atomic,
            requested_debt_atomic=policy.requested_debt_atomic,
            max_safe_debt_atomic=available_debt_atomic,
            projected_ltv_bps=projected_ltv_bps,
            projected_health_factor_bps=projected_hf_bps,
            reserve_required_atomic=reserve_required_atomic,
            reasons=tuple(reasons),
            evidence=dict(market.provenance),
        )

    return CreditProposal(
        status=MissionStatus.PROPOSED,
        action=PolicyAction.HOLD,
        collateral_required_atomic=collateral_required_atomic,
        requested_debt_atomic=policy.requested_debt_atomic,
        max_safe_debt_atomic=available_debt_atomic,
        projected_ltv_bps=projected_ltv_bps,
        projected_health_factor_bps=projected_hf_bps,
        reserve_required_atomic=reserve_required_atomic,
        reasons=("requested borrow is inside Aave and Segue policy limits",),
        evidence=dict(market.provenance),
    )


def keeper_action(
    health_factor_bps: int,
    reserve_atomic: int,
    repay_threshold_bps: int,
    approval_threshold_bps: int,
    emergency_repay_enabled: bool,
) -> PolicyAction:
    if health_factor_bps <= 0:
        return PolicyAction.BLOCKED
    if health_factor_bps < approval_threshold_bps:
        return PolicyAction.NEEDS_APPROVAL
    if health_factor_bps < repay_threshold_bps:
        if emergency_repay_enabled and reserve_atomic > 0:
            return PolicyAction.REPAY_FROM_RESERVE
        return PolicyAction.NEEDS_APPROVAL
    return PolicyAction.HOLD


def atomic_to_usd(amount_atomic: int, decimals: int, price_usd: Decimal) -> Decimal:
    return Decimal(amount_atomic) * price_usd / (Decimal(10) ** decimals)


def usd_to_atomic(
    value_usd: Decimal,
    decimals: int,
    price_usd: Decimal,
    rounding: str,
) -> int:
    amount = value_usd * (Decimal(10) ** decimals) / price_usd
    return int(amount.to_integral_value(rounding=rounding))


def ratio_bps(numerator: Decimal, denominator: Decimal) -> int:
    if denominator <= 0:
        return 0
    return int((numerator * Decimal(10_000) / denominator).to_integral_value(rounding=ROUND_FLOOR))


def health_factor_bps(
    collateral_value: Decimal,
    debt_value: Decimal,
    liquidation_threshold_bps: int,
) -> int:
    if debt_value <= 0:
        return 0
    adjusted = collateral_value * Decimal(liquidation_threshold_bps) / Decimal(10_000)
    return int((adjusted * Decimal(10_000) / debt_value).to_integral_value(rounding=ROUND_FLOOR))


def ceil_mul_div(value: int, numerator: int, denominator: int) -> int:
    return (value * numerator + denominator - 1) // denominator


def _blocked(policy: CreditPolicy, reason: str) -> CreditProposal:
    policy.validate()
    return CreditProposal(
        status=MissionStatus.BLOCKED,
        action=PolicyAction.BLOCKED,
        collateral_required_atomic=0,
        requested_debt_atomic=policy.requested_debt_atomic,
        max_safe_debt_atomic=0,
        projected_ltv_bps=0,
        projected_health_factor_bps=0,
        reserve_required_atomic=0,
        reasons=(reason,),
        evidence={},
    )

