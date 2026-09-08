from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import dataclass
from typing import Any

from .models import is_address


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

