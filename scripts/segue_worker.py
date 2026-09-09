"""Run one durable Segue reconciliation pass.

This command never signs or broadcasts. It is suitable for a cron job, a
container scheduler, or a manually triggered recovery pass after a restart.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.segue_api.mission import MissionStore  # noqa: E402
from backend.segue_api.morpho import API as MORPHO_API  # noqa: E402
from backend.segue_api.worker import reconcile_live, reconcile_receipt  # noqa: E402


def load_env() -> None:
    for name in (".env", ".env.local"):
        path = ROOT / name
        if not path.exists():
            continue
        for raw in path.read_text().splitlines():
            line = raw.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def main(argv: list[str] | None = None) -> int:
    load_env()
    parser = argparse.ArgumentParser(description="Reconcile Segue missions from live Base state")
    parser.add_argument("--mission-id", help="reconcile one mission; otherwise reconcile all durable missions")
    parser.add_argument("--wallet", help="limit an all-missions pass to one owner")
    args = parser.parse_args(argv)
    rpc = os.environ.get("BASE_RPC_URL", "")
    if not rpc:
        print("BLOCKED: BASE_RPC_URL is required for live worker reads", file=sys.stderr)
        return 2
    store = MissionStore(os.environ.get("SEGUE_DB_PATH", str(ROOT / "segue_missions.sqlite3")))
    try:
        if args.mission_id:
            missions = [store.get(args.mission_id)]
        elif args.wallet:
            missions = store.by_owner(args.wallet)
        else:
            rows = store.db.execute("select payload from missions order by rowid desc").fetchall()
            missions = [store.get(json.loads(row[0])["id"]) for row in rows]
        output = []
        for mission in missions:
            if mission is None:
                continue
            current = reconcile_live(store, mission.id, MORPHO_API, rpc)
            for action in store.actions(current.id):
                if action["status"] == "SUBMITTED" and action.get("tx_hash"):
                    current = reconcile_receipt(store, current.id, action["tx_hash"], rpc, action["idempotency_key"])
            output.append({"mission_id": current.id, "state": current.state.value, "updated_at": current.updated_at})
        print(json.dumps({"reconciled": output}, indent=2))
        return 0
    finally:
        store.close()


if __name__ == "__main__":
    raise SystemExit(main())
