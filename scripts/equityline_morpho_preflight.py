from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]

NVDA_DEFAULT = "0xb20000000000000000000078ee7ce2fE4908108C"
USDC_DEFAULT = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
API_DEFAULT = "https://api.morpho.org"


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
        request = Request(f"{base_url.rstrip('/')}/v1/blue/markets?{query}{suffix}", headers={"accept": "application/json"})
        with urlopen(request, timeout=20) as response:
            page = json.loads(response.read().decode("utf-8"))
        all_items.extend(page.get("data", []))
        cursor = page.get("cursor")
        if not cursor:
            break
    return {"data": all_items}

def fetch_json(url: str) -> dict:
    with urlopen(Request(url, headers={"accept": "application/json"}), timeout=20) as response:
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
        if str(market.get("collateral_token", "")).lower() != collateral.lower():
            continue
        if str(market.get("loan_token", "")).lower() == loan.lower():
            matches.append(market)
    if not matches:
        raise ValueError(
            f"Morpho Blue has no matching NVDAc market (found {len(matches)}); verify the configured token address"
        )
    # Prefer USDC when several markets share the same collateral.
    market = sorted(matches, key=lambda m: 0 if str(m.get("loan_token", "")).lower() == USDC_DEFAULT.lower() else 1)[0]
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
        market = select_market(fetch_markets(api, loan, collateral), loan, collateral)
        selector = f"8453:{market['marketId']}"
        state = fetch_json(f"{api}/v0/blue/markets/{selector}/state").get("data", {})
        apy = fetch_json(f"{api}/v0/blue/markets/{selector}/apy-averages").get("data", {})
        market["_borrow_assets"] = state.get("total_borrow_assets", state.get("borrowAssets", 0))
        market["_borrow_rate"] = apy.get("borrow_apy_averages", apy.get("borrowApy"))
    except Exception as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 2
    print("MORPHO_PREFLIGHT_OK")
    print("chain_id=8453")
    print(f"market_id={market['marketId']}")
    print(f"loan_token={loan}")
    print(f"collateral_token={collateral}")
    print(f"oracle={market['oracle']}")
    print(f"irm={market['irmAddress']}")
    print(f"lltv={market['lltv']}")
    print("available_borrow_liquidity_atomic=UNVERIFIED")
    print(f"current_borrow_rate={market['_borrow_rate']}")
    print("health_formula=max_borrow = collateral * oracle_price / 1e36 * lltv; healthy iff max_borrow >= borrowed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
