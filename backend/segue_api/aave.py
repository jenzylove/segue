from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from .models import AaveMarket, TokenRef, is_address


BASE_CHAIN_ID = 8453


class AaveConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class AaveDeployment:
    chain_id: int
    pool_addresses_provider: str
    pool: str
    protocol_data_provider: str
    source: str

    def validate(self) -> None:
        if self.chain_id != BASE_CHAIN_ID:
            raise AaveConfigError("Segue credit backend is locked to Base mainnet")
        for name, value in (
            ("AAVE_POOL_ADDRESSES_PROVIDER", self.pool_addresses_provider),
            ("AAVE_POOL_ADDRESS", self.pool),
            ("AAVE_PROTOCOL_DATA_PROVIDER", self.protocol_data_provider),
        ):
            if not is_address(value):
                raise AaveConfigError(f"{name} must be a verified nonzero Base address")
        if not self.source:
            raise AaveConfigError("Aave deployment provenance source is required")


def deployment_from_env(env: dict[str, str] | None = None) -> AaveDeployment:
    values = env if env is not None else os.environ
    deployment = AaveDeployment(
        chain_id=int(values.get("BASE_CHAIN_ID", "8453")),
        pool_addresses_provider=values.get("AAVE_POOL_ADDRESSES_PROVIDER", ""),
        pool=values.get("AAVE_POOL_ADDRESS", ""),
        protocol_data_provider=values.get("AAVE_PROTOCOL_DATA_PROVIDER", ""),
        source=values.get("AAVE_DEPLOYMENT_SOURCE", ""),
    )
    deployment.validate()
    return deployment


def rpc_call(rpc_url: str, method: str, params: list[Any]) -> Any:
    if not rpc_url:
        raise AaveConfigError("BASE_RPC_URL is required for live Aave reads")
    payload = json.dumps(
        {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    ).encode("utf-8")
    request = urllib.request.Request(
        rpc_url,
        data=payload,
        headers={"content-type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        data = json.loads(response.read().decode("utf-8"))
    if "error" in data:
        raise AaveConfigError(f"RPC error: {data['error']}")
    return data["result"]


def verify_base_chain(rpc_url: str) -> None:
    chain_id_hex = rpc_call(rpc_url, "eth_chainId", [])
    if int(chain_id_hex, 16) != BASE_CHAIN_ID:
        raise AaveConfigError("RPC endpoint is not Base mainnet")


def require_contract_code(rpc_url: str, address: str, label: str) -> None:
    if not is_address(address):
        raise AaveConfigError(f"{label} is not a valid EVM address")
    code = rpc_call(rpc_url, "eth_getCode", [address, "latest"])
    if code in ("0x", "0x0", None):
        raise AaveConfigError(f"{label} has no bytecode on Base")


def read_aave_market(
    rpc_url: str,
    deployment: AaveDeployment,
    collateral: TokenRef,
    debt_asset: TokenRef,
) -> AaveMarket:
    deployment.validate()
    collateral.validate()
    debt_asset.validate()
    oracle = decode_address(eth_call(rpc_url, deployment.pool_addresses_provider, "0xfca513a8"))
    require_contract_code(rpc_url, oracle, "Aave Oracle")

    collateral_config = decode_reserve_config(
        eth_call(
            rpc_url,
            deployment.protocol_data_provider,
            selector_with_address("0x3e150141", collateral.address),
        )
    )
    debt_config = decode_reserve_config(
        eth_call(
            rpc_url,
            deployment.protocol_data_provider,
            selector_with_address("0x3e150141", debt_asset.address),
        )
    )
    debt_reserve = decode_reserve_data(
        eth_call(
            rpc_url,
            deployment.protocol_data_provider,
            selector_with_address("0x35ea6a75", debt_asset.address),
        )
    )
    debt_tokens = decode_three_addresses(
        eth_call(
            rpc_url,
            deployment.protocol_data_provider,
            selector_with_address("0xd2493b6c", debt_asset.address),
        )
    )
    unit = decode_uint(eth_call(rpc_url, oracle, "0x8c89b64f"))
    if unit <= 0:
        raise AaveConfigError("Aave oracle base currency unit is invalid")
    collateral_price = aave_price_to_decimal(
        decode_uint(eth_call(rpc_url, oracle, selector_with_address("0xb3596f07", collateral.address))),
        unit,
    )
    debt_price = aave_price_to_decimal(
        decode_uint(eth_call(rpc_url, oracle, selector_with_address("0xb3596f07", debt_asset.address))),
        unit,
    )
    available_liquidity = decode_uint(
        eth_call(rpc_url, debt_asset.address, selector_with_address("0x70a08231", debt_tokens[0]))
    )

    return AaveMarket(
        collateral=collateral,
        debt_asset=debt_asset,
        pool=deployment.pool,
        protocol_data_provider=deployment.protocol_data_provider,
        ltv_bps=collateral_config["ltv_bps"],
        liquidation_threshold_bps=collateral_config["liquidation_threshold_bps"],
        liquidation_bonus_bps=collateral_config["liquidation_bonus_bps"],
        borrow_apr_bps=ray_to_bps(debt_reserve["variable_borrow_rate"]),
        available_liquidity_atomic=available_liquidity,
        collateral_price_usd=collateral_price,
        debt_price_usd=debt_price,
        active=collateral_config["is_active"] and debt_config["is_active"],
        frozen=collateral_config["is_frozen"] or debt_config["is_frozen"],
        paused=collateral_config["is_paused"] or debt_config["is_paused"],
        borrowing_enabled=debt_config["borrowing_enabled"],
        collateral_enabled=collateral_config["usage_as_collateral_enabled"],
        provenance={
            "deployment": deployment.source,
            "oracle": oracle,
            "debt_a_token": debt_tokens[0],
        },
    )


def eth_call(rpc_url: str, to: str, data: str) -> str:
    return rpc_call(rpc_url, "eth_call", [{"to": to, "data": data}, "latest"])


def selector_with_address(selector: str, address: str) -> str:
    if not is_address(address):
        raise AaveConfigError("cannot encode invalid address")
    return selector + address.lower().removeprefix("0x").rjust(64, "0")


def decode_words(data: str, min_words: int) -> list[int]:
    if not isinstance(data, str) or not data.startswith("0x"):
        raise AaveConfigError("RPC call returned malformed data")
    body = data[2:]
    if len(body) < min_words * 64 or len(body) % 64 != 0:
        raise AaveConfigError("RPC call returned short or misaligned data")
    return [int(body[index:index + 64], 16) for index in range(0, len(body), 64)]


def decode_uint(data: str) -> int:
    return decode_words(data, 1)[0]


def decode_address(data: str) -> str:
    value = decode_uint(data)
    address = "0x" + f"{value:040x}"[-40:]
    if not is_address(address):
        raise AaveConfigError("RPC call returned invalid address")
    return address


def decode_three_addresses(data: str) -> tuple[str, str, str]:
    words = decode_words(data, 3)
    decoded = tuple("0x" + f"{value:040x}"[-40:] for value in words[:3])
    for address in decoded:
        if not is_address(address):
            raise AaveConfigError("Aave reserve token address is invalid")
    return decoded


def decode_reserve_config(data: str) -> dict[str, Any]:
    words = decode_words(data, 10)
    return {
        "decimals": words[0],
        "ltv_bps": words[1],
        "liquidation_threshold_bps": words[2],
        "liquidation_bonus_bps": words[3],
        "reserve_factor_bps": words[4],
        "usage_as_collateral_enabled": words[5] != 0,
        "borrowing_enabled": words[6] != 0,
        "stable_borrow_rate_enabled": words[7] != 0,
        "is_active": words[8] != 0,
        "is_frozen": words[9] != 0,
        "is_paused": len(words) > 10 and words[10] != 0,
    }


def decode_reserve_data(data: str) -> dict[str, int]:
    words = decode_words(data, 12)
    return {
        "unbacked": words[0],
        "accrued_to_treasury_scaled": words[1],
        "total_a_token": words[2],
        "total_stable_debt": words[3],
        "total_variable_debt": words[4],
        "liquidity_rate": words[5],
        "variable_borrow_rate": words[6],
        "stable_borrow_rate": words[7],
        "average_stable_borrow_rate": words[8],
        "liquidity_index": words[9],
        "variable_borrow_index": words[10],
        "last_update_timestamp": words[11],
    }


def aave_price_to_decimal(price: int, unit: int) -> Decimal:
    if price <= 0:
        raise AaveConfigError("Aave oracle returned a nonpositive price")
    return Decimal(price) / Decimal(unit)


def ray_to_bps(rate_ray: int) -> int:
    return rate_ray * 10_000 // 10**27
