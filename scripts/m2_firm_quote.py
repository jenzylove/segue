#!/usr/bin/env python3
"""Fetch and validate a firm 1inch Classic Swap transaction for Segue M2.

Supports both halves of the real Base-mainnet proof:
- buy:  USDC -> configured Coinbase B20
- sell: configured Coinbase B20 -> USDC

The script never signs or broadcasts. It writes the validated provider response and
router calldata under .local/ so the exact payload can be handed to the bounded
StockPolicyVault execution script.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from decimal import Decimal
from pathlib import Path

BASE_CHAIN_ID = 8453
ONEINCH_BASE_URL = f"https://api.1inch.com/swap/v6.1/{BASE_CHAIN_ID}"
USER_AGENT = "Mozilla/5.0 (compatible; Segue-M2-Firm-Quote/1.1)"
BALANCE_OF_SELECTOR = "70a08231"


def load_dotenv(path: str = ".env") -> None:
    p = Path(path)
    if not p.exists():
        return
    for raw in p.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def norm(address: str | None) -> str:
    return (address or "").lower()


def valid_address(address: str | None) -> bool:
    value = address or ""
    return value.startswith("0x") and len(value) == 42 and all(c in "0123456789abcdefABCDEF" for c in value[2:])


def safe_host(url: str) -> str:
    return urllib.parse.urlparse(url).hostname or "configured RPC"


def rpc(method: str, params: list) -> str:
    url = os.environ["BASE_RPC_URL"]
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    req = urllib.request.Request(
        url,
        body,
        {"Content-Type": "application/json", "Accept": "application/json", "User-Agent": USER_AGENT},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode("utf-8", "replace")[:500]
        raise RuntimeError(f"RPC {method} via {safe_host(url)} failed HTTP {exc.code}: {body_text}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"RPC {method} via {safe_host(url)} failed: {exc.reason}") from exc
    if "error" in payload:
        raise RuntimeError(f"RPC {method} failed: {payload['error']}")
    return payload["result"]


def balance_of(token: str, account: str) -> int:
    if not valid_address(token) or not valid_address(account):
        raise ValueError("balanceOf requires valid token/account addresses")
    data = "0x" + BALANCE_OF_SELECTOR + account[2:].rjust(64, "0")
    result = rpc("eth_call", [{"to": token, "data": data}, "latest"])
    return int(result, 16)


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
        body = exc.read().decode("utf-8", "replace")[:1000]
        request_id = exc.headers.get("X-Request-Id") if exc.headers else None
        suffix = f" requestId={request_id}" if request_id else ""
        raise RuntimeError(f"1inch {path} failed HTTP {exc.code}: {body}{suffix}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"1inch {path} failed: {exc.reason}") from exc


def parse_tx_value(value: object) -> int:
    if value is None or value == "":
        return 0
    if isinstance(value, int):
        return value
    text = str(value)
    return int(text, 16) if text.lower().startswith("0x") else int(text)


def resolve_trade(direction: str) -> tuple[str, str, str]:
    usdc = os.environ["USDC_ADDRESS"]
    b20 = os.environ["B20_TOKEN_ADDRESS"]
    vault = os.environ["DEMO_VAULT_ADDRESS"]

    if direction == "buy":
        amount = os.environ.get("M2_BUY_USDC_ATOMIC", "1000000")
        if int(amount) <= 0:
            raise ValueError("M2_BUY_USDC_ATOMIC must be positive")
        return usdc, b20, amount

    override = os.environ.get("M2_SELL_B20_ATOMIC", "").strip()
    amount_int = int(override) if override else balance_of(b20, vault)
    if amount_int <= 0:
        raise RuntimeError("demo vault has no B20 balance to sell")
    return b20, usdc, str(amount_int)


def validate_swap_payload(
    swap: dict,
    *,
    sell_token: str,
    buy_token: str,
    vault: str,
    execution_target: str,
) -> tuple[int, str]:
    src_info = swap.get("srcToken") or {}
    dst_info = swap.get("dstToken") or {}
    if norm(src_info.get("address")) != norm(sell_token):
        raise RuntimeError(f"1inch src token mismatch: {src_info.get('address')}")
    if norm(dst_info.get("address")) != norm(buy_token):
        raise RuntimeError(f"1inch dst token mismatch: {dst_info.get('address')}")

    dst_amount = int(swap.get("dstAmount") or 0)
    if dst_amount <= 0:
        raise RuntimeError("1inch returned zero dstAmount")

    tx = swap.get("tx") or {}
    if norm(tx.get("from")) != norm(vault):
        raise RuntimeError(f"1inch tx.from mismatch: {tx.get('from')}")
    if norm(tx.get("to")) != norm(execution_target):
        raise RuntimeError(f"1inch tx.to mismatch: {tx.get('to')}")

    calldata = str(tx.get("data") or "")
    if not calldata.startswith("0x") or len(calldata) < 10:
        raise RuntimeError("1inch swap missing usable tx.data")
    if parse_tx_value(tx.get("value")) != 0:
        raise RuntimeError("ERC-20→ERC-20 swap unexpectedly requires native value")

    return dst_amount, calldata


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fetch a validated Segue M2 1inch transaction")
    parser.add_argument("--direction", choices=("buy", "sell"), default="buy")
    args = parser.parse_args(argv)

    load_dotenv()
    required = (
        "BASE_RPC_URL",
        "ONEINCH_API_KEY",
        "EXECUTOR_ADDRESS",
        "USDC_ADDRESS",
        "B20_TOKEN_ADDRESS",
        "DEMO_VAULT_ADDRESS",
        "EXECUTION_TARGET_ADDRESS",
    )
    missing = [key for key in required if not os.environ.get(key)]
    if missing:
        print("FIRM QUOTE: BLOCKED — missing " + ", ".join(missing))
        return 2

    vault = os.environ["DEMO_VAULT_ADDRESS"]
    executor = os.environ["EXECUTOR_ADDRESS"]
    configured_target = os.environ["EXECUTION_TARGET_ADDRESS"]
    if not valid_address(vault) or not valid_address(executor) or not valid_address(configured_target):
        raise ValueError("DEMO_VAULT_ADDRESS, EXECUTOR_ADDRESS and EXECUTION_TARGET_ADDRESS must be valid addresses")

    sell_token, buy_token, sell_amount = resolve_trade(args.direction)

    slippage_bps = int(os.environ.get("M2_ONEINCH_SLIPPAGE_BPS", "50"))
    if slippage_bps <= 0 or slippage_bps > 5000:
        raise ValueError("M2_ONEINCH_SLIPPAGE_BPS must be between 1 and 5000")
    slippage_pct = str(Decimal(slippage_bps) / Decimal(100))

    live_spender = str(oneinch_get("approve/spender").get("address") or "")
    if not valid_address(live_spender):
        raise RuntimeError(f"1inch returned invalid approve/spender address: {live_spender}")
    if norm(live_spender) != norm(configured_target):
        raise RuntimeError(
            "configured execution target no longer matches 1inch approve/spender: "
            f"configured={configured_target}, live={live_spender}"
        )

    swap = oneinch_get(
        "swap",
        {
            "src": sell_token,
            "dst": buy_token,
            "amount": sell_amount,
            "from": vault,
            "origin": executor,
            "receiver": vault,
            "slippage": slippage_pct,
            "allowPartialFill": "false",
            "disableEstimate": "false",
            "forceApprove": "true",
            "includeProtocols": "true",
            "includeTokensInfo": "true",
        },
    )

    dst_amount, calldata = validate_swap_payload(
        swap,
        sell_token=sell_token,
        buy_token=buy_token,
        vault=vault,
        execution_target=configured_target,
    )

    Path(".local").mkdir(exist_ok=True)
    quote_path = Path(f".local/m2-quote-{args.direction}.json")
    calldata_path = Path(f".local/m2-calldata-{args.direction}.txt")
    quote_path.write_text(json.dumps(swap, indent=2), encoding="utf-8")
    calldata_path.write_text(calldata + "\n", encoding="utf-8")

    print(f"FIRM QUOTE ({args.direction.upper()}): PASS")
    print(f"  vault/from/receiver: {vault}")
    print(f"  origin: {executor}")
    print(f"  sellToken: {sell_token}")
    print(f"  buyToken: {buy_token}")
    print(f"  sellAmount: {sell_amount}")
    print(f"  dstAmount quoted: {dst_amount}")
    print(f"  slippage: {slippage_pct}%")
    print(f"  transaction.to: {configured_target}")
    print(f"  saved provider response: {quote_path}")
    print(f"  saved router calldata: {calldata_path}")
    print("No transaction was broadcast.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"FIRM QUOTE: FAIL — {exc}", file=sys.stderr)
        raise SystemExit(1)
