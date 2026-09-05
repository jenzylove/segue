#!/usr/bin/env python3
"""Fetch and validate a firm 0x AllowanceHolder quote for the deployed M2 demo vault.

This script does not broadcast a transaction. It writes the validated quote to
.local/m2-quote.json for the explicit mainnet execution step.
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
EXPECTED_ALLOWANCE_HOLDER = "0x0000000000001ff3684f28c67538d4d072c22734"


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


def main() -> int:
    load_dotenv()
    required = ("ZEROX_API_KEY", "USDC_ADDRESS", "B20_TOKEN_ADDRESS", "DEMO_VAULT_ADDRESS")
    missing = [key for key in required if not os.environ.get(key)]
    if missing:
        print("FIRM QUOTE: BLOCKED — missing " + ", ".join(missing))
        return 2

    sell_amount = os.environ.get("M2_BUY_USDC_ATOMIC", "1000000")  # default: 1 USDC
    if int(sell_amount) <= 0:
        raise ValueError("M2_BUY_USDC_ATOMIC must be positive")

    vault = os.environ["DEMO_VAULT_ADDRESS"]
    sell_token = os.environ["USDC_ADDRESS"]
    buy_token = os.environ["B20_TOKEN_ADDRESS"]

    params = urllib.parse.urlencode(
        {
            "chainId": str(BASE_CHAIN_ID),
            "sellToken": sell_token,
            "buyToken": buy_token,
            "sellAmount": sell_amount,
            "taker": vault,
            "recipient": vault,
            "slippageBps": os.environ.get("M2_ZEROX_SLIPPAGE_BPS", "50"),
        }
    )
    req = urllib.request.Request(
        f"https://api.0x.org/swap/allowance-holder/quote?{params}",
        headers={
            "0x-api-key": os.environ["ZEROX_API_KEY"],
            "0x-version": "v2",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            quote = json.load(response)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")[:1000]
        raise RuntimeError(f"0x quote failed HTTP {exc.code}: {body}") from exc

    if norm(quote.get("sellToken")) != norm(sell_token):
        raise RuntimeError("0x sellToken mismatch")
    if norm(quote.get("buyToken")) != norm(buy_token):
        raise RuntimeError("0x buyToken mismatch")
    if str(quote.get("sellAmount")) != str(sell_amount):
        raise RuntimeError("0x sellAmount mismatch")

    transaction = quote.get("transaction") or {}
    tx_to = norm(transaction.get("to"))
    if tx_to != EXPECTED_ALLOWANCE_HOLDER:
        raise RuntimeError(f"unexpected 0x transaction.to: {transaction.get('to')}")
    if not transaction.get("data") or not str(transaction["data"]).startswith("0x"):
        raise RuntimeError("0x quote missing transaction.data")
    if int(transaction.get("value") or 0) != 0:
        raise RuntimeError("ERC-20→ERC-20 quote unexpectedly requires native value")

    allowance = ((quote.get("issues") or {}).get("allowance") or {})
    spender = allowance.get("spender")
    if spender and norm(spender) != EXPECTED_ALLOWANCE_HOLDER:
        raise RuntimeError(f"unexpected allowance spender: {spender}")

    buy_amount = int(quote.get("buyAmount") or 0)
    if buy_amount <= 0:
        raise RuntimeError("0x returned zero buyAmount")

    Path(".local").mkdir(exist_ok=True)
    Path(".local/m2-quote.json").write_text(json.dumps(quote, indent=2), encoding="utf-8")

    print("FIRM QUOTE: PASS")
    print(f"  vault: {vault}")
    print(f"  sellAmount: {sell_amount}")
    print(f"  buyAmount quoted: {buy_amount}")
    print(f"  transaction.to: {transaction.get('to')}")
    print("  saved: .local/m2-quote.json")
    print("No transaction was broadcast.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"FIRM QUOTE: FAIL — {exc}", file=sys.stderr)
        raise SystemExit(1)
