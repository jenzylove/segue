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
from .morpho import discover_nvda_markets, market_state
from .morpho_risk import proposal as morpho_proposal
from .morpho_plans import borrower_action_plan, lender_supply_plan
from .mission import Mission, MissionState, MissionStore
import uuid


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

    @app.post("/v1/deferred/aave/proposal")
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

    @app.post("/v1/credit/proposal")
    def morpho_credit_proposal(body: dict[str, object]) -> dict[str, object]:
        owner = str(body.get("wallet", "")); collateral_amount = int(body.get("collateral_amount_atomic", 0)); requested = int(body.get("desired_usdc_atomic", 0))
        if not owner or collateral_amount <= 0 or requested <= 0: raise HTTPException(status_code=400, detail="wallet, collateral amount and desired USDC are required")
        markets = discover_nvda_markets()
        if not markets: raise HTTPException(status_code=404, detail="no verified Morpho NVDAc market")
        market = next((m for m in markets if m.get("loan_token", "").lower() == "0x833589fcD6eDb6E08f4c7C32D4f71b54bdA02913".lower()), markets[0])
        state = market_state("https://api.morpho.org", market["market_id"])
        return {"wallet": owner, "market": market, "market_state": state, "risk": {"state": "WAITING_FOR_LIQUIDITY" if state["available_liquidity"] == 0 else "PROPOSED", "available_liquidity_atomic": state["available_liquidity"]}, "provenance": "https://api.morpho.org/v1/blue/markets"}

    @app.get("/v1/morpho/nvda-markets")
    def morpho_markets() -> dict[str, object]:
        try:
            markets = discover_nvda_markets()
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return {"chain_id": 8453, "collateral": "0xb20000000000000000000078ee7ce2fE4908108C", "markets": markets}

    @app.get("/v1/morpho/market")
    def morpho_market() -> dict[str, object]:
        markets = discover_nvda_markets()
        if not markets:
            raise HTTPException(status_code=404, detail="no Morpho Blue NVDAc market")
        return {"chain_id": 8453, "market": markets[0], "source": "https://api.morpho.org/v1/blue/markets"}

    _missions = MissionStore()

    @app.post("/v1/missions")
    def create_mission(body: dict[str, object]) -> dict[str, object]:
        market_id = str(body.get("market_id", ""))
        owner = str(body.get("owner", ""))
        if not market_id or not owner:
            raise HTTPException(status_code=400, detail="owner and market_id are required")
        mission = Mission(str(uuid.uuid4()), owner, MissionState.PROPOSED, market_id, dict(body.get("policy", {})), dict(body.get("snapshot", {})))
        return asdict(_missions.save(mission))

    @app.get("/v1/missions/{mission_id}")
    def get_mission(mission_id: str) -> dict[str, object]:
        mission = _missions.get(mission_id)
        if mission is None:
            raise HTTPException(status_code=404, detail="mission not found")
        return asdict(mission)

    @app.get("/v1/missions/{mission_id}/timeline")
    def mission_timeline(mission_id: str) -> dict[str, object]:
        if _missions.get(mission_id) is None: raise HTTPException(status_code=404, detail="mission not found")
        return {"mission_id": mission_id, "events": _missions.timeline(mission_id)}

    @app.post("/v1/missions/{mission_id}/plan/{action}")
    def action_plan(mission_id: str, action: str, body: dict[str, object]) -> dict[str, object]:
        mission = _missions.get(mission_id)
        if mission is None: raise HTTPException(status_code=404, detail="mission not found")
        return borrower_action_plan(str(body["morpho"]), mission.market_id, action, str(body.get("calldata", "0x")))

    @app.post("/v1/morpho/lender-plan")
    def lender_plan(body: dict[str, object]) -> dict[str, object]:
        return lender_supply_plan(str(body["morpho"]), str(body["usdc"]), str(body["market_id"]), int(body["amount"]), str(body.get("calldata", "0x")))


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
