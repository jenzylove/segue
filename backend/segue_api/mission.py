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
        self.db.commit()

    def save(self, mission: Mission) -> Mission:
        mission.updated_at = datetime.now(timezone.utc).isoformat()
        self.db.execute("insert or replace into missions values (?,?)", (mission.id, json.dumps(asdict(mission), default=lambda x: x.value)))
        self.db.commit(); return mission

    def get(self, mission_id: str) -> Mission | None:
        row = self.db.execute("select payload from missions where id=?", (mission_id,)).fetchone()
        if not row: return None
        value = json.loads(row[0]); value["state"] = MissionState(value["state"]); return Mission(**value)
