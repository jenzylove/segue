from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import m2_condition_probe as probe  # noqa: E402


def encoded(words: list[int]) -> str:
    return "0x" + "".join(value.to_bytes(32, "big").hex() for value in words)


class ConditionProbeDecodeTest(unittest.TestCase):
    def test_decodes_ready_preview(self) -> None:
        result = probe.decode_preview(encoded([1, 0, 22_995_730_000, 1_000_000, 4348]))
        self.assertTrue(result["executable"])
        self.assertEqual(result["reasonLabel"], "READY")
        self.assertEqual(result["sellAmount"], 1_000_000)

    def test_decodes_false_condition_preview(self) -> None:
        result = probe.decode_preview(encoded([0, 5, 22_995_730_000, 0, 0]))
        self.assertFalse(result["executable"])
        self.assertEqual(result["reasonLabel"], "CONDITION_FALSE")

    def test_rejects_short_return_data(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "short data"):
            probe.decode_preview("0x00")


if __name__ == "__main__":
    unittest.main()
