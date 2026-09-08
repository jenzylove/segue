from __future__ import annotations

import unittest

from backend.segue_api.aave import AaveConfigError, deployment_from_env


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


if __name__ == "__main__":
    unittest.main()

