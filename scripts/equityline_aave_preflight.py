from __future__ import annotations

import os
import sys

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.segue_api.aave import (  # noqa: E402
    AaveConfigError,
    deployment_from_env,
    read_aave_market,
    require_contract_code,
    verify_base_chain,
)
from backend.segue_api.models import TokenRef  # noqa: E402


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def main() -> int:
    load_env_file(ROOT / ".env")
    try:
        deployment = deployment_from_env()
        rpc_url = os.environ.get("BASE_RPC_URL", "")
        verify_base_chain(rpc_url)
        require_contract_code(rpc_url, deployment.pool_addresses_provider, "Aave PoolAddressesProvider")
        require_contract_code(rpc_url, deployment.pool, "Aave Pool")
        require_contract_code(rpc_url, deployment.protocol_data_provider, "Aave ProtocolDataProvider")
        market = read_aave_market(
            rpc_url,
            deployment,
            TokenRef(
                symbol=os.environ.get("B20_SYMBOL", "NVDAc"),
                address=os.environ.get("B20_TOKEN_ADDRESS", ""),
                decimals=int(os.environ.get("B20_TOKEN_DECIMALS", "18")),
                source=os.environ.get("B20_TOKEN_SOURCE", "Base/Coinbase B20 configured token"),
            ),
            TokenRef(
                symbol="USDC",
                address=os.environ.get("USDC_ADDRESS", ""),
                decimals=int(os.environ.get("USDC_DECIMALS", "6")),
                source=os.environ.get("USDC_TOKEN_SOURCE", "Base USDC configured token"),
            ),
        )
        if not market.is_usable:
            raise AaveConfigError("Aave market exists but is not usable under Segue credit policy inputs")
    except AaveConfigError as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 2

    print("AAVE_PREFLIGHT_OK")
    print(f"chain_id={deployment.chain_id}")
    print(f"pool_addresses_provider={deployment.pool_addresses_provider}")
    print(f"pool={deployment.pool}")
    print(f"protocol_data_provider={deployment.protocol_data_provider}")
    print(f"source={deployment.source}")
    print(f"collateral={market.collateral.symbol}:{market.collateral.address}")
    print(f"debt_asset={market.debt_asset.symbol}:{market.debt_asset.address}")
    print(f"ltv_bps={market.ltv_bps}")
    print(f"liquidation_threshold_bps={market.liquidation_threshold_bps}")
    print(f"variable_borrow_apr_bps={market.borrow_apr_bps}")
    print(f"available_debt_liquidity_atomic={market.available_liquidity_atomic}")
    print(f"collateral_price_usd={market.collateral_price_usd}")
    print(f"debt_price_usd={market.debt_price_usd}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
