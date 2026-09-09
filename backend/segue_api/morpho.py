from __future__ import annotations

import json
import os
from decimal import Decimal
from urllib.request import Request, urlopen
from urllib.request import Request, urlopen

API = "https://api.morpho.org"
MORPHO_BLUE_BASE = "0xBBBBBbbBBb9cC5e90e3b3Af64bdAF62C37EEFFCb"
ADAPTIVE_CURVE_IRM_BASE = "0x46415998764C29aB2a25CbeA6254146D50D22687"
LOCKED_MARKET_ID = "0x91360eea2686ef7ce4966b4e82cf6ff712af02baf0f7211459780d9f5af1612a"

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

def borrower_position(api: str, market_id: str, wallet: str) -> dict:
    with urlopen(Request(f"{api}/v0/blue/markets/8453:{market_id}/users/{wallet}/position",headers={"accept":"application/json"}),timeout=20) as response:
        return json.loads(response.read().decode()).get("data", {})

def erc20_balance(rpc_url: str, token: str, wallet: str) -> int:
    data="0x70a08231"+wallet[2:].lower().rjust(64,"0")
    return int(rpc_call(rpc_url,"eth_call",[{"to":token,"data":data},"latest"]),16)

def discover_qualified_market(rpc_url: str, api: str = API, collateral: str = "0xb20000000000000000000078ee7ce2fE4908108C") -> dict:
    candidates = discover_nvda_markets(api, collateral)
    qualified=[]
    for market in candidates:
        if market.get("market_id", "").lower() != LOCKED_MARKET_ID.lower(): continue
        if market.get("loan_token", "").lower() != "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913".lower(): continue
        state=market_state(api, market["market_id"])
        if state["available_liquidity"] <= 0: continue
        try:
            oracle_state=json.loads(urlopen(Request(f"{api}/v0/oracles/8453:{market['oracle_address']}/state",headers={"accept":"application/json"}),timeout=20).read().decode()).get("data",{})
            market["api_oracle_price"]=oracle_state.get("price")
            irm_code=rpc_call(rpc_url,"eth_getCode",[market["irm_address"],"latest"])
            direct=verified_oracle_price(rpc_url, market["oracle_address"])
            api_oracle=market.get("api_oracle_price")
            if api_oracle and abs(Decimal(str(direct))-Decimal(str(api_oracle))) / Decimal(str(direct)) > Decimal("0.01"): continue
        except Exception: continue
        if not irm_code or irm_code in ("0x","0x0") or market["irm_address"].lower() != ADAPTIVE_CURVE_IRM_BASE.lower(): continue
        market.update(state); qualified.append(market)
    if not qualified: raise ValueError("no qualified Morpho NVDAc market")
    selected=sorted(qualified, key=lambda m: m["available_liquidity"], reverse=True)[0]
    selected["provenance"]={"market_source": f"{api}/v1/blue/markets", "deployment_source": "https://docs.morpho.org/developers/contracts/addresses/", "locked_market_id": LOCKED_MARKET_ID}
    return selected


def discover_nvda_markets(api: str = API, collateral: str = "0xb20000000000000000000078ee7ce2fE4908108C") -> list[dict]:
    query = f"chain_id=8453&collateral_token={collateral}&limit=100"
    with urlopen(Request(f"{api}/v1/blue/markets?{query}", headers={"accept": "application/json"}), timeout=20) as response:
        payload = json.loads(response.read().decode())
    return [item for item in payload.get("data", []) if item.get("collateral_token", "").lower() == collateral.lower()]
