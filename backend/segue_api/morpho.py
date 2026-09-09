from __future__ import annotations

import json
import os
from urllib.request import Request, urlopen
from urllib.request import Request, urlopen

API = "https://api.morpho.org"
MORPHO_BLUE_BASE = "0xBBBBBbbBBb9cC5e90e3b3Af64bdAF62C37EEFFCb"
ADAPTIVE_CURVE_IRM_BASE = "0x46415998764C29aB2a25CbeA6254146D50D22687"

def rpc_call(rpc: str, method: str, params: list) -> object:
    body=json.dumps({"jsonrpc":"2.0","id":1,"method":method,"params":params}).encode()
    with urlopen(Request(rpc, data=body, headers={"content-type":"application/json"}), timeout=20) as response:
        data=json.loads(response.read().decode())
    if "error" in data: raise ValueError(data["error"])
    return data["result"]

def verified_oracle_price(rpc: str, oracle: str) -> int:
    if not oracle.startswith("0x") or len(oracle) != 42: raise ValueError("invalid oracle address")
    code=rpc_call(rpc,"eth_getCode",[oracle,"latest"])
    if not isinstance(code,str) or code in ("0x","0x0"): raise ValueError("oracle has no Base bytecode")
    raw=rpc_call(rpc,"eth_call",[{"to":oracle,"data":"0xa035b1fe"},"latest"])
    if not isinstance(raw,str) or len(raw) != 66: raise ValueError("oracle price response malformed")
    price=int(raw,16)
    if price <= 0: raise ValueError("oracle price is nonpositive")
    return price

def market_state(api: str, market_id: str) -> dict:
    with urlopen(Request(f"{api}/v0/blue/markets/8453:{market_id}/state", headers={"accept":"application/json"}), timeout=20) as response:
        payload=json.loads(response.read().decode()).get("data", {})
    supply=int(payload.get("total_supply_assets", 0)); borrow=int(payload.get("total_borrow_assets", 0))
    return {"total_supplied_assets": supply, "total_borrowed_assets": borrow, "available_liquidity": max(0, supply-borrow)}


def discover_nvda_markets(api: str = API, collateral: str = "0xb20000000000000000000078ee7ce2fE4908108C") -> list[dict]:
    query = f"chain_id=8453&collateral_token={collateral}&limit=100"
    with urlopen(Request(f"{api}/v1/blue/markets?{query}", headers={"accept": "application/json"}), timeout=20) as response:
        payload = json.loads(response.read().decode())
    return [item for item in payload.get("data", []) if item.get("collateral_token", "").lower() == collateral.lower()]
