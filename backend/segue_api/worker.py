from __future__ import annotations

import os
from decimal import Decimal

from .mission import Mission, MissionState, MissionStore
from .morpho import API, LOCKED_MARKET_ID, borrower_position, discover_qualified_market, market_state, onchain_position, rpc_call, live_position_snapshot, verified_oracle_price
from .morpho_risk import proposal


def reconcile_mission(store: MissionStore, mission_id: str, available_liquidity: int, onchain_borrowed: int = 0) -> Mission:
    mission = store.get(mission_id)
    if mission is None: raise ValueError("mission not found")
    if mission.state in (MissionState.CLOSED,): return mission
    if onchain_borrowed > 0: mission.state = MissionState.BORROWED
    elif available_liquidity <= 0: mission.state = MissionState.WAITING_FOR_LIQUIDITY
    elif mission.state in (MissionState.PROPOSED, MissionState.APPROVED, MissionState.WAITING_FOR_LIQUIDITY): mission.state = MissionState.BORROW_READY
    store.event(mission_id, "MISSION_STATE", {"state": mission.state.value, "source": "reconcile_mission"})
    return store.save(mission)


def _risk(market: dict, snapshot: dict, reserve_bps: int = 2000) -> dict:
    collateral = int(snapshot.get("collateral_position_atomic", 0))
    debt = int(snapshot.get("debt_assets_atomic", 0))
    out = proposal({**market, "_available": int(market.get("available_liquidity", 0))}, collateral, 8, Decimal(str(market["direct_oracle_price"])), 6, max(debt, 1), reserve_bps)
    out["current_debt_atomic"] = debt
    collateral_value_atomic = Decimal(str(out["collateral_value_usd"])) * Decimal(10**6)
    out["current_ltv"] = str(Decimal(debt) / collateral_value_atomic) if debt and collateral_value_atomic else "0"
    max_debt = int(out["protocol_max_debt_atomic"])
    out["health_factor"] = str(Decimal(max_debt) / Decimal(debt)) if debt else "inf"
    out["health_factor_bps"] = int(Decimal(max_debt) * Decimal(10000) / Decimal(debt)) if debt else 2**31
    out["safety_buffer_atomic"] = max(0, max_debt - debt)
    return out


def reconcile_live(store: MissionStore, mission_id: str, api: str = API, rpc_url: str | None = None) -> Mission:
    mission = store.get(mission_id)
    if mission is None: raise ValueError("mission not found")
    rpc = rpc_url or os.environ.get("BASE_RPC_URL", "")
    if not rpc: raise ValueError("BASE_RPC_URL is required for live reconciliation")
    market = {"market_id": mission.market_id, **mission.snapshot.get("market", {})}
    if not market.get("loan_token"):
        market = discover_qualified_market(rpc, api)
    else:
        # Never trust a persisted market without revalidating the locked identity.
        fresh = discover_qualified_market(rpc, api)
        if fresh["market_id"].lower() != mission.market_id.lower(): raise ValueError("mission market is no longer the locked market")
        market = fresh
    snapshot = live_position_snapshot(rpc, api, market, mission.owner)
    snapshot["oracle_price_1e36"] = verified_oracle_price(rpc, market["oracle_address"])
    risk = _risk(market, snapshot, int(mission.policy.get("reserve_bps", 2000)))
    mission.snapshot = {**mission.snapshot, "market": market, "position": snapshot, "risk": risk}
    borrowed = int(snapshot.get("borrow_shares", 0))
    if borrowed > 0: mission.state = MissionState.BORROWED
    elif snapshot["market"]["available_liquidity"] <= 0: mission.state = MissionState.WAITING_FOR_LIQUIDITY
    elif mission.state not in (MissionState.CLOSED, MissionState.REPAID): mission.state = MissionState.BORROW_READY
    store.snapshot(mission_id, "market", market); store.snapshot(mission_id, "position", snapshot); store.snapshot(mission_id, "risk", risk)
    store.event(mission_id, "LIVE_RECONCILIATION", {"state": mission.state.value, "borrow_shares": borrowed, "debt_assets_atomic": snapshot["debt_assets_atomic"]})
    return store.save(mission)


def reconcile_receipt(store: MissionStore, mission_id: str, tx_hash: str, rpc_url: str, action_key: str | None = None) -> Mission:
    mission = store.get(mission_id)
    if mission is None: raise ValueError("mission not found")
    action = store.get_action(action_key) if action_key else None
    pre_position = (action.get("evidence") or {}).get("pre_position", {}) if action else {}
    if action and action["status"] == "CONFIRMED":
        return mission
    tx = rpc_call(rpc_url, "eth_getTransactionByHash", [tx_hash]) if action else None
    tx_check = _check_transaction(action, tx) if action else {"checked": False}
    if tx_check.get("mismatch"):
        evidence = {"tx_hash": tx_hash, "status": "FAILED", "transaction": tx, "transaction_check": tx_check, "pre_position": pre_position}
        if action_key:
            store.update_action(action_key, status="FAILED", tx_hash=tx_hash, evidence=evidence)
        store.event(mission_id, "TX_MISMATCH", evidence)
        mission.state = MissionState.ERROR
        return store.save(mission)
    receipt = rpc_call(rpc_url, "eth_getTransactionReceipt", [tx_hash])
    if receipt is None:
        if action_key: store.update_action(action_key, status="SUBMITTED", tx_hash=tx_hash, evidence={"submitted": True, "transaction_check": tx_check, "postcondition_verified": False, "pre_position": pre_position})
        store.event(mission_id, "TX_PENDING", {"tx_hash": tx_hash, "transaction_check": tx_check}); return mission
    status = int(str(receipt.get("status", "0x0")), 16)
    kind = "TX_CONFIRMED" if status == 1 else "TX_FAILED"
    evidence = {"tx_hash": tx_hash, "receipt": receipt, "transaction": tx, "transaction_check": tx_check, "status": "CONFIRMED" if status == 1 else "FAILED", "pre_position": pre_position}
    if action_key: store.update_action(action_key, status="SUBMITTED" if status == 1 else "FAILED", tx_hash=tx_hash, evidence=evidence)
    store.event(mission_id, kind, evidence)
    if status != 1:
        mission.state = MissionState.ERROR
        return store.save(mission)
    mission.tx_hash = tx_hash
    # A successful receipt is not enough: state is reconciled from fresh provider reads.
    try:
        reconciled = reconcile_live(store, mission_id, rpc_url=rpc_url)
        postcondition = _verify_postcondition(action, reconciled) if action else {"verified": True, "reason": "no action key supplied"}
        evidence["postcondition"] = postcondition
        if not postcondition.get("verified"):
            if action_key:
                store.update_action(action_key, status="SUBMITTED", tx_hash=tx_hash, evidence={**evidence, "postcondition_verified": False})
            store.event(mission_id, "POSTCONDITION_PENDING", {"tx_hash": tx_hash, "postcondition": postcondition})
            return store.save(reconciled)
        if action_key:
            evidence["postcondition_verified"] = True
            evidence["position"] = reconciled.snapshot.get("position", {})
            store.update_action(action_key, status="CONFIRMED", tx_hash=tx_hash, evidence=evidence)
            operation = str(action.get("plan", {}).get("flow", action.get("action", "")))
            position = reconciled.snapshot.get("position", {})
            if operation == "full-repay" and int(position.get("borrow_shares", 0)) == 0:
                reconciled.state = MissionState.REPAID
                store.event(mission_id, "FULL_REPAY_CONFIRMED", {"tx_hash": tx_hash, "borrow_shares": 0})
            elif operation in {"withdraw", "withdraw-collateral"} and int(position.get("collateral_position_atomic", 0)) == 0:
                reconciled.state = MissionState.CLOSED
                store.event(mission_id, "COLLATERAL_WITHDRAW_CONFIRMED", {"tx_hash": tx_hash})
            store.save(reconciled)
        return reconciled
    except Exception as exc:
        if action_key:
            evidence["postcondition_verified"] = False
            evidence["reconciliation_error"] = str(exc)
            store.update_action(action_key, status="SUBMITTED", tx_hash=tx_hash, evidence=evidence)
        store.event(mission_id, "POSTCONDITION_PENDING", {"tx_hash": tx_hash, "error": str(exc)})
        return store.save(mission)


def action_is_confirmed(store: MissionStore, key: str) -> bool:
    action = store.get_action(key)
    return bool(action and action["status"] == "CONFIRMED")


def _check_transaction(action: dict | None, tx: object) -> dict:
    if not action:
        return {"checked": False, "reason": "no action key supplied"}
    if not isinstance(tx, dict):
        return {"checked": False, "reason": "transaction details unavailable from provider"}
    plan = action.get("plan") or {}
    calls = plan.get("actions") or []
    to = str(tx.get("to", "")).lower()
    data = str(tx.get("input", tx.get("data", ""))).lower()
    pairs = {(str(call.get("target", "")).lower(), str(call.get("calldata", ""))[:10].lower()) for call in calls}
    targets = {target for target, _ in pairs}
    selectors = {selector for _, selector in pairs}
    target_ok = to in targets
    selector_ok = data[:10] in selectors
    pair_ok = (to, data[:10]) in pairs
    return {"checked": True, "target_ok": target_ok, "selector_ok": selector_ok, "pair_ok": pair_ok, "target": tx.get("to"), "selector": data[:10], "expected_targets": sorted(targets), "expected_selectors": sorted(selectors), "mismatch": not pair_ok}


def _verify_postcondition(action: dict | None, mission: Mission) -> dict:
    if not action:
        return {"verified": True, "reason": "no action key supplied"}
    position = mission.snapshot.get("position", {})
    plan = action.get("plan") or {}
    flow = str(plan.get("flow", action.get("action", "")))
    amount = int(plan.get("amount_atomic", 0) or 0)
    before = (action.get("evidence") or {}).get("pre_position") or {}
    shares = int(position.get("borrow_shares", 0) or 0)
    collateral = int(position.get("collateral_position_atomic", 0) or 0)
    if flow == "full-repay":
        return {"verified": shares == 0, "borrow_shares": shares, "expected": 0}
    if flow == "repay":
        previous = int(before.get("borrow_shares", 0) or 0)
        return {"verified": shares < previous if previous else shares >= 0, "borrow_shares": shares, "previous_borrow_shares": previous}
    if flow == "borrow":
        return {"verified": shares > 0, "borrow_shares": shares, "minimum": 1}
    if flow in {"supply-collateral", "supplyCollateral"}:
        return {"verified": collateral >= amount, "collateral_position_atomic": collateral, "minimum": amount}
    if flow in {"withdraw", "withdraw-collateral"}:
        previous = int(before.get("collateral_position_atomic", 0) or 0)
        return {"verified": collateral <= max(0, previous - amount) if previous else collateral >= 0, "collateral_position_atomic": collateral, "previous_collateral_atomic": previous, "amount_atomic": amount}
    return {"verified": True, "reason": "no stricter postcondition registered"}
