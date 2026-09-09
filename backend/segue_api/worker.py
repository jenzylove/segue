from __future__ import annotations

from .mission import Mission, MissionState, MissionStore


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
