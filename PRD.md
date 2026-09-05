# Product Requirements Document — Segue
**Product:** Segue  
**Hackathon:** Base Builder Quest — Tokenized Stocks  
**Target deadline:** September 9, 2026, 11:59 PM EST  
**Status:** Product direction locked; implementation not started  
**Source of truth:** This file is the build contract. Changes require a documented blocker or new verified evidence.

---

## 1. Product thesis

Segue is a 24/7 conditional execution layer for Coinbase Tokenized Stocks on Base.

A user programs a sequence of stock actions once — for example:

> If NVDAc falls 5% from my reference price, buy $20.  
> After that purchase, if NVDAc rises 8% from the new reference, sell half.  
> Then, if AAPLc falls below my chosen price, rotate the proceeds into AAPLc.  
> Never deploy more than $50 and never execute outside my price-deviation limit.

The user does not need to keep the app open. A background executor monitors the onchain conditions and advances the sequence automatically. The user's personal vault enforces the exact rule, token allowlist, sequence state, and spending limits onchain.

Segue does **not** predict stocks. It executes rules the user already chose.

---

## 2. Problem

Coinbase Tokenized Stocks can trade 24/7 on Base, but users still have to monitor markets and manually act when conditions occur.

Existing trading products already provide manual swaps, single limit orders, DCA, and portfolio rebalancing. The gap Segue targets is **dependent multi-step execution**:

- one action activates only after a previous action actually succeeds;
- later actions can reference the price at the previous execution;
- the sequence can move between different tokenized stocks;
- the whole workflow remains bounded by the user's hard spending and execution limits;
- the workflow continues with the browser closed.

### Job to be done

> "I know the rules I want to follow. Execute them for me when the conditions occur, in the order I specified, without making me watch the market all day."

---

## 3. Target user

A rules-based investor or active trader in an eligible non-US jurisdiction who:

- already knows what prices/percentage moves should trigger their action;
- wants exposure to Coinbase Tokenized Stocks;
- does not want to monitor markets continuously;
- wants strict control over maximum capital deployed;
- values an auditable onchain execution trail.

The product must not enable trading for U.S. users. The interface must include an eligibility acknowledgement and a clear statement that Coinbase Tokenized Stocks are only available in eligible jurisdictions outside the U.S.

---

## 4. Differentiation

The differentiator is **the sequence**, not merely automation.

A normal limit order:

`NVDA <= X → buy`

Segue:

`condition → trade → new reference → next condition → next trade → next condition...`

Each later step is inactive until the previous step succeeds. A backend worker may decide *when to attempt execution*, but it cannot change what the user authorized.

### Explicitly rejected product directions

- generic stock brokerage;
- "AI, buy NVDA";
- generic AI stock picker;
- DCA-only product;
- single limit/stop order product;
- passive portfolio rebalancer;
- Avelune-style TAKE/PASS training journey;
- copy of Sequence's DreamDEX/Somnia architecture;
- social trading, leaderboards, copy trading, lending, or extra DeFi features for this submission.

---

## 5. Supported MVP workflow

### Conditions

MVP supports these deterministic condition types:

1. `PRICE_ABOVE`
2. `PRICE_BELOW`
3. `UP_BPS_FROM_REFERENCE`
4. `DOWN_BPS_FROM_REFERENCE`

A reference price is captured:
- when a policy is activated for its first step; or
- immediately after a successful prior step when the next step becomes active.

All condition checks use the Coinbase Tokenized Stock's verified Chainlink total-return feed.

### Actions

MVP supports:

1. Buy a verified B20 stock using USDC.
2. Sell a verified B20 stock into USDC.
3. Rotate a verified B20 stock into another verified B20 stock.
4. Stop the sequence.

Amount modes:
- fixed token/USDC amount;
- percentage of the vault's available balance for sell actions: 25%, 50%, 75%, or 100%.

### Sequence semantics

- A policy contains ordered steps.
- Exactly one step is `ACTIVE` at a time.
- Later steps are `QUEUED`.
- A successful trade marks the active step `EXECUTED`.
- The next queued step becomes active and records its new reference price.
- A failed quote or unsafe execution does **not** advance the sequence.
- A cancelled/expired policy executes nothing further.
- Each step can execute only once.

MVP is a **linear dependent sequence**. Generic branching/OCO trees are deferred. We will not add them before submission unless all required milestones are already complete.

---

## 6. Trading/data model

### Verified assets only

Never identify a Coinbase Tokenized Stock by ticker alone.

The application maintains a verified asset registry sourced from Base's official Coinbase Tokenized Stocks list. Each supported asset record must include:

- ticker;
- company name;
- B20 contract address;
- token decimals;
- Chainlink total-return feed address;
- feed decimals;
- active/paused status.

USDC on Base is the settlement asset.

### B20 corporate actions

B20 balances do not permanently map 1 token to 1 underlying share because the B20 multiplier changes for splits/dividends.

For user-facing valuation and execution conditions, use the corresponding **Chainlink total-return feed**, which Base states already incorporates the multiplier. The app must not implement percentage triggers from a naive raw token balance or an unrelated stock feed.

---

## 7. Architecture

```text
Browser wallet
     |
     | create personal vault / deposit USDC / save policy
     v
StockPolicyVaultFactory
     |
     v
User-owned StockPolicyVault
- holds only that user's strategy assets
- stores policy steps
- stores active step + reference price
- enforces supported assets
- rechecks Chainlink condition onchain
- enforces max capital / per-step amount
- enforces max price deviation
- enforces one-time step execution
- owner can pause/cancel/withdraw
     ^
     |
     | executeStep(stepId, 0x target/calldata)
     |
Automation Worker (FastAPI service)
- has a dedicated gas-only Base wallet
- never owns user funds
- reads active vaults/steps
- asks vault whether a step is executable
- obtains a firm 0x quote only when needed
- submits execution
- records tx/evidence
     |
     +--> CDP Base RPC
     +--> 0x Swap API
     +--> PostgreSQL index/cache
```

### Why a personal vault

The user needs automation after leaving the browser. The worker therefore needs authority to submit the transaction later.

Rather than giving the worker a user's private key, each user gets a personal smart-contract vault. The vault gives the worker only one power: attempt execution of the rule the user already stored.

The worker cannot:
- change a condition;
- change the next token;
- change the amount;
- raise the user's risk cap;
- withdraw;
- execute a completed step;
- trade an unverified token.

### Factory

`StockPolicyVaultFactory`:
- one vault per wallet for MVP;
- deploys vaults with immutable/shared trusted configuration;
- emits `VaultCreated(owner, vault)`;
- holds no user funds;
- has no withdrawal authority over user vaults.

### Vault

Core storage:

```text
owner
executor
paused
maxDeployedUSDC
supported registry/config

Policy
- policyId
- status
- createdAt
- currentStep
- maxDeployedUSDC

Step
- status
- conditionAsset
- conditionFeed
- conditionType
- threshold / deltaBps
- referencePrice
- sellToken
- buyToken
- amountMode
- amount
- maxDeviationBps
- expiresAt
```

Core events:

```text
PolicyCreated
StepActivated
ExecutionAttempted
StepExecuted
ExecutionRejected
PolicyCompleted
PolicyCancelled
PausedSet
Deposited
Withdrawn
```

---

## 8. 0x execution design

0x is the routing/quote provider. Base lists 0x as a supported tokenized-stock swap integration, and 0x Swap API supports Base.

### Quote flow

The worker requests a firm 0x Swap API quote with:

- `chainId=8453`;
- `taker=<user vault>`;
- `recipient=<user vault>`;
- verified sell token;
- verified buy token;
- exact amount defined by the active step.

The API key remains server-side.

### Contract safety boundary

The vault must not blindly trust a quote.

On every execution:

1. Re-read the active Chainlink condition.
2. Recheck step status and expiry.
3. Derive the exact maximum sell amount from the stored rule.
4. Calculate the minimum acceptable buy amount from verified total-return prices and the user's `maxDeviationBps`.
5. Snapshot the buy-token balance.
6. Approve the official 0x allowance target for **only the exact sell amount** needed for this call.
7. Call the fixed, verified 0x execution target returned by the supported integration path.
8. Reset allowance to zero where appropriate.
9. Require the vault's buy-token balance to have increased by at least the onchain-computed minimum.
10. Only then mark the step executed and activate the next step.

If any postcondition fails, the whole transaction reverts and the sequence does not advance.

This means the worker can supply routing calldata but cannot use it to make the vault accept an unbounded or wrong-asset trade.

---

## 9. Automation worker

### Runtime

Reuse the proven server-side execution pattern from Avelune, not its product logic.

Recommended stack:
- Python 3.12
- FastAPI
- SQLAlchemy
- PostgreSQL
- a dedicated always-on worker loop in the same deployable service or a separate worker process
- Web3.py or a minimal EVM client for contract reads/writes
- HTTPX for 0x

### Loop

Every ~20–30 seconds:

1. Read/index active vaults and active steps.
2. Call the vault's view method (`canExecute` / equivalent).
3. If false: do nothing.
4. If true: request a firm 0x quote.
5. Validate quote chain, taker, recipient, token pair, amount, and target.
6. Submit `executeStep`.
7. Wait for receipt.
8. Persist the transaction hash and decoded result.
9. Do not retry a confirmed/executed step.

### Restart behavior

The blockchain is the source of truth.

PostgreSQL stores:
- indexing cursors/checkpoints;
- friendly policy names/UI metadata;
- provider request metadata;
- transaction evidence;
- worker health.

On restart the worker must reconcile with onchain policy/step state before taking action. A missing DB row must not make an onchain policy disappear.

---

## 10. Frontend

### Stack

- Next.js
- TypeScript
- React
- Wagmi + Viem
- Base mainnet only in final production mode
- ERC-8021 Builder Code attribution from the start

### Primary screen

The product must visually read as a trading product.

For a selected stock:

**NVDAc — NVIDIA**
- current verified total-return/reference price;
- current executable 0x quote where useful;
- 24/7 status;
- real chart context.

Then the rule:

```text
WHEN
[stock] [falls/rises/reaches] [condition]

DO
[buy/sell/rotate] [$ / %]

THEN
[next condition + action]

MAX CAPITAL
[$...]

MAX EXECUTION DEVIATION
[...%]

[Review sequence] [Activate]
```

Also show a simple path:

`NVDAc condition → Buy → +8% condition → Sell 50% → AAPLc condition → Buy`

### Chart

For the hackathon frontend:
- use real external market-chart data only;
- label the chart clearly if it represents the underlying listed stock rather than the B20 pool;
- show the actual B20/Chainlink reference and 0x executable quote separately;
- never fabricate a price series.

A TradingView embed for underlying-stock context is acceptable if implemented accurately and labelled. The automation itself must rely on the verified Chainlink B20 total-return feed, not the chart widget.

### Important UX rule

Infrastructure must not lead the experience.

The user flow is:

`connect → inspect stock → build sequence → review risk → create/fund vault if needed → activate → live`

Not:

`connect → learn contracts → configure executor → approve protocols → eventually see stocks`

---

## 11. AI/model boundary

**No AI API is required for the core submission.**

The product's value is deterministic automation, not prediction.

Do not add Gemini/OpenAI/Claude to the core path.

Optional post-core convenience:
- a plain-language rule parser that fills the structured form;
- if an LLM is used later, every generated rule must be validated against the fixed capability registry and explicitly shown to the user before activation.

This is deferred until the real mainnet automation loop is complete.

---

## 12. Integrations ledger

| Integration | Purpose | Required | Credential / cost | Definition of complete |
|---|---|---:|---|---|
| Base mainnet | execution network | YES | gas ETH | deployed contracts + real tx |
| Coinbase B20 assets | stock assets | YES | none | verified official addresses used |
| Chainlink total-return feeds | trigger + valuation source | YES | onchain reads, no API key | contract reads verified feed |
| 0x Swap API | route/quote B20 trades | YES | API key; free developer access expected to be sufficient | real B20 quote + executed swap |
| CDP Base Node | reliable RPC | YES | free project/RPC available | deployed app uses private RPC |
| Base Builder Code / ERC-8021 | hackathon attribution | YES | free registration | present on real Base tx |
| PostgreSQL | worker checkpoint/history cache | YES | Railway/other DB | restart-safe reconciliation |
| TradingView or real chart source | trading UI context | YES for polished UI, not execution | likely no paid API if widget used | real labelled chart renders |
| AI provider | optional rule parser | NO | none for MVP | deferred |
| Telegram | none | NO | — | do not add |
| Telegraph | none | NO | — | do not add |
| Firestore | none | NO | — | do not add |
| Vertex/Gemini | none in core | NO | — | do not add |
| Chainlink Automation | not needed for MVP | NO | — | do not add |

---

## 13. Secrets and external setup required

### Required from the builder

1. **Dedicated Base automation/deployer wallet**
   - private key stored only in local/deployment secrets;
   - small amount of Base ETH for contract deployment + worker gas;
   - this wallet does **not** hold user strategy funds.

2. **Browser test wallet**
   - regular Rabby/MetaMask/Coinbase wallet;
   - small Base ETH for user transactions;
   - USDC for the real demo trade.

3. **0x API key**
   - server-side only.

4. **CDP account + private Base RPC endpoint**
   - free mainnet RPC tier is sufficient for the hackathon.

5. **Base Builder Code**
   - register free through Base's builder tooling;
   - integrate before the first evidence transactions we plan to showcase.

6. **PostgreSQL connection**
   - Railway PostgreSQL, Neon, Supabase, or equivalent.
   - If an existing Railway setup is already available, prefer it over creating new infrastructure.

### Optional

- Basescan API key for automated source verification.
- Deployment platform credentials (Vercel/Railway) if not already connected.

### Expected direct spend

- Base ETH for deployment/executor gas.
- Small USDC amount for real B20 trades.
- No AI subscription required.
- CDP/Base RPC and 0x developer access should be started on available free tiers unless an actual limit blocks the build.
- Hosting/database cost depends on existing Railway/Vercel plan; do not buy a new service unless the existing/free tier cannot support an always-on worker.

---

## 14. Known risks / blockers to track from day one

These are not reasons to redesign. They are explicit gates the build must clear.

### B1 — Real B20 route exists
**Pass condition:** 0x returns an executable Base mainnet quote for at least one official Coinbase B20 stock ↔ USDC pair using the vault as taker/recipient.

### B2 — Vault can execute real B20 swap
**Pass condition:** a deployed user vault completes a real Base mainnet USDC → B20 purchase through the production execution path, and the B20 output lands in that vault.

### B3 — Sell path closes the loop
**Pass condition:** the same vault can sell all/part of a B20 balance back to USDC through the same bounded execution path.

### B4 — Chainlink condition is correct
**Pass condition:** contract reads the official total-return feed and rejects execution when false / allows execution when true.

### B5 — Automation works with browser closed
**Pass condition:** an ACTIVE policy is advanced by the deployed worker without the frontend being open.

### B6 — Sequence really chains
**Pass condition:** step 2 cannot execute before step 1; after step 1 succeeds, step 2 becomes ACTIVE with the expected new reference price.

### B7 — Worker cannot escape user limits
**Pass condition:** tests and real-path checks prove wrong token, excess sell amount, stale/completed step, unsafe price deviation, and unauthorized withdrawal fail.

### B8 — Multi-user isolation
**Pass condition:** two wallets resolve to different vaults and cannot alter/withdraw from each other's vaults.

### B9 — Onchain recovery
**Pass condition:** clear browser storage and reconnect; active/completed policies reconstruct from chain + indexer, not localStorage.

### B10 — Builder Code attribution
**Pass condition:** at least one showcased Base transaction contains valid ERC-8021 attribution for our registered code.

### B11 — Public production flow
**Pass condition:** judge can open live URL, connect an eligible wallet, inspect real stock data, build/review a policy, and reach activation without dead controls.

### B12 — Submission proof
**Pass condition:** public demo video, X post tagging @buildonbase, live URL, Builder Code, and form are all ready before deadline.

**The project is not submission-ready until B1–B12 are either PASS or explicitly ruled unnecessary by a PRD amendment supported by new evidence.**

---

## 15. Build milestones

Every milestone ends with:
1. tests/verification;
2. commit;
3. push to GitHub;
4. PRD/status reconciliation;
5. explicit `MILESTONE READY: YES/NO`.

### Milestone 0 — Repository + source of truth

Outcome:
- clean repo;
- this PRD;
- BUILD_RULES.md;
- `.env.example`;
- architecture folders;
- integration ledger;
- official verified asset registry format;
- CI baseline.

Stop condition:
- repo builds/tests from clean clone;
- no secrets committed.

### Milestone 1 — Contract state machine

Outcome:
- factory + user vault;
- policy/step state;
- condition types;
- budgets;
- pause/cancel/withdraw;
- Chainlink checks;
- exact one-step activation;
- 0x bounded-call safety boundary;
- Foundry tests.

Stop condition:
- contract test suite proves state, access control, risk, idempotency, postconditions.

### Milestone 2 — Real Base mainnet buy + sell

Outcome:
- deploy exact tested contracts;
- fund one personal vault with a tiny USDC amount;
- production 0x quote;
- real official B20 buy;
- real B20 sell;
- record tx hashes and before/after balances.

Stop condition:
- B1, B2, B3, B4 pass.

**Do not start UI redesign before this milestone passes.**

### Milestone 3 — Autonomous worker

Outcome:
- worker indexes/reconciles policies;
- active condition becomes executable;
- obtains 0x quote only when needed;
- submits and records real execution;
- safe retry/idempotency;
- restart recovery.

Stop condition:
- B5 and B6 pass with real deployed service.

### Milestone 4 — Persistence + history + multi-user

Outcome:
- PostgreSQL checkpoints/history;
- two-wallet isolation;
- chain recovery after clean browser state;
- execution timeline.

Stop condition:
- B7, B8, B9 pass.

### Milestone 5 — Trading frontend

Outcome:
- wallet connect;
- stock list;
- real price/chart context;
- structured sequence builder;
- review/risk;
- just-in-time vault creation/funding;
- activate;
- live/history surfaces;
- cancel/withdraw.

Stop condition:
- deployed browser flow works against real backend/contracts.

### Milestone 6 — Deployment + final mainnet evidence

Outcome:
- production frontend;
- production worker;
- exact production contract addresses;
- Builder Code attribution;
- one complete real automated sequence captured as evidence.

Stop condition:
- B10 and B11 pass.

### Milestone 7 — Submission

Outcome:
- README truth audit;
- 1–2 line problem statement;
- Loom demo;
- public X post tagging @buildonbase;
- live URL;
- Builder Code;
- submission form.

Stop condition:
- B12 pass;
- exact final commit frozen.

---

## 16. Demo path

Target demo: under 3 minutes.

1. Open a real Coinbase Tokenized Stock and show actual reference price/chart context.
2. Build a small sequence with a tiny real capital limit.
3. Show the path visually.
4. Activate and fund once.
5. Explain that the worker has no authority to change the rule or withdraw.
6. Close/leave the app.
7. Show a previously captured or live real autonomous transition:
   - condition true;
   - onchain condition rechecked;
   - 0x route used;
   - Base transaction succeeded;
   - next step activated.
8. Reopen dashboard and show the same state reconstructed from chain.
9. Open Basescan evidence with Builder Code attribution.

No simulated trade may be presented as the real autonomous path.

---

## 17. Submission requirements

Current Base Builder Quest requirements:

- build a project that helps people trade or use Coinbase Tokenized Stocks on Base;
- projects enabling trading for U.S. users are out of scope;
- public Loom demo;
- post demo on X and tag `@buildonbase`;
- live project URL;
- Base Builder Code;
- submission tweet URL;
- submit the official form before Sep 9, 2026, 11:59 PM EST.

Prize pool:
- $2,000 top project;
- remaining $3,000 split across five finalists.

No weighted public judging rubric is currently published; Base states winners are selected at its discretion.

---

## 18. Non-goals before submission

Do not add before the required loop is complete:

- AI stock recommendations;
- portfolio optimization;
- Aave/Morpho lending;
- social/copy trading;
- mobile native app;
- cross-chain deposits;
- fiat onramp;
- arbitrary branching graph;
- notifications/Telegram;
- agent marketplace;
- governance;
- token issuance;
- performance promises;
- backtesting as a required activation gate.

A deterministic replay can be added only after all required blockers are cleared.

---

## 19. Decision ledger

### Locked

- Product name: Segue.
- Network: Base mainnet.
- Assets: official Coinbase Tokenized Stocks (B20) + Base USDC.
- Core product: dependent conditional stock sequences.
- Execution: 0x Swap API + user-owned bounded vault.
- Trigger truth: official Chainlink total-return feeds.
- Automation: always-on backend worker; browser is not required.
- Worker authority: attempt execution only; contract rechecks and bounds it.
- Custody: user-specific vault; worker never has withdrawal authority.
- Frontend: structured trading builder first.
- AI: not required.
- Persistence: chain is source of truth; PostgreSQL indexes/caches.
- Attribution: ERC-8021/Base Builder Code from the beginning.
- Mainnet evidence is mandatory for "done."

### Can change only with new verified blocker/evidence

- 0x as routing provider.
- custom vault architecture.
- Chainlink feed as trigger source.
- FastAPI background worker.
- linear sequence semantics for MVP.

### Deferred

- generic branching/OCO;
- LLM rule parser;
- replay/backtest;
- alerts;
- extra DeFi composability.

---

## 20. PRD maintenance protocol

After every milestone:

1. Compare repository HEAD against this PRD.
2. Update the Milestone Status table below.
3. Add exact evidence: test counts, tx hashes, contract addresses, deployment URLs.
4. Mark any newly discovered blocker.
5. Do **not** delete a difficult requirement to make status look green.
6. If architecture must change, add a dated decision entry explaining:
   - verified evidence;
   - what broke;
   - why the new path preserves the product thesis.
7. Commit PRD/status updates in the same milestone commit or an immediately following documentation commit.

### Milestone status

| Milestone | Status | Commit | Evidence |
|---|---|---|---|
| M0 Repo/source of truth | IN PROGRESS | `5485836` | Repo initialized; source-of-truth files being added |
| M1 Contract state machine | NOT STARTED | — | — |
| M2 Real mainnet buy/sell | NOT STARTED | — | — |
| M3 Autonomous worker | NOT STARTED | — | — |
| M4 Persistence/multi-user | NOT STARTED | — | — |
| M5 Trading frontend | NOT STARTED | — | — |
| M6 Production evidence | NOT STARTED | — | — |
| M7 Submission | NOT STARTED | — | — |

---

## 21. Final definition of done

The product is complete only when:

- [ ] public repository is clean and reproducible;
- [ ] contracts are deployed to Base mainnet;
- [ ] official B20 addresses and feeds are verified;
- [ ] one real B20 buy succeeded;
- [ ] one real B20 sell succeeded;
- [ ] a multi-step policy advanced in the correct order;
- [ ] the browser was closed while the worker executed a real step;
- [ ] hard spending/deviation limits were enforced;
- [ ] second wallet is isolated;
- [ ] state recovers without localStorage;
- [ ] production UI uses real data;
- [ ] Builder Code attribution appears on evidence transaction(s);
- [ ] public live URL works;
- [ ] README matches implementation;
- [ ] Loom/X/form submission material is complete.

If any of those are false, the build is not yet a complete hackathon submission.

---

## 22. Research references used to lock architecture

Official / primary:
- Base: Stocks just got updated — https://blog.base.org/tokenized-stocks
- Base Engineering: B20 standard — https://blog.base.dev/b20-tokenized-stocks-on-base
- Base verified stock list — https://base.org/stocks
- Base Request for Builders — https://blog.base.org/request-for-builders-tokenized-stocks
- Base Builder Codes / ERC-8021 — https://blog.base.dev/builder-codes-and-erc-8021-fixing-onchain-attribution
- Base build skill / Builder Codes — https://github.com/base/skills
- Coinbase CDP Node — https://docs.cdp.coinbase.com/data/node/overview
- 0x Swap API — https://docs.0x.org/docs/introduction/quickstart/swap-tokens-with-0x-swap-api
- 0x contracts — https://docs.0x.org/docs/core-concepts/contracts
- 0x rate limits — https://docs.0x.org/docs/developer-resources/rate-limits

Quest evidence:
- official Base announcement/form is summarized and source-verified at:
  https://viamu.app/opportunities/base-tokenized-stocks-2026
