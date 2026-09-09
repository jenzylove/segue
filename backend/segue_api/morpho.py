from __future__ import annotations

import json
from urllib.request import Request, urlopen

API = "https://api.morpho.org"


def discover_nvda_markets(api: str = API, collateral: str = "0xb20000000000000000000078ee7ce2fE4908108C") -> list[dict]:
    query = f"chain_id=8453&collateral_token={collateral}&limit=100"
    with urlopen(Request(f"{api}/v1/blue/markets?{query}", headers={"accept": "application/json"}), timeout=20) as response:
        payload = json.loads(response.read().decode())
    return [item for item in payload.get("data", []) if item.get("collateral_token", "").lower() == collateral.lower()]
