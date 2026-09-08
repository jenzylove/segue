from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from decimal import Decimal

from backend.segue_api.aave import (
    AaveConfigError,
    AaveDeployment,
    aave_price_to_decimal,
    decode_reserve_config,
    decode_reserve_data,
    deployment_from_env,
    ray_to_bps,
    read_aave_market,
    selector_with_address,
)
from backend.segue_api.models import TokenRef
from scripts.equityline_aave_preflight import load_env_file


class AaveConfigTests(unittest.TestCase):
    def test_requires_verified_addresses_and_source(self) -> None:
        with self.assertRaises(AaveConfigError):
            deployment_from_env({"BASE_CHAIN_ID": "8453"})

    def test_accepts_base_deployment_from_env(self) -> None:
        deployment = deployment_from_env(
            {
                "BASE_CHAIN_ID": "8453",
                "AAVE_POOL_ADDRESSES_PROVIDER": "0x1111111111111111111111111111111111111111",
                "AAVE_POOL_ADDRESS": "0x2222222222222222222222222222222222222222",
                "AAVE_PROTOCOL_DATA_PROVIDER": "0x3333333333333333333333333333333333333333",
                "AAVE_DEPLOYMENT_SOURCE": "official Aave deployment docs",
            }
        )

        self.assertEqual(deployment.chain_id, 8453)

    def test_rejects_non_base_chain(self) -> None:
        with self.assertRaises(AaveConfigError):
            deployment_from_env(
                {
                    "BASE_CHAIN_ID": "1",
                    "AAVE_POOL_ADDRESSES_PROVIDER": "0x1111111111111111111111111111111111111111",
                    "AAVE_POOL_ADDRESS": "0x2222222222222222222222222222222222222222",
                    "AAVE_PROTOCOL_DATA_PROVIDER": "0x3333333333333333333333333333333333333333",
                    "AAVE_DEPLOYMENT_SOURCE": "official Aave deployment docs",
                }
            )

    def test_preflight_loads_dotenv_without_overwriting_process_env(self) -> None:
        env_file = Path(self.id().replace(".", "_") + ".env")
        try:
            env_file.write_text("AAVE_POOL_ADDRESS=0x2222222222222222222222222222222222222222\n"
                                "AAVE_DEPLOYMENT_SOURCE='official source'\n")
            with patch.dict("os.environ", {"AAVE_POOL_ADDRESS": "already-set"}, clear=True):
                load_env_file(env_file)
                import os

                self.assertEqual(os.environ["AAVE_POOL_ADDRESS"], "already-set")
                self.assertEqual(os.environ["AAVE_DEPLOYMENT_SOURCE"], "official source")
        finally:
            env_file.unlink(missing_ok=True)

    def test_decodes_aave_reserve_config_and_rates(self) -> None:
        data = encoded_words([18, 5000, 6500, 10500, 1000, 1, 1, 0, 1, 0, 0])
        config = decode_reserve_config(data)

        self.assertEqual(config["ltv_bps"], 5000)
        self.assertEqual(config["liquidation_threshold_bps"], 6500)
        self.assertTrue(config["usage_as_collateral_enabled"])
        self.assertTrue(config["borrowing_enabled"])
        self.assertFalse(config["is_paused"])

        reserve = decode_reserve_data(encoded_words([0, 0, 1, 2, 3, 4, 35 * 10**24, 0, 0, 0, 0, 123]))
        self.assertEqual(ray_to_bps(reserve["variable_borrow_rate"]), 350)
        self.assertEqual(aave_price_to_decimal(100_000_000, 100_000_000), Decimal("1"))

    def test_read_aave_market_builds_from_live_call_shapes(self) -> None:
        deployment = AaveDeployment(
            chain_id=8453,
            pool_addresses_provider="0x1111111111111111111111111111111111111111",
            pool="0x2222222222222222222222222222222222222222",
            protocol_data_provider="0x3333333333333333333333333333333333333333",
            source="official source",
        )
        collateral = TokenRef("NVDAc", "0xb20000000000000000000078ee7ce2fE4908108C", 18, "official")
        debt = TokenRef("USDC", "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913", 6, "official")
        oracle = "0x4444444444444444444444444444444444444444"
        a_token = "0x5555555555555555555555555555555555555555"
        calls = [
            encoded_address(oracle),
            encoded_words([18, 5000, 6500, 10500, 1000, 1, 0, 0, 1, 0, 0]),
            encoded_words([6, 8000, 8500, 10500, 1000, 0, 1, 0, 1, 0, 0]),
            encoded_words([0, 0, 0, 0, 0, 0, 42 * 10**24, 0, 0, 0, 0, 123]),
            encoded_words([int(a_token, 16), int("0x6666666666666666666666666666666666666666", 16),
                           int("0x7777777777777777777777777777777777777777", 16)]),
            encoded_words([100_000_000]),
            encoded_words([12_500_000_000]),
            encoded_words([100_000_000]),
            encoded_words([25_000_000]),
        ]

        def fake_rpc(_url: str, method: str, params: list[object]) -> str:
            self.assertIn(method, ("eth_call", "eth_getCode"))
            if method == "eth_getCode":
                return "0x6000"
            return calls.pop(0)

        with patch("backend.segue_api.aave.rpc_call", side_effect=fake_rpc):
            market = read_aave_market("https://example.invalid", deployment, collateral, debt)

        self.assertEqual(market.ltv_bps, 5000)
        self.assertEqual(market.borrow_apr_bps, 420)
        self.assertEqual(market.available_liquidity_atomic, 25_000_000)
        self.assertEqual(market.collateral_price_usd, Decimal("125"))
        self.assertTrue(market.is_usable)
        self.assertEqual(calls, [])


def encoded_words(values: list[int]) -> str:
    return "0x" + "".join(f"{value:064x}" for value in values)


def encoded_address(address: str) -> str:
    return encoded_words([int(address, 16)])


if __name__ == "__main__":
    unittest.main()
