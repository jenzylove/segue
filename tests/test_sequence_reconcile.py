from __future__ import annotations

import unittest
from unittest.mock import patch

from backend.segue_api.sequence_chain import (
    POLICY_CREATED_TOPIC,
    STEP_ACTIVATED_TOPIC,
    STEP_EXECUTED_TOPIC,
    reconcile_sequence_receipt,
)


VAULT = "0x4444444444444444444444444444444444444444"
TX = "0x" + "a" * 64


def topic(value: int) -> str:
    return "0x" + f"{value:064x}"


class SequenceReceiptTests(unittest.TestCase):
    def test_pending_receipt_does_not_advance(self) -> None:
        with patch("backend.segue_api.sequence_chain.rpc_call", return_value=None):
            result = reconcile_sequence_receipt("rpc", {"vault_address": VAULT}, TX)
        self.assertEqual(result["status"], "PENDING")
        self.assertEqual(result["events"], [])

    def test_policy_execution_and_next_reference_are_decoded(self) -> None:
        receipt = {
            "status": "0x1",
            "logs": [
                {"address": VAULT, "topics": [POLICY_CREATED_TOPIC, topic(7)], "data": "0x" + topic(2)[2:] + topic(1_000_000)[2:]},
                {"address": VAULT, "topics": [STEP_EXECUTED_TOPIC, topic(7), topic(0)], "data": "0x" + topic(1_000_000)[2:] + topic(123)[2:] + topic(100)[2:]},
                {"address": VAULT, "topics": [STEP_ACTIVATED_TOPIC, topic(7), topic(1)], "data": "0x" + topic(223_000_000)[2:]},
            ],
        }
        with patch("backend.segue_api.sequence_chain.rpc_call", return_value=receipt):
            result = reconcile_sequence_receipt("rpc", {"vault_address": VAULT}, TX)
        self.assertEqual(result["status"], "CONFIRMED")
        self.assertEqual([event["kind"] for event in result["events"]], ["POLICY_CREATED", "STEP_EXECUTED", "STEP_ACTIVATED"])
        self.assertEqual(result["events"][-1]["reference_price"], 223_000_000)


if __name__ == "__main__":
    unittest.main()
