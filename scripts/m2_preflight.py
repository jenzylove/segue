#!/usr/bin/env python3
"""M2 readiness checks for Segue.

No third-party Python packages are required. The script loads .env when present,
checks Base RPC, public contract/feed addresses, deployer gas balance, and a real
1inch Classic Swap route for the configured Coinbase B20 asset. It never prints
secrets or the full private RPC URL.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

BASE_CHAIN_ID = 8453
DECIMALS_SELECTOR = "0x313ce567"
LATEST_ROUND_DATA_SELECTOR = "0xfeaf968c"
USER_AGENT = "Mozilla/5.0 (compatible; Segue-M2-Preflight/1.1)"
USDC_MAX_STALENESS = 2 * 60 * 60
EQUITY_MAX_STALENESS = 6 * 60 * 60
ONEINCH_BASE_URL = f"https://api.1inch.com/swap/v6.1/{BASE_CHAIN_ID}"

REQUIRED = (
    "BASE_RPC_URL",
    "EXECUTOR_ADDRESS",
    "ONEINCH_API_KEY",
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


def safe_host(url: str) -> str:
    """Return only the hostname so provider keys/path tokens never reach logs."""
    return urllib.parse.urlparse(url).hostname or "configured RPC"


def rpc(method: str, params: list) -> str:
    url = os.environ["BASE_RPC_URL"]
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    req = urllib.request.Request(
        url,
        body,
        {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", "replace")[:500]
        raise RuntimeError(
            f"RPC {method} via {safe_host(url)} failed HTTP {exc.code}: {error_body}"
        ) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"RPC {method} via {safe_host(url)} failed: {exc.reason}") from exc

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


def check_feed(label: str, address: str, max_staleness: int) -> tuple[int, int, int]:
    decimals = uint_word(eth_call(address, DECIMALS_SELECTOR))
    data = eth_call(address, LATEST_ROUND_DATA_SELECTOR)
    answer = int_word(data, 1)
    updated_at = uint_word(data, 3)
    if answer <= 0 or updated_at == 0:
        raise RuntimeError(f"{label} returned invalid latestRoundData")

    age = max(0, int(time.time()) - updated_at)
    print(
        f"  {label}: feed decimals={decimals}, answer={answer}, "
        f"updatedAt={updated_at}, age={age / 3600:.2f}h"
    )
    if age > max_staleness:
        raise RuntimeError(
            f"{label} is stale for Segue: age={age / 3600:.2f}h, "
            f"max={max_staleness / 3600:.0f}h"
        )
    return answer, updated_at, age


def oneinch_get(path: str, params: dict[str, str] | None = None) -> dict:
    query = f"?{urllib.parse.urlencode(params)}" if params else ""
    req = urllib.request.Request(
        f"{ONEINCH_BASE_URL}/{path}{query}",
        headers={
            "Authorization": f"Bearer {os.environ['ONEINCH_API_KEY']}",
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")[:700]
        request_id = exc.headers.get("X-Request-Id") if exc.headers else None
        suffix = f" requestId={request_id}" if request_id else ""
        raise RuntimeError(f"1inch {path} failed HTTP {exc.code}: {body}{suffix}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"1inch {path} failed: {exc.reason}") from exc


def check_oneinch_route() -> str:
    spender_payload = oneinch_get("approve/spender")
    spender = str(spender_payload.get("address") or "")
    if not spender.startswith("0x") or len(spender) != 42:
        raise RuntimeError(f"1inch returned invalid spender: {json.dumps(spender_payload)[:400]}")
    check_code("1inch execution target", spender)

    quote = oneinch_get(
        "quote",
        {
            "src": os.environ["USDC_ADDRESS"],
            "dst": os.environ["B20_TOKEN_ADDRESS"],
            "amount": os.environ.get("M2_BUY_USDC_ATOMIC", "1000000"),
            "includeProtocols": "true",
        },
    )
    dst_amount = int(quote.get("dstAmount") or 0)
    if dst_amount <= 0:
        raise RuntimeError(f"1inch returned no usable USDC→B20 route: {json.dumps(quote)[:500]}")

    print(f"  1inch: USDC→B20 route available, dstAmount={dst_amount}")
    print(f"  1inch execution target: {spender}")

    configured = os.environ.get("EXECUTION_TARGET_ADDRESS", "").strip()
    if configured and configured.lower() != spender.lower():
        raise RuntimeError(
            "EXECUTION_TARGET_ADDRESS does not match 1inch approve/spender; "
            f"configured={configured}, live={spender}"
        )

    Path(".local").mkdir(exist_ok=True)
    Path(".local/m2-preflight.json").write_text(
        json.dumps(
            {
                "chainId": BASE_CHAIN_ID,
                "executionTarget": spender,
                "sellToken": os.environ["USDC_ADDRESS"],
                "buyToken": os.environ["B20_TOKEN_ADDRESS"],
                "sellAmount": os.environ.get("M2_BUY_USDC_ATOMIC", "1000000"),
                "quotedDstAmount": str(dst_amount),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return spender


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
    if eth_balance == 0:
        print("  executor gas: BLOCKED — fund with a small amount of Base ETH before deployment/execution")

    for label, key in (
        ("USDC", "USDC_ADDRESS"),
        ("USDC/USD feed", "USDC_FEED_ADDRESS"),
        ("B20 token", "B20_TOKEN_ADDRESS"),
        ("B20 total-return feed", "B20_FEED_ADDRESS"),
    ):
        check_code(label, os.environ[key])

    check_token("USDC", os.environ["USDC_ADDRESS"])
    check_token("B20 token", os.environ["B20_TOKEN_ADDRESS"])

    # Provider route is checked before freshness so a weekend-stale equity feed does
    # not hide whether the replacement execution rail actually supports Coinbase B20.
    execution_target = check_oneinch_route()

    check_feed("USDC/USD", os.environ["USDC_FEED_ADDRESS"], USDC_MAX_STALENESS)
    check_feed("B20 total-return", os.environ["B20_FEED_ADDRESS"], EQUITY_MAX_STALENESS)

    if eth_balance == 0:
        raise RuntimeError("executor has zero Base ETH for deployment/execution gas")

    print("M2 PREFLIGHT: PASS")
    print(f"Set EXECUTION_TARGET_ADDRESS={execution_target} in .env before deployment.")
    print("Saved public route evidence to .local/m2-preflight.json.")
    print("This proves RPC/feed/token/1inch route readiness only. It does NOT prove B1-B4 or execute a transaction.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001 - CLI must fail closed with one concise reason.
        print(f"M2 PREFLIGHT: FAIL — {exc}", file=sys.stderr)
        raise SystemExit(1)
