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
  - stores policy + active step
  - reads official Chainlink total-return feeds
  - enforces supported assets, amount caps, expiry and deviation
  - revalidates condition at execution
        ↑
        │ executeStep
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

## Trust boundary

The worker is intentionally untrusted with respect to user funds.

It may:
- pay gas;
- request a quote;
- attempt the currently authorized step.

It may not:
- withdraw;
- change conditions;
- change assets;
- change amounts;
- raise caps;
- advance a step that did not successfully execute.

The vault must independently verify the condition and execution postconditions before state advances.

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
