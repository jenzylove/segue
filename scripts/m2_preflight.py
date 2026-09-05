#!/usr/bin/env python3
"""M2 readiness checks for Segue.

No third-party Python packages are required. The script loads .env when present,
checks the Base RPC, public contract/feed addresses, deployer gas balance, and 0x
API access. It never prints secrets or the full private RPC URL.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

BASE_CHAIN_ID = 8453
DECIMALS_SELECTOR = "0x313ce567"
LATEST_ROUND_DATA_SELECTOR = "0xfeaf968c"

REQUIRED = (
    "BASE_RPC_URL",
    "EXECUTOR_ADDRESS",
    "ZEROX_API_KEY",
    "USDC_ADDRESS",
    "USDC_FEED_ADDRESS",
    "B20_TOKEN_ADDRESS",
    "B20_FEED_ADDRESS",
)


def load_dotenv(path: str = ".env") -> None:
    p = Path(path)
    if not p.exists():
        return
    for raw in p.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def rpc(method: str, params: list) -> str:
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    req = urllib.request.Request(
        os.environ["BASE_RPC_URL"], body, {"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=20) as response:
        payload = json.load(response)
    if "error" in payload:
        raise RuntimeError(f"RPC {method} failed: {payload['error']}")
    return payload["result"]


def eth_call(to: str, data: str) -> str:
    return rpc("eth_call", [{"to": to, "data": data}, "latest"])


def uint_word(hex_data: str, index: int = 0) -> int:
    body = hex_data[2:]
    start = index * 64
    return int(body[start : start + 64], 16)


def int_word(hex_data: str, index: int) -> int:
    value = uint_word(hex_data, index)
    return value - (1 << 256) if value >= (1 << 255) else value


def check_code(label: str, address: str) -> None:
    code = rpc("eth_getCode", [address, "latest"])
    # B20 native assets may not look like ordinary deployed EVM bytecode. A successful
    # ERC-20 decimals() call is the stronger compatibility test below.
    if code == "0x":
        print(f"  {label}: no EVM bytecode (allowed for native B20; probing interface)")
    else:
        print(f"  {label}: code present")


def check_token(label: str, address: str) -> int:
    result = eth_call(address, DECIMALS_SELECTOR)
    decimals = uint_word(result)
    if decimals > 18:
        raise RuntimeError(f"{label} reports unsupported decimals={decimals}")
    print(f"  {label}: ERC-20 decimals={decimals}")
    return decimals


def check_feed(label: str, address: str) -> tuple[int, int]:
    decimals = uint_word(eth_call(address, DECIMALS_SELECTOR))
    data = eth_call(address, LATEST_ROUND_DATA_SELECTOR)
    answer = int_word(data, 1)
    updated_at = uint_word(data, 3)
    if answer <= 0 or updated_at == 0:
        raise RuntimeError(f"{label} returned invalid latestRoundData")
    print(f"  {label}: feed decimals={decimals}, answer={answer}, updatedAt={updated_at}")
    return answer, updated_at


def check_zerox_route() -> None:
    params = urllib.parse.urlencode(
        {
            "chainId": str(BASE_CHAIN_ID),
            "sellToken": os.environ["USDC_ADDRESS"],
            "buyToken": os.environ["B20_TOKEN_ADDRESS"],
            "sellAmount": "1000000",  # 1 USDC indicative route only
        }
    )
    req = urllib.request.Request(
        f"https://api.0x.org/swap/allowance-holder/price?{params}",
        headers={
            "0x-api-key": os.environ["ZEROX_API_KEY"],
            "0x-version": "v2",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")[:500]
        raise RuntimeError(f"0x price request failed HTTP {exc.code}: {body}") from exc

    buy_amount = payload.get("buyAmount")
    liquidity = payload.get("liquidityAvailable")
    if not buy_amount or int(buy_amount) <= 0:
        raise RuntimeError(f"0x returned no usable route: {json.dumps(payload)[:500]}")
    print(f"  0x: indicative USDC→B20 route available, buyAmount={buy_amount}, liquidity={liquidity}")


def main() -> int:
    load_dotenv()
    missing = [name for name in REQUIRED if not os.environ.get(name)]
    if missing:
        print("M2 PREFLIGHT: BLOCKED")
        print("Missing .env values: " + ", ".join(missing))
        return 2

    chain_id = int(rpc("eth_chainId", []), 16)
    if chain_id != BASE_CHAIN_ID:
        raise RuntimeError(f"wrong chain: expected {BASE_CHAIN_ID}, got {chain_id}")
    print("M2 PREFLIGHT")
    print(f"  RPC: Base mainnet chainId={chain_id}")

    executor = os.environ["EXECUTOR_ADDRESS"]
    eth_balance = int(rpc("eth_getBalance", [executor, "latest"]), 16)
    print(f"  executor: {executor}")
    print(f"  executor ETH: {eth_balance / 10**18:.8f}")

    for label, key in (
        ("USDC", "USDC_ADDRESS"),
        ("USDC/USD feed", "USDC_FEED_ADDRESS"),
        ("B20 token", "B20_TOKEN_ADDRESS"),
        ("B20 total-return feed", "B20_FEED_ADDRESS"),
    ):
        check_code(label, os.environ[key])

    check_token("USDC", os.environ["USDC_ADDRESS"])
    check_token("B20 token", os.environ["B20_TOKEN_ADDRESS"])
    check_feed("USDC/USD", os.environ["USDC_FEED_ADDRESS"])
    check_feed("B20 total-return", os.environ["B20_FEED_ADDRESS"])
    check_zerox_route()

    print("M2 PREFLIGHT: PASS")
    print("This proves RPC/feed/token/API readiness only. It does NOT prove B1-B4 or execute a transaction.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001 - CLI must fail closed with one concise reason.
        print(f"M2 PREFLIGHT: FAIL — {exc}", file=sys.stderr)
        raise SystemExit(1)
