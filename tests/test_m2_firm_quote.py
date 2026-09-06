from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import m2_firm_quote as firm  # noqa: E402


VAULT = "0x1111111111111111111111111111111111111111"
TARGET = "0x2222222222222222222222222222222222222222"
USDC = "0x3333333333333333333333333333333333333333"
B20 = "0x4444444444444444444444444444444444444444"


def good_swap() -> dict:
    return {
        "srcToken": {"address": USDC},
        "dstToken": {"address": B20},
        "dstAmount": "12345",
        "tx": {"from": VAULT, "to": TARGET, "data": "0x12345678abcdef", "value": "0"},
    }


class FirmQuoteValidationTest(unittest.TestCase):
    def test_accepts_bounded_erc20_swap(self) -> None:
        amount, calldata = firm.validate_swap_payload(
            good_swap(), sell_token=USDC, buy_token=B20, vault=VAULT, execution_target=TARGET
        )
        self.assertEqual(amount, 12345)
        self.assertEqual(calldata, "0x12345678abcdef")

    def test_rejects_wrong_execution_target(self) -> None:
        payload = good_swap()
        payload["tx"]["to"] = "0x5555555555555555555555555555555555555555"
        with self.assertRaisesRegex(RuntimeError, "tx.to mismatch"):
            firm.validate_swap_payload(payload, sell_token=USDC, buy_token=B20, vault=VAULT, execution_target=TARGET)

    def test_rejects_wrong_vault_from(self) -> None:
        payload = good_swap()
        payload["tx"]["from"] = "0x5555555555555555555555555555555555555555"
        with self.assertRaisesRegex(RuntimeError, "tx.from mismatch"):
            firm.validate_swap_payload(payload, sell_token=USDC, buy_token=B20, vault=VAULT, execution_target=TARGET)

    def test_rejects_native_value_for_erc20_route(self) -> None:
        payload = good_swap()
        payload["tx"]["value"] = "0x1"
        with self.assertRaisesRegex(RuntimeError, "native value"):
            firm.validate_swap_payload(payload, sell_token=USDC, buy_token=B20, vault=VAULT, execution_target=TARGET)

    def test_rejects_wrong_token_pair(self) -> None:
        payload = good_swap()
        payload["dstToken"]["address"] = USDC
        with self.assertRaisesRegex(RuntimeError, "dst token mismatch"):
            firm.validate_swap_payload(payload, sell_token=USDC, buy_token=B20, vault=VAULT, execution_target=TARGET)

    def test_sell_defaults_to_actual_vault_b20_balance(self) -> None:
        env = {"USDC_ADDRESS": USDC, "B20_TOKEN_ADDRESS": B20, "DEMO_VAULT_ADDRESS": VAULT}
        with patch.dict(os.environ, env, clear=False), patch.object(firm, "balance_of", return_value=777) as read:
            os.environ.pop("M2_SELL_B20_ATOMIC", None)
            sell, buy, amount = firm.resolve_trade("sell")
        self.assertEqual((sell, buy, amount), (B20, USDC, "777"))
        read.assert_called_once_with(B20, VAULT)

    def test_explicit_sell_amount_does_not_read_balance(self) -> None:
        env = {
            "USDC_ADDRESS": USDC,
            "B20_TOKEN_ADDRESS": B20,
            "DEMO_VAULT_ADDRESS": VAULT,
            "M2_SELL_B20_ATOMIC": "321",
        }
        with patch.dict(os.environ, env, clear=False), patch.object(firm, "balance_of") as read:
            sell, buy, amount = firm.resolve_trade("sell")
        self.assertEqual((sell, buy, amount), (B20, USDC, "321"))
        read.assert_not_called()


if __name__ == "__main__":
    unittest.main()
