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

## Verified Morpho Blue Base deployment

The active credit rail is Morpho Blue. The official deployment registry is
https://docs.morpho.org/developers/contracts/addresses/.

```text
Morpho Blue:    0xBBBBBbbBBb9cC5e90e3b3Af64bdAF62C37EEFFCb
AdaptiveCurveIRM: 0x46415998764C29aB2a25CbeA6254146D50D22687
Locked market:  0x91360eea2686ef7ce4966b4e82cf6ff712af02baf0f7211459780d9f5af1612a
```

The backend verifies Morpho bytecode, enabled IRM, direct `idToMarketParams`,
the selected oracle `price()` and the Morpho API oracle state on every live
qualification. Keep `BASE_RPC_URL` private and local.

## Read-only preflight

Run from the repository root:

```powershell
python scripts\equityline_morpho_preflight.py
```

The script loads `.env`, queries Morpho Blue's public market index, locks the
selected market, verifies its Base bytecode and MarketParams, compares the live
oracle state with direct `price()`, and prints only public market facts.

Passing preflight is not transaction evidence. It only means Segue can attempt
the next phase: user-approved supply/borrow/repay command preparation.

## Unsigned transaction planning

`backend/segue_api/morpho_plans.py` prepares unsigned transaction objects for:

- exact NVDAc collateral approval to Morpho Blue;
- Morpho `supplyCollateral` and `borrow`;
- exact USDC repayment approval;
- Morpho `repay` by fresh shares for full close;
- Morpho `withdrawCollateral` after borrow shares reach zero.

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
(`https://api.morpho.org/v1/blue/markets`, chain 8453) for canonical NVDAc and
then qualifies the locked market. The health check follows Morpho Blue's
onchain rule: `maxBorrow = collateral * oraclePrice / 1e36 * LLTV` and a
position is healthy when `maxBorrow >= borrowed`. No borrowing or signing is
performed.

The old Aave preflight and planner remain only as historical compatibility code;
they are not imported by the active proposal, mission or transaction routes.
