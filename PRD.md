# Product Requirements Document — Segue

**Product:** Segue  
**Tagline:** Program what your portfolio does next.  
**Hackathon:** Base Builder Quest — Tokenized Stocks  
**Target network:** Base mainnet  
**Current repository baseline for this revision:** `589fd0c61075f712b876c3f7e847c248de52b357`
**Current build state:** M1 contract state machine complete; the original M2 vault buy/sell path remains protected by its provider/funding gates; the Morpho Blue B20 credit mission is implemented and has a real Base-mainnet read/borrow proof; the current API, worker and landing surface use live Morpho state.
**Source of truth:** This PRD is the product/build contract. `BUILD_RULES.md`, `AGENTS.md`, `docs/INTEGRATIONS.md`, `docs/ARCHITECTURE.md`, and milestone-specific docs are subordinate execution documents.

---

# 0. How to use this PRD

This document is intentionally detailed so a coding agent can continue Segue without rediscovering the product or silently simplifying the hard parts.

It is **not** intended to prevent research or implementation judgment.

## 0.1 Locked product decisions

Do not change these for convenience:

- Segue is a conditional execution layer for **Coinbase Tokenized Stocks (B20) on Base**, not a generic DeFi app.
- The core differentiator is **dependent multi-step execution**.
- A later step activates only after the prior trade actually succeeds.
- A user-owned vault holds strategy funds and enforces the stored policy onchain.
- The automation worker pays gas/attempts execution but may not withdraw user funds or rewrite a policy.
- Chainlink total-return feeds are trigger/valuation truth for supported B20 assets.
- 1inch Classic Swap is the current production routing path after the verified 0x RWA blocker.
- Morpho Blue is the verified credit rail for NVDAc-backed USDC borrowing on Base.
- Base chain state is authoritative for ownership, policy state, balances, and execution state.
- PostgreSQL is an index/cache/history layer, never the authority for whether an onchain policy exists.
- No fake market data, fake trades, fake hashes, or frontend-only state may be presented as production evidence.

## 0.2 Research-open areas

The coding agent **should research** unresolved external facts before implementing them. Examples:

- which additional B20 stocks beyond the M2 proof asset should appear in the final curated frontend catalogue;
- exact current official token/feed metadata for those additional assets;
- the best real chart-data provider that is practical for the hackathon;
- current 1inch API response details and current approved spender/execution target;
- deployment platform details for the worker, PostgreSQL, and frontend;
- exact current Base Builder Code integration steps;
- current hackathon submission mechanics if they change.

Research rules:

1. Prefer official Base, Coinbase, Chainlink, 1inch, and ERC/Base documentation.
2. Verify live onchain/provider behavior where the product depends on it.
3. Record important external facts and provenance in `docs/INTEGRATIONS.md` or the relevant milestone doc.
4. Do not invent addresses, tickers, feeds, provider capabilities, or compliance claims.
5. If new verified evidence makes a locked implementation path impossible, preserve the product thesis, document the blocker, propose the smallest replacement, and add a dated decision entry before changing architecture.

## 0.3 Status vocabulary

Use these terms precisely:

- **planned** — described but no implementation yet;
- **implemented** — code exists;
- **locally tested** — local/unit/integration tests pass;
- **real provider tested** — live external provider call succeeded;
- **mainnet verified** — real Base-mainnet state/transaction proves the claim;
- **deployed** — released to the target environment;
- **browser verified** — real public browser flow exercised successfully;
- **blocked** — verified external/internal blocker prevents the required outcome;
- **deferred** — intentionally outside current required scope.

Never collapse these into “done.”

---

# 1. Product thesis

**Segue is a self-managing credit and sequenced policy layer for Coinbase Tokenized Stocks on Base.**

A user can hold or acquire supported B20 stocks, borrow USDC against them through real Base credit markets, and precommit what should happen next when risk or opportunity conditions change.

The user decides the policy. Segue executes only when the user's precommitted conditions become true and the relevant onchain/protocol evidence allows the action.

Credit example:

> I own NVDAc on Base and want 20 USDC without selling it. Use the locked Morpho Blue market, keep the position above my health-factor buffer, reserve enough USDC for emergency repayment, and if risk deteriorates, prepare a share-based repay before asking me for approval.

Sequenced trading example:

> If NVDAc falls 5% from the price when this step becomes active, buy $20. After that purchase succeeds, if NVDAc rises 8% from the new reference price, sell 50% of the position. Then, if another verified B20 stock reaches my chosen condition, rotate the proceeds into it. Never deploy more than $50 and never accept execution beyond my chosen deviation limit.

The user may leave the browser. Segue continues monitoring and can advance the sequence later.

Segue does **not** predict stocks, recommend trades, decide the next asset, invent lending parameters, or dynamically rewrite the user's rules.

## 1.0 2026-09-08 pivot decision

The hackathon narrative now centers on **B20-backed credit missions**:

`B20 collateral -> safe borrow -> monitored credit mission -> sequenced repay/de-risk action`

The original stock-routing vault remains part of the architecture for B20
acquisition and sequenced follow-up actions, while the Morpho credit mission is
the second product path. The combined user promise is:

**Keep the stock. Unlock USDC liquidity. Let Segue enforce what happens next.**

This pivot is allowed by the user and recorded here because Base publicly frames
Coinbase Tokenized Stocks as composable DeFi assets, including lending/borrowing
and credit/yield use cases. The pivot does not permit fake integrations, guessed
addresses, unsafe wallet authority, or a claim that Morpho credit is verified
until real Base/Morpho evidence is captured.

## 1.1 Problem

Tokenized stocks can be available outside normal market hours, but the user still faces a manual loop:

`watch price → wait → act → watch again → act again`

Single limit/stop orders solve only one isolated instruction. DCA solves recurring purchases. Rebalancers target a portfolio allocation. None of those is the core Segue job.

Segue targets the gap:

`condition → bounded trade → new reference → next condition → bounded trade → ...`

Each later action exists because the previous one actually completed.

## 1.2 Job to be done

> “I already know the rules I want to follow. Execute them in the order I specified when the conditions occur, without making me monitor the market continuously.”

## 1.3 Target user

Primary target:

- rules-based investor/trader;
- eligible to access the underlying Coinbase B20 product;
- wants a small, explicit stock automation rather than an AI recommendation engine;
- values strict capital limits, transparent conditions, and an auditable onchain trail;
- may want the strategy to keep running after the app closes.

The MVP is not designed for high-frequency trading, institutional execution, discretionary AI portfolio management, or complex options-like strategies.

## 1.4 Product promise

A judge/user should understand Segue in one sentence:

**Define what should happen next in your tokenized-stock strategy, set the limits once, and let Segue execute each step only when the prior step and the new condition allow it.**

---

# 2. Product principles

1. **The sequence is the product.** Do not reduce Segue to a swap page with automation copy.
2. **User intent is precommitted.** The worker must never invent the next trade.
3. **Hard limits live onchain.** A malicious/buggy worker should fail against the vault rather than exceed the rule.
4. **Real data only.** Market context, price truth, routing, transactions, and state must come from real sources on the production path.
5. **Chain first, cache second.** Recoverability must survive browser/localStorage loss and worker restarts.
6. **Fail closed.** Stale/invalid oracle data or unsafe execution means do not trade.
7. **Small proof before polish.** Mainnet buy/sell and autonomous continuation precede major frontend styling work.
8. **Infrastructure should disappear behind the product.** Lead with stock, condition, action, limits, and sequence—not contract jargon.

---

# 3. Scope and non-goals

## 3.1 Required MVP capability

A user can:

1. connect an eligible wallet on Base;
2. inspect a curated set of verified B20 stocks with real market context;
3. construct a linear sequence of up to 8 deterministic steps;
4. define each step’s condition, action, amount, expiry, and maximum execution deviation;
5. define a total deployed-capital limit;
6. create/reuse their own Segue vault;
7. fund the vault with required strategy assets;
8. activate one live policy;
9. close the app;
10. have the worker monitor the active step and attempt it when executable;
11. have the vault independently recheck the condition and economic limits;
12. advance to the next step only after a successful trade;
13. reopen the app and recover current/history state from chain/indexed evidence;
14. cancel/pause/withdraw as the owner;
15. inspect transaction/evidence history.

## 3.2 Explicit non-goals for the hackathon MVP

Do not add unless the core path is finished and there is a specific approved reason:

- AI stock picking or autonomous recommendations;
- chat-first trading;
- social/copy trading;
- unbounded leverage/derivatives;
- governance/token issuance;
- cross-chain routing/deposits;
- fiat onramp;
- tax/accounting suite;
- generalized agent marketplace;
- complex branching/OCO trees;
- arbitrary user-written smart-contract conditions;
- high-frequency execution;
- notifications as a substitute for automation;
- passive portfolio rebalancing as the main product;
- DCA as the main product;
- a clone of Sequence’s Somnia/DreamDEX architecture.

Plain-language parsing and deterministic backtesting/replay are optional/deferred until the live required path is complete.

---

# 4. Asset and market model

## 4.1 Settlement asset

Base USDC is the settlement asset.

Current M2 verified public configuration:

- Base chain id: `8453`
- USDC: `0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913`
- USDC/USD Chainlink feed: `0x7e860098F58bBFC8648a4311b374B1D669a2bc6B`

These values are already present in `.env.example` and M2 tooling. Reverify against the official/current sources before a fresh immutable production deployment if there is any doubt.

## 4.2 M2 proof stock

The locked M2 proof asset is Coinbase NVIDIA tokenized stock (`NVDAc`).

Current verified public configuration:

- NVDAc token: `0xb20000000000000000000078ee7ce2fE4908108C`
- NVDA total-return Chainlink feed: `0x04689a41629776563E6822F76f2e57D148d28513`

M2 must prove the complete USDC → NVDAc → USDC round trip before the product claims generalized stock execution.

## 4.3 Final frontend stock catalogue

The frontend must **not** be coded as “NVDA only” even though NVDAc is the proof asset.

The catalogue should be registry-driven and support a small curated set of official Coinbase B20 stocks for the final demo/product. Before adding each stock, research and verify:

- canonical company/ticker display name;
- exact Base B20 token address;
- token decimals;
- exact relevant Chainlink total-return feed;
- feed decimals;
- observed update behavior / suitable staleness policy;
- whether 1inch currently returns a valid route for the intended pair;
- active/paused support state.

Prefer a smaller verified catalogue over a large speculative list. The coding agent may choose the practical number after research, but every displayed “tradable” asset must have provenance.

## 4.4 Registry behavior

`AssetRegistry` is the onchain allowlist/price-source registry.

Important current properties:

- token/feed pairing is immutable once registered;
- owner may add an asset or pause/resume an existing asset;
- token and feed decimals are read from chain at registration;
- prices are normalized to `1e8`;
- invalid/incomplete/stale feeds revert;
- supported B20 assets are explicitly marked `isB20`.

Do not identify an asset by ticker alone in execution logic.

## 4.5 Total-return price truth

B20 token/share representation may reflect corporate-action mechanics such as dividends/splits through the B20 multiplier. Segue therefore uses the official Chainlink **total-return feed** for supported equity condition/valuation truth instead of assuming raw token units map permanently to one underlying share.

## 4.6 24/7 trading vs feed freshness

A B20 token may remain tradable while the corresponding equity total-return feed is no longer fresh enough for Segue’s configured policy.

Therefore:

- monitoring may continue 24/7;
- execution is **not** guaranteed 24/7;
- a stale trigger/valuation feed must fail closed;
- product copy must not imply that Segue fabricates fresh equity prices outside the feed’s update window;
- the UI must expose a meaningful “price feed stale / execution paused until fresh data” state rather than a generic failure.

---

# 5. Sequence language and exact semantics

## 5.1 Sequence shape

MVP sequences are **linear**.

- minimum: 1 step;
- maximum: 8 steps;
- exactly one step may be `ACTIVE`;
- future steps are `QUEUED`;
- a completed step is `EXECUTED`;
- cancellation converts remaining active/queued steps to `CANCELLED`;
- only one policy may be live in a user vault at a time in the current contract architecture;
- historical completed/cancelled policies may coexist with the current policy.

Concurrent live sequences per vault are deferred.

## 5.2 Condition types

Supported deterministic conditions:

1. `PRICE_ABOVE`
2. `PRICE_BELOW`
3. `UP_BPS_FROM_REFERENCE`
4. `DOWN_BPS_FROM_REFERENCE`

### Absolute conditions

Examples:

- “When NVDAc is at or above $X” → `PRICE_ABOVE`
- “When NVDAc is at or below $X” → `PRICE_BELOW`

Absolute thresholds are expressed in the normalized oracle-price domain expected by the contract/UI conversion layer.

### Relative conditions

Examples:

- “When NVDAc rises 8% from this step’s activation price” → `UP_BPS_FROM_REFERENCE`
- “When NVDAc falls 5% from this step’s activation price” → `DOWN_BPS_FROM_REFERENCE`

Relative conditions use basis points and a **reference price captured when that step becomes active**.

This is crucial: later relative steps must not use the original policy-creation price. A later step receives a fresh reference only after the preceding trade succeeds and the later step activates.

## 5.3 Actions / trading pairs

Supported action classes:

1. USDC → verified B20 stock (buy)
2. verified B20 stock → USDC (sell)
3. verified B20 stock → another verified B20 stock (rotate), where the contract’s current pair rules and provider route support it
4. owner cancels/stops the sequence

The UI may phrase these as **Buy**, **Sell**, and **Rotate**, but must serialize them into the exact stored token pair.

## 5.4 Amount modes

Current contract modes:

- `FIXED`
- `PERCENT_BALANCE`

Supported percentage values for `PERCENT_BALANCE`:

- 25%
- 50%
- 75%
- 100%

UI must never offer percentage values the contract rejects.

For fixed mode, the UI must clearly indicate the asset/unit being sold (for example `$20 USDC` or a fixed B20 quantity) and must convert human units to token atomic units correctly.

## 5.5 Risk controls

Each policy/step can involve:

- policy-level maximum deployed USDC;
- vault-wide maximum deployed USDC;
- per-step exact/percentage sell amount;
- per-step maximum execution deviation (`maxDeviationBps`);
- optional step expiry;
- supported-asset allowlist;
- exact sell/buy token pair;
- one-time execution state.

The frontend should make `MAX CAPITAL` and `MAX EXECUTION DEVIATION` understandable before activation.

## 5.6 Lifecycle

Primary lifecycle:

`draft in UI → review → create/fund vault if needed → create policy → step 0 ACTIVE → worker monitors → condition true → worker obtains route → vault rechecks → trade succeeds → step EXECUTED → next step ACTIVE + reference captured → ... → policy COMPLETED`

If execution fails or safety checks fail:

- the active step remains active;
- later steps remain queued;
- the worker may retry later only when safe/idempotent;
- confirmed execution must never be repeated.

If the owner cancels:

- policy becomes cancelled;
- no later execution may occur;
- owner retains withdrawal authority over vault assets.

## 5.7 Expiry

A step with `expiresAt != 0` must not execute after expiry.

The UI must show expiry in human-readable form and should warn the user when a queued step’s expiry could occur before it ever becomes active.

Do not silently auto-extend an expired user rule.

---

# 6. Core user journeys

## 6.1 First-time user

1. Land on Segue and understand the product before connecting.
2. See that Segue is for eligible users and tokenized stocks on Base.
3. Connect wallet.
4. Switch/request Base network if necessary.
5. Inspect supported stocks.
6. Open a stock workspace.
7. Build a sequence in plain trading language.
8. Review the sequence path and risk limits.
9. If no vault exists, create canonical vault.
10. Configure/confirm executor and vault max deployed capital.
11. Fund the vault with the required starting asset.
12. Activate policy.
13. See the active step, reference price, feed freshness, current condition state, and vault balances.
14. Leave the app.

## 6.2 Returning user

1. Connect wallet.
2. Discover canonical vault from factory.
3. Reconstruct active/history state from chain/indexer.
4. Show current active policy without requiring localStorage.
5. Show most relevant live state first: current stock/condition, progress, funds, latest worker/evidence status.
6. Allow cancel/pause/withdraw actions that the owner genuinely controls.

## 6.3 Judge/demo user

The judge should be able to understand without reading architecture docs:

- which stock is being watched;
- what the condition is;
- what trade will happen;
- what happens after that trade;
- how much capital is at risk;
- why the worker cannot steal/rewrite the strategy;
- whether the browser needs to stay open;
- where the real onchain evidence is.

---

# 7. Smart-contract architecture

```text
User wallet
  │
  ├─ creates canonical vault through StockPolicyVaultFactory
  ├─ funds vault
  ├─ creates/cancels policy
  └─ retains withdrawal + executor/pause/limit controls
       │
       ▼
StockPolicyVaultFactory
  ├─ one vault per wallet
  ├─ immutable registry
  ├─ immutable Base USDC settlement token
  └─ immutable execution/allowance target
       │
       ▼
User-owned StockPolicyVault
  ├─ assets/funds
  ├─ current/historical policies
  ├─ ordered step state
  ├─ Chainlink-backed condition recheck
  ├─ exact amount + cap enforcement
  ├─ min acceptable output calculation
  ├─ one-time state transition
  └─ next-step activation only after postconditions pass
       ▲
       │ executeStep(policyId, provider calldata)
       │
Automation executor / worker
```

## 7.1 Factory requirements

`StockPolicyVaultFactory`:

- permissionless canonical one-vault-per-wallet creation for MVP;
- stores shared immutable registry, settlement token, and execution target;
- emits `VaultCreated(owner, vault, executor, maxDeployedUSDC)`;
- has no admin withdrawal or policy-authority path over user vaults.

## 7.2 Vault ownership model

The vault owner is the user wallet that created it.

Owner powers currently include:

- set executor;
- set vault max deployed USDC, subject to current deployed exposure;
- pause/unpause;
- deposit settlement asset;
- withdraw assets;
- create policy;
- cancel policy;
- execute their own step if desired because `executeStep` allows owner or executor.

The automation worker is not the owner.

## 7.3 Worker trust boundary

The worker may:

- read chain state;
- evaluate whether the contract says the step is executable;
- call a routing provider;
- supply routing calldata;
- pay gas;
- call `executeStep`;
- record evidence.

The worker may **not**:

- withdraw user funds;
- alter the stored condition;
- alter sell/buy assets;
- increase amount/caps;
- skip a step;
- activate a queued step early;
- mark a step completed without a successful trade;
- force an output below the vault’s minimum;
- execute an already completed/cancelled policy.

## 7.4 Vault execution invariants

Before accepting a trade, the vault must independently:

1. require live policy / active step;
2. reject paused/expired state;
3. read fresh Chainlink-backed condition price;
4. require the stored condition is true;
5. resolve the exact stored sell amount;
6. require sufficient balance;
7. enforce policy/vault deployed-USDC caps;
8. compute minimum acceptable buy output from verified price truth and `maxDeviationBps`;
9. snapshot balances;
10. set only the exact temporary sell allowance to the immutable execution target;
11. execute worker-supplied calldata;
12. reset allowance to zero;
13. require the exact stored sell amount actually left the vault;
14. require the intended buy-token balance increased by at least the minimum;
15. update exposure accounting;
16. only then mark the step `EXECUTED`;
17. only then activate/capture reference for the next step or complete the policy.

Any failure must revert the transaction so sequence state does not falsely advance.

## 7.5 Exposure accounting

When USDC is sold into B20 exposure:

- increase policy deployed-USDC;
- increase vault deployed-USDC;
- enforce both caps before execution.

When B20 is sold back to USDC:

- reduce policy exposure up to that policy’s amount;
- independently reduce vault-wide exposure up to the vault total;
- preserve correct accounting even if a later policy sells B20 originating from a previous policy.

---

# 8. Price, slippage, and economic safety

## 8.1 Condition truth vs execution quote

Two different truths exist:

- **Condition/valuation truth:** verified Chainlink total-return feeds.
- **Executable route:** live 1inch Classic Swap response.

A 1inch quote must never replace the oracle condition check.

## 8.2 Minimum output

The vault computes a Chainlink-derived expected cross-asset amount, scaled by token decimals, then applies the user’s `maxDeviationBps` to derive the minimum accepted output.

The worker/provider cannot lower that minimum.

## 8.3 Exact sell amount

A step must not advance after a partial or smaller-than-stored sale. Current hardening requires `sold == resolved sellAmount`.

## 8.4 Provider quote validation

Before broadcasting, the worker must validate at least:

- Base chain id;
- expected sell token;
- expected buy token;
- exact sell amount;
- quote/swap `from` semantics expected by current 1inch API;
- executor/origin semantics expected by provider;
- receiver is the Segue vault where required;
- `tx.to` equals the deployment-frozen execution target;
- native value is zero unless a future explicitly supported path requires otherwise;
- calldata is present;
- quote is current enough for safe execution;
- no unsupported partial-fill behavior is enabled;
- provider output does not require the executor to custody strategy funds.

Provider schemas are research-open because APIs can evolve; the safety invariants are not.

---

# 9. Execution provider boundary

## 9.1 Current provider: 1inch Classic Swap

0x was the original route. A real Base-mainnet USDC→NVDAc request returned HTTP 422 `BUY_TOKEN_NOT_AUTHORIZED_FOR_TRADE` due provider-side RWA/legal authorization. That is documented evidence, not a parameter bug.

Segue therefore moved only the routing adapter to **1inch Classic Swap**.

## 9.2 Immutable execution target

Before factory deployment:

1. query the live 1inch `approve/spender` endpoint;
2. verify the returned public target;
3. set it as `EXECUTION_TARGET_ADDRESS` locally;
4. deploy the factory with that target frozen;
5. later firm route responses are valid only if `tx.to` matches the frozen target.

Do not deploy with an invented/default router address.

## 9.3 Provider-switch rule

Do not replace 1inch merely because another API is easier.

A switch requires:

- verified blocker evidence;
- proof the replacement supports the required B20 production path;
- preservation of the bounded vault architecture;
- documented decision entry;
- new real route verification before production claims.

---

# 10. Automation worker

## 10.1 Locked runtime direction

- Python 3.12
- FastAPI
- SQLAlchemy
- PostgreSQL
- Web3.py or a minimal maintained EVM client
- HTTPX for provider calls
- always-on worker/service

Exact hosting provider is research-open.

## 10.2 Worker loop

Target cadence: approximately every 20–30 seconds unless provider/runtime constraints justify another reasonable interval.

For each cycle:

1. reconcile factory/vault/policy state from chain;
2. determine the canonical active policy/step;
3. call `previewExecution(policyId)`;
4. if not executable, record/refresh reason and do not request a firm route unnecessarily;
5. if executable, obtain firm 1inch transaction data;
6. validate provider response against stored/previewed rule;
7. submit `executeStep` from the dedicated executor wallet;
8. wait for receipt or track it safely;
9. re-read chain state after confirmation;
10. persist transaction/evidence metadata;
11. never retry a step already confirmed/executed;
12. continue to the next policy only from chain truth.

## 10.3 Restart behavior

On process restart:

- never trust “last attempted” local memory;
- reconcile chain state before any action;
- resume monitoring only active onchain steps;
- treat stored database records as checkpoints/evidence, not authorization;
- deduplicate transactions/events using deterministic identifiers such as vault + policyId + stepIndex + tx hash/block.

## 10.4 Error handling

At minimum distinguish:

- condition false;
- stale oracle/feed;
- insufficient balance;
- policy/vault cap;
- expired step;
- provider route unavailable;
- provider response invalid;
- RPC unavailable;
- gas/funding issue for executor;
- reverted vault execution;
- already executed due race/reconciliation;
- unsupported/paused asset.

Do not turn an unknown/provider outage into “condition false” or “safe.”

## 10.5 Secrets

Server-only/protected:

- `EXECUTOR_PRIVATE_KEY`
- `ONEINCH_API_KEY`
- private RPC credentials if used
- `DATABASE_URL`
- deployment credentials

Never place these in frontend bundles, commits, docs, screenshots, logs, or chat output.

---

# 11. Persistence and indexing

The current implementation uses a durable SQLite index for restart-safe
mission/action history and UX. PostgreSQL can replace that index at deployment
scale, but the chain remains authoritative.

The exact schema may evolve during implementation. It should be sufficient to represent the following conceptual records.

## 11.1 Vault index

Suggested fields:

- chain_id
- owner_address
- vault_address
- factory_address
- executor_address
- discovered_block
- last_reconciled_block
- paused
- vault_max_deployed_usdc
- vault_deployed_usdc

## 11.2 Policy index

Suggested fields:

- vault_address
- policy_id
- status
- created_at / created_block
- current_step
- step_count
- policy_max_deployed_usdc
- deployed_usdc
- last_reconciled_block

## 11.3 Step index

Suggested fields:

- vault_address
- policy_id
- step_index
- status
- condition asset/type/threshold/delta
- reference price
- sell token
- buy token
- amount mode/value
- max deviation
- expiry
- activated block/time
- executed block/time
- execution tx hash

## 11.4 Worker/evidence records

Suggested fields:

- deterministic work key
- preview reason/result
- observed price/update time
- quote provider
- provider request/response provenance excluding secrets
- route target
- attempted tx hash
- receipt status
- sold/bought/min output
- block number
- error category
- timestamps

Do not persist private keys or raw secret-bearing provider headers.

---

# 12. Backend/API contract

The final frontend may read some chain state directly with Viem/Wagmi and use the backend for indexed metadata/history/worker health.

Do not force an unnecessary centralized mutation API for actions the user should sign directly.

A practical backend should expose enough to support:

- supported curated asset metadata + provenance/freshness context;
- wallet/vault lookup;
- policy/history/indexed evidence lookup;
- worker status for active policy;
- execution evidence;
- health/readiness.

Exact REST route names are implementation details. Freeze them once the backend is stable so frontend work does not chase moving contracts.

Any API response that mirrors chain state should include enough identifiers to reconcile it to chain (chain id, vault, policy id, block/tx where relevant).

---

# 13. Frontend product contract

## 13.1 Stack

- Next.js
- TypeScript
- React
- Wagmi
- Viem
- Base mainnet final production mode
- ERC-8021 Builder Code attribution on supported transaction paths

## 13.2 Information architecture

Minimum meaningful surfaces:

1. **Landing / product explanation**
2. **Stock catalogue / discovery**
3. **Stock detail + sequence builder**
4. **Review / risk confirmation**
5. **Vault setup / funding state**
6. **Active Sequence workspace**
7. **History / evidence**
8. **Owner controls** — cancel, pause, withdraw where applicable

These may be routes, panels, or a unified workspace; exact composition is a design decision.

## 13.3 Stock catalogue

Each supported asset card/row should communicate useful real information, not decorative fake metrics.

Potential fields after provider research:

- company name;
- B20 ticker;
- current/last verified price context;
- feed freshness / status;
- simple real chart context where available;
- availability/support status.

Never label an underlying-equity chart as the exact B20 execution price if it is not.

## 13.4 Sequence builder

The primary builder should read like a trading rule, not a form schema.

Target visual grammar:

```text
WHEN
[NVDAc] [falls] [5% from activation price]

DO
[Buy] [$20] [NVDAc]

THEN
[when NVDAc rises 8% from the new reference]
[Sell] [50%]

THEN
[...]

MAX CAPITAL        [$50]
MAX DEVIATION      [5%]
EXPIRY             [optional]
```

The UI must make dependencies obvious: step 2 is not simultaneously live with step 1.

Show a compact sequence path such as:

`NVDAc -5% → Buy $20 → +8% from new reference → Sell 50% → ...`

## 13.5 Review screen

Before activation, summarize:

- every condition/action in human language;
- exact starting asset/funding requirement;
- maximum capital;
- maximum execution deviation;
- expiries;
- user vault address if known;
- that the automation executor cannot withdraw or rewrite the rule;
- that execution depends on fresh verified feeds and available routes;
- jurisdiction/eligibility acknowledgement.

## 13.6 Active workspace

Must show real state:

- policy status;
- active step number / total steps;
- active condition;
- reference price where relevant;
- latest verified price and freshness;
- current preview status/reason;
- vault balances;
- next queued step(s);
- past executed steps + tx links;
- worker/evidence status without pretending an offchain attempt is a confirmed trade.

## 13.7 Empty/loading/error states

Required deliberate states include:

- wallet disconnected;
- wrong network;
- no vault yet;
- vault exists but unfunded;
- no active policy;
- stale feed;
- route temporarily unavailable;
- worker unavailable but chain state still readable;
- insufficient executor gas (operator-facing, not necessarily user-facing);
- policy expired;
- cancelled/completed policy;
- unsupported/paused asset.

## 13.8 Visual direction

The product should feel like a premium modern trading interface, not a generic AI dashboard.

Priorities:

- stock/condition/action hierarchy;
- clean sequence visualization;
- clear risk limits;
- strong state transitions;
- restrained technical detail;
- real evidence links.

When frontend work begins, the coding agent should research/reference strong contemporary trading/automation interfaces and may propose visual implementation details. Do not change the product flow to mimic a reference.

---

# 14. Eligibility and compliance UX

Coinbase B20 access is jurisdiction-sensitive. The product must not knowingly enable restricted U.S. users to trade the B20 product.

For the hackathon frontend:

- clearly disclose that tokenized-stock availability is restricted by jurisdiction;
- include an eligibility acknowledgement before activation/trading actions;
- link to the relevant official product/eligibility information where appropriate;
- do not write copy implying universal availability;
- do not implement a fake compliance bypass;
- if the external provider blocks an asset/jurisdiction, treat that as a real restriction rather than an error to circumvent.

The agent may research the exact current wording/requirements from official Coinbase/Base materials before final UI copy.

---

# 15. Base Builder Code / attribution

ERC-8021/Base Builder Code attribution is required for the submission/evidence path.

Requirements:

- research the current official integration method before implementation;
- add attribution to supported Segue-originated transactions where required;
- do not alter contract semantics just to add attribution if the standard supports transaction-level tagging;
- verify at least one showcased Base transaction carries valid project attribution;
- record the evidence transaction and Builder Code in submission docs.

The exact current SDK/API wiring is research-open; B10 is not.

---

# 16. Integration ledger

The live detailed ledger is `docs/INTEGRATIONS.md` and must be reconciled as work progresses.

Required integrations:

- Base mainnet
- official Coinbase B20 assets
- official Chainlink total-return feeds
- 1inch Classic Swap / current supported execution target
- Base RPC
- PostgreSQL
- FastAPI worker
- real chart/market context source for frontend
- ERC-8021/Base Builder Code

Explicitly not required for core MVP:

- 0x (superseded after verified RWA blocker)
- AI provider
- Telegram/Telegraph
- Firestore/Vertex
- Chainlink Automation

---

# 17. Current credential / local-operator boundary

The coding agent must not request that secrets be pasted into chat or committed.

Current M2 environment names:

- `BASE_RPC_URL`
- `EXECUTOR_PRIVATE_KEY`
- `EXECUTOR_ADDRESS`
- `DEMO_OWNER_PRIVATE_KEY`
- `DEMO_OWNER_ADDRESS`
- `ONEINCH_API_KEY`
- `EXECUTION_TARGET_ADDRESS`
- `ASSET_REGISTRY_ADDRESS`
- `FACTORY_ADDRESS`
- `DEMO_VAULT_ADDRESS`
- `DATABASE_URL`
- `BASE_BUILDER_CODE`

The human builder performs secret/funding/signature steps locally when necessary. The coding agent should prepare exact commands/scripts, validate non-secret output, and stop at the secret boundary rather than inventing credentials.

Use deliberately tiny mainnet amounts for proof.

---

# 18. Failure and safety matrix

| Failure | Required behavior |
|---|---|
| Chainlink feed stale | No trade; surface stale-data reason |
| Condition false | No route request if avoidable; remain ACTIVE |
| Insufficient vault sell balance | No trade; remain ACTIVE |
| Policy/vault capital cap exceeded | No trade |
| Step expired | No trade; surface expired state |
| 1inch route unavailable | No trade; retry later safely |
| Provider target mismatches frozen target | Reject route |
| Provider returns wrong pair/amount/receiver | Reject route |
| Vault output below minimum | Revert; do not advance |
| Less than exact fixed/resolved sell amount consumed | Revert; do not advance |
| Worker submits duplicate after confirmed execution | Chain state/idempotency prevents second execution |
| Worker restarts | Reconcile chain before action |
| DB unavailable | Do not fabricate state; chain remains authority; degrade history/indexing gracefully |
| RPC unavailable | No trade; retry after recovery |
| Executor gas empty | No trade; operator alert/status; user funds remain safe |
| User cancels policy | Remaining steps cannot execute |
| User pauses vault | Worker cannot execute |
| Unsupported/paused asset | Policy creation/execution rejected as appropriate |

---

# 19. Observability and proof

For every real production-path execution, capture enough evidence to answer:

- which exact git commit was deployed/executed;
- which chain and block;
- which user/vault;
- which policy/step;
- what the stored condition was;
- what oracle price/reference made it executable;
- what asset/amount was sold;
- what asset/amount was received;
- what minimum output the vault required;
- which transaction hash proved it;
- what state the policy moved to afterward.

Do not rely only on worker logs. Prefer transaction receipts, emitted events, contract reads, balance snapshots, and explorer links.

M2 already includes deterministic snapshot/condition tooling for this purpose.

---

# 20. Testing strategy

## 20.1 Contract tests

Must cover at least:

- supported/unsupported assets;
- price normalization;
- invalid/incomplete/stale feed rejection;
- one-vault-per-wallet factory isolation;
- owner/executor authorization;
- policy creation constraints;
- exactly one active policy per vault;
- step ordering;
- reference capture timing;
- all condition types;
- fixed amount;
- 25/50/75/100% balance amount modes;
- expiry;
- pause/cancel;
- policy/vault caps;
- exact-sell enforcement;
- unsafe output rejection;
- temporary allowance reset;
- completed-step one-time execution;
- multi-user/cross-vault isolation;
- cross-policy vault exposure accounting.

M1’s locked contract milestone has already passed 24 Foundry tests. Do not rewrite the tested contract architecture casually.

## 20.2 Provider adapter tests

Use fixtures/mocks for parsing/validation, but also perform real provider verification when credentials are available.

Test:

- expected 1inch response parsing;
- malformed response;
- wrong target;
- wrong pair;
- wrong amount;
- wrong receiver/origin/from semantics;
- missing calldata;
- nonzero native value where unsupported;
- stale/invalid route data where detectable.

## 20.3 Worker tests

Test:

- preview false → no execution;
- preview ready → firm route + execution path;
- duplicate cycles/idempotency;
- restart reconciliation;
- receipt success/failure;
- RPC/provider transient failures;
- completed policy is not retried;
- two-step chaining state changes;
- database checkpoint recovery.

## 20.4 Backend/frontend integration

Test real API/state shapes. Avoid a separate fake frontend data model.

## 20.5 Browser verification

Before submission verify at least:

- connect/wrong-network behavior;
- stock selection;
- sequence construction;
- review;
- canonical vault lookup/creation;
- funding/activation path;
- active state after reload;
- history/evidence;
- cancel/withdraw controls;
- mobile usability;
- public URL accessibility;
- no dead buttons;
- no fake hardcoded stock/tx state.

## 20.6 Regression rule

Any real mainnet/browser bug that can be reproduced reasonably should receive a regression test.

---

# 21. Completion gates B1–B12

These gates are binding evidence requirements, not suggestions.

## B1 — Real B20 route exists

1inch returns a firm executable Base-mainnet transaction for at least one official Coinbase B20 ↔ USDC pair, using the deployed Segue vault/executor semantics and the factory’s frozen execution target.

## B2 — Real B20 buy

A deployed Segue vault completes a real Base-mainnet USDC → official B20 purchase through the production path and receives the B20 output.

## B3 — Real B20 sell

The same bounded path sells all/part of a B20 balance back to USDC.

## B4 — Real Chainlink condition

The deployed contract reads the exact official total-return feed, accepts a true condition, rejects a false condition, and fails safely on stale data.

## B5 — Browser-closed automation

A deployed worker advances an ACTIVE policy while the frontend is not open.

## B6 — Real chaining

Step 2 cannot execute before step 1. After successful step 1, step 2 becomes ACTIVE with the expected new reference price and can later execute.

## B7 — Worker cannot escape limits

Tests and real-path evidence cover wrong token, wrong/excess/partial sell, stale/completed step, unsafe output/deviation, and unauthorized withdrawal boundaries.

## B8 — Multi-user isolation

Two wallets resolve to different canonical vaults and cannot alter/withdraw from each other’s vaults.

## B9 — Onchain recovery

After browser/local cache state is cleared, active/completed policies reconstruct from chain/indexed evidence.

## B10 — Builder Code attribution

At least one showcased Base transaction contains valid Segue ERC-8021/Base Builder Code attribution.

## B11 — Public production flow

A judge can open the public URL, connect an eligible wallet, inspect real market context, build/review a sequence, and reach the real activation path without dead controls.

## B12 — Submission proof

Public demo video, X post tagging `@buildonbase`, live project URL, Builder Code, submission tweet URL, and official form are complete before the official deadline.

**Segue is not submission-ready until B1–B12 pass or a requirement is explicitly amended by documented new evidence.**

---

# 22. Milestone plan and current state

Every milestone ends with:

`inspect → implement → test → real verification where required → reconcile PRD/integration ledger → commit → push → report exact SHA`

| Milestone | Status | Evidence / stop condition |
|---|---|---|
| M0 Repo/source of truth | **COMPLETE** | PRD/build rules/agent instructions/docs/env/CI baseline |
| M1 Contract state machine | **COMPLETE** | `615b1908856670601e2d9ae05fc1d4ec52cc66f8`; Foundry build + 24 tests |
| M2 Real Base-mainnet buy/sell | **IN PROGRESS — tooling audited** | Route/deploy/vault/policy/condition/snapshot tooling passes local audit; B1–B4 still require protected provider/mainnet execution |
| M2C Morpho Blue credit mission | **MAINNET PROOF / SIGNATURE READY** | Locked NVDAc/USDC market, real collateral + borrow evidence, live proposal/risk, unsigned close path |
| M3 Autonomous worker | **IMPLEMENTED LOCALLY** | Live Morpho reads, receipt/postcondition reconciliation, retry/idempotency; public worker host still requires deployment credentials |
| M4 Persistence/history/multi-user | **IMPLEMENTED LOCALLY** | Durable SQLite missions/actions/snapshots/timeline and restart recovery; PostgreSQL scale-out remains future work |
| M5 Trading frontend | **IMPLEMENTED LOCALLY** | Frozen landing surface and `/app.html` position workspace read live Morpho position/risk/liquidity/evidence in browser |
| M6 Production deployment/evidence | **PREPARED** | Docker/unified FastAPI service and deployment runbook; public host + Builder Code evidence remain credential/funding work |
| M7 Submission | NOT STARTED | B12 + final docs/demo/freeze |

## 22.1 M2 current exact handoff state

Current repository HEAD before this PRD revision was `414916b539f2d360c0caefa43e729e8e6de940e7`.

Since the initial 1inch provider switch, the repo added/hardened:

- deployment and read-only verification scripts;
- separate demo-owner vs gas-only executor roles;
- canonical demo vault creation/funding path;
- real two-step M2 round-trip policy creation;
- firm buy/sell quote validation;
- bounded `executeStep` broadcast path where executor calls the vault, not 1inch directly;
- deterministic before/after balance + policy + block + git-SHA snapshots;
- true-condition and deliberately-false-condition evidence probes;
- artifact verification and regression tests;
- secret-scanning hardening.

M2 is **not complete** until B1–B4 have real evidence.

The 2026-09-07 continuation audit hardened block-pinned evidence, exact stale
revert capture, target/feed/calldata validation, distinct owner/executor roles,
post-round-trip false-policy setup, and ERC-8021 suffixing on supported M2 script
calls. It produced local test evidence only; see `docs/M2_AUDIT.md`.

The immediate human-only dependencies may include:

- a valid `ONEINCH_API_KEY` stored locally;
- current live execution target resolved from 1inch;
- deliberately small Base ETH balances for required gas wallets;
- deliberately small demo-owner USDC for the proof trade;
- a fresh enough NVDA total-return feed for the condition proof.

Follow `docs/M2_MAINNET.md` rather than inventing a new M2 flow.

## 22.2 M3 autonomous worker

Required outcome:

A deployed always-on worker can discover/reconcile the active policy, wait until the contract reports it ready, obtain/validate a route, execute the exact step, survive restart, and advance a later step without the browser.

Stop condition: B5–B6 with real deployed evidence.

## 22.3 M4 persistence/history/multi-user

Required outcome:

- durable SQLite-backed indexing/checkpoints for the current single-instance API;
- PostgreSQL adapter for multi-instance scale-out (optional deployment upgrade);
- restart-safe reconciliation;
- queryable execution history/evidence;
- two-wallet isolation demonstration;
- recovery after browser/localStorage clearing.

Stop condition: B7–B9.

## 22.4 M5 frontend

Required outcome:

The product is understandable and usable as a real stock automation product against the actual contracts/backend/data.

Stop condition: full browser journey works against real deployed services without mocks or dead controls.

## 22.5 M6 production/evidence

Required outcome:

- production worker;
- production/public frontend;
- exact contract addresses documented;
- Builder Code attribution proven;
- at least one complete unattended sequence evidence bundle;
- mobile/desktop browser verification.

Stop condition: B10–B11.

## 22.6 M7 submission

Required outcome:

- README/docs truth audit;
- concise demo video;
- X post;
- public URL;
- Builder Code;
- official form;
- exact final SHA frozen.

Stop condition: B12.

---

# 23. Codex / coding-agent execution protocol

When handing this repository to Codex or another coding agent, the agent must begin by reading:

1. `AGENTS.md`
2. `BUILD_RULES.md`
3. `PRD.md`
4. `docs/INTEGRATIONS.md`
5. the current milestone doc (currently `docs/M2_MAINNET.md`)
6. recent commits and current repository tree

Then it must state, before changing code:

- current HEAD;
- what is already implemented;
- what is only locally tested;
- what requires real external/mainnet proof;
- current milestone;
- exact next stop condition;
- any credential/funding action that only the human builder can perform.

The agent has freedom to research and choose routine implementation details **inside** the locked product architecture.

It should not ask the user to make decisions that can be resolved through official documentation, repo inspection, tests, or safe provider research.

It must stop/ask before:

- replacing a locked provider/chain/oracle architecture;
- weakening user-owned vault authority/safety;
- cutting dependent sequencing;
- switching a required real path to simulation;
- making a destructive production change;
- inventing unsupported market data or addresses.

At the end of each milestone report compactly:

**FINAL GITHUB HEAD**  
**IMPLEMENTED**  
**TESTS**  
**REAL PROVIDER / MAINNET EVIDENCE**  
**DEPLOYMENT**  
**PERSISTENCE / LOG EVIDENCE**  
**FRONTEND / BROWSER VERIFICATION**  
**BLOCKERS**  
**MILESTONE READY: YES/NO**

A report is not proof; the reviewer should inspect the diff/evidence before accepting it.

---

# 24. Demo path

Target demo: approximately 2–3 minutes unless official rules specify otherwise.

Suggested flow:

1. Open Segue and show a real supported B20 stock with real market context.
2. Build a small dependent sequence in plain language.
3. Show the visual path and hard limits.
4. Review and activate/fund once.
5. Explain in one sentence that the user vault owns funds/rules and the worker only attempts the stored action.
6. Leave/close the frontend.
7. Show real autonomous evidence: condition becomes ready → worker attempts → vault rechecks → 1inch-routed Base transaction succeeds → next step becomes active.
8. Show the later dependent step/evidence if available.
9. Reopen the app and show the same state recovered from chain/indexer.
10. Open explorer/evidence and Builder Code attribution.

Never present a mocked/simulated transaction as the autonomous production proof.

---

# 25. Submission requirements

Track and reverify the current official quest requirements before final submission.

Current requirements already being tracked include:

- project materially helps people trade/use Coinbase Tokenized Stocks on Base;
- restricted users/jurisdictions are handled appropriately;
- public demo video;
- X post tagging `@buildonbase`;
- live project URL;
- Base Builder Code;
- submission tweet URL;
- official form before the official deadline.

Do not rely on an old third-party deadline/rubric if an official current page contradicts it.

---

# 26. Architecture / hardening decision ledger

## 2026-09-05 — Exact executor spend

The executor may choose route calldata but may not cause a fixed/resolved step to advance after selling less than the stored amount. Vault execution requires exact sell consumption in addition to minimum-output postconditions.

## 2026-09-05 — Cross-policy vault exposure

A later policy selling B20 acquired by a previous completed policy must reduce vault-wide deployed-USDC exposure even when the new policy’s local exposure began at zero. Policy-local and vault-wide reductions are bounded independently.

## 2026-09-05 — Quote-math precision

Minimum-buy computation scales by token-decimal difference before principal division to preserve useful precision between 6-decimal USDC and B20 assets.

## 2026-09-05 — Routing provider changed from 0x to 1inch

Verified evidence forced this change:

1. Base mainnet, official NVDAc, and configured Chainlink feeds were reachable.
2. The live 0x USDC→NVDAc request returned `BUY_TOKEN_NOT_AUTHORIZED_FOR_TRADE` due provider legal/RWA authorization.
3. 1inch publicly supports Coinbase B20 stocks on Base.
4. Only the routing adapter changed; Base/B20/Chainlink/vault/sequence thesis stayed intact.
5. 1inch still requires real Segue provider/mainnet verification before B1–B3 are claimed.

## 2026-09-06 — Separate demo owner and executor roles

M2 tooling separates the user/demo-owner wallet from the gas-only executor. Do not collapse them merely to simplify proof: the product claim depends on demonstrating that the worker can execute without owning the strategy funds.

## 2026-09-06 — Deterministic M2 evidence snapshots

M2 records block number, git SHA, owner/executor, policy/current-step state, deployed-cap state, and vault USDC/B20 balances before/after real actions so mainnet completion is evidence-based rather than narrative.

## 2026-09-09 — Morpho Blue credit mission proof

Morpho Blue is the active credit rail for the B20 mission. The locked Base
market is `0x91360eea2686ef7ce4966b4e82cf6ff712af02baf0f7211459780d9f5af1612a`.
The reference wallet has `2,323,053` NVDAc atomic collateral and
`1,000,000,000,000` borrow shares; the approval, collateral-supply and borrow
transactions are recorded in the durable evidence index. The mission API uses
the direct Morpho oracle and share-based close semantics. This credit proof does
not close the separate 1inch vault buy/sell gates.

---

# 27. Final definition of done

Segue is complete for submission only when all required items are true:

- [x] repository/source-of-truth baseline exists;
- [x] build rules and agent instructions exist;
- [x] bounded contract state machine is locally verified;
- [x] M2 real-path scripts/evidence tooling are prepared;
- [x] Morpho Blue NVDAc/USDC credit mission has a real Base-mainnet reference position and signature-ready full-close path;
- [ ] current 1inch B20 firm route is live-verified;
- [ ] contracts are deployed to Base mainnet;
- [ ] deployed registry contains verified official assets/feeds;
- [ ] real USDC → B20 buy succeeds through the Segue vault;
- [ ] real B20 → USDC sell succeeds through the same bounded path;
- [ ] real true/false/stale Chainlink behavior is captured;
- [ ] autonomous worker is deployed;
- [ ] browser can be closed while a real step executes;
- [ ] real dependent step 2 activates only after step 1;
- [x] SQLite mission/action indexing and restart recovery for the current credit path;
- [ ] PostgreSQL multi-instance scale-out;
- [ ] worker cannot escape stored limits;
- [ ] second-wallet isolation is demonstrated;
- [ ] state recovers without localStorage;
- [ ] production UI uses real stock/price/history data;
- [ ] public frontend is browser-verified on desktop and mobile;
- [ ] Builder Code attribution is proven on evidence transaction(s);
- [ ] README/docs match current implementation exactly;
- [ ] demo video/X post/form are complete;
- [ ] exact final commit SHA is frozen.

If a required unchecked item remains, do not call Segue a complete submission.

---

# 28. PRD maintenance protocol

After every meaningful milestone:

1. inspect repository HEAD and diff;
2. update milestone status/evidence here;
3. update `docs/INTEGRATIONS.md`;
4. update milestone-specific docs when commands/evidence changed;
5. keep blocked/difficult requirements visible;
6. never convert planned/local work into deployed/mainnet wording;
7. add dated decision entries for architecture changes caused by verified evidence;
8. commit/push the reconciliation before moving on.

---

# 29. Primary research references

Prefer official/current sources and reverify details that can change.

- Base tokenized stocks: https://blog.base.org/tokenized-stocks
- B20 engineering / total-return feeds: https://blog.base.dev/b20-tokenized-stocks-on-base
- Base stocks directory: https://base.org/stocks
- Base Request for Builders: https://blog.base.org/request-for-builders-tokenized-stocks
- Builder Codes / ERC-8021: https://blog.base.dev/builder-codes-and-erc-8021-fixing-onchain-attribution
- Coinbase CDP Node: https://docs.cdp.coinbase.com/data/node/overview
- Chainlink feeds: https://data.chain.link/feeds
- 1inch Coinbase Tokenized Stocks support: https://1inch.com/blog/post/coinbase-tokenized-stocks
- 1inch Classic Swap API: https://business.1inch.com/portal/documentation/apis/swap/classic-swap/introduction
- 1inch API authentication: https://business.1inch.com/portal/documentation/apis/authentication

Historical evidence and current provider status belong in `docs/INTEGRATIONS.md`.
