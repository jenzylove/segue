# Segue Architecture

`PRD.md` is authoritative. This file is a compact implementation map.

## Current product shape

Segue now combines the original sequenced-execution system with the EquityLine
credit thesis:

```text
Buy or hold Coinbase B20 stock
  -> use supported B20 as Aave collateral
  -> borrow bounded USDC
  -> monitor health, APR, reserve and oracle state
  -> execute sequenced repay/de-risk/routing actions under user policy
```

The original vault contracts remain useful for bounded stock routing and later
policy execution. The backend adds a credit mission layer that treats Aave
market state, user balances, health factor and receipts as evidence.

## Runtime

```text
Browser wallet
  └─ acquire/hold supported B20, approve bounded credit mission
        ↓
Segue API + policy engine
  - discovers supported B20 collateral
  - reads Aave Base market parameters
  - computes safe borrow envelope
  - records mission/evidence state
        ↓
Aave Pool on Base
  - supply B20 collateral
  - borrow/repay USDC
  - expose account health/liquidation state
        ↓
StockPolicyVaultFactory
        ↓
StockPolicyVault (per user)
  - holds user strategy funds
  - stores policy + active/queued/executed steps
  - reads verified Chainlink-backed prices through AssetRegistry
  - enforces supported assets, expiry, policy/vault caps and deviation
  - revalidates the condition at execution
  - gives the execution target only the exact sell allowance for the active rule
  - advances only after exact sell + minimum-output postconditions pass
        ↑
        │ executeStep(policyId, routing calldata)
        │
FastAPI automation worker
  - gas-only executor wallet
  - discovers/reconciles active credit missions and vault policies
  - asks onchain/protocol state whether an action is executable
  - submits bounded repay/de-risk/routing transactions
  - persists tx/provider/protocol evidence
        ├─ Base RPC
        ├─ Aave Pool/DataProvider
        ├─ 1inch Classic Swap API
        └─ PostgreSQL cache/index
```

## Credit backend

The backend has three policy components:

- Credit Agent: reads verified B20 holdings and Aave parameters, then computes
  the safe borrowing envelope under the user's max LTV, minimum health factor,
  reserve and borrow-APR policy.
- Treasury Agent: executes supply, borrow, repay and withdraw only after wallet
  approval or a pre-authorized bounded policy.
- Policy Agent: applies the Segue sequence model to post-borrow actions such as
  hold, repay from reserve, unwind permitted allocation, or request approval.

The first committed backend slice lives in `backend/segue_api`. It is deliberately
dependency-light for local tests and exposes a FastAPI app when FastAPI is
installed.

Current read-only Aave preflight is documented in `docs/CREDIT_BACKEND.md`.

## M1 contracts now implemented

### `AssetRegistry`

- immutable owner;
- add-only token/feed registrations;
- per-asset pause/resume;
- token and feed decimals captured at registration;
- B20 marker;
- configurable max staleness;
- Chainlink round validation;
- normalized USD price at 1e8.

Once a token/feed pair is registered, M1 provides no function to silently replace its feed.

### `StockPolicyVaultFactory`

- permissionless one-vault-per-wallet creation;
- stores shared registry, settlement token and fixed execution-target configuration;
- factory retains no policy or withdrawal authority over user vaults;
- emits `VaultCreated` for later chain-backed discovery.

### `StockPolicyVault`

- immutable user owner;
- owner-selectable gas executor;
- one live policy at a time for MVP, while completed policy history remains onchain;
- maximum eight ordered steps;
- exactly one `ACTIVE` step; later steps remain `QUEUED`;
- first reference price captured at policy creation;
- later reference price captured only after the previous step actually succeeds;
- fixed sell amount or 25/50/75/100% balance mode;
- policy-wide and vault-wide deployed-USDC caps;
- owner pause, cancel, withdrawal and executor rotation;
- reentrancy guard around token-moving paths.

Execution uses a deliberately narrow boundary:

1. re-read the active policy/step and Chainlink-backed condition;
2. resolve the exact stored sell amount;
3. compute an oracle-based minimum buy amount using the user's deviation bound;
4. snapshot sell/buy balances;
5. set allowance to zero, then approve **exactly** the resolved sell amount to the fixed execution target;
6. call the route calldata supplied by the worker;
7. reset allowance to zero;
8. require the vault sold exactly the stored amount;
9. require the intended buy-token balance increased by at least the minimum;
10. only then mark the step executed and activate/capture the next reference.

A revert at any point leaves the sequence unadvanced.

## Execution provider boundary

The vault is deliberately **not coupled to a quote API**. It only knows one immutable execution contract address supplied by the factory. The offchain adapter must validate provider output before passing calldata to the vault.

M2 originally selected 0x. A real 2026-09-05 USDC → NVDAc request reached 0x and returned `BUY_TOKEN_NOT_AUTHORIZED_FOR_TRADE` due provider-side legal restrictions. Segue does not attempt to bypass that restriction.

M2 now uses 1inch Classic Swap because Base and 1inch publicly document support for Coinbase Tokenized Stocks on Base. The deployment does not guess a router address: `m2_preflight.py` resolves 1inch's live `approve/spender` value, verifies code on Base, and the deployment freezes that public address as the factory's execution target. The firm-quote path rechecks that live spender before accepting calldata.

This changes the routing adapter only; the user-vault trust boundary is unchanged.

## Trust boundary

The worker is intentionally untrusted with respect to user funds.

It may:
- pay gas;
- request a quote;
- supply routing calldata;
- attempt the currently authorized step.

It may not:
- withdraw;
- change conditions;
- change assets;
- change amounts;
- raise caps;
- partially execute a fixed rule and still advance it;
- advance a step that did not successfully satisfy the postconditions.

The vault independently verifies the condition, exact spend and received asset before state advances.

## Source of truth

Onchain state is authoritative for:
- vault ownership;
- policy existence;
- active/queued/executed status;
- budgets;
- balances;
- execution events.

PostgreSQL is used for:
- indexing cursors;
- friendly UI metadata;
- worker health;
- 1inch request/response provenance;
- transaction evidence cache.

The app must recover after local/browser state is cleared.

## Verification status

M1 is **locally contract-verified**:

- Foundry build succeeds with Solidity 0.8.24 via IR;
- 24 tests pass, 0 fail;
- tests cover ordered activation, reference capture, false/true relative conditions, caps, pause/cancel, unauthorized withdrawal, stale feeds, exact one-time execution, unsafe output reversion, executor overspend prevention, partial-sell prevention and cross-policy vault exposure release.

M2 evidence so far:

- Base mainnet chain id, official NVDAc token interface and configured Chainlink feeds were reached by the real preflight;
- the old 0x route is provider-blocked for NVDAc on the current Segue API account;
- the 1inch adapter, live-spender validation and firm-transaction validation are implemented and syntax/contract CI is green;
- a real 1inch NVDAc API response is **not yet verified** because a Segue 1inch API key is still required;
- no Segue contracts have been deployed to Base mainnet and no B20 buy/sell is claimed yet.

Those remain M2 gates.

## Reuse policy

Reuse ideas and contained modules from Sequence/Avelune only where they reduce build time without importing their product assumptions.

Useful Sequence concepts:
- per-wallet vault/factory;
- ordered step state machine;
- idempotency;
- hard risk caps;
- event timeline.

Useful Avelune concepts:
- always-on worker lifecycle;
- deterministic market qualification;
- persistence/recovery discipline;
- chart-oriented UI patterns.

Do not copy either repository wholesale.
