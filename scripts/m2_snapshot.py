#!/usr/bin/env python3
"""Capture the exact Base state needed around each irreversible M2 transaction."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

BASE_CHAIN_ID = 8453
USER_AGENT = "Mozilla/5.0 (compatible; Segue-M2-Snapshot/1.0)"
BALANCE_OF_SELECTOR = "70a08231"
POLICY_STATUS = ("NONE", "LIVE", "COMPLETED", "CANCELLED")
STEP_STATUS = ("NONE", "QUEUED", "ACTIVE", "EXECUTED", "CANCELLED")


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


def artifact() -> dict:
    path = Path("out/StockPolicyVault.sol/StockPolicyVault.json")
    if not path.exists():
        raise RuntimeError("Foundry artifact missing; run `forge build` first")
    return json.loads(path.read_text(encoding="utf-8"))


def selector(signature: str, art: dict) -> str:
    value = (art.get("methodIdentifiers") or {}).get(signature)
    if not value:
        raise RuntimeError(f"selector missing from Foundry artifact: {signature}")
    return "0x" + value


def encode_uint(value: int) -> str:
    if value < 0:
        raise ValueError("uint argument cannot be negative")
    return value.to_bytes(32, "big").hex()


def words(result: str, minimum: int) -> list[int]:
    body = result[2:] if result.startswith("0x") else result
    if len(body) < minimum * 64:
        raise RuntimeError(f"short eth_call return: expected {minimum} words, got {len(body) // 64}")
    return [int(body[i * 64 : (i + 1) * 64], 16) for i in range(len(body) // 64)]


def address_word(value: int) -> str:
    return "0x" + value.to_bytes(32, "big").hex()[-40:]


def eth_call(to: str, data: str) -> str:
    return rpc("eth_call", [{"to": to, "data": data}, "latest"])


def read_uint(vault: str, signature: str, art: dict) -> int:
    return words(eth_call(vault, selector(signature, art)), 1)[0]


def read_address(vault: str, signature: str, art: dict) -> str:
    return address_word(read_uint(vault, signature, art))


def balance_of(token: str, account: str) -> int:
    data = "0x" + BALANCE_OF_SELECTOR + account[2:].rjust(64, "0")
    return words(eth_call(token, data), 1)[0]


def decode_policy(result: str) -> dict[str, int | str]:
    raw = words(result, 6)
    status = raw[0]
    return {
        "status": status,
        "statusLabel": POLICY_STATUS[status] if status < len(POLICY_STATUS) else f"UNKNOWN_{status}",
        "createdAt": raw[1],
        "currentStep": raw[2],
        "stepCount": raw[3],
        "maxDeployedUSDC": raw[4],
        "deployedUSDC": raw[5],
    }


def decode_step(result: str) -> dict[str, int | str]:
    raw = words(result, 12)
    status = raw[0]
    return {
        "status": status,
        "statusLabel": STEP_STATUS[status] if status < len(STEP_STATUS) else f"UNKNOWN_{status}",
        "conditionAsset": address_word(raw[1]),
        "conditionType": raw[2],
        "threshold": raw[3],
        "deltaBps": raw[4],
        "referencePrice": raw[5],
        "sellToken": address_word(raw[6]),
        "buyToken": address_word(raw[7]),
        "amountMode": raw[8],
        "amount": raw[9],
        "maxDeviationBps": raw[10],
        "expiresAt": raw[11],
    }


def git_head() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Capture Segue M2 vault/policy/balance state")
    parser.add_argument("--label", required=True, help="e.g. before-buy, after-buy, after-sell")
    parser.add_argument("--policy-id", type=int, default=None)
    args = parser.parse_args(argv)

    if not re.fullmatch(r"[A-Za-z0-9._-]+", args.label):
        raise ValueError("label may contain only letters, numbers, dot, underscore and dash")

    load_dotenv()
    required = ("BASE_RPC_URL", "DEMO_VAULT_ADDRESS", "USDC_ADDRESS", "B20_TOKEN_ADDRESS")
    missing = [name for name in required if not os.environ.get(name)]
    if missing:
        print("M2 SNAPSHOT: BLOCKED — missing " + ", ".join(missing))
        return 2

    chain_id = int(rpc("eth_chainId", []), 16)
    if chain_id != BASE_CHAIN_ID:
        raise RuntimeError(f"wrong chain: expected {BASE_CHAIN_ID}, got {chain_id}")

    art = artifact()
    vault = os.environ["DEMO_VAULT_ADDRESS"]
    policy_id = args.policy_id if args.policy_id is not None else int(os.environ.get("M2_POLICY_ID", "0"))
    block_number = int(rpc("eth_blockNumber", []), 16)

    state: dict[str, object] = {
        "label": args.label,
        "capturedAtUnix": int(time.time()),
        "chainId": chain_id,
        "blockNumber": block_number,
        "gitCommit": git_head(),
        "vault": vault,
        "owner": read_address(vault, "owner()", art),
        "executor": read_address(vault, "executor()", art),
        "activePolicyId": read_uint(vault, "activePolicyId()", art),
        "vaultMaxDeployedUSDC": read_uint(vault, "vaultMaxDeployedUSDC()", art),
        "vaultDeployedUSDC": read_uint(vault, "vaultDeployedUSDC()", art),
        "balances": {
            "USDC": balance_of(os.environ["USDC_ADDRESS"], vault),
            "B20": balance_of(os.environ["B20_TOKEN_ADDRESS"], vault),
        },
    }

    if policy_id > 0:
        policy_call = selector("policies(uint256)", art) + encode_uint(policy_id)
        policy = decode_policy(eth_call(vault, policy_call))
        state["policyId"] = policy_id
        state["policy"] = policy
        if int(policy["stepCount"]) > 0:
            current_step = int(policy["currentStep"])
            step_call = selector("getStep(uint256,uint8)", art) + encode_uint(policy_id) + encode_uint(current_step)
            state["currentStep"] = decode_step(eth_call(vault, step_call))

    Path(".local").mkdir(exist_ok=True)
    output = Path(f".local/m2-snapshot-{args.label}.json")
    output.write_text(json.dumps(state, indent=2), encoding="utf-8")

    print("M2 SNAPSHOT: PASS")
    print(f"  label: {args.label}")
    print(f"  block: {block_number}")
    print(f"  git: {state['gitCommit']}")
    print(f"  vault: {vault}")
    print(f"  USDC: {state['balances']['USDC']}")
    print(f"  B20: {state['balances']['B20']}")
    if "policy" in state:
        policy = state["policy"]
        print(f"  policy {policy_id}: {policy['statusLabel']} step={policy['currentStep']}/{policy['stepCount']}")
        print(f"  current step: {state['currentStep']['statusLabel']}")
    print(f"  saved: {output}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"M2 SNAPSHOT: FAIL — {exc}", file=sys.stderr)
        raise SystemExit(1)
