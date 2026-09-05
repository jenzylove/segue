# Segue Architecture

`PRD.md` is authoritative. This file is a compact implementation map.

## Runtime

```text
Browser wallet
  └─ create/fund/configure user vault
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
  - discovers/reconciles active vaults
  - asks onchain state whether a step is executable
  - obtains validated 0x quote
  - submits transaction
  - persists tx/provider evidence
        ├─ Base RPC
        ├─ 0x Swap API
        └─ PostgreSQL cache/index
```

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
- stores shared registry, settlement token and execution/allowance target configuration;
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
- 0x request/response provenance;
- transaction evidence cache.

The app must recover after local/browser state is cleared.

## Verification status

M1 is **locally contract-verified only**:

- Foundry build succeeds with Solidity 0.8.24 via IR;
- 24 tests pass, 0 fail;
- tests cover ordered activation, reference capture, false/true relative conditions, caps, pause/cancel, unauthorized withdrawal, stale feeds, exact one-time execution, unsafe output reversion, executor overspend prevention, partial-sell prevention and cross-policy vault exposure release.

M1 does **not** claim:
- an official B20 token/feed has been registered on Base mainnet;
- a live 0x quote has been accepted;
- a real B20 buy/sell has occurred.

Those are M2 gates.

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
