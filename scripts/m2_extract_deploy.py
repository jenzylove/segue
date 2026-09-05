#!/usr/bin/env python3
"""Extract Segue M2 deployment addresses from Foundry's broadcast artifact."""

from __future__ import annotations

import json
import sys
from pathlib import Path

DEFAULT = Path("broadcast/DeployMainnet.s.sol/8453/run-latest.json")


def main() -> int:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT
    if not path.exists():
        print(f"deployment artifact not found: {path}", file=sys.stderr)
        return 2

    payload = json.loads(path.read_text(encoding="utf-8"))
    found: dict[str, str] = {}
    for tx in payload.get("transactions", []):
        name = tx.get("contractName")
        address = tx.get("contractAddress")
        if name in {"AssetRegistry", "StockPolicyVaultFactory"} and address:
            found[name] = address

    missing = {"AssetRegistry", "StockPolicyVaultFactory"} - found.keys()
    if missing:
        print("missing deployment addresses: " + ", ".join(sorted(missing)), file=sys.stderr)
        return 1

    print(f"ASSET_REGISTRY_ADDRESS={found['AssetRegistry']}")
    print(f"FACTORY_ADDRESS={found['StockPolicyVaultFactory']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
