from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path


class MissionState(str, Enum):
    PROPOSED = "PROPOSED"; APPROVED = "APPROVED"; BORROW_READY = "BORROW_READY"; WAITING_FOR_LIQUIDITY = "WAITING_FOR_LIQUIDITY"; BORROWED = "BORROWED"; MANAGED = "MANAGED"; DE_RISKING = "DE_RISKING"; NEEDS_APPROVAL = "NEEDS_APPROVAL"; REPAID = "REPAID"; CLOSED = "CLOSED"


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


class MissionStore:
    def __init__(self, path: str | Path = "segue_missions.sqlite3"):
        self.db = sqlite3.connect(path)
        self.db.execute("create table if not exists missions (id text primary key, payload text not null)")
        self.db.execute("create table if not exists mission_events (id integer primary key autoincrement, mission_id text, kind text, payload text, created_at text)")
        self.db.execute("create table if not exists mission_actions (idempotency_key text primary key, mission_id text, action text, status text, plan text, tx_hash text, evidence text, created_at text)")
        self.db.commit()

    def save(self, mission: Mission) -> Mission:
        mission.updated_at = datetime.now(timezone.utc).isoformat()
        self.db.execute("insert or replace into missions values (?,?)", (mission.id, json.dumps(asdict(mission), default=lambda x: x.value)))
        self.db.commit(); return mission

    def event(self, mission_id: str, kind: str, payload: dict) -> None:
        self.db.execute("insert into mission_events(mission_id,kind,payload,created_at) values (?,?,?,?)", (mission_id, kind, json.dumps(payload), datetime.now(timezone.utc).isoformat()))
        self.db.commit()

    def timeline(self, mission_id: str) -> list[dict]:
        return [{"kind": r[0], "payload": json.loads(r[1]), "created_at": r[2]} for r in self.db.execute("select kind,payload,created_at from mission_events where mission_id=? order by id", (mission_id,))]

    def action(self, key: str, mission_id: str, action: str, plan: dict, status: str = "READY") -> dict:
        row=self.db.execute("select idempotency_key,mission_id,action,status,plan,tx_hash,evidence from mission_actions where idempotency_key=?",(key,)).fetchone()
        if row:return {"idempotency_key":row[0],"mission_id":row[1],"action":row[2],"status":row[3],"plan":json.loads(row[4]),"tx_hash":row[5],"evidence":json.loads(row[6] or "{}")}
        self.db.execute("insert into mission_actions(idempotency_key,mission_id,action,status,plan,created_at) values (?,?,?,?,?,?)",(key,mission_id,action,status,json.dumps(plan),datetime.now(timezone.utc).isoformat()));self.db.commit()
        return {"idempotency_key":key,"mission_id":mission_id,"action":action,"status":status,"plan":plan}

    def get(self, mission_id: str) -> Mission | None:
        row = self.db.execute("select payload from missions where id=?", (mission_id,)).fetchone()
        if not row: return None
        value = json.loads(row[0]); value["state"] = MissionState(value["state"]); return Mission(**value)

    def close(self) -> None:
        self.db.close()
