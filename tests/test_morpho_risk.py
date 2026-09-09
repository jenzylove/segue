import unittest
from decimal import Decimal
from backend.segue_api.morpho_risk import proposal

class RiskTests(unittest.TestCase):
    def test_zero_liquidity_is_waiting(self):
        out=proposal({'lltv_wad':'770000000000000000','_available':0},100*10**8,8,Decimal('1000000000000000000000000000000000000'),6,10000000)
        self.assertEqual(out['state'],'WAITING_FOR_LIQUIDITY'); self.assertEqual(out['available_executable_borrow_atomic'],0)
    def test_safe_limit(self):
        out=proposal({'lltv_wad':'770000000000000000','_available':10**12},10**8,8,Decimal('1000000000000000000000000000000000000'),6,10**9)
        self.assertLessEqual(out['safe_max_debt_atomic'],out['protocol_max_debt_atomic'])

    def test_live_wallet_atomic_oracle_vector(self):
        out=proposal({'lltv_wad':'770000000000000000','_available':98000000},2323053,8,Decimal('2247166507103088006823230806107758134'),6,1000000)
        self.assertEqual(out['collateral_value_usd'], '5.220286')
        self.assertEqual(out['protocol_max_debt_atomic'], 4019620)
        self.assertEqual(out['safe_max_debt_atomic'], 3215696)
        self.assertEqual(out['state'], 'PROPOSED')
