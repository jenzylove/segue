"""Regression coverage for the continuation audit; all RPC/provider data are mocks."""
import contextlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import m2_condition_probe as probe
import m2_firm_quote as firm
import m2_preflight as preflight
import m2_snapshot as snap

ADDRESS = "0x" + "11" * 20


def encoded(values):
    return "0x" + "".join(f"{v:064x}" for v in values)


class AuditTests(unittest.TestCase):
    def test_only_native_b20_may_have_no_bytecode(self):
        with patch.object(preflight, "rpc", return_value="0x"):
            with self.assertRaisesRegex(RuntimeError, "no EVM bytecode"):
                preflight.check_code("execution target", ADDRESS)
            preflight.check_code("B20", ADDRESS, allow_native_b20=True)

    def test_preflight_rejects_incomplete_round(self):
        with patch.object(preflight, "eth_call", side_effect=[encoded([8]), encoded([9, 100, 1, 1, 8])]):
            with self.assertRaisesRegex(RuntimeError, "incomplete"):
                preflight.check_feed("equity", ADDRESS, 21600)

    def test_preflight_rejects_zero_normalized_price(self):
        with patch.object(preflight, "eth_call", side_effect=[encoded([18]), encoded([9, 1, 1, 1, 9])]):
            with self.assertRaisesRegex(RuntimeError, "zero price"):
                preflight.check_feed("equity", ADDRESS, 21600)

    def test_snapshot_helpers_pin_every_call_to_block(self):
        art = {"methodIdentifiers": {"owner()": "8da5cb5b"}}
        with patch.object(snap, "rpc", return_value=encoded([17])) as rpc:
            snap.read_address(ADDRESS, "owner()", art, "0x123")
            snap.balance_of(ADDRESS, ADDRESS, "0x123")
        self.assertEqual(len(rpc.call_args_list), 2)
        for call in rpc.call_args_list:
            self.assertEqual(call.args[1][-1], "0x123")

    def test_stale_decode_requires_exact_error_and_equity_token(self):
        data = probe.STALE_PRICE_SELECTOR + encoded([int(ADDRESS, 16), 123])[2:]
        self.assertEqual(probe.decode_stale(data, ADDRESS)["updatedAt"], 123)
        for bad in (None, "0x", "0x00000000" + data[10:], data + "00"):
            with self.assertRaises(RuntimeError):
                probe.decode_stale(bad, ADDRESS)
        with self.assertRaisesRegex(RuntimeError, "token"):
            probe.decode_stale(data, "0x" + "22" * 20)

    def test_condition_evidence_pins_block_and_preserves_false_and_stale(self):
        env = {"BASE_RPC_URL": "https://example.invalid", "DEMO_VAULT_ADDRESS": ADDRESS,
               "B20_TOKEN_ADDRESS": ADDRESS}
        stale = probe.STALE_PRICE_SELECTOR + encoded([int(ADDRESS, 16), 123])[2:]
        cwd = Path.cwd()
        with tempfile.TemporaryDirectory() as tmp:
            try:
                os.chdir(tmp)
                with patch.dict(os.environ, env, clear=True), patch.object(probe, "load_dotenv"), \
                     patch.object(probe, "preview_selector", return_value="0x12345678"), \
                     contextlib.redirect_stdout(io.StringIO()):
                    for expect, result in (("false", encoded([0, 5, 100, 0, 0])), ("stale", probe.RpcRevert(stale))):
                        with patch.object(probe, "rpc", side_effect=["0x2105", "0x123", result]) as rpc:
                            self.assertEqual(probe.main(["--policy-id", "2", "--expect", expect]), 0)
                            self.assertEqual(rpc.call_args_list[-1].args[1][-1], "0x123")
                        evidence = json.loads(Path(f".local/m2-condition-2-{expect}.json").read_text())
                        self.assertEqual(evidence["blockNumber"], 0x123)
                    self.assertTrue(Path(".local/m2-condition-2-false.json").exists())
            finally:
                os.chdir(cwd)

    def test_firm_quote_wrong_chain_never_calls_provider(self):
        env = {name: ADDRESS for name in ("EXECUTOR_ADDRESS", "USDC_ADDRESS", "B20_TOKEN_ADDRESS",
                                         "DEMO_VAULT_ADDRESS", "EXECUTION_TARGET_ADDRESS")}
        env.update(BASE_RPC_URL="https://example.invalid", ONEINCH_API_KEY="test-only")
        with patch.dict(os.environ, env, clear=True), patch.object(firm, "load_dotenv"), \
             patch.object(firm, "rpc", return_value="0x1"), patch.object(firm, "oneinch_get") as provider:
            with self.assertRaisesRegex(RuntimeError, "wrong chain"):
                firm.main(["--direction", "buy"])
            provider.assert_not_called()

    def test_firm_quote_rejects_nonhex_and_odd_calldata(self):
        for data in ("0x1234567z", "0x123456789"):
            payload = {"srcToken": {"address": ADDRESS}, "dstToken": {"address": ADDRESS},
                       "dstAmount": "1", "tx": {"from": ADDRESS, "to": ADDRESS, "data": data, "value": "0"}}
            with self.assertRaisesRegex(RuntimeError, "tx.data"):
                firm.validate_swap_payload(payload, sell_token=ADDRESS, buy_token=ADDRESS,
                                           vault=ADDRESS, execution_target=ADDRESS)
