from __future__ import annotations

from .mission import Mission, MissionState, MissionStore
from .morpho import market_state, borrower_position, rpc_call


def reconcile_mission(store: MissionStore, mission_id: str, available_liquidity: int, onchain_borrowed: int = 0) -> Mission:
    mission = store.get(mission_id)
    if mission is None:
        raise ValueError("mission not found")
    if mission.state in (MissionState.CLOSED, MissionState.REPAID):
        return mission
    if onchain_borrowed > 0:
        mission.state = MissionState.BORROWED
    elif available_liquidity <= 0:
        mission.state = MissionState.WAITING_FOR_LIQUIDITY
    elif mission.state in (MissionState.PROPOSED, MissionState.APPROVED, MissionState.WAITING_FOR_LIQUIDITY):
        mission.state = MissionState.BORROW_READY
    return store.save(mission)

def reconcile_live(store: MissionStore, mission_id: str, api: str = "https://api.morpho.org") -> Mission:
    mission=store.get(mission_id)
    if mission is None: raise ValueError("mission not found")
    state=market_state(api, mission.market_id); position=borrower_position(api, mission.market_id, mission.owner)
    borrowed=int(position.get("borrow_shares",0))
    mission.snapshot={**mission.snapshot,"market_state":state,"position":position}
    mission.state=MissionState.BORROWED if borrowed>0 else (MissionState.WAITING_FOR_LIQUIDITY if state["available_liquidity"]<=0 else MissionState.BORROW_READY)
    store.event(mission_id,"LIVE_RECONCILIATION",{"market_state":state,"position":position})
    return store.save(mission)

def reconcile_receipt(store: MissionStore, mission_id: str, tx_hash: str, rpc_url: str) -> Mission:
    mission=store.get(mission_id)
    if mission is None: raise ValueError("mission not found")
    receipt=rpc_call(rpc_url,"eth_getTransactionReceipt",[tx_hash])
    if receipt is None:
        store.event(mission_id,"TX_PENDING",{"tx_hash":tx_hash}); return mission
    status=int(receipt.get("status","0x0"),16)
    store.event(mission_id,"TX_CONFIRMED" if status==1 else "TX_FAILED",{"tx_hash":tx_hash,"receipt":receipt})
    if status != 1: return store.save(mission)
    position=borrower_position("https://api.morpho.org",mission.market_id,mission.owner)
    if int(position.get("borrow_shares",0))>0: mission.state=MissionState.BORROWED
    else: mission.state=MissionState.REPAID
    mission.tx_hash=tx_hash; mission.snapshot={**mission.snapshot,"position":position}; return store.save(mission)
