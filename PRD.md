# Product Requirements Document — Segue

**Product:** Segue  
**Hackathon:** Base Builder Quest — Tokenized Stocks  
**Deadline:** September 9, 2026, 11:59 PM EST  
**Status:** M1 contract state machine complete and locally verified; M2 real Base mainnet integration pending  
**Source of truth:** This file is the build contract. Architecture or scope changes require verified blocker evidence and a dated decision entry.

---

## 1. Product thesis

**Segue is a 24/7 conditional execution layer for Coinbase Tokenized Stocks on Base.**

A user defines a dependent stock sequence once, for example:

> If NVDAc falls 5%, buy $20. After that purchase, if NVDAc rises 8%, sell half. Then, if AAPLc is below my chosen level, rotate the proceeds into AAPLc. Never deploy more than $50 and never execute outside my price-deviation limit.

The user may leave the app. A background worker monitors conditions and attempts execution, while the user's personal smart-contract vault enforces the exact precommitted rule and hard limits onchain.

Segue does **not** predict stocks. It executes rules the user already chose.

### Problem

Coinbase Tokenized Stocks can trade 24/7, but users still need to monitor markets and manually decide what happens next. Existing products already cover manual swaps, single limit/stop orders, DCA and portfolio rebalancing. Segue targets the gap between them: **dependent multi-step execution** where each next action becomes active only after the previous action really succeeds.

### Job to be done

> “I know the rules I want to follow. Execute them for me when the conditions occur, in the order I specified, without making me watch the market all day.”

### Target user

Rules-based investors/traders in eligible non-US jurisdictions who want Coinbase Tokenized Stock exposure, strict capital limits and an auditable onchain trail without continuous monitoring.

The app must not enable B20 trading for U.S. users. The frontend must include an eligibility acknowledgement and clearly state the jurisdiction limitation.

---

## 2. Differentiation and non-goals

A normal limit order:

`NVDA <= X → buy`

Segue:

`condition → trade → new reference → next condition → next trade → ...`

The differentiator is **the sequence**, not merely automation.

Do not turn the MVP into:
- a generic brokerage;
- an AI stock picker or “AI, buy NVDA” assistant;
- a DCA-only or single-order product;
- a passive portfolio rebalancer;
- Avelune TAKE/PASS training;
- a copy of Sequence's Somnia/DreamDEX architecture;
- social/copy trading, lending, portfolio optimization, cross-chain deposits, fiat onramp, governance, token issuance, alerts, an agent marketplace or extra DeFi features.

AI is not required for the core submission. A plain-language rule parser and deterministic replay/backtest remain deferred until the required mainnet loop is complete.

---

## 3. MVP workflow

### Conditions

Supported deterministic condition types:
1. `PRICE_ABOVE`
2. `PRICE_BELOW`
3. `UP_BPS_FROM_REFERENCE`
4. `DOWN_BPS_FROM_REFERENCE`

Reference price is captured when the first step activates and again only after a successful prior step activates the next one.

Execution conditions use the verified Chainlink total-return feed associated with the supported B20 asset.

### Actions

Supported actions:
1. Base USDC → verified B20 stock.
2. Verified B20 stock → Base USDC.
3. Verified B20 stock → another verified B20 stock.
4. Stop/cancel the sequence.

Amount modes:
- fixed token/USDC amount;
- 25%, 50%, 75% or 100% of available sell-token balance.

### Sequence semantics

- maximum 8 steps for MVP;
- exactly one step is `ACTIVE`;
- later steps remain `QUEUED`;
- a successful trade marks the active step `EXECUTED`;
- only then does the next step become active and capture its new reference price;
- failed, unsafe or reverted execution does not advance state;
- cancelled/expired policy executes nothing further;
- each step can execute only once;
- generic branching/OCO trees are deferred.

---

## 4. Trading and price truth

### Verified assets only

Never identify a supported stock by ticker alone. Segue maintains a verified registry sourced from Base/Coinbase B20 information. Each supported asset must bind:
- ticker/company metadata offchain;
- exact B20 contract address;
- token decimals;
- exact Chainlink total-return feed;
- feed decimals/staleness policy;
- active/paused state.

Base USDC is the settlement asset.

### B20 corporate actions

B20 token/share representation can change through the B20 multiplier for splits/dividends. Segue therefore uses the official Chainlink **total-return feed** for trigger and valuation truth rather than a naive raw token/share assumption.

---

## 5. Locked architecture

```text
Browser wallet
  ↓ create/fund/configure
StockPolicyVaultFactory
  ↓
User-owned StockPolicyVault
  - holds that user's strategy assets
  - stores policy + ordered step state
  - uses AssetRegistry / Chainlink price truth
  - rechecks condition at execution
  - enforces assets, exact amount, expiry, caps and deviation
  - advances only after execution postconditions pass
  ↑
  │ executeStep(policyId, routing calldata)
  │
FastAPI automation worker
  - dedicated gas-only executor wallet
  - never owns user strategy funds
  - reconciles onchain policies
  - asks whether active step is executable
  - obtains validated 0x quote only when needed
  - submits execution and records evidence
  ├─ CDP/Base RPC
  ├─ 0x Swap API
  └─ PostgreSQL index/cache
```

### Factory

`StockPolicyVaultFactory`:
- permissionless one-vault-per-wallet creation for MVP;
- shared registry, settlement-token and fixed execution-target configuration;
- emits `VaultCreated(owner, vault, executor, maxDeployedUSDC)`;
- retains no policy or withdrawal authority over user vaults.

### Vault trust boundary

The worker may pay gas, request a quote, supply routing calldata and attempt the current rule. It may **not** withdraw funds, alter conditions/assets/amounts, increase caps, execute a completed step or cause a different token pair to be accepted.

The vault must independently:
1. re-read active policy/step and condition;
2. re-read verified Chainlink-backed price truth;
3. resolve the exact stored sell amount;
4. check policy/vault deployed-USDC caps;
5. compute minimum acceptable output from verified prices + user `maxDeviationBps`;
6. snapshot sell/buy balances;
7. approve only the exact resolved sell amount to the fixed 0x execution/allowance target;
8. execute worker-supplied routing calldata;
9. reset allowance to zero where appropriate;
10. require the exact stored sell amount was consumed;
11. require intended buy-token balance increased by at least the minimum;
12. only then mark the step executed and activate the next step.

Any failed postcondition reverts and leaves the sequence unadvanced.

### Source of truth

Blockchain state is authoritative for vault ownership, policy existence, active/queued/executed state, budgets, balances and execution events.

PostgreSQL may store indexing cursors, friendly UI metadata, worker health, provider provenance and transaction evidence cache. LocalStorage/PostgreSQL must not determine whether a real onchain policy exists.

---

## 6. Automation worker

Locked runtime direction:
- Python 3.12;
- FastAPI;
- SQLAlchemy/PostgreSQL;
- Web3.py or minimal EVM client;
- HTTPX for 0x;
- always-on worker process/service.

Target loop every ~20–30 seconds:
1. discover/reconcile active vaults/steps;
2. call onchain `previewExecution`/equivalent;
3. if false, do nothing;
4. if true, request a firm 0x quote;
5. validate chain, taker, recipient, token pair, amount, allowance/execution target and freshness;
6. submit `executeStep`;
7. wait for receipt;
8. persist tx/evidence;
9. never retry a confirmed/completed step.

On restart, reconcile against chain before action.

---

## 7. Frontend contract

Stack:
- Next.js + TypeScript + React;
- Wagmi + Viem;
- Base mainnet final production mode;
- ERC-8021 Builder Code attribution from the transaction path onward.

Primary experience must read as a trading product:

```text
NVDAc — NVIDIA
real price/chart context

WHEN
[stock] [falls/rises/reaches] [condition]

DO
[buy/sell/rotate] [$ / %]

THEN
[next condition + action]

MAX CAPITAL [$...]
MAX EXECUTION DEVIATION [...%]

[Review] [Activate]
```

Show the sequence path visually, e.g.:

`NVDAc condition → Buy → +8% → Sell 50% → AAPLc condition → Buy`

Use only real chart/market data. If an underlying-equity chart is used, label it as underlying-stock context; actual automation truth remains the B20 Chainlink total-return feed and actual 0x execution quote.

User flow:

`connect → inspect stock → build sequence → review risk → create/fund vault if needed → activate → live`

Infrastructure jargon must not lead the experience.

---

## 8. Integration ledger

The detailed live ledger is `docs/INTEGRATIONS.md`.

Required:
- Base mainnet;
- official Coinbase B20 assets;
- official Chainlink total-return feeds;
- 0x Swap API / supported execution target;
- CDP/Base RPC;
- ERC-8021/Base Builder Code;
- PostgreSQL;
- a real chart source for polished frontend context.

Not required:
- AI provider;
- Telegram/Telegraph;
- Firestore/Vertex;
- Chainlink Automation.

### Credential state after M1

- `EXECUTOR_PRIVATE_KEY`: obtained by builder; secret, never commit/paste.
- `BASE_RPC_URL`: obtained by builder; secret, never commit/paste.
- `ZEROX_API_KEY`: pending; required for M2 real quote/trade, not M1.
- `BASE_BUILDER_CODE`: Base app setup started; domain verification waits for deployed Segue URL.
- `DATABASE_URL`: later worker/persistence milestone.

---

## 9. Blockers / gates B1–B12

These are completion gates, not reasons to silently redesign.

### B1 — Real B20 route exists
0x returns an executable Base mainnet quote for at least one official B20 ↔ USDC pair with the vault as taker/recipient.

### B2 — Real B20 buy
A deployed Segue vault completes a real Base mainnet USDC → B20 purchase through the production path and receives the B20 output.

### B3 — Real B20 sell
The same vault can sell all/part of a B20 balance back to USDC through the same bounded path.

### B4 — Real Chainlink condition
The deployed contract reads the exact official total-return feed and rejects a false condition / accepts a true condition.

### B5 — Browser-closed automation
A deployed worker advances an ACTIVE policy without the frontend open.

### B6 — Real chaining
Step 2 cannot execute before step 1; after successful step 1, step 2 becomes ACTIVE with the expected new reference.

### B7 — Worker cannot escape limits
Tests and real-path checks cover wrong token, wrong/excess/partial sell amount, stale/completed step, unsafe price deviation and unauthorized withdrawal.

### B8 — Multi-user isolation
Two wallets resolve to different vaults and cannot alter/withdraw from each other's vaults.

### B9 — Onchain recovery
After clearing browser state, active/completed policies reconstruct from chain/indexed evidence rather than localStorage.

### B10 — Builder Code attribution
At least one showcased Base transaction contains valid project ERC-8021 attribution.

### B11 — Public production flow
Judge can open the live URL, connect an eligible wallet, inspect real stock data, build/review a policy and reach activation without dead controls.

### B12 — Submission proof
Public demo video, X post tagging `@buildonbase`, live URL, Builder Code and official form are complete before deadline.

**Segue is not submission-ready until B1–B12 pass or a requirement is explicitly amended with new verified evidence.**

---

## 10. Milestone plan and current status

Every milestone ends with: verify → commit/push → reconcile PRD/integration ledger → report exact evidence → only then continue.

| Milestone | Status | Commit | Evidence |
|---|---|---|---|
| M0 Repo/source of truth | **COMPLETE** | `ac2cba1c7e309a35244816c36e781471600275fe` | Source-of-truth baseline + secret-safe CI green |
| M1 Contract state machine | **COMPLETE** | `615b1908856670601e2d9ae05fc1d4ec52cc66f8` | Foundry build green; 24 tests passed, 0 failed; vault/factory/registry implemented + hardened |
| M2 Real Base mainnet buy/sell | NOT STARTED | — | Must pass B1–B4 |
| M3 Autonomous worker | NOT STARTED | — | Must pass B5–B6 with deployed service |
| M4 Persistence/history/multi-user | NOT STARTED | — | Must pass B7–B9 |
| M5 Trading frontend | NOT STARTED | — | Deployed browser flow against real backend/contracts |
| M6 Production evidence | NOT STARTED | — | Must pass B10–B11 |
| M7 Submission | NOT STARTED | — | Must pass B12; freeze exact final commit |

### M0 — Repository + source of truth

Required: PRD, build rules, AGENTS.md, environment example, architecture/integration docs, asset-registry schema and CI baseline. **Complete.**

### M1 — Contract state machine

Required: factory, per-user vault, policy/step state, deterministic conditions, caps, pause/cancel/withdraw, Chainlink checking boundary, ordered activation, bounded 0x execution boundary and contract tests. **Complete locally.**

M1 evidence:
- Solidity 0.8.24 / Foundry 1.8.1 build succeeded via IR;
- 24 tests passed, 0 failed, 0 skipped on GitHub Actions;
- covered ordered activation, reference capture, true/false relative conditions, stale feed rejection, caps, pause/cancel, unauthorized withdrawal, exact one-time execution, unsafe output reversion, executor overspend, partial-sell prevention, multi-user factory isolation and cross-policy vault exposure release;
- no mainnet/provider success is claimed by M1.

### M2 — Real Base mainnet buy + sell

Required outcome:
- verify exact official Base USDC, chosen B20 token and total-return feed;
- verify current supported 0x allowance/execution target from official/live evidence;
- deploy the exact tested contracts;
- fund one vault with tiny USDC;
- obtain production 0x quote;
- execute real B20 buy;
- execute real B20 sell;
- record tx hashes and before/after balances;
- pass B1–B4.

**Do not begin the main frontend redesign before M2 passes.**

### M3 — Autonomous worker

Build/deploy the reconciliation + quote + execution loop with restart-safe idempotency. Pass B5–B6.

### M4 — Persistence/history/multi-user

PostgreSQL checkpoints/evidence, two-wallet isolation and chain-backed recovery. Pass B7–B9.

### M5 — Trading frontend

Wallet connect, stock list, real price/chart context, structured builder, review/risk, JIT vault creation/funding, activation, live/history, cancel/withdraw.

### M6 — Deployment + final evidence

Production frontend/worker, exact contract addresses, Builder Code attribution and one complete autonomous sequence. Pass B10–B11.

### M7 — Submission

README truth audit, under-3-minute demo, X post, live URL, Builder Code and form. Pass B12 and freeze final SHA.

---

## 11. M1 architecture decisions / hardening ledger

### 2026-09-05 — Exact executor spend

The executor may choose route calldata but may not cause a fixed step to advance after selling less than the stored resolved amount. Vault execution now requires `sold == sellAmount` in addition to the minimum-output postcondition.

### 2026-09-05 — Cross-policy vault exposure

A later policy selling B20 acquired by a previous completed policy must release vault-wide deployed-USDC exposure even when the new policy's local deployed amount began at zero. Policy-local and vault-wide reductions are therefore bounded independently.

### 2026-09-05 — Quote-math precision

Minimum-buy computation scales by token-decimal difference before the principal division to avoid unnecessary precision loss between 6-decimal USDC and 18-decimal assets. Final minimum output remains conservatively rounded down.

These are hardening corrections inside the locked architecture, not product pivots.

---

## 12. Demo path

Target under 3 minutes:
1. open a real B20 stock with real price/chart context;
2. build a tiny real-capital sequence;
3. show the sequence path and hard limits;
4. activate/fund once;
5. explain the worker cannot change rules or withdraw;
6. leave/close the app;
7. show real autonomous evidence: condition true → contract recheck → 0x route → Base transaction → next step activated;
8. reopen and show the same state recovered from chain;
9. open block explorer evidence including Builder Code attribution.

Never present a mocked/simulated trade as the real autonomous path.

---

## 13. Submission requirements

Current quest requirements tracked for closure:
- project helps people trade/use Coinbase Tokenized Stocks on Base;
- do not enable U.S. users to trade the restricted stock product;
- public Loom/demo video;
- X post tagging `@buildonbase`;
- live project URL;
- Base Builder Code;
- submission tweet URL;
- official form before Sep 9, 2026, 11:59 PM EST.

Prize pool tracked: $2,000 top project; remaining $3,000 split across five finalists. No weighted public judging rubric is currently published.

---

## 14. Final definition of done

The product is complete only when:
- [x] repository/source-of-truth baseline exists and CI is green;
- [x] bounded contract state machine is locally verified;
- [ ] contracts are deployed to Base mainnet;
- [ ] official B20 addresses and feeds are verified in the deployed registry;
- [ ] one real B20 buy succeeds;
- [ ] one real B20 sell succeeds;
- [ ] multi-step policy advances in the correct real order;
- [ ] browser can be closed while worker executes a real step;
- [ ] hard spending/deviation limits are proven on real path;
- [ ] second wallet is isolated;
- [ ] state recovers without localStorage;
- [ ] production UI uses real data;
- [ ] Builder Code appears on evidence transaction(s);
- [ ] public URL works end-to-end;
- [ ] README matches implementation;
- [ ] Loom/X/form submission material is complete.

If any unchecked required item remains, Segue is not yet a complete submission.

---

## 15. PRD maintenance protocol

After every milestone:
1. compare repository HEAD against this PRD;
2. update milestone status and exact evidence;
3. update `docs/INTEGRATIONS.md`;
4. keep difficult requirements visible;
5. do not call planned/implemented/local work deployed or mainnet-verified;
6. if architecture must change, add a dated entry with verified blocker evidence and explain why the replacement preserves the product thesis;
7. commit/push the reconciliation before moving on.

---

## 16. Research references used to lock architecture

Primary references:
- Base tokenized stocks: https://blog.base.org/tokenized-stocks
- B20 engineering/total-return feeds: https://blog.base.dev/b20-tokenized-stocks-on-base
- Base stocks directory: https://base.org/stocks
- Base Request for Builders: https://blog.base.org/request-for-builders-tokenized-stocks
- Builder Codes/ERC-8021: https://blog.base.dev/builder-codes-and-erc-8021-fixing-onchain-attribution
- Coinbase CDP Node: https://docs.cdp.coinbase.com/data/node/overview
- 0x Swap API: https://docs.0x.org/docs/introduction/quickstart/swap-tokens-with-0x-swap-api
- 0x contracts: https://docs.0x.org/docs/core-concepts/contracts
- 0x rate limits: https://docs.0x.org/docs/developer-resources/rate-limits

Quest tracking reference:
- https://viamu.app/opportunities/base-tokenized-stocks-2026
