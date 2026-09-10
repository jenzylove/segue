from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any


CONDITIONS = {"PRICE_ABOVE", "PRICE_BELOW", "UP_BPS_FROM_REFERENCE", "DOWN_BPS_FROM_REFERENCE"}
ACTIONS = {"BUY", "SELL", "ROTATE"}
AMOUNT_MODES = {"FIXED", "PERCENT_BALANCE"}
PERCENT_AMOUNTS = {2500, 5000, 7500, 10000}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _address(value: Any, field: str) -> str:
    value = str(value or "")
    if len(value) != 42 or not value.startswith("0x"):
        raise ValueError(f"{field} must be a valid EVM address")
    try:
        int(value[2:], 16)
    except ValueError as exc:
        raise ValueError(f"{field} must be a valid EVM address") from exc
    return value


def validate_steps(steps: Any) -> list[dict[str, Any]]:
    if not isinstance(steps, list) or not 1 <= len(steps) <= 8:
        raise ValueError("steps must contain between 1 and 8 linear steps")
    normalized: list[dict[str, Any]] = []
    for index, raw in enumerate(steps):
        if not isinstance(raw, dict):
            raise ValueError(f"step {index + 1} must be an object")
        condition = str(raw.get("condition_type", raw.get("condition", ""))).upper()
        action = str(raw.get("action", "")).upper()
        mode = str(raw.get("amount_mode", "FIXED")).upper()
        if condition not in CONDITIONS:
            raise ValueError(f"step {index + 1} has unsupported condition")
        if action not in ACTIONS:
            raise ValueError(f"step {index + 1} has unsupported action")
        if mode not in AMOUNT_MODES:
            raise ValueError(f"step {index + 1} has unsupported amount mode")
        amount = int(raw.get("amount", 0) or 0)
        if amount <= 0:
            raise ValueError(f"step {index + 1} amount must be positive")
        if mode == "PERCENT_BALANCE" and amount not in PERCENT_AMOUNTS:
            raise ValueError(f"step {index + 1} percentage must be 2500, 5000, 7500 or 10000 bps")
        deviation = int(raw.get("max_deviation_bps", raw.get("maxDeviationBps", 0)) or 0)
        if deviation < 0 or deviation >= 10_000:
            raise ValueError(f"step {index + 1} max_deviation_bps must be below 10000")
        expiry = int(raw.get("expires_at", raw.get("expiry", 0)) or 0)
        threshold = int(raw.get("threshold", 0) or 0)
        delta = int(raw.get("delta_bps", raw.get("deltaBps", 0)) or 0)
        sell_token = _address(raw.get("sell_token"), f"step {index + 1} sell_token")
        buy_token = _address(raw.get("buy_token"), f"step {index + 1} buy_token")
        if sell_token.lower() == buy_token.lower():
            raise ValueError(f"step {index + 1} sell_token and buy_token must differ")
        if condition in {"PRICE_ABOVE", "PRICE_BELOW"} and threshold <= 0:
            raise ValueError(f"step {index + 1} threshold must be positive")
        if condition in {"UP_BPS_FROM_REFERENCE", "DOWN_BPS_FROM_REFERENCE"} and not 0 < delta < 10_000:
            raise ValueError(f"step {index + 1} delta_bps must be between 1 and 9999")
        normalized.append({
            "condition_type": condition,
            "threshold": threshold,
            "delta_bps": delta,
            "action": action,
            "sell_token": sell_token,
            "buy_token": buy_token,
            "amount_mode": mode,
            "amount": amount,
            "max_deviation_bps": deviation,
            "expires_at": expiry,
            "status": "ACTIVE" if index == 0 else "QUEUED",
            "reference_price": None,
            "condition_progress": None,
            "execution": None,
        })
    return normalized


class SequenceStore:
    def __init__(self, db: sqlite3.Connection):
        self.db = db
        self.db.execute("create table if not exists sequences (id text primary key, wallet text not null, payload text not null, created_at text not null, updated_at text not null)")
        self.db.execute("create table if not exists sequence_events (id integer primary key autoincrement, sequence_id text, kind text, payload text, created_at text)")
        self.db.commit()

    def save(self, value: dict[str, Any]) -> dict[str, Any]:
        now = _now()
        value = {**value, "updated_at": now, "created_at": value.get("created_at") or now}
        self.db.execute("insert or replace into sequences(id,wallet,payload,created_at,updated_at) values (?,?,?,?,?)", (value["id"], value["wallet"], json.dumps(value), value["created_at"], value["updated_at"]))
        self.db.commit()
        return value

    def create(self, wallet: str, steps: Any, *, max_capital_atomic: int = 0, vault_address: str | None = None) -> dict[str, Any]:
        normalized = validate_steps(steps)
        if max_capital_atomic <= 0:
            raise ValueError("max_capital_atomic must be positive")
        value = {"id": str(uuid.uuid4()), "wallet": wallet, "status": "DRAFT", "active_step": 0, "step_count": len(normalized), "max_capital_atomic": max_capital_atomic, "vault_address": vault_address, "execution_supported": False, "execution_status": "SIGNATURE_REQUIRED_FOR_ONCHAIN_POLICY", "execution_provider": "1inch Classic Swap · ONEINCH_API_KEY required for live routing", "steps": normalized}
        result = self.save(value)
        self.event(result["id"], "SEQUENCE_CREATED", {"wallet": wallet, "step_count": len(normalized), "source": "Segue M1/M2 contract semantics"})
        return result

    def event(self, sequence_id: str, kind: str, payload: dict[str, Any]) -> None:
        self.db.execute("insert into sequence_events(sequence_id,kind,payload,created_at) values (?,?,?,?)", (sequence_id, kind, json.dumps(payload, default=str), _now()))
        self.db.commit()

    def get(self, sequence_id: str) -> dict[str, Any] | None:
        row = self.db.execute("select payload from sequences where id=?", (sequence_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def by_wallet(self, wallet: str) -> list[dict[str, Any]]:
        rows = self.db.execute("select payload from sequences where lower(wallet)=lower(?) order by created_at desc", (wallet,)).fetchall()
        return [json.loads(row[0]) for row in rows]

    def events(self, sequence_id: str) -> list[dict[str, Any]]:
        rows = self.db.execute("select kind,payload,created_at from sequence_events where sequence_id=? order by id", (sequence_id,)).fetchall()
        return [{"kind": row[0], "payload": json.loads(row[1]), "created_at": row[2]} for row in rows]
