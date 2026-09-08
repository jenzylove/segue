from __future__ import annotations

from dataclasses import asdict
from decimal import Decimal

try:
    from fastapi import FastAPI, HTTPException
    from pydantic import BaseModel, Field
except ImportError:  # pragma: no cover - keeps domain tests dependency-light.
    FastAPI = None
    HTTPException = Exception
    BaseModel = object

    def Field(default=None, **_: object) -> object:
        return default

from .models import AaveMarket, CreditPolicy, TokenRef
from .risk import build_credit_proposal


if FastAPI:
    app = FastAPI(title="Segue Credit Backend", version="0.2.0")
else:
    app = None


class ProposalRequest(BaseModel):
    collateral_symbol: str = Field(..., min_length=1)
    collateral_address: str
    collateral_decimals: int = Field(..., ge=0, le=36)
    collateral_balance_atomic: int = Field(..., gt=0)
    collateral_price_usd: str
    debt_symbol: str = "USDC"
    debt_address: str
    debt_decimals: int = 6
    debt_price_usd: str = "1"
    requested_debt_atomic: int = Field(..., gt=0)
    max_ltv_bps: int = Field(4_000, gt=0, le=10_000)
    min_health_factor_bps: int = Field(15_000, ge=10_000)
    reserve_bps: int = Field(2_000, ge=0, le=10_000)
    max_borrow_apr_bps: int = Field(2_000, ge=0)
    aave_pool: str
    aave_data_provider: str
    aave_ltv_bps: int = Field(..., ge=0, le=10_000)
    aave_liquidation_threshold_bps: int = Field(..., ge=0, le=10_000)
    aave_liquidation_bonus_bps: int = Field(..., ge=0)
    aave_borrow_apr_bps: int = Field(..., ge=0)
    aave_available_liquidity_atomic: int = Field(..., ge=0)
    aave_active: bool = True
    aave_frozen: bool = False
    aave_paused: bool = False
    aave_borrowing_enabled: bool = True
    aave_collateral_enabled: bool = True
    provenance_source: str


if FastAPI:

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "product": "segue-credit"}

    @app.post("/v1/credit/proposal")
    def credit_proposal(request: ProposalRequest) -> dict[str, object]:
        try:
            proposal = build_credit_proposal(
                _market_from_request(request),
                _policy_from_request(request),
                request.collateral_balance_atomic,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return asdict(proposal)


def _market_from_request(request: ProposalRequest) -> AaveMarket:
    return AaveMarket(
        collateral=TokenRef(
            symbol=request.collateral_symbol,
            address=request.collateral_address,
            decimals=request.collateral_decimals,
            source=request.provenance_source,
        ),
        debt_asset=TokenRef(
            symbol=request.debt_symbol,
            address=request.debt_address,
            decimals=request.debt_decimals,
            source=request.provenance_source,
        ),
        pool=request.aave_pool,
        protocol_data_provider=request.aave_data_provider,
        ltv_bps=request.aave_ltv_bps,
        liquidation_threshold_bps=request.aave_liquidation_threshold_bps,
        liquidation_bonus_bps=request.aave_liquidation_bonus_bps,
        borrow_apr_bps=request.aave_borrow_apr_bps,
        available_liquidity_atomic=request.aave_available_liquidity_atomic,
        collateral_price_usd=Decimal(request.collateral_price_usd),
        debt_price_usd=Decimal(request.debt_price_usd),
        active=request.aave_active,
        frozen=request.aave_frozen,
        paused=request.aave_paused,
        borrowing_enabled=request.aave_borrowing_enabled,
        collateral_enabled=request.aave_collateral_enabled,
        provenance={"market": request.provenance_source},
    )


def _policy_from_request(request: ProposalRequest) -> CreditPolicy:
    return CreditPolicy(
        requested_debt_atomic=request.requested_debt_atomic,
        max_ltv_bps=request.max_ltv_bps,
        min_health_factor_bps=request.min_health_factor_bps,
        reserve_bps=request.reserve_bps,
        max_borrow_apr_bps=request.max_borrow_apr_bps,
    )

