from __future__ import annotations

import json
from decimal import Decimal
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .evm import address_word, bytes32_word, keccak256, selector

API = "https://api.morpho.org"
MORPHO_BLUE_BASE = "0xBBBBBbbBBb9cC5e90e3b3Af64bdAF62C37EEFFCb"
ADAPTIVE_CURVE_IRM_BASE = "0x46415998764C29aB2a25CbeA6254146D50D22687"
LOCKED_MARKET_ID = "0x91360eea2686ef7ce4966b4e82cf6ff712af02baf0f7211459780d9f5af1612a"
CANONICAL_COLLATERAL = "0xb20000000000000000000078ee7ce2fE4908108C"
USDC_BASE = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"


def rpc_call(rpc: str, method: str, params: list) -> object:
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    with urlopen(Request(rpc, data=body, headers={"content-type": "application/json", "user-agent": "segue/1.0"}), timeout=20) as response:
        data = json.loads(response.read().decode())
    if "error" in data:
        raise ValueError(data["error"])
    return data["result"]


def fetch_json(url: str) -> dict:
    with urlopen(Request(url, headers={"accept": "application/json", "user-agent": "segue/1.0"}), timeout=20) as response:
        return json.loads(response.read().decode())


def _raw_call(rpc: str, target: str, signature: str, args: list[str]) -> str:
    raw = rpc_call(rpc, "eth_call", [{"to": target, "data": selector(signature) + "".join(args)}, "latest"])
    if not isinstance(raw, str) or not raw.startswith("0x"):
        raise ValueError(f"{signature} returned malformed data")
    return raw[2:]


def _uints(raw: str, count: int) -> list[int]:
    if len(raw) < count * 64:
        raise ValueError("ABI response is too short")
    return [int(raw[i * 64:(i + 1) * 64], 16) for i in range(count)]


def verified_oracle_price(rpc: str, oracle: str) -> int:
    code = rpc_call(rpc, "eth_getCode", [oracle, "latest"])
    if not isinstance(code, str) or code in ("0x", "0x0"):
        raise ValueError("oracle has no Base bytecode")
    raw = rpc_call(rpc, "eth_call", [{"to": oracle, "data": selector("price()")}, "latest"])
    if not isinstance(raw, str) or len(raw) != 66:
        raise ValueError("oracle price response malformed")
    price = int(raw, 16)
    if price <= 0:
        raise ValueError("oracle price is nonpositive")
    return price


def market_state(api: str, market_id: str) -> dict:
    payload = fetch_json(f"{api.rstrip('/')}/v0/blue/markets/8453:{market_id}/state").get("data", {})
    supply = int(payload.get("total_supply_assets", payload.get("supplyAssets", 0)) or 0)
    borrow = int(payload.get("total_borrow_assets", payload.get("borrowAssets", 0)) or 0)
    return {
        "total_supplied_assets": supply,
        "total_borrowed_assets": borrow,
        "total_supply_shares": int(payload.get("total_supply_shares", 0) or 0),
        "total_borrow_shares": int(payload.get("total_borrow_shares", 0) or 0),
        "available_liquidity": max(0, supply - borrow),
        "source": f"{api.rstrip('/')}/v0/blue/markets/8453:{market_id}/state",
    }


def borrower_position(api: str, market_id: str, wallet: str) -> dict:
    payload = fetch_json(f"{api.rstrip('/')}/v0/blue/markets/8453:{market_id}/users/{wallet}/position")
    return payload.get("data", payload)


def erc20_balance(rpc_url: str, token: str, wallet: str) -> int:
    raw = rpc_call(rpc_url, "eth_call", [{"to": token, "data": selector("balanceOf(address)") + address_word(wallet)}, "latest"])
    return int(raw, 16)


def onchain_market_params(rpc: str, market_id: str, morpho: str = MORPHO_BLUE_BASE) -> dict:
    values = _uints(_raw_call(rpc, morpho, "idToMarketParams(bytes32)", [bytes32_word(market_id)]), 5)
    params = {
        "loan_token": "0x" + f"{values[0]:040x}",
        "collateral_token": "0x" + f"{values[1]:040x}",
        "oracle_address": "0x" + f"{values[2]:040x}",
        "irm_address": "0x" + f"{values[3]:040x}",
        "lltv_wad": str(values[4]),
        "market_id": market_id,
        "source": "Base eth_call idToMarketParams(bytes32)",
    }
    if params["loan_token"].lower() == "0x" + "0" * 40:
        raise ValueError("locked Morpho market does not exist on Base")
    return params


def onchain_market(rpc: str, market_id: str, morpho: str = MORPHO_BLUE_BASE) -> dict:
    values = _uints(_raw_call(rpc, morpho, "market(bytes32)", [bytes32_word(market_id)]), 6)
    return {
        "total_supply_assets": values[0], "total_supply_shares": values[1],
        "total_borrow_assets": values[2], "total_borrow_shares": values[3],
        "last_update": values[4], "fee": values[5],
        "available_liquidity": max(0, values[0] - values[2]),
        "source": "Base eth_call market(bytes32)",
    }


def onchain_position(rpc: str, market_id: str, wallet: str, morpho: str = MORPHO_BLUE_BASE) -> dict:
    values = _uints(_raw_call(rpc, morpho, "position(bytes32,address)", [bytes32_word(market_id), address_word(wallet)]), 3)
    return {"supply_shares": values[0], "borrow_shares": values[1], "collateral": values[2], "source": "Base eth_call position(bytes32,address)"}


def recover_borrow_events(rpc: str, wallet: str, market_id: str, from_block: int, to_block: int) -> list[dict]:
    """Find Morpho Borrow events for a borrower without trusting an indexer."""
    topic = "0x" + keccak256(b"Borrow(bytes32,address,address,address,uint256,uint256)").hex()
    borrower_topic = "0x" + wallet[2:].lower().rjust(64, "0")
    # EventsLib indexes id, caller, and onBehalf.  Query the market first and
    # match the borrower against either indexed actor so delegated borrows are
    # not silently missed.
    logs = rpc_call(rpc, "eth_getLogs", [{"address": MORPHO_BLUE_BASE, "fromBlock": hex(from_block), "toBlock": hex(to_block), "topics": [topic, "0x" + bytes32_word(market_id)] }])
    if not isinstance(logs, list):
        return []
    return [log for log in logs if borrower_topic in [str(item).lower() for item in (log.get("topics", [])[2:4])]]


def _shares_to_assets_up(shares: int, total_assets: int, total_shares: int) -> int:
    if shares <= 0 or total_shares <= 0:
        return 0
    return (shares * total_assets + total_shares - 1) // total_shares


def live_position_snapshot(rpc: str, api: str, market: dict, wallet: str) -> dict:
    params = onchain_market_params(rpc, market["market_id"])
    for key in ("loan_token", "collateral_token", "oracle_address", "irm_address", "lltv_wad"):
        if str(params[key]).lower() != str(market[key]).lower():
            raise ValueError(f"onchain {key} differs from discovered market")
    on_market = onchain_market(rpc, market["market_id"])
    on_position = onchain_position(rpc, market["market_id"], wallet)
    api_position = borrower_position(api, market["market_id"], wallet)
    debt_assets = int(api_position.get("borrow_assets", api_position.get("borrowAssets", 0)) or 0)
    if debt_assets <= 0:
        debt_assets = _shares_to_assets_up(on_position["borrow_shares"], on_market["total_borrow_assets"], on_market["total_borrow_shares"])
    return {
        "wallet": wallet,
        "collateral_balance_atomic": erc20_balance(rpc, market["collateral_token"], wallet),
        "collateral_position_atomic": on_position["collateral"],
        "supply_shares": on_position["supply_shares"],
        "borrow_shares": on_position["borrow_shares"],
        "debt_assets_atomic": debt_assets,
        "market": on_market,
        "api_position": api_position,
        "source": "Base RPC + Morpho API cross-check",
    }


def discover_nvda_markets(api: str = API, collateral: str = CANONICAL_COLLATERAL) -> list[dict]:
    query = urlencode({"chain_id": "8453", "collateral_token": collateral, "limit": "100"})
    payload = fetch_json(f"{api.rstrip('/')}/v1/blue/markets?{query}")
    data = payload.get("data", payload.get("items", []))
    if isinstance(data, dict):
        data = data.get("items", [])
    return [item for item in data if isinstance(item, dict) and str(item.get("collateral_token", item.get("collateralToken", ""))).lower() == collateral.lower()]


def discover_qualified_market(rpc_url: str, api: str = API, collateral: str = CANONICAL_COLLATERAL) -> dict:
    candidates = discover_nvda_markets(api, collateral)
    locked = next((m for m in candidates if str(m.get("market_id", m.get("id", ""))).lower() == LOCKED_MARKET_ID.lower()), None)
    if locked is None:
        raise ValueError("locked Morpho NVDAc market is not indexed")
    market_id = locked.get("market_id", locked.get("id"))
    loan = locked.get("loan_token", locked.get("loanToken", ""))
    if isinstance(loan, dict): loan = loan.get("address", "")
    col = locked.get("collateral_token", locked.get("collateralToken", collateral))
    if isinstance(col, dict): col = col.get("address", collateral)
    oracle = locked.get("oracle_address", locked.get("oracle", ""))
    if isinstance(oracle, dict): oracle = oracle.get("address", "")
    irm = locked.get("irm_address", locked.get("irmAddress", ""))
    lltv = locked.get("lltv_wad", locked.get("lltv", 0))
    if isinstance(lltv, float): lltv = int(Decimal(str(lltv)) * 10**18)
    if isinstance(lltv, str) and "." in lltv: lltv = int(Decimal(lltv) * 10**18)
    market = {"market_id": market_id, "loan_token": loan, "collateral_token": col, "oracle_address": oracle, "irm_address": irm, "lltv_wad": str(lltv), "listed": locked.get("listed", "UNKNOWN")}
    if market["loan_token"].lower() != USDC_BASE.lower():
        raise ValueError("locked Morpho market loan token is not Base USDC")
    params = onchain_market_params(rpc_url, market_id)
    for key in ("loan_token", "collateral_token", "oracle_address", "irm_address", "lltv_wad"):
        if str(params[key]).lower() != str(market[key]).lower():
            raise ValueError(f"discovered {key} disagrees with Base MarketParams")
    state = market_state(api, market_id)
    direct = verified_oracle_price(rpc_url, params["oracle_address"])
    oracle_state = fetch_json(f"{api.rstrip('/')}/v0/oracles/8453:{params['oracle_address']}/state").get("data", {})
    api_price = oracle_state.get("price")
    if api_price and abs(Decimal(str(direct)) - Decimal(str(api_price))) / Decimal(str(direct)) > Decimal("0.01"):
        raise ValueError("Morpho API oracle price disagrees with Base price()")
    irm_code = rpc_call(rpc_url, "eth_getCode", [params["irm_address"], "latest"])
    enabled = _uints(_raw_call(rpc_url, MORPHO_BLUE_BASE, "isIrmEnabled(address)", [address_word(params["irm_address"])]), 1)[0]
    if params["irm_address"].lower() != ADAPTIVE_CURVE_IRM_BASE.lower() or not irm_code or irm_code in ("0x", "0x0") or not enabled:
        raise ValueError("locked Morpho IRM is not enabled/supported on Base")
    market.update(state)
    market.update({"direct_oracle_price": direct, "api_oracle_price": api_price, "oracle_state": oracle_state, "provenance": {"market_source": f"{api}/v1/blue/markets", "onchain_params": "Base eth_call idToMarketParams", "deployment_source": "https://docs.morpho.org/developers/contracts/addresses/"}})
    return market
