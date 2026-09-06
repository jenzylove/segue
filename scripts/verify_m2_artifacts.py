from __future__ import annotations

import json
from pathlib import Path

ARTIFACT = Path("out/StockPolicyVault.sol/StockPolicyVault.json")
REQUIRED = {
    "previewExecution(uint256)",
    "policies(uint256)",
    "getStep(uint256,uint8)",
    "owner()",
    "executor()",
    "activePolicyId()",
    "vaultMaxDeployedUSDC()",
    "vaultDeployedUSDC()",
}


def main() -> None:
    if not ARTIFACT.exists():
        raise SystemExit("StockPolicyVault Foundry artifact is missing")
    payload = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    identifiers = payload.get("methodIdentifiers") or {}
    missing = sorted(REQUIRED - identifiers.keys())
    if missing:
        raise SystemExit("M2 artifact method identifiers missing: " + ", ".join(missing))
    for signature in sorted(REQUIRED):
        selector = identifiers[signature]
        if len(selector) != 8:
            raise SystemExit(f"invalid selector for {signature}: {selector}")
    print("M2 Foundry artifact selectors OK")


if __name__ == "__main__":
    main()
