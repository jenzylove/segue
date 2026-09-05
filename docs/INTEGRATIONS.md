# Segue Integration Ledger

This ledger stays live for the entire build. Do not let planned integrations silently disappear.

| Integration | Purpose | Required | Credential | Status | Completion evidence |
|---|---|---:|---|---|---|
| Base mainnet | execution network | YES | Base ETH | real provider tested | M2 preflight reached chainId 8453 and read configured contracts/feeds; deployment + real tx still pending |
| Coinbase B20 assets | tokenized stocks | YES | none | real provider tested | M2 preflight read official NVDAc on Base and confirmed ERC-20 decimals=8; deployed-registry evidence still pending |
| Chainlink total-return feeds | trigger + valuation truth | YES | none | real provider tested | M2 preflight read USDC/USD and NVDA total-return feeds on Base; freshness is now enforced before live M2 execution |
| 1inch Classic Swap API | B20 quote/routing | YES | `ONEINCH_API_KEY` | adapter implemented | Official 1inch material states Coinbase B20 stocks on Base are supported; Segue preflight/firm-quote adapters implemented; dedicated key + live route still required |
| 0x Swap API | superseded M2 route | NO | `ZEROX_API_KEY` | blocked | Live USDC→NVDAc request returned HTTP 422 `BUY_TOKEN_NOT_AUTHORIZED_FOR_TRADE` / legal restrictions on 2026-09-05; do not bypass provider compliance |
| Base RPC | reliable chain access | YES | `BASE_RPC_URL` | real provider tested | Public Base RPC fallback reached mainnet and completed token/feed calls; production worker RPC choice remains deployment-stage work |
| ERC-8021 Builder Code | Base attribution | YES | `BASE_BUILDER_CODE` | planned | Base app created; domain registration/attributed evidence tx remain deployment-stage work |
| PostgreSQL | worker checkpoints/history cache | YES | `DATABASE_URL` | planned | M4: restart-safe worker reconciliation |
| Real chart source | trading context UI | YES for frontend | TBD | planned | M5: labelled live chart renders |
| AI provider | optional rule parser | NO | none | deferred | not part of core submission |
| Telegram/Telegraph | none | NO | none | rejected | do not add |
| Firestore/Vertex | none | NO | none | rejected | do not add |
| Chainlink Automation | none for MVP | NO | none | rejected | worker handles automation |

## M1 integration boundary

M1 proves contract behavior without claiming production execution:

- `AssetRegistry` stores immutable token/feed pairs, normalizes prices to 1e8, and rejects invalid, incomplete, inactive, or stale feeds.
- `StockPolicyVault` rechecks the condition at execution time and computes a Chainlink-price-based minimum output before state can advance.
- the swap boundary is a fixed execution contract configured in the factory; the worker may supply route calldata but receives only the exact sell allowance resolved from the stored rule.
- a step advances only after the exact stored sell amount leaves the vault and at least the minimum verified buy-token amount arrives.

The vault's safety model is provider-agnostic. The M2 deployment script now receives the execution target from `EXECUTION_TARGET_ADDRESS`; preflight resolves that value from 1inch's live `approve/spender` endpoint before deployment.

## 2026-09-05 provider decision — 0x → 1inch

Verified blocker evidence:

- Base mainnet RPC, official NVDAc and both Chainlink feeds were successfully reached from the real M2 preflight.
- The subsequent 0x USDC→NVDAc request failed with HTTP 422 `BUY_TOKEN_NOT_AUTHORIZED_FOR_TRADE`, with the provider message stating that the buy token was not authorized due to legal restrictions.
- This is provider-side authorization, not a missing Segue parameter and must not be bypassed.

Replacement evidence:

- Base publicly lists 1inch as a venue for Coinbase Tokenized Stock swaps.
- 1inch publicly announced support for Coinbase B20 stocks on Base, including NVDAc.
- 1inch Classic Swap supports Base (`8453`) and exposes `quote`, `swap`, and `approve/spender` APIs.

Therefore M2 replaces only the routing adapter. Coinbase B20, Base, Chainlink, per-user vaults, the fixed execution-target trust boundary, and the product thesis remain unchanged. The replacement is not considered **real provider tested** until Segue obtains a 1inch key and the live NVDAc route passes.

## Credential status

- `BASE_RPC_URL`: configured locally; never commit or paste a private endpoint.
- `EXECUTOR_PRIVATE_KEY`: obtained; never commit or paste it.
- `EXECUTOR_ADDRESS`: configured, but M2 preflight reported zero Base ETH; fund a deliberately small gas amount before deployment.
- `ONEINCH_API_KEY`: required next; store only in local/server environment.
- `EXECUTION_TARGET_ADDRESS`: leave blank until the live 1inch preflight prints the current `approve/spender` address, then copy that public address locally before deployment.
- `ZEROX_API_KEY`: historical/superseded for M2 after the verified RWA authorization blocker.
- `BASE_BUILDER_CODE`: app setup started; domain verification waits for a deployed Segue URL and is not an M2 transaction-path blocker.

## Feed-hours limitation

Coinbase B20 tokens can trade 24/7, but the configured Chainlink equity total-return feed can be stale outside its update window. Segue intentionally fails closed. M2 preflight now enforces the same 6-hour equity / 2-hour USDC staleness limits used by the contracts rather than merely printing timestamps.

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
