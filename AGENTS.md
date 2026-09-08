# Segue Agent Instructions

Read these files before making material changes:

1. `PRD.md` — authoritative product contract, product semantics, UX, architecture, research boundaries, blockers, milestones, and definition of done.
2. `BUILD_RULES.md` — mandatory execution discipline.
3. `docs/CODEX_HANDOFF.md` — current continuation state and first task.
4. `docs/INTEGRATIONS.md` — live provider/integration ledger.
5. `docs/M2_MAINNET.md` — current mainnet gate/runbook while M2 remains open.
6. `docs/CREDIT_BACKEND.md` — current B20-backed credit/Aave backend runbook.
7. `README.md` — public product framing.

Then inspect the repository tree, recent commits, and current HEAD before coding.

## Product contract

Segue is a Base-mainnet conditional execution layer for Coinbase Tokenized Stocks.

Core loop:

`condition → bounded trade → new reference → next condition → bounded trade`

A later step activates only after the previous step actually succeeds. The browser does not need to stay open. A user-owned vault enforces the stored policy and hard limits onchain; the worker may attempt execution but may not change the policy or withdraw user funds.

Segue does **not** predict stocks or choose trades for the user.

## Locked core integrations

- Base mainnet
- official Coinbase B20 stock assets
- official Chainlink total-return feeds
- 1inch Classic Swap with one preflight-resolved immutable execution target
- user-owned bounded vault/factory
- FastAPI automation worker
- PostgreSQL as index/cache, never source of truth
- ERC-8021/Base Builder Code attribution

0x was the original M2 route. A real Base-mainnet request returned `BUY_TOKEN_NOT_AUTHORIZED_FOR_TRADE` for NVDAc, so the verified provider-side blocker and dated switch to 1inch are recorded in `PRD.md` / `docs/INTEGRATIONS.md`. Do not silently restore 0x or swap providers again without new verified evidence.

## Research is expected

Do not treat the PRD as a ban on research.

Research unresolved external details yourself using official/current sources before asking the user, including provider schemas, additional B20 catalogue candidates, exact current feeds, chart-data options, deployment choices, and Builder Code mechanics.

Do not invent addresses, capabilities, or market data. Record important findings and provenance in the integration ledger or relevant milestone doc.

The product thesis, dependent-sequence semantics, chain/oracle choice, user-owned vault safety boundary, and required real-evidence gates are not research-open convenience choices.

## Current build state

M1 contracts are complete.

M2 real Base-mainnet buy/sell is still open, but the repo already contains hardened route/deployment/vault/policy/condition/snapshot tooling. Real B1–B4 evidence still requires the human builder's protected local credentials/funding and actual Base-mainnet/provider execution.

Do not call M2 complete from tests, indicative quotes, simulations, or code existence.

Do not begin a major frontend redesign before the required production path is proven. Research/preparation may continue, but do not replace real backend behavior with frontend mocks.

## Human/secret boundary

Never ask the user to paste private keys, API keys, private RPC URLs, database credentials, or wallet secrets into chat/repo.

When a milestone reaches a secret/funding/signature boundary:

1. prepare the exact safe command/script;
2. explain the minimum human action required;
3. stop before the secret itself;
4. continue from public/non-secret output after the user runs it.

## Build order

Current intended order:

`M2 real mainnet path → M3 autonomous worker → M4 persistence/recovery → M5 real frontend → M6 deployment/evidence → M7 submission`

At the end of each milestone:

`verify → inspect evidence → update PRD/integration ledger → commit → push → report exact SHA`

Report:

**FINAL GITHUB HEAD**  
**IMPLEMENTED**  
**TESTS**  
**REAL PROVIDER / MAINNET EVIDENCE**  
**DEPLOYMENT**  
**PERSISTENCE / LOG EVIDENCE**  
**FRONTEND / BROWSER VERIFICATION**  
**BLOCKERS**  
**MILESTONE READY: YES/NO**

Do not output YES if a required verification step was skipped.
