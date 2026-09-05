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
- 0x Swap API
- user-owned bounded vault/factory
- FastAPI automation worker
- PostgreSQL as index/cache, never source of truth
- ERC-8021/Base Builder Code attribution

Do not swap these for convenience. If verified evidence proves a blocker, document it in `PRD.md` before changing architecture.

## Build order

Follow the milestones in `PRD.md`. In particular, do not begin the main frontend redesign before the real Base mainnet B20 buy and sell path is proven.

At the end of each milestone: verify → update PRD evidence → commit → push → report exact SHA and `MILESTONE READY: YES/NO`.
