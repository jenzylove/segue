from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

NVDA_DEFAULT = "0xb20000000000000000000078ee7ce2fE4908108C"
USDC_DEFAULT = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
API_DEFAULT = "https://api.morpho.org"
LOCKED_MARKET_ID = "0x91360eea2686ef7ce4966b4e82cf6ff712af02baf0f7211459780d9f5af1612a"


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def fetch_markets(base_url: str, loan: str, collateral: str) -> dict:
    # The public REST endpoint's token filters vary by API version; chain/listing
    # filters are stable, so verify the exact token pair locally from the response.
    query = urlencode({"chain_id": "8453", "collateral_token": collateral, "limit": "100"})
    all_items = []
    cursor = None
    for _ in range(20):
        suffix = f"&cursor={cursor}" if cursor else ""
        request = Request(f"{base_url.rstrip('/')}/v1/blue/markets?{query}{suffix}", headers={"accept": "application/json", "user-agent": "segue/1.0"})
        with urlopen(request, timeout=20) as response:
            page = json.loads(response.read().decode("utf-8"))
        all_items.extend(page.get("data", []))
        cursor = page.get("cursor")
        if not cursor:
            break
    return {"data": all_items}

def fetch_json(url: str) -> dict:
    with urlopen(Request(url, headers={"accept": "application/json", "user-agent": "segue/1.0"}), timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def _address(value: object) -> str:
    return value.get("address", "") if isinstance(value, dict) else str(value or "")


def select_market(payload: dict, loan: str, collateral: str) -> dict:
    data = payload.get("data")
    items = payload.get("items", data.get("items", []) if isinstance(data, dict) else [])
    if isinstance(data, list):
        items = data
    if not isinstance(items, list):
        raise ValueError("Morpho API response has no market items")
    matches = []
    for market in items:
        if not isinstance(market, dict):
            continue
        market_collateral = market.get("collateral_token", _address(market.get("collateralAsset", market.get("collateralToken"))))
        market_loan = market.get("loan_token", _address(market.get("loanAsset", market.get("loanToken"))))
        if str(market_collateral).lower() != collateral.lower():
            continue
        if str(market_loan).lower() == loan.lower():
            matches.append(market)
    if not matches:
        raise ValueError(
            f"Morpho Blue has no matching NVDAc market (found {len(matches)}); verify the configured token address"
        )
    # The product has a locked, independently qualified market. Keep the
    # fallback for unit-test fixtures and older operator calls, but never pick
    # an arbitrary first result when the locked id is present.
    market = next((m for m in matches if str(m.get("marketId", m.get("market_id", ""))).lower() == LOCKED_MARKET_ID.lower()), None)
    market = market or sorted(matches, key=lambda m: 0 if str(m.get("loan_token", _address(m.get("loanAsset")))).lower() == USDC_DEFAULT.lower() else 1)[0]
    for old, new in (("market_id", "marketId"), ("lltv_wad", "lltv"), ("oracle_address", "oracle"), ("irm_address", "irmAddress")):
        if old in market and new not in market:
            market[new] = market[old]
    required = ("marketId", "lltv", "oracle", "irmAddress")
    if any(not market.get(key) for key in required) or not _address(market.get("oracle")):
        raise ValueError("market is missing verified Morpho parameters")
    market["_borrow_assets"] = int((market.get("state") or {}).get("borrowAssets", market.get("borrowAssets", 0)))
    market["_borrow_rate"] = (market.get("state") or {}).get("borrowRate", market.get("borrowRate"))
    market["_borrow_rate"] = market.get("_borrow_rate")
    return market


def main() -> int:
    load_env(ROOT / ".env")
    loan = os.environ.get("USDC_ADDRESS", USDC_DEFAULT)
    collateral = os.environ.get("B20_TOKEN_ADDRESS", NVDA_DEFAULT)
    try:
        api = os.environ.get("MORPHO_API_URL", API_DEFAULT)
        rpc = os.environ.get("BASE_RPC_URL", "")
        if not rpc:
            raise ValueError("BASE_RPC_URL is required for live Base verification")
        from backend.segue_api.morpho import discover_qualified_market
        market = discover_qualified_market(rpc, api, collateral)
        if int(market.get("available_liquidity", 0)) <= 0:
            raise ValueError("selected Morpho Blue market has zero available borrow liquidity")
    except Exception as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 2
    print("MORPHO_PREFLIGHT_OK")
    print("chain_id=8453")
    print(f"market_id={market['market_id']}")
    print(f"loan_token={market['loan_token']}")
    print(f"collateral_token={collateral}")
    print(f"oracle={market['oracle_address']}")
    print(f"irm={market['irm_address']}")
    print(f"lltv={market['lltv_wad']}")
    print(f"available_borrow_liquidity_atomic={market['available_liquidity']}")
    print(f"oracle_price_1e36={market['direct_oracle_price']}")
    print(f"api_oracle_price={market['api_oracle_price']}")
    print("health_formula=max_borrow = collateral * oracle_price / 1e36 * lltv; healthy iff max_borrow >= borrowed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
