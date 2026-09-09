import tempfile, unittest
from backend.segue_api.mission import Mission, MissionState, MissionStore
from backend.segue_api.worker import reconcile_mission

class MissionTests(unittest.TestCase):
    def test_restart_and_liquidity_resume(self):
        with tempfile.TemporaryDirectory() as d:
            store = MissionStore(d + "/missions.sqlite3")
            store.save(Mission("m1", "0x"+"1"*40, MissionState.APPROVED, "0xmarket", {}, {}))
            self.assertEqual(reconcile_mission(store, "m1", 0).state, MissionState.WAITING_FOR_LIQUIDITY)
            self.assertEqual(reconcile_mission(store, "m1", 100).state, MissionState.BORROW_READY)

if __name__ == "__main__": unittest.main()
