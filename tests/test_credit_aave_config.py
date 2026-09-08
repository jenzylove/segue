from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from backend.segue_api.aave import AaveConfigError, deployment_from_env
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


if __name__ == "__main__":
    unittest.main()
