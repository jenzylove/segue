import tempfile, unittest
from pathlib import Path
from backend.segue_api.mission import Mission, MissionState, MissionStore
from backend.segue_api.worker import reconcile_mission

class MissionTests(unittest.TestCase):
    def test_creates_parent_directory_for_configured_database(self):
        with tempfile.TemporaryDirectory() as d:
            path = f"{d}/nested/mission-data/missions.sqlite3"
            store = MissionStore(path)
            self.assertTrue(store.db.execute("select 1").fetchone())
            self.assertTrue(Path(path).exists())
            store.close()

    def test_restart_and_liquidity_resume(self):
        with tempfile.TemporaryDirectory() as d:
            store = MissionStore(d + "/missions.sqlite3")
            store.save(Mission("m1", "0x"+"1"*40, MissionState.APPROVED, "0xmarket", {}, {}))
            self.assertEqual(reconcile_mission(store, "m1", 0).state, MissionState.WAITING_FOR_LIQUIDITY)
            self.assertEqual(reconcile_mission(store, "m1", 100).state, MissionState.BORROW_READY)
            store.close()

if __name__ == "__main__": unittest.main()
