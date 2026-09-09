# Segue Integration Ledger

## 2026-09-08 — Product pivot to B20-backed credit missions

Decision: keep the Segue name and reuse the sequenced policy architecture, but
shift the primary hackathon narrative toward a self-managing credit line for
Coinbase Tokenized Stocks on Base.

Official/current evidence:

- Base's tokenized-stocks builder request explicitly calls out credit, yield and
  self-repaying borrow structures as design space for programmable equities.
- Base's stocks page describes Coinbase Tokenized Stocks as usable across Base
  DeFi and lists Aave for lending/borrowing against tokenized stock positions.
- Base's B20 engineering post says B20 tokens pair with Chainlink total-return
  feeds and that builders must verify addresses, feeds and token lists against
  official sources.

Open verification:

- exact current Aave Base deployment addresses;
- exact B20 collateral reserves accepted by Aave today;
- LTV, liquidation threshold, borrowable USDC liquidity, borrow APR and minimum
  practical demo size;
- live deposit -> borrow -> repay -> withdraw evidence.

Implementation boundary:

- do not hardcode guessed Aave market addresses or risk parameters;
- do not claim an Aave/B20 credit milestone passed until live Base/Aave evidence
  exists;
- keeper actions may only operate inside explicit policy limits.

This ledger stays live for the entire build. Do not let planned integrations silently disappear.

| Integration | Purpose | Required | Credential | Status | Completion evidence |
|---|---|---:|---|---|---|
| Base mainnet | execution network | YES | Base ETH | real provider tested | M2 preflight reached chainId 8453 and read configured contracts/feeds; deployment + real tx still pending |
| Coinbase B20 assets | tokenized stocks | YES | none | real provider tested | M2 preflight read official NVDAc on Base and confirmed ERC-20 decimals=8; deployed-registry evidence still pending |
| Chainlink total-return feeds | trigger + valuation truth | YES | none | real provider tested | M2 preflight read USDC/USD and NVDA total-return feeds on Base; freshness is now enforced before live M2 execution |
| 1inch Classic Swap API | B20 quote/routing | YES | `ONEINCH_API_KEY` | locally tested | Official v6.1 request semantics rechecked 2026-09-07; response/preflight validators and runbook integration pass locally; dedicated key + live route still required |
| 0x Swap API | superseded M2 route | NO | `ZEROX_API_KEY` | blocked | Live USDC→NVDAc request returned HTTP 422 `BUY_TOKEN_NOT_AUTHORIZED_FOR_TRADE` / legal restrictions on 2026-09-05; do not bypass provider compliance |
| Morpho Blue API | credit market discovery | PENDING | none for public API | preflight added | `scripts/equityline_morpho_preflight.py` queries official Morpho Base markets and fails closed until a borrowable NVDAc→USDC market is verified |
| Morpho Blue Base deployment | credit execution | VERIFIED | none | qualified market selected | Official deployment `0xBBBBBbbBBb9cC5e90e3b3Af64bdAF62C37EEFFCb`; qualification found usable USDC markets `0x9136…1612a` and `0xb4b4…3d13`; selection ranks available liquidity after direct oracle checks |

## Live credit proof

Segue's verified credit rail is Morpho Blue on Base, locked to market
`0x91360eea2686ef7ce4966b4e82cf6ff712af02baf0f7211459780d9f5af1612a`.
The borrower wallet `0x48C8B4D40dE216C652ED4D67f6466CeBA90054CA` supplied
`2,323,053` NVDAc atomic and holds a live `1,000,000` atomic USDC debt. Approval
and collateral-supply receipts are recorded in the evidence timeline; the
worker reads the current position instead of trusting frontend state.
| Base RPC | reliable chain access | YES | `BASE_RPC_URL` | real provider tested | Public Base RPC fallback reached mainnet and completed token/feed calls; production worker RPC choice remains deployment-stage work |
| ERC-8021 Builder Code | Base attribution | YES | `BASE_BUILDER_CODE` | locally tested | Schema-0 suffix matches the official `ox/erc8021` vector and M2 state-changing contract-call scripts append it; real code + attributed receipt remain required |
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

## 2026-09-07 M2 continuation audit

The local M2 path now has block-pinned snapshots, exact stale-error evidence,
strict target/feed/calldata validation, distinct false/stale proof files, and
Builder Code suffixes on supported state-changing contract calls. See
`docs/M2_AUDIT.md`. No live 1inch response or Base transaction was produced, so
B1-B4 and real attribution remain unverified.

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
