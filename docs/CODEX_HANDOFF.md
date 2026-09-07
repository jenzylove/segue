# Segue — Codex Continuation Handoff

**Purpose:** Fast continuation without product rediscovery.  
**Baseline before this file:** `b2ede3f3ca754d49b11bfe7b2ab80fc0bfd4d575`  
**Current milestone:** M2 — prove the real Base-mainnet USDC ↔ Coinbase B20 path and close B1–B4.  

---

## 1. Read before doing anything

Read, in this order:

1. `AGENTS.md`
2. `BUILD_RULES.md`
3. `PRD.md`
4. `docs/INTEGRATIONS.md`
5. `docs/M2_MAINNET.md`
6. recent commits + current tree

Do not rediscover or redesign Segue from scratch.

---

## 2. Product in one paragraph

Segue lets an eligible user pre-program a dependent sequence of tokenized-stock actions on Base. Each step has a deterministic market condition, exact/percentage action, expiry, capital cap, and execution-deviation guard. A user-owned vault holds funds and enforces the rules onchain. A gas-only worker monitors and attempts the active step, but cannot withdraw funds or change the user’s strategy. After a successful trade, only then does the next step activate and capture its reference price.

Core loop:

`condition → bounded trade → new reference → next condition → bounded trade`

Do not turn it into an AI stock picker, a generic swap app, or a collection of unrelated limit orders.

---

## 3. Current verified implementation

### Complete / locked

- Base-mainnet contract architecture implemented.
- `AssetRegistry` with immutable token/feed bindings and stale-feed rejection.
- one canonical user-owned `StockPolicyVault` per wallet through `StockPolicyVaultFactory`.
- deterministic conditions:
  - `PRICE_ABOVE`
  - `PRICE_BELOW`
  - `UP_BPS_FROM_REFERENCE`
  - `DOWN_BPS_FROM_REFERENCE`
- fixed and 25/50/75/100% balance amount modes.
- maximum 8 linear steps.
- exactly one active live policy per vault for MVP.
- later steps activate only after the prior step successfully executes.
- exact-sell enforcement, Chainlink-derived minimum output, policy/vault deployed-USDC caps, pause/cancel/withdraw boundaries.
- M1 Foundry contract milestone: 24 tests passed at the locked M1 commit.

### Current M2 tooling already present

- `scripts/m2_preflight.py`
- `scripts/m2_firm_quote.py`
- `scripts/m2_condition_probe.py`
- `scripts/m2_snapshot.py`
- `scripts/m2_extract_deploy.py`
- `scripts/verify_m2_artifacts.py`
- `script/DeployMainnet.s.sol`
- `script/VerifyM2Deployment.s.sol`
- `script/PrepareM2Vault.s.sol`
- `script/CreateM2RoundTripPolicy.s.sol`
- `script/ExecuteM2Quote.s.sol`
- `script/CreateM2FalseConditionPolicy.s.sol`
- `script/CancelM2FalsePolicy.s.sol`

The M2 proof deliberately uses separate roles:

- demo owner: owns the vault and strategy funds;
- executor: gas-only automation/deployment role;
- executor must not become vault owner for convenience.

### M2 proof asset

- Base chain: `8453`
- USDC: `0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913`
- USDC/USD feed: `0x7e860098F58bBFC8648a4311b374B1D669a2bc6B`
- NVDAc: `0xb20000000000000000000078ee7ce2fE4908108C`
- NVDA total-return feed: `0x04689a41629776563E6822F76f2e57D148d28513`

Reverify immutable production values against official/current sources if evidence suggests they changed. Do not substitute guessed addresses.

---

## 4. Provider decision already made

0x was tested first. A real Base-mainnet USDC→NVDAc request returned:

`BUY_TOKEN_NOT_AUTHORIZED_FOR_TRADE`

This was treated as a real provider-side RWA/legal restriction, not something to bypass.

The project switched only the routing adapter to **1inch Classic Swap** because 1inch supports Coinbase B20 stocks on Base.

Do not switch back to 0x or replace 1inch for convenience. A provider change needs new verified blocker evidence and PRD reconciliation.

---

## 5. What M2 still must prove

M2 is **not complete** until all four have real evidence:

### B1
A firm executable 1inch Base-mainnet route exists for the deployed/funded Segue vault and matches the factory-frozen execution target.

### B2
A real Segue vault executes USDC → official B20 on Base mainnet and receives B20.

### B3
The same bounded production path executes B20 → USDC.

### B4
The deployed vault reads the official total-return feed and demonstrably:

- accepts a true condition;
- rejects a false condition;
- fails safely on stale feed data.

Unit tests, simulations, indicative quotes, or a provider HTTP 200 do not close B2/B3.

---

## 6. Human-only boundary

Protected local values may be required:

- `ONEINCH_API_KEY`
- `EXECUTOR_PRIVATE_KEY`
- `DEMO_OWNER_PRIVATE_KEY`
- private RPC/database/deployment credentials

Never request these in chat or commit them.

The human builder also controls tiny real funding/signing actions.

When the next step requires one of these, prepare the exact command from `docs/M2_MAINNET.md`, identify the minimum balance/action, and stop at that boundary.

---

## 7. First Codex task

Before changing code, audit the repository against the current M2 stop condition.

Do the following:

1. inspect current HEAD, tree, and recent commits;
2. read all source-of-truth docs listed above;
3. inspect the M2 scripts/contracts and their tests rather than trusting previous summaries;
4. run the non-secret/local CI/test/validation paths available in the environment;
5. identify whether any code defect still prevents the exact `docs/M2_MAINNET.md` real runbook;
6. research current official 1inch Classic Swap request semantics only where the code/runtime needs confirmation;
7. do **not** broadcast a mainnet transaction or invent credentials;
8. fix only real defects found in the M2 path;
9. add regression tests for fixes where reasonable;
10. reconcile docs only if the actual code/evidence changes;
11. commit/push a clean milestone-ready state.

Then report:

**CURRENT / FINAL GITHUB HEAD**  
**M2 CODE AUDIT**  
**TESTS RUN**  
**REAL PROVIDER EVIDENCE AVAILABLE**  
**EXACT HUMAN ACTION REQUIRED NEXT**  
**B1/B2/B3/B4 STATUS**  
**M2 READY TO ATTEMPT MAINNET: YES/NO**  
**M2 COMPLETE: YES/NO**

`M2 COMPLETE` must remain NO until the real required Base evidence exists.

---

## 8. After M2 passes

Do not stop to re-brainstorm the product.

Continue in this order:

### M3 — autonomous worker

Build/deploy a restart-safe FastAPI worker that reconciles chain state, calls `previewExecution`, requests/validates 1inch only when ready, submits the exact vault step, records evidence, and never retries a confirmed step.

Must close B5–B6.

### M4 — persistence/history/multi-user

Add PostgreSQL indexing/checkpoints/evidence, restart recovery, two-wallet isolation proof, and chain-backed browser recovery.

Must close B7–B9.

### M5 — real frontend

Build the trading product around the real backend/contracts/data:

- stock catalogue;
- stock detail + real market/chart context;
- structured sequence builder;
- risk review;
- canonical vault setup/funding;
- activation;
- active sequence workspace;
- history/evidence;
- cancel/pause/withdraw controls;
- stale feed / unavailable route / wrong network / no vault / unfunded states.

Do not use fake stock data or fake onchain history.

### M6 — production + evidence

Deploy worker/frontend, verify public browser flow, add/verify Builder Code, capture one complete unattended dependent sequence, verify mobile/desktop.

### M7 — submission

Truth-audit docs, record demo, create X post, complete official form, freeze exact final SHA.

---

## 9. Research freedom

You are expected to research unresolved current facts rather than asking the user to micromanage them.

Research is appropriate for:

- additional official B20 assets/feeds for final catalogue;
- real chart source;
- current 1inch schemas;
- hosting/deployment details;
- Builder Code integration;
- current hackathon submission details.

Research is **not** permission to change:

- Base mainnet;
- Coinbase B20 focus;
- Chainlink total-return trigger truth;
- 1inch without blocker evidence;
- user-owned vault trust boundary;
- dependent-step semantics;
- real mainnet evidence requirements.

---

## 10. Reviewer relationship

The human builder will relay Codex milestone reports to a separate reviewer.

Make your reports auditable. Include exact commit SHA, filenames changed, test commands/results, real tx/provider evidence when it exists, and explicit remaining blockers.

Do not use test counts or prose summaries as substitutes for evidence.
