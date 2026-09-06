from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import m2_snapshot as snap  # noqa: E402


def encoded(values: list[int]) -> str:
    return "0x" + "".join(value.to_bytes(32, "big").hex() for value in values)


class SnapshotDecodeTest(unittest.TestCase):
    def test_policy_decode(self) -> None:
        policy = snap.decode_policy(encoded([1, 100, 1, 2, 1_000_000, 950_000]))
        self.assertEqual(policy["statusLabel"], "LIVE")
        self.assertEqual(policy["currentStep"], 1)
        self.assertEqual(policy["stepCount"], 2)
        self.assertEqual(policy["deployedUSDC"], 950_000)

    def test_step_decode(self) -> None:
        a = int("11" * 20, 16)
        b = int("22" * 20, 16)
        c = int("33" * 20, 16)
        step = snap.decode_step(encoded([2, a, 0, 100, 0, 99, b, c, 0, 1_000_000, 500, 12345]))
        self.assertEqual(step["statusLabel"], "ACTIVE")
        self.assertEqual(step["conditionAsset"].lower(), "0x" + "11" * 20)
        self.assertEqual(step["sellToken"].lower(), "0x" + "22" * 20)
        self.assertEqual(step["buyToken"].lower(), "0x" + "33" * 20)
        self.assertEqual(step["amount"], 1_000_000)

    def test_short_policy_return_rejected(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "short eth_call return"):
            snap.decode_policy("0x00")


if __name__ == "__main__":
    unittest.main()
