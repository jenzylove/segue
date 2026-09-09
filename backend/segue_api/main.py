from __future__ import annotations

import os
import uuid
import time
from decimal import Decimal
from pathlib import Path
from typing import Any

try:
    from fastapi import FastAPI, Header, HTTPException
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.staticfiles import StaticFiles
except ImportError:  # pragma: no cover
    FastAPI = None
    Header = lambda default=None: default  # type: ignore
    HTTPException = Exception
    CORSMiddleware = None
    StaticFiles = None

from .mission import Mission, MissionState, MissionStore
from .morpho import (
    API as MORPHO_API,
    CANONICAL_COLLATERAL,
    LOCKED_MARKET_ID,
    MORPHO_BLUE_BASE,
    USDC_BASE,
    borrower_position,
    discover_qualified_market,
    erc20_balance,
    live_position_snapshot,
    verified_oracle_price,
)
from .morpho_plans import borrower_action_plan, full_repay_plan, lender_supply_plan, withdraw_plan
from .morpho_risk import proposal as morpho_proposal
from .worker import reconcile_live, reconcile_receipt


ROOT = Path(__file__).resolve().parents[2]


def _load_env() -> None:
    for name in (".env", ".env.local"):
        path = ROOT / name
        if not path.exists(): continue
        for line in path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip().strip("'\""))


_load_env()
if FastAPI:
    app = FastAPI(title="Segue Credit API", version="1.0.0")
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
else:
    app = None

_missions = MissionStore(os.environ.get("SEGUE_DB_PATH", str(ROOT / "segue_missions.sqlite3")))
_position_cache: dict[str, tuple[float, dict[str, Any]]] = {}


def _rpc() -> str:
    value = os.environ.get("BASE_RPC_URL", "")
    if not value: raise HTTPException(status_code=503, detail="BASE_RPC_URL is required for live Base reads")
    return value


def _wallet(body: dict[str, Any]) -> str:
    value = str(body.get("wallet", body.get("owner", "")))
    if len(value) != 42 or not value.startswith("0x"):
        raise HTTPException(status_code=400, detail="wallet must be a valid EVM address")
    try: int(value[2:], 16)
    except ValueError: raise HTTPException(status_code=400, detail="wallet must be a valid EVM address")
    return value


def _reject_protocol_inputs(body: dict[str, Any]) -> None:
    forbidden = {"calldata", "market_id", "morpho_address", "loan_token", "collateral_token", "oracle", "irm", "lltv", "collateral_price_usd", "debt_address"}
    supplied = sorted(forbidden.intersection(body))
    if supplied: raise HTTPException(status_code=400, detail=f"backend-owned protocol fields are not accepted: {', '.join(supplied)}")


def _market() -> dict:
    try: return discover_qualified_market(_rpc(), MORPHO_API)
    except HTTPException: raise
    except Exception as exc: raise HTTPException(status_code=502, detail=str(exc)) from exc


def _snapshot(market: dict, wallet: str) -> dict:
    try: return live_position_snapshot(_rpc(), MORPHO_API, market, wallet)
    except Exception as exc: raise HTTPException(status_code=502, detail=f"live position read failed: {exc}") from exc


def _risk(market: dict, position: dict, desired: int, reserve_bps: int) -> dict:
    raw = int(market.get("direct_oracle_price") or verified_oracle_price(_rpc(), market["oracle_address"]))
    # `_available` is an internal copy of live liquidity; it can never be
    # overridden by request data.
    result = morpho_proposal({**market, "_available": int(market.get("available_liquidity", 0))}, int(position["collateral_position_atomic"]), 8, Decimal(raw), 6, desired, reserve_bps)
    value_atomic = int(Decimal(result["collateral_value_usd"]) * Decimal(10**6))
    debt = int(position.get("debt_assets_atomic", 0))
    protocol_max = int(result["protocol_max_debt_atomic"])
    result.update({
        "oracle_price_1e36": raw,
        "current_debt_atomic": debt,
        "current_ltv": str(Decimal(debt) / Decimal(value_atomic)) if debt and value_atomic else "0",
        "health_factor": str(Decimal(protocol_max) / Decimal(debt)) if debt else "inf",
        "health_factor_bps": int(Decimal(protocol_max) * 10000 / Decimal(debt)) if debt else None,
        "safety_buffer_atomic": max(0, protocol_max - debt),
        "market_liquidity_atomic": market.get("available_liquidity", 0),
    })
    return result


def _durable_evidence(wallet: str) -> tuple[list[dict[str, Any]], list[str]]:
    """Return the latest wallet timeline and unique transaction evidence."""
    missions = _missions.by_owner(wallet)
    if not missions:
        return [], []
    timeline = _missions.timeline(missions[0].id)
    hashes: set[str] = set()
    for event in timeline:
        payload = event.get("payload", {})
        for key, value in payload.items():
            if key.endswith("tx") and isinstance(value, str) and value.startswith("0x"):
                hashes.add(value)
    return timeline, sorted(hashes)


if FastAPI:

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "product": "segue", "credit_rail": "morpho-blue", "chain_id": "8453"}

    @app.get("/v1/credit/position")
    def credit_position(wallet: str) -> dict[str, Any]:
        key = wallet.lower()
        try:
            market = _market(); position = _snapshot(market, wallet); risk = _risk(market, position, 1_000_000, 2_000)
            timeline, evidence_hashes = _durable_evidence(wallet)
            payload = {"wallet": wallet, "market": market, "position": position, "risk": risk, "mission_state": "BORROWED" if position["borrow_shares"] else "BORROW_READY", "live_state_stale": False, "refreshed_at": time.time(), "timeline": timeline, "evidence_count": len(evidence_hashes), "evidence_hashes": evidence_hashes}
            _position_cache[key] = (time.time(), payload)
            return payload
        except HTTPException:
            cached = _position_cache.get(key)
            if cached and time.time() - cached[0] < 300:
                payload = dict(cached[1]); payload["live_state_stale"] = True; payload["stale_reason"] = "provider temporarily unavailable; showing last verified snapshot"; return payload
            raise

    @app.post("/v1/credit/proposal")
    def credit_proposal(body: dict[str, Any]) -> dict[str, Any]:
        _reject_protocol_inputs(body)
        wallet = _wallet(body); requested = int(body.get("desired_usdc_atomic", 0))
        if requested <= 0: raise HTTPException(status_code=400, detail="desired_usdc_atomic must be positive")
        market = _market(); position = _snapshot(market, wallet)
        collateral = int(body.get("collateral_amount_atomic") or position["collateral_balance_atomic"] or position["collateral_position_atomic"])
        if collateral <= 0: raise HTTPException(status_code=400, detail="wallet has no NVDAc collateral")
        position["collateral_position_atomic"] = collateral
        risk = _risk(market, position, requested, int(body.get("reserve_bps", 2_000)))
        return {"wallet": wallet, "market": market, "position": position, "risk": risk, "mission_state": "BORROWED" if position["borrow_shares"] else ("PROPOSED" if risk["state"] == "PROPOSED" else risk["state"]), "provenance": market.get("provenance", {})}

    @app.get("/v1/morpho/nvda-markets")
    def morpho_markets() -> dict[str, Any]:
        market = _market()
        return {"chain_id": 8453, "collateral": CANONICAL_COLLATERAL, "selected_market_id": market["market_id"], "markets": [market]}

    @app.get("/v1/morpho/market")
    def morpho_market() -> dict[str, Any]:
        market = _market(); return {"chain_id": 8453, "market": market, "source": market["provenance"]}

    @app.post("/v1/missions")
    def create_mission(body: dict[str, Any]) -> dict[str, Any]:
        _reject_protocol_inputs(body)
        owner = _wallet(body); market = _market(); position = _snapshot(market, owner)
        policy = dict(body.get("policy") or {})
        state = MissionState.BORROWED if position["borrow_shares"] else (MissionState.BORROW_READY if market["available_liquidity"] else MissionState.WAITING_FOR_LIQUIDITY)
        mission = Mission(str(uuid.uuid4()), owner, state, LOCKED_MARKET_ID, policy, {"market": market, "position": position})
        _missions.save(mission); _missions.snapshot(mission.id, "market", market); _missions.snapshot(mission.id, "position", position); _missions.event(mission.id, "MISSION_CREATED", {"state": state.value, "source": "Base RPC"})
        return {**mission.__dict__, "state": mission.state.value}

    @app.get("/v1/missions")
    def list_missions(wallet: str) -> dict[str, Any]:
        _wallet({"wallet": wallet})
        missions = _missions.by_owner(wallet)
        return {"wallet": wallet, "missions": [{**mission.__dict__, "state": mission.state.value, "actions": _missions.actions(mission.id)} for mission in missions]}

    @app.get("/v1/missions/{mission_id}")
    def get_mission(mission_id: str) -> dict[str, Any]:
        mission = _missions.get(mission_id)
        if not mission: raise HTTPException(status_code=404, detail="mission not found")
        return {**mission.__dict__, "state": mission.state.value, "actions": _missions.actions(mission_id)}

    @app.post("/v1/missions/{mission_id}/refresh")
    @app.get("/v1/missions/{mission_id}/risk")
    def refresh_mission(mission_id: str) -> dict[str, Any]:
        try: mission = reconcile_live(_missions, mission_id, MORPHO_API, _rpc())
        except Exception as exc: raise HTTPException(status_code=502, detail=str(exc)) from exc
        return {"mission_id": mission_id, "state": mission.state.value, "snapshot": mission.snapshot}

    @app.get("/v1/missions/{mission_id}/status")
    def mission_status(mission_id: str) -> dict[str, Any]:
        mission = _missions.get(mission_id)
        if not mission: raise HTTPException(status_code=404, detail="mission not found")
        return {"mission_id": mission_id, "state": mission.state.value, "snapshot": mission.snapshot}

    @app.get("/v1/missions/{mission_id}/timeline")
    @app.get("/v1/missions/{mission_id}/evidence")
    def mission_timeline(mission_id: str) -> dict[str, Any]:
        if not _missions.get(mission_id): raise HTTPException(status_code=404, detail="mission not found")
        return {"mission_id": mission_id, "events": _missions.timeline(mission_id), "snapshots": _missions.snapshots(mission_id), "actions": _missions.actions(mission_id)}

    @app.get("/v1/missions/{mission_id}/actions")
    def mission_actions(mission_id: str) -> dict[str, Any]:
        if not _missions.get(mission_id): raise HTTPException(status_code=404, detail="mission not found")
        return {"mission_id": mission_id, "actions": _missions.actions(mission_id)}

    @app.get("/v1/missions/{mission_id}/action-requirements")
    def action_requirements(mission_id: str) -> dict[str, Any]:
        mission = _missions.get(mission_id)
        if not mission: raise HTTPException(status_code=404, detail="mission not found")
        position = mission.snapshot.get("position", {})
        return {"mission_id": mission_id, "state": mission.state.value, "requirements": {"borrow_shares": int(position.get("borrow_shares", 0)), "withdrawal_allowed": int(position.get("borrow_shares", 0)) == 0, "fresh_reconciliation_required": True}, "actions": _missions.actions(mission_id)}

    @app.post("/v1/missions/{mission_id}/actions/{action_key}/submit")
    def submit_action(mission_id: str, action_key: str, body: dict[str, Any]) -> dict[str, Any]:
        if not _missions.get(mission_id): raise HTTPException(status_code=404, detail="mission not found")
        tx_hash = str(body.get("tx_hash", ""))
        if not tx_hash.startswith("0x") or len(tx_hash) != 66: raise HTTPException(status_code=400, detail="a 32-byte transaction hash is required")
        action = _missions.get_action(action_key)
        if not action or action["mission_id"] != mission_id: raise HTTPException(status_code=404, detail="action not found")
        if action["status"] == "CONFIRMED": return action
        result = _missions.update_action(action_key, status="SUBMITTED", tx_hash=tx_hash, evidence={"submitted": True, "postcondition_verified": False})
        _missions.event(mission_id, "TX_SUBMITTED", {"idempotency_key": action_key, "tx_hash": tx_hash})
        return result

    @app.post("/v1/missions/{mission_id}/plan/{action}")
    def action_plan(mission_id: str, action: str, body: dict[str, Any], idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")) -> dict[str, Any]:
        _reject_protocol_inputs(body)
        mission = _missions.get(mission_id)
        if not mission: raise HTTPException(status_code=404, detail="mission not found")
        normalized = {"supplyCollateral": "supply", "withdrawCollateral": "withdraw"}.get(action, action)
        key = str(body.get("idempotency_key") or idempotency_key or f"{mission_id}:{action}:{body.get('amount', 0)}")
        existing = _missions.get_action(key)
        if existing:
            if existing["mission_id"] != mission_id or existing["action"] != normalized:
                raise HTTPException(status_code=409, detail="idempotency key is already bound to a different action")
            return existing
        market = _market(); amount = int(body.get("amount", 0))
        if amount <= 0 and normalized != "withdraw": raise HTTPException(status_code=400, detail="amount must be positive")
        pre_position = _snapshot(market, mission.owner)
        if normalized == "withdraw":
            position = pre_position
            if position["borrow_shares"]: raise HTTPException(status_code=409, detail="withdrawal gated until borrow shares are zero")
            plan = withdraw_plan(MORPHO_BLUE_BASE, mission.market_id, wallet=mission.owner, market=market, collateral_amount=amount or position["collateral_position_atomic"])
        else:
            plan = borrower_action_plan(MORPHO_BLUE_BASE, mission.market_id, normalized, wallet=mission.owner, amount=amount, market=market)
        plan["pre_position"] = pre_position
        result = _missions.action(key, mission_id, normalized, plan, status="READY", evidence={"pre_position": pre_position})
        mission.plan = plan
        _missions.save(mission)
        return result

    @app.post("/v1/morpho/lender-plan")
    def lender_plan(body: dict[str, Any]) -> dict[str, Any]:
        _reject_protocol_inputs(body)
        wallet = _wallet(body); amount = int(body.get("amount", 0))
        if amount <= 0: raise HTTPException(status_code=400, detail="amount must be positive")
        market = _market(); plan = lender_supply_plan(MORPHO_BLUE_BASE, USDC_BASE, market["market_id"], amount, wallet=wallet, market=market)
        return {"idempotency_key": f"lender:{wallet.lower()}:{market['market_id']}:{amount}", "status": "READY", **plan}

    @app.post("/v1/missions/{mission_id}/repay-close")
    def prepare_full_repay(mission_id: str, body: dict[str, Any] | None = None, idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")) -> dict[str, Any]:
        _reject_protocol_inputs(body or {})
        mission = _missions.get(mission_id)
        if not mission: raise HTTPException(status_code=404, detail="mission not found")
        requested_key = str((body or {}).get("idempotency_key") or idempotency_key or "")
        if requested_key:
            existing = _missions.get_action(requested_key)
            if existing:
                if existing["mission_id"] != mission_id or existing["action"] != "full-repay":
                    raise HTTPException(status_code=409, detail="idempotency key is already bound to a different action")
                return existing
        market = _market(); position = _snapshot(market, mission.owner); shares = int(position["borrow_shares"])
        if shares <= 0: raise HTTPException(status_code=409, detail="position has no borrow shares")
        debt = int(position["debt_assets_atomic"]); approval = debt + max(1, debt // 100) + 1
        plan = full_repay_plan(MORPHO_BLUE_BASE, mission.market_id, wallet=mission.owner, market=market, borrow_shares=shares, approval_amount=approval)
        plan["pre_position"] = position
        key = requested_key or f"{mission_id}:full-repay:{shares}"
        result = _missions.action(key, mission_id, "full-repay", plan, evidence={"pre_position": position})
        mission.plan = plan
        _missions.save(mission)
        return result

    @app.post("/v1/missions/{mission_id}/reconcile")
    def reconcile(mission_id: str, body: dict[str, Any]) -> dict[str, Any]:
        tx_hash = str(body.get("tx_hash", "")); key = body.get("idempotency_key")
        if not tx_hash: raise HTTPException(status_code=400, detail="tx_hash is required")
        try: mission = reconcile_receipt(_missions, mission_id, tx_hash, _rpc(), str(key) if key else None)
        except Exception as exc: raise HTTPException(status_code=502, detail=str(exc)) from exc
        return {"mission_id": mission_id, "state": mission.state.value, "tx_hash": mission.tx_hash, "snapshot": mission.snapshot, "timeline": _missions.timeline(mission_id)}

    # Serve the frozen landing surface from the same deployable service. API
    # routes above remain authoritative; this catch-all handles frontend paths.
    app.mount("/", StaticFiles(directory=str(ROOT / "frontend"), html=True), name="frontend")
