import unittest
from backend.segue_api.morpho_plans import borrower_action_plan, lender_supply_plan

class MorphoPlanTests(unittest.TestCase):
    def test_actions_are_unsigned_and_pinned(self):
        p = borrower_action_plan('0x'+'1'*40, '0x'+'2'*64, 'borrow')
        self.assertEqual(p['chain_id'], 8453); self.assertEqual(p['value'], '0'); self.assertIn('wallet signature required', p['preconditions'])
    def test_lender_amount_positive(self):
        with self.assertRaises(ValueError): lender_supply_plan('0x'+'1'*40, '0x'+'2'*40, '0x'+'3'*64, 0)

if __name__ == '__main__': unittest.main()
