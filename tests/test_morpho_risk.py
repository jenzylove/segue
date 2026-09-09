import unittest
from decimal import Decimal
from backend.segue_api.morpho_risk import proposal

class RiskTests(unittest.TestCase):
    def test_zero_liquidity_is_waiting(self):
        out=proposal({'lltv_wad':'770000000000000000','_available':0},100*10**8,8,Decimal('100'),6,10000000)
        self.assertEqual(out['state'],'WAITING_FOR_LIQUIDITY'); self.assertEqual(out['available_executable_borrow_atomic'],0)
    def test_safe_limit(self):
        out=proposal({'lltv_wad':'770000000000000000','_available':10**12},10**8,8,Decimal('100'),6,10**9)
        self.assertLessEqual(out['safe_max_debt_atomic'],out['protocol_max_debt_atomic'])
