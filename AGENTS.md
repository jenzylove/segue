# Segue Agent Instructions

Read these files before making material changes:

1. `PRD.md` — product contract, architecture, blockers, milestones, definition of done.
2. `BUILD_RULES.md` — mandatory execution discipline.
3. `README.md` — public product framing and current milestone.

## Current product contract

Segue is a Base-mainnet conditional execution layer for Coinbase Tokenized Stocks. The locked core loop is:

`condition → bounded trade → next condition → bounded trade`

A later step activates only after the previous step actually succeeds. The browser does not need to stay open. A user-owned vault enforces the stored policy and hard limits onchain; the worker may attempt execution but may not change the policy or withdraw user funds.

## Locked core integrations

- Base mainnet
- official Coinbase B20 stock assets
- official Chainlink total-return feeds
- 1inch Classic Swap API with one preflight-resolved immutable execution target
- user-owned bounded vault/factory
- FastAPI automation worker
- PostgreSQL as index/cache, never source of truth
- ERC-8021/Base Builder Code attribution

0x was the original M2 route. A real Base-mainnet request returned `BUY_TOKEN_NOT_AUTHORIZED_FOR_TRADE` for NVDAc and 0x documents non-stablecoin RWAs as opt-in, so `PRD.md` records the verified provider-side blocker and the dated switch to 1inch. Do not silently restore 0x or swap providers again without new verified evidence.

## Build order

M1 contracts are complete. M2 real Base-mainnet buy/sell is in progress. Do not begin the main frontend redesign before the real B20 buy and sell path is proven.

At the end of each milestone: verify → update PRD evidence → commit → push → report exact SHA and `MILESTONE READY: YES/NO`.
