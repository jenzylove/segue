from __future__ import annotations

from dataclasses import dataclass

ZERO = "0x0000000000000000000000000000000000000000"

@dataclass(frozen=True)
class UnsignedPlan:
    chain_id: int
    target: str
    calldata: str
    value: str
    market_id: str
    preconditions: tuple[str, ...]
    expected_postcondition: str

def plan_call(target: str, market_id: str, calldata: str, post: str, *pre: str) -> dict:
    if not target.startswith("0x") or len(target) != 42 or not calldata.startswith("0x"):
        raise ValueError("invalid unsigned transaction target or calldata")
    return {"chain_id": 8453, "target": target, "calldata": calldata, "value": "0", "market_id": market_id, "preconditions": list(pre), "expected_postcondition": post}

def lender_supply_plan(morpho: str, usdc: str, market_id: str, amount: int, calldata: str = "0x") -> dict:
    if amount <= 0: raise ValueError("supply amount must be positive")
    return plan_call(morpho, market_id, calldata, "market total supplied assets increases by amount", f"USDC allowance to Morpho >= {amount}", f"USDC balance >= {amount}")

def borrower_action_plan(morpho: str, market_id: str, action: str, calldata: str = "0x") -> dict:
    posts = {"supply": "collateral supplied to selected market", "borrow": "borrowed assets credited to borrower", "repay": "borrow balance decreases", "withdraw": "collateral returned to borrower"}
    if action not in posts: raise ValueError("unsupported Morpho action")
    return plan_call(morpho, market_id, calldata, posts[action], "market parameters match selected market", "wallet signature required")
