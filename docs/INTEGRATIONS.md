# Segue Integration Ledger

This ledger stays live for the entire build. Do not let planned integrations silently disappear.

| Integration | Purpose | Required | Credential | Status | Completion evidence |
|---|---|---:|---|---|---|
| Base mainnet | execution network | YES | Base ETH | planned | M2: deployed contracts + real tx |
| Coinbase B20 assets | tokenized stocks | YES | none | planned | M2: verified official addresses in registry |
| Chainlink total-return feeds | trigger + valuation truth | YES | none | locally tested | M1 `AssetRegistry` + vault condition path pass mocked feed tests; M2 must verify official Base feeds onchain |
| 0x Swap API | B20 quote/routing | YES | `ZEROX_API_KEY` | adapter implemented | Dedicated Segue API key obtained; M1 bounded AllowanceHolder boundary is mock-tested; real quote/buy/sell remains M2 |
| CDP/Base RPC | reliable chain access | YES | `BASE_RPC_URL` | credentials obtained | Builder obtained a private Base mainnet endpoint; value remains secret. M2 preflight must verify it onchain |
| ERC-8021 Builder Code | Base attribution | YES | `BASE_BUILDER_CODE` | planned | Base app created; domain registration/attributed evidence tx remain deployment-stage work |
| PostgreSQL | worker checkpoints/history cache | YES | `DATABASE_URL` | planned | M4: restart-safe worker reconciliation |
| Real chart source | trading context UI | YES for frontend | TBD | planned | M5: labelled live chart renders |
| AI provider | optional rule parser | NO | none | deferred | not part of core submission |
| Telegram/Telegraph | none | NO | none | rejected | do not add |
| Firestore/Vertex | none | NO | none | rejected | do not add |
| Chainlink Automation | none for MVP | NO | none | rejected | worker handles automation |

## M1 integration boundary

M1 deliberately proves contract behavior without claiming external/mainnet verification:

- `AssetRegistry` stores immutable token/feed pairs, normalizes prices to 1e8, and rejects invalid, incomplete, inactive, or stale feeds.
- `StockPolicyVault` rechecks the condition at execution time and computes a Chainlink-price-based minimum output before state can advance.
- the 0x integration boundary is fixed to the configured allowance/execution contract; the worker may supply route calldata but receives only the exact sell allowance resolved from the stored rule.
- a step advances only after the exact stored sell amount leaves the vault and at least the minimum verified buy-token amount arrives.

No production B20 address, Chainlink feed, 0x API response, or Base mainnet transaction is claimed yet. Those are M2 gates B1–B4.

## Credential status

- `BASE_RPC_URL`: obtained; never commit or paste the full private endpoint.
- `EXECUTOR_PRIVATE_KEY`: obtained; never commit or paste it.
- `ZEROX_API_KEY`: obtained in a dedicated Segue 0x team; never commit or paste it.
- `BASE_BUILDER_CODE`: app setup started; domain verification waits for a deployed Segue URL and is not an M2 transaction-path blocker.

## Status vocabulary

Use only:
- planned
- credentials obtained
- adapter implemented
- locally tested
- real provider tested
- mainnet verified
- deployed
- browser verified
- blocked
- deferred
- rejected

Update this file with exact evidence at each milestone.
