# Segue Credit Backend Runbook

This milestone adds the B20-backed credit path to Segue while preserving the
existing bounded routing vault.

## Product path

```text
supported B20 collateral
  -> Morpho Blue Base market discovery
  -> safe borrow proposal
  -> user-approved supply/borrow
  -> monitored credit mission
  -> sequenced repay/de-risk action
```

The backend must never invent lending parameters, token addresses, prices, health
factors, liquidity or receipts. If a critical read is unavailable, return
`BLOCKED`.

## Official Aave Base deployment source

Use the official Aave address book:

https://github.com/aave-dao/aave-address-book/blob/main/src/AaveV3Base.sol

Current fields to place in local `.env`:

```dotenv
AAVE_POOL_ADDRESSES_PROVIDER=0xe20fCBdBfFC4Dd138cE8b2E6FBb6CB49777ad64D
AAVE_POOL_ADDRESS=0xA238Dd80C259a72e81d7e4664a9801593F98d1c5
AAVE_PROTOCOL_DATA_PROVIDER=0x0F43731EB8d45A581f4a36DD74F5f358bc90C73A
AAVE_DEPLOYMENT_SOURCE=https://github.com/aave-dao/aave-address-book/blob/main/src/AaveV3Base.sol
```

These values are public. Keep `BASE_RPC_URL` private and local.

## Read-only preflight

Run from the repository root:

```powershell
python scripts\equityline_aave_preflight.py
```

The script loads `.env`, verifies Base chain id, verifies the Aave deployment
contracts have bytecode, reads the Aave oracle, reads reserve configuration for
the configured B20 and USDC assets, checks debt liquidity, and prints only public
market facts.

Passing preflight is not transaction evidence. It only means Segue can attempt
the next phase: user-approved supply/borrow/repay command preparation.

## Unsigned transaction planning

`backend/segue_api/tx_plan.py` prepares unsigned transaction objects for:

- exact B20 collateral approval to the Aave Pool;
- Aave `supply`;
- Aave variable-rate USDC `borrow`;
- exact USDC repayment approval;
- Aave `repay`;
- Aave `withdraw`.

The planner first builds the deterministic credit proposal. If the market is
paused, frozen, not collateral-enabled, not borrow-enabled, too expensive under
policy, under-liquid, or below the user's minimum health factor, it refuses to
produce transactions.

The planner does not sign or broadcast. Its output is the human boundary.

## Human boundary

Stop before any command that needs:

- a private key;
- a wallet signature;
- token approvals;
- funding;
- a live borrow/repay transaction.

At that point, prepare the exact command and let the human builder run it locally.
## Morpho discovery preflight

`python scripts/equityline_morpho_preflight.py` queries Morpho's public REST API
(`https://api.morpho.org/v1/blue/markets`, chain 8453) for the configured
NVDAc/USDC pair. It prints `MORPHO_PREFLIGHT_OK` only when exactly one listed
market has verified market id, oracle, IRM, LLTV, nonzero borrow liquidity, and
current borrow rate. The health check follows Morpho Blue's onchain rule:
`maxBorrow = collateral * oraclePrice / 1e36 * LLTV` and a position is healthy
when `maxBorrow >= borrowed`. No borrowing or signing is performed.
