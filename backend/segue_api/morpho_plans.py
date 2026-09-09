from __future__ import annotations

from dataclasses import dataclass
import subprocess

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

def _cast(signature: str, args: list[str]) -> str:
    result = subprocess.run(["cast", "calldata", signature, *args], text=True, capture_output=True)
    if result.returncode: raise ValueError(result.stderr.strip() or "official ABI encoding failed")
    return result.stdout.strip()

def _market_tuple(market: dict) -> str:
    return f"({market['loan_token']},{market['collateral_token']},{market['oracle_address']},{market['irm_address']},{market['lltv_wad']})"

def lender_supply_plan(morpho: str, usdc: str, market_id: str, amount: int, *, wallet: str, market: dict) -> dict:
    if amount <= 0: raise ValueError("supply amount must be positive")
    approve = plan_call(usdc, market_id, _cast("approve(address,uint256)",[morpho,str(amount)]), "USDC allowance is set", "lender wallet holds USDC")
    supply = plan_call(morpho, market_id, _cast("supply((address,address,address,address,uint256),uint256,uint256,address,bytes)",[_market_tuple(market),str(amount),"0",wallet,"0x"]), "market supplied assets increase", "approval transaction confirmed")
    return {"actions":[approve,supply],"market":market}

def borrower_action_plan(morpho: str, market_id: str, action: str, *, wallet: str, amount: int, market: dict) -> dict:
    posts = {"supply": "collateral supplied to selected market", "borrow": "borrowed assets credited to borrower", "repay": "borrow balance decreases", "withdraw": "collateral returned to borrower"}
    if action not in posts: raise ValueError("unsupported Morpho action")
    if amount <= 0: raise ValueError("action amount must be positive")
    m = _market_tuple(market)
    if action == "supply":
        return {"actions":[plan_call(market["collateral_token"],market_id,_cast("approve(address,uint256)",[morpho,str(amount)]),"collateral allowance is set"),plan_call(morpho,market_id,_cast("supplyCollateral((address,address,address,address,uint256),uint256,address,bytes)",[m,str(amount),wallet,"0x"]),posts[action])],"market":market}
    sigs={"borrow":"borrow((address,address,address,address,uint256),uint256,uint256,address,address)","repay":"repay((address,address,address,address,uint256),uint256,uint256,address,bytes)","withdraw":"withdrawCollateral((address,address,address,address,uint256),uint256,address,address)"}
    args={"borrow":[m,str(amount),"0",wallet,wallet],"repay":[m,str(amount),"0",wallet,"0x"],"withdraw":[m,str(amount),wallet,wallet]}[action]
    return {"actions":[plan_call(morpho,market_id,_cast(sigs[action],args),posts[action])],"market":market}

def full_repay_plan(morpho: str, market_id: str, *, wallet: str, market: dict, borrow_shares: int, approval_amount: int) -> dict:
    if borrow_shares <= 0: raise ValueError("fresh borrow shares must be positive")
    if approval_amount <= 0: raise ValueError("USDC approval must cover accrued debt")
    m=_market_tuple(market)
    approve=plan_call(market["loan_token"],market_id,_cast("approve(address,uint256)",[morpho,str(approval_amount)]),"USDC allowance covers accrued debt")
    repay=plan_call(morpho,market_id,_cast("repay((address,address,address,address,uint256),uint256,uint256,address,bytes)",[m,"0",str(borrow_shares),wallet,"0x"]),"borrow shares equal zero","fresh position borrow shares verified")
    return {"actions":[approve,repay],"market":market,"borrow_shares":borrow_shares,"approval_amount":approval_amount}
