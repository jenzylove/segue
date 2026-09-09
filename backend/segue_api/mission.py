from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


class MissionState(str, Enum):
    PROPOSED = "PROPOSED"; APPROVED = "APPROVED"; BORROW_READY = "BORROW_READY"; WAITING_FOR_LIQUIDITY = "WAITING_FOR_LIQUIDITY"; BORROWED = "BORROWED"; MANAGED = "MANAGED"; DE_RISKING = "DE_RISKING"; NEEDS_APPROVAL = "NEEDS_APPROVAL"; REPAID = "REPAID"; CLOSED = "CLOSED"; ERROR = "ERROR"


@dataclass
class Mission:
    id: str
    owner: str
    state: MissionState
    market_id: str
    policy: dict
    snapshot: dict
    plan: dict | None = None
    tx_hash: str | None = None
    updated_at: str = ""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class MissionStore:
    """Durable SQLite index; Base chain remains the source of truth."""

    def __init__(self, path: str | Path = "segue_missions.sqlite3"):
        # SQLite does not create missing parent directories.  Railway mounts
        # the persistent volume at runtime, so make the configured directory
        # available before the module-level store opens its database.  This
        # also keeps local/custom SEGUE_DB_PATH values from failing at import.
        if str(path) != ":memory:":
            db_path = Path(path).expanduser()
            db_path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("create table if not exists missions (id text primary key, payload text not null)")
        self.db.execute("create table if not exists mission_events (id integer primary key autoincrement, mission_id text, kind text, payload text, created_at text)")
        self.db.execute("create table if not exists mission_actions (idempotency_key text primary key, mission_id text, action text, status text, plan text, tx_hash text, evidence text, created_at text, updated_at text)")
        self.db.execute("create table if not exists mission_snapshots (id integer primary key autoincrement, mission_id text, kind text, payload text, created_at text)")
        self.db.commit()
        self._ensure_action_columns()

    def _ensure_action_columns(self) -> None:
        cols = {row[1] for row in self.db.execute("pragma table_info(mission_actions)")}
        if "updated_at" not in cols:
            self.db.execute("alter table mission_actions add column updated_at text")
            self.db.commit()

    def save(self, mission: Mission) -> Mission:
        mission.updated_at = _now()
        payload = json.dumps(asdict(mission), default=lambda value: value.value if isinstance(value, Enum) else str(value))
        self.db.execute("insert or replace into missions values (?,?)", (mission.id, payload))
        self.db.commit()
        return mission

    def event(self, mission_id: str, kind: str, payload: dict) -> None:
        self.db.execute("insert into mission_events(mission_id,kind,payload,created_at) values (?,?,?,?)", (mission_id, kind, json.dumps(payload, default=str), _now()))
        self.db.commit()

    def snapshot(self, mission_id: str, kind: str, payload: dict) -> None:
        self.db.execute("insert into mission_snapshots(mission_id,kind,payload,created_at) values (?,?,?,?)", (mission_id, kind, json.dumps(payload, default=str), _now()))
        self.db.commit()

    def timeline(self, mission_id: str) -> list[dict]:
        return [{"kind": row[0], "payload": json.loads(row[1]), "created_at": row[2]} for row in self.db.execute("select kind,payload,created_at from mission_events where mission_id=? order by id", (mission_id,))]

    def snapshots(self, mission_id: str) -> list[dict]:
        return [{"kind": row[0], "payload": json.loads(row[1]), "created_at": row[2]} for row in self.db.execute("select kind,payload,created_at from mission_snapshots where mission_id=? order by id", (mission_id,))]

    def action(self, key: str, mission_id: str, action: str, plan: dict, status: str = "READY", evidence: dict | None = None) -> dict:
        if not key:
            raise ValueError("idempotency key is required")
        row = self.db.execute("select * from mission_actions where idempotency_key=?", (key,)).fetchone()
        if row:
            if row["mission_id"] != mission_id or row["action"] != action:
                raise ValueError("idempotency key is already bound to a different action")
            return self._action_dict(row)
        now = _now()
        initial_evidence = evidence or {}
        self.db.execute("insert into mission_actions(idempotency_key,mission_id,action,status,plan,tx_hash,evidence,created_at,updated_at) values (?,?,?,?,?,?,?,?,?)", (key, mission_id, action, status, json.dumps(plan, default=str), None, json.dumps(initial_evidence, default=str), now, now))
        self.db.commit()
        self.event(mission_id, "ACTION_READY", {"idempotency_key": key, "action": action})
        return {"idempotency_key": key, "mission_id": mission_id, "action": action, "status": status, "plan": plan, "tx_hash": None, "evidence": initial_evidence}

    def _action_dict(self, row: sqlite3.Row) -> dict:
        return {"idempotency_key": row["idempotency_key"], "mission_id": row["mission_id"], "action": row["action"], "status": row["status"], "plan": json.loads(row["plan"] or "{}"), "tx_hash": row["tx_hash"], "evidence": json.loads(row["evidence"] or "{}")}

    def get_action(self, key: str) -> dict | None:
        row = self.db.execute("select * from mission_actions where idempotency_key=?", (key,)).fetchone()
        return self._action_dict(row) if row else None

    def actions(self, mission_id: str) -> list[dict]:
        return [self._action_dict(row) for row in self.db.execute("select * from mission_actions where mission_id=? order by created_at", (mission_id,))]

    def update_action(self, key: str, *, status: str | None = None, tx_hash: str | None = None, evidence: dict | None = None) -> dict:
        row = self.db.execute("select * from mission_actions where idempotency_key=?", (key,)).fetchone()
        if not row:
            raise ValueError("action idempotency key not found")
        current = row["status"]
        requested = status or current
        # A failed submission can be retried with the same idempotency key,
        # while a confirmed action is terminal and can never be resubmitted.
        allowed = {"READY": {"READY", "SUBMITTED", "FAILED"}, "SUBMITTED": {"SUBMITTED", "CONFIRMED", "FAILED"}, "CONFIRMED": {"CONFIRMED"}, "FAILED": {"FAILED", "SUBMITTED"}}
        if requested not in allowed.get(current, {current}):
            raise ValueError(f"invalid action transition {current} -> {requested}")
        values = {"status": requested, "tx_hash": tx_hash if tx_hash is not None else row["tx_hash"], "evidence": json.dumps(evidence if evidence is not None else json.loads(row["evidence"] or "{}")), "updated_at": _now()}
        self.db.execute("update mission_actions set status=?,tx_hash=?,evidence=?,updated_at=? where idempotency_key=?", (values["status"], values["tx_hash"], values["evidence"], values["updated_at"], key))
        self.db.commit()
        return self.get_action(key)  # type: ignore[return-value]

    def get(self, mission_id: str) -> Mission | None:
        row = self.db.execute("select payload from missions where id=?", (mission_id,)).fetchone()
        if not row: return None
        value = json.loads(row[0]); value["state"] = MissionState(value["state"]); return Mission(**value)

    def by_owner(self, owner: str) -> list[Mission]:
        """Return durable missions for wallet recovery after a restart."""
        rows = self.db.execute("select payload from missions order by rowid desc").fetchall()
        missions: list[Mission] = []
        for row in rows:
            value = json.loads(row[0])
            if str(value.get("owner", "")).lower() != owner.lower():
                continue
            value["state"] = MissionState(value["state"])
            missions.append(Mission(**value))
        return missions

    def close(self) -> None:
        self.db.close()
