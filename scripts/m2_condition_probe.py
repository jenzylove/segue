#!/usr/bin/env python3
"""Capture read-only mainnet evidence from StockPolicyVault.previewExecution."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

BASE_CHAIN_ID = 8453
USER_AGENT = "Mozilla/5.0 (compatible; Segue-M2-Condition-Probe/1.0)"
PREVIEW_REASONS = (
    "READY",
    "PAUSED",
    "POLICY_INACTIVE",
    "STEP_INACTIVE",
    "EXPIRED",
    "CONDITION_FALSE",
    "ZERO_SELL",
    "INSUFFICIENT_BALANCE",
    "POLICY_CAP",
    "VAULT_CAP",
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
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


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
        error_body = exc.read().decode("utf-8", "replace")[:500]
        raise RuntimeError(
            f"RPC {method} via {safe_host(url)} failed HTTP {exc.code}: {error_body}"
        ) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"RPC {method} via {safe_host(url)} failed: {exc.reason}") from exc
    if "error" in payload:
        raise RuntimeError(f"RPC {method} failed: {payload['error']}")
    return payload["result"]


def preview_selector() -> str:
    artifact = Path("out/StockPolicyVault.sol/StockPolicyVault.json")
    if not artifact.exists():
        raise RuntimeError("Foundry artifact missing; run `forge build` first")
    payload = json.loads(artifact.read_text(encoding="utf-8"))
    identifiers = payload.get("methodIdentifiers") or {}
    selector = identifiers.get("previewExecution(uint256)")
    if not selector:
        raise RuntimeError("previewExecution selector missing from Foundry artifact")
    return "0x" + selector


def decode_preview(result: str) -> dict[str, int | bool | str]:
    body = result[2:] if result.startswith("0x") else result
    if len(body) < 64 * 5:
        raise RuntimeError(f"previewExecution returned short data ({len(body)} hex chars)")
    words = [int(body[i * 64 : (i + 1) * 64], 16) for i in range(5)]
    executable = bool(words[0])
    reason = words[1]
    label = PREVIEW_REASONS[reason] if reason < len(PREVIEW_REASONS) else f"UNKNOWN_{reason}"
    return {
        "executable": executable,
        "reason": reason,
        "reasonLabel": label,
        "currentPriceUsd1e8": words[2],
        "sellAmount": words[3],
        "minBuyAmount": words[4],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Capture Segue M2 previewExecution evidence")
    parser.add_argument("--policy-id", type=int, default=None)
    parser.add_argument("--expect", choices=("ready", "false", "any"), default="any")
    args = parser.parse_args(argv)

    load_dotenv()
    required = ("BASE_RPC_URL", "DEMO_VAULT_ADDRESS")
    missing = [name for name in required if not os.environ.get(name)]
    if missing:
        print("CONDITION PROBE: BLOCKED — missing " + ", ".join(missing))
        return 2

    policy_id = args.policy_id if args.policy_id is not None else int(os.environ.get("M2_POLICY_ID", "0"))
    if policy_id <= 0:
        raise ValueError("policy id must be positive")

    chain_id = int(rpc("eth_chainId", []), 16)
    if chain_id != BASE_CHAIN_ID:
        raise RuntimeError(f"wrong chain: expected {BASE_CHAIN_ID}, got {chain_id}")

    vault = os.environ["DEMO_VAULT_ADDRESS"]
    calldata = preview_selector() + policy_id.to_bytes(32, "big").hex()
    raw = rpc("eth_call", [{"to": vault, "data": calldata}, "latest"])
    decoded = decode_preview(raw)
    block_number = int(rpc("eth_blockNumber", []), 16)

    if args.expect == "ready" and not decoded["executable"]:
        raise RuntimeError(f"expected READY, got {decoded['reasonLabel']}")
    if args.expect == "false" and (
        decoded["executable"] or decoded["reasonLabel"] != "CONDITION_FALSE"
    ):
        raise RuntimeError(
            f"expected CONDITION_FALSE, got executable={decoded['executable']} reason={decoded['reasonLabel']}"
        )

    evidence = {
        "capturedAtUnix": int(time.time()),
        "chainId": chain_id,
        "blockNumber": block_number,
        "vault": vault,
        "policyId": policy_id,
        **decoded,
    }
    Path(".local").mkdir(exist_ok=True)
    output = Path(f".local/m2-condition-{policy_id}.json")
    output.write_text(json.dumps(evidence, indent=2), encoding="utf-8")

    print("CONDITION PROBE: PASS")
    print(f"  block: {block_number}")
    print(f"  vault: {vault}")
    print(f"  policyId: {policy_id}")
    print(f"  executable: {decoded['executable']}")
    print(f"  reason: {decoded['reasonLabel']}")
    print(f"  currentPriceUsd1e8: {decoded['currentPriceUsd1e8']}")
    print(f"  sellAmount: {decoded['sellAmount']}")
    print(f"  minBuyAmount: {decoded['minBuyAmount']}")
    print(f"  saved: {output}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"CONDITION PROBE: FAIL — {exc}", file=sys.stderr)
        raise SystemExit(1)
