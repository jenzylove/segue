from __future__ import annotations

"""Bridge durable sequence drafts to Segue's deployed M1 vault ABI.

The sequence store is intentionally protocol-light.  This module is the single
translation boundary into ``StockPolicyVault``: it loads deployment values from
server configuration, encodes the canonical contract calls, and refuses pairs
or fields that the deployed NVDAc registry cannot enforce.
"""

import os
from typing import Any

from .b20 import CANONICAL_COLLATERAL
from .evm import address_word, encode_bytes_tail, keccak256, selector, word
from .morpho import USDC_BASE, rpc_call
from .sequence import validate_steps


CONDITION_CODES = {
    "PRICE_ABOVE": 0,
    "PRICE_BELOW": 1,
    "UP_BPS_FROM_REFERENCE": 2,
    "DOWN_BPS_FROM_REFERENCE": 3,
}
AMOUNT_MODE_CODES = {"FIXED": 0, "PERCENT_BALANCE": 1}
POLICY_SIGNATURE = "createPolicy((address,uint8,uint256,uint16,address,address,uint8,uint256,uint16,uint40)[],uint256)"


def _event_topic(signature: str) -> str:
    return "0x" + keccak256(signature.encode()).hex()


POLICY_CREATED_TOPIC = _event_topic("PolicyCreated(uint256,uint8,uint256)")
STEP_ACTIVATED_TOPIC = _event_topic("StepActivated(uint256,uint8,uint256)")
STEP_EXECUTED_TOPIC = _event_topic("StepExecuted(uint256,uint8,uint256,uint256,uint256)")
POLICY_COMPLETED_TOPIC = _event_topic("PolicyCompleted(uint256)")


def _address(value: Any, field: str) -> str:
    value = str(value or "")
    if len(value) != 42 or not value.startswith("0x"):
        raise ValueError(f"{field} must be a valid EVM address")
    try:
        if int(value[2:], 16) == 0:
            raise ValueError
    except ValueError as exc:
        raise ValueError(f"{field} must be a valid nonzero EVM address") from exc
    return value


def _condition_asset(step: dict[str, Any]) -> str:
    value = step.get("condition_asset") or step.get("conditionAsset")
    if not value:
        # Existing drafts predate the explicit field.  For the only currently
        # supported route the stock side is unambiguous, so recover it without
        # inventing a caller-supplied protocol identity.
        value = step.get("buy_token") if str(step.get("action", "")).upper() == "BUY" else step.get("sell_token")
    return _address(value, "condition_asset")


def _onchain_step(step: dict[str, Any]) -> list[str]:
    condition = str(step.get("condition_type", "")).upper()
    action = str(step.get("action", "")).upper()
    mode = str(step.get("amount_mode", "FIXED")).upper()
    condition_asset = _condition_asset(step)
    sell_token = _address(step.get("sell_token"), "sell_token")
    buy_token = _address(step.get("buy_token"), "buy_token")
    if condition_asset.lower() != CANONICAL_COLLATERAL.lower():
        raise ValueError("M1 activation currently supports only the verified NVDAc condition feed")
    if {sell_token.lower(), buy_token.lower()} != {USDC_BASE.lower(), CANONICAL_COLLATERAL.lower()}:
        raise ValueError("M1 activation currently supports only the verified NVDAc/USDC pair")
    if action not in {"BUY", "SELL"}:
        raise ValueError("M1 activation currently supports BUY and SELL; ROTATE needs another verified feed")
    if condition not in CONDITION_CODES:
        raise ValueError("unsupported condition")
    if mode not in AMOUNT_MODE_CODES:
        raise ValueError("unsupported amount mode")
    amount = int(step.get("amount", 0) or 0)
    threshold = int(step.get("threshold", 0) or 0)
    delta = int(step.get("delta_bps", 0) or 0)
    deviation = int(step.get("max_deviation_bps", 0) or 0)
    expiry = int(step.get("expires_at", 0) or 0)
    return [
        address_word(condition_asset),
        word(CONDITION_CODES[condition]),
        word(threshold),
        word(delta),
        address_word(sell_token),
        address_word(buy_token),
        word(AMOUNT_MODE_CODES[mode]),
        word(amount),
        word(deviation),
        word(expiry),
    ]


def create_policy_calldata(steps: Any, max_capital_atomic: int) -> str:
    normalized = validate_steps(steps)
    if max_capital_atomic <= 0:
        raise ValueError("max_capital_atomic must be positive")
    encoded = [_onchain_step(step) for step in normalized]
    # ABI head: offset to the dynamic tuple array, then policy cap.  Each
    # StepInput is static and occupies exactly ten 32-byte words.
    args = word(64) + word(max_capital_atomic) + word(len(encoded))
    args += "".join("".join(words) for words in encoded)
    return selector(POLICY_SIGNATURE) + args


def create_vault_calldata(executor: str, max_capital_atomic: int) -> str:
    executor = _address(executor, "executor")
    if max_capital_atomic <= 0:
        raise ValueError("max_capital_atomic must be positive")
    return selector("createVault(address,uint256)") + address_word(executor) + word(max_capital_atomic)


def approve_calldata(spender: str, amount_atomic: int) -> str:
    spender = _address(spender, "spender")
    if amount_atomic <= 0:
        raise ValueError("approval amount must be positive")
    return selector("approve(address,uint256)") + address_word(spender) + word(amount_atomic)


def deposit_settlement_calldata(amount_atomic: int) -> str:
    if amount_atomic <= 0:
        raise ValueError("deposit amount must be positive")
    return selector("depositSettlement(uint256)") + word(amount_atomic)


def execute_step_calldata(policy_id: int, route_calldata: str) -> str:
    if policy_id <= 0:
        raise ValueError("policy_id must be positive")
    if not isinstance(route_calldata, str) or not route_calldata.startswith("0x") or len(route_calldata) < 10:
        raise ValueError("validated route calldata is required")
    int(route_calldata[2:], 16)
    return selector("executeStep(uint256,bytes)") + word(policy_id) + word(64) + encode_bytes_tail(bytes.fromhex(route_calldata[2:]))


def _plan(target: str, calldata: str, operation: str, note: str, *, wallet: str | None = None) -> dict[str, Any]:
    return {"target": _address(target, "target"), "calldata": calldata, "value": "0", "operation": operation, "note": note, **({"wallet": wallet} if wallet else {})}


def resolve_vault(rpc: str, factory: str, owner: str) -> str | None:
    raw = rpc_call(rpc, "eth_call", [{"to": _address(factory, "factory"), "data": selector("vaultOf(address)") + address_word(_address(owner, "owner"))}, "latest"])
    if not isinstance(raw, str) or len(raw) < 66:
        raise ValueError("factory vaultOf returned malformed data")
    value = int(raw[-64:], 16)
    return None if value == 0 else "0x" + f"{value:040x}"


def build_activation_plan(sequence: dict[str, Any], *, factory: str, executor: str, vault: str | None = None) -> dict[str, Any]:
    factory = _address(factory, "factory")
    executor = _address(executor, "executor")
    owner = _address(sequence.get("wallet"), "wallet")
    cap = int(sequence.get("max_capital_atomic", 0) or 0)
    steps = validate_steps(sequence.get("steps"))
    actions: list[dict[str, Any]] = []
    # The caller must pass the freshly resolved factory mapping. Persisted
    # vault state is evidence/cache and must never override a live lookup.
    resolved_vault = vault
    if not resolved_vault:
        actions.append(_plan(factory, create_vault_calldata(executor, cap), "createVault", "Owner creates the canonical one-vault-per-wallet contract." , wallet=owner))
        return {
            "status": "AWAITING_VAULT",
            "sequence_id": sequence["id"],
            "wallet": owner,
            "factory": factory,
            "executor": executor,
            "actions": actions,
            "next_step": "Confirm VaultCreated, then request this plan again to fund and create the policy.",
        }
    resolved_vault = _address(resolved_vault, "vault")
    actions.extend([
        _plan(USDC_BASE, approve_calldata(resolved_vault, cap), "approveSettlement", "Owner approves the exact sequence cap to the Segue vault.", wallet=owner),
        _plan(resolved_vault, deposit_settlement_calldata(cap), "depositSettlement", "Owner funds the vault with the sequence settlement asset.", wallet=owner),
        _plan(resolved_vault, create_policy_calldata(steps, cap), "createPolicy", "Owner activates the persisted M1 sequence; step 0 captures its onchain reference.", wallet=owner),
    ])
    return {
        "status": "SIGNATURE_READY",
        "sequence_id": sequence["id"],
        "wallet": owner,
        "factory": factory,
        "executor": executor,
        "vault": resolved_vault,
        "actions": actions,
        "postcondition": "PolicyCreated and StepActivated events prove step 0 is ACTIVE with a reference price.",
    }


def build_execute_plan(vault: str, policy_id: int, route_calldata: str, *, executor: str) -> dict[str, Any]:
    return {
        "status": "SIGNATURE_READY",
        "wallet": _address(executor, "executor"),
        "vault": _address(vault, "vault"),
        "actions": [_plan(_address(vault, "vault"), execute_step_calldata(policy_id, route_calldata), "executeStep", "Executor submits the validated 1inch route; the vault rechecks condition, exact spend and minimum output.", wallet=executor)],
        "postcondition": "StepExecuted followed by StepActivated proves the first action and new reference before step 2 becomes ACTIVE.",
    }


def deployment_config() -> dict[str, str]:
    return {name: os.environ.get(name, "").strip() for name in ("FACTORY_ADDRESS", "EXECUTOR_ADDRESS", "EXECUTION_TARGET_ADDRESS", "ONEINCH_API_KEY")}


def reconcile_sequence_receipt(rpc: str, sequence: dict[str, Any], tx_hash: str) -> dict[str, Any]:
    """Decode only Segue vault events from a real receipt.

    A successful receipt without the expected vault event is deliberately not
    promoted to an active/advanced sequence state.
    """
    if not isinstance(tx_hash, str) or not tx_hash.startswith("0x") or len(tx_hash) != 66:
        raise ValueError("tx_hash must be a 32-byte transaction hash")
    receipt = rpc_call(rpc, "eth_getTransactionReceipt", [tx_hash])
    if receipt is None:
        return {"status": "PENDING", "tx_hash": tx_hash, "events": []}
    status = int(str(receipt.get("status", "0x0")), 16)
    if status != 1:
        return {"status": "FAILED", "tx_hash": tx_hash, "receipt": receipt, "events": []}
    vault = str(sequence.get("vault_address") or "").lower()
    if not vault:
        raise ValueError("sequence has no persisted canonical vault")
    decoded: list[dict[str, Any]] = []
    for log in receipt.get("logs") or []:
        if str(log.get("address", "")).lower() != vault:
            continue
        topics = [str(value).lower() for value in (log.get("topics") or [])]
        if not topics:
            continue
        data = str(log.get("data", "0x"))[2:]
        if topics[0] == POLICY_CREATED_TOPIC.lower() and len(topics) >= 2:
            decoded.append({"kind": "POLICY_CREATED", "policy_id": int(topics[1], 16), "step_count": int(data[0:64], 16) if len(data) >= 64 else None, "max_capital_atomic": int(data[64:128], 16) if len(data) >= 128 else None})
        elif topics[0] == STEP_ACTIVATED_TOPIC.lower() and len(topics) >= 3:
            decoded.append({"kind": "STEP_ACTIVATED", "policy_id": int(topics[1], 16), "step_index": int(topics[2], 16), "reference_price": int(data[-64:], 16) if len(data) >= 64 else None})
        elif topics[0] == STEP_EXECUTED_TOPIC.lower() and len(topics) >= 3:
            decoded.append({"kind": "STEP_EXECUTED", "policy_id": int(topics[1], 16), "step_index": int(topics[2], 16), "sold_atomic": int(data[0:64], 16) if len(data) >= 64 else None, "bought_atomic": int(data[64:128], 16) if len(data) >= 128 else None, "min_buy_atomic": int(data[128:192], 16) if len(data) >= 192 else None})
        elif topics[0] == POLICY_COMPLETED_TOPIC.lower() and len(topics) >= 2:
            decoded.append({"kind": "POLICY_COMPLETED", "policy_id": int(topics[1], 16)})
    if not decoded:
        raise ValueError("successful receipt contains no expected Segue policy event")
    return {"status": "CONFIRMED", "tx_hash": tx_hash, "receipt": receipt, "events": decoded}
