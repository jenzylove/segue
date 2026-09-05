#!/usr/bin/env python3
"""Fetch and validate a firm 1inch Classic Swap transaction for Segue's M2 demo vault.

This script does not broadcast a transaction. It writes the validated response to
.local/m2-quote.json for the explicit Base-mainnet execution step.
"""

from __future__ import annotations

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
USER_AGENT = "Mozilla/5.0 (compatible; Segue-M2-Firm-Quote/1.0)"


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


def main() -> int:
    load_dotenv()
    required = (
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

    sell_amount = os.environ.get("M2_BUY_USDC_ATOMIC", "1000000")
    if int(sell_amount) <= 0:
        raise ValueError("M2_BUY_USDC_ATOMIC must be positive")

    slippage_bps = int(os.environ.get("M2_ONEINCH_SLIPPAGE_BPS", "50"))
    if slippage_bps <= 0 or slippage_bps > 5000:
        raise ValueError("M2_ONEINCH_SLIPPAGE_BPS must be between 1 and 5000")
    slippage_pct = str(Decimal(slippage_bps) / Decimal(100))

    vault = os.environ["DEMO_VAULT_ADDRESS"]
    executor = os.environ["EXECUTOR_ADDRESS"]
    sell_token = os.environ["USDC_ADDRESS"]
    buy_token = os.environ["B20_TOKEN_ADDRESS"]
    configured_target = os.environ["EXECUTION_TARGET_ADDRESS"]

    live_spender = str(oneinch_get("approve/spender").get("address") or "")
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
            # The vault grants the exact allowance inside executeStep immediately before
            # calling 1inch, so API simulation must not require a pre-existing allowance.
            "forceApprove": "true",
            "includeProtocols": "true",
            "includeTokensInfo": "true",
        },
    )

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
    if norm(tx.get("to")) != norm(configured_target):
        raise RuntimeError(f"1inch tx.to mismatch: {tx.get('to')}")
    if not tx.get("data") or not str(tx["data"]).startswith("0x"):
        raise RuntimeError("1inch swap missing tx.data")
    if int(tx.get("value") or 0) != 0:
        raise RuntimeError("ERC-20→ERC-20 swap unexpectedly requires native value")

    Path(".local").mkdir(exist_ok=True)
    Path(".local/m2-quote.json").write_text(json.dumps(swap, indent=2), encoding="utf-8")

    print("FIRM QUOTE: PASS")
    print(f"  vault/from/receiver: {vault}")
    print(f"  origin: {executor}")
    print(f"  sellAmount: {sell_amount}")
    print(f"  dstAmount quoted: {dst_amount}")
    print(f"  slippage: {slippage_pct}%")
    print(f"  transaction.to: {tx.get('to')}")
    print("  saved: .local/m2-quote.json")
    print("No transaction was broadcast.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"FIRM QUOTE: FAIL — {exc}", file=sys.stderr)
        raise SystemExit(1)
