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
    query = urlencode({"chain_id": "8453", "listed": "true", "limit": "100"})
    request = Request(f"{base_url.rstrip('/')}/v1/blue/markets?{query}", headers={"accept": "application/json"})
    with urlopen(request, timeout=20) as response:
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
        if _address(market.get("loanAsset", market.get("loanToken", market.get("loan_token")))).lower() != loan.lower():
            continue
        if _address(market.get("collateralAsset", market.get("collateralToken", market.get("collateral_token")))).lower() != collateral.lower():
            continue
        state = market.get("state") or {}
        borrow_assets = state.get("borrowAssets", market.get("borrowAssets", market.get("borrow_assets", 0)))
        if int(borrow_assets or 0) > 0:
            matches.append(market)
    if len(matches) != 1:
        raise ValueError(f"expected exactly one borrowable NVDAc/USDC market, found {len(matches)}")
    market = matches[0]
    for old, new in (("market_id", "marketId"), ("lltv_wad", "lltv"), ("oracle_address", "oracle"), ("irm_address", "irmAddress")):
        if old in market and new not in market:
            market[new] = market[old]
    required = ("marketId", "lltv", "oracle", "irmAddress")
    if any(not market.get(key) for key in required) or not _address(market.get("oracle")):
        raise ValueError("market is missing verified Morpho parameters")
    market["_borrow_assets"] = int((market.get("state") or {}).get("borrowAssets", market.get("borrowAssets", 0)))
    market["_borrow_rate"] = (market.get("state") or {}).get("borrowRate", market.get("borrowRate"))
    if market["_borrow_rate"] is None:
        raise ValueError("market is missing current borrow rate")
    return market


def main() -> int:
    load_env(ROOT / ".env")
    loan = os.environ.get("USDC_ADDRESS", USDC_DEFAULT)
    collateral = os.environ.get("B20_TOKEN_ADDRESS", NVDA_DEFAULT)
    try:
        market = select_market(fetch_markets(os.environ.get("MORPHO_API_URL", API_DEFAULT), loan, collateral), loan, collateral)
    except Exception as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 2
    print("MORPHO_PREFLIGHT_OK")
    print("chain_id=8453")
    print(f"market_id={market['marketId']}")
    print(f"loan_token={loan}")
    print(f"collateral_token={collateral}")
    print(f"oracle={_address(market['oracle'])}")
    print(f"irm={market['irmAddress']}")
    print(f"lltv={market['lltv']}")
    print(f"available_borrow_liquidity_atomic={market['_borrow_assets']}")
    print(f"current_borrow_rate={market['_borrow_rate']}")
    print("health_formula=max_borrow = collateral * oracle_price / 1e36 * lltv; healthy iff max_borrow >= borrowed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
