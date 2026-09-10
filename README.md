# Segue

**Program what your portfolio does next.**

Segue is a self-managing credit and policy layer for **Coinbase Tokenized Stocks (B20) on Base**. A user can hold or acquire supported B20 stocks, borrow USDC against them through real Base credit markets, and precommit what should happen next when risk or opportunity conditions change.

The product does not predict stocks or invent trades. It reads real market/protocol state and executes rules the user already chose.

## Build status

- M0 repository/source of truth: **COMPLETE**
- M1 bounded contract state machine: **COMPLETE** — 24 Foundry tests passed on the locked contract milestone
- M2 real Base-mainnet B20 buy/sell: **IN PROGRESS**
- M2C Morpho Blue/B20 credit backend: **MAINNET READS VERIFIED**
- Credit mission API, durable reconciliation, live landing surface and position workspace: **IMPLEMENTED LOCALLY**

M2 has already verified Base mainnet RPC access, the configured official NVDAc contract and Chainlink feeds. The original 0x route was blocked by provider-side RWA authorization, so the dated PRD decision switches only the execution adapter to **1inch Classic Swap**, which supports Coinbase Tokenized Stocks on Base. The vault security boundary remains one immutable execution target plus exact temporary allowance and post-balance checks.

The original M2 vault trading path still requires its separate 1inch key, deployment and funded trade evidence. The credit rail has a separate real Base-mainnet proof: NVDAc collateral is supplied and 1 USDC is borrowed in Morpho Blue market `0x91360eea2686ef7ce4966b4e82cf6ff712af02baf0f7211459780d9f5af1612a`. The API reads that position directly from Base and Morpho, and never treats a quote or simulation as execution proof.

## Core loop

`B20 collateral → safe borrow → monitored credit mission → sequenced repay/de-risk action`

A later action is not active until the prior action or risk condition is verified. User-specific vaults and credit missions enforce allowed assets, exact amounts, capital caps, price/risk limits, sequence state, and withdrawal authority.

## Price and execution truth

- Coinbase B20 contracts are the assets Segue trades.
- Chainlink total-return feeds are the trigger/valuation truth.
- 1inch Classic Swap supplies routing calldata; the vault independently validates the economic result.
- Morpho Blue on Base supplies credit parameters where NVDAc collateral borrowing is used; the locked MarketParams and oracle are revalidated on every live read.
- Base contract state is authoritative for policies, balances and execution history.

B20 tokens may trade while an equity total-return feed is outside its update window. Segue fails closed on stale feed data rather than pretending a trigger is current.

## Hackathon

Built for the **Base Builder Quest — Tokenized Stocks**.

The authoritative build contract is `PRD.md`; implementation discipline is in `BUILD_RULES.md` and `AGENTS.md`.
Segue is an autopilot for tokenized-stock positions: unlock liquidity without selling, or program what your portfolio should do next, while Segue enforces the user's bounded policy after they leave. Credit, Treasury and Policy are one system: the API reads a position, calculates a safe action, prepares a bounded transaction, records evidence, and advances the next policy step only after provider postconditions are proven.

The credit mission uses Morpho Blue on Base; the original dependent stock-sequence system remains the policy and treasury execution layer.

The unified FastAPI service serves the landing page at `/` and the connected-wallet
workspace at `/app.html`. The workspace is organized as Portfolio, Sequences,
Credit and Activity. Portfolio balances come from the official Base B20 catalogue
and live ERC-20 reads; only assets with verified rails expose those actions. The
Credit tab remains the recoverable Morpho position workspace and the Sequences tab
stores bounded drafts that mirror the M1/M2 contract semantics. The browser reads
the API and prepares unsigned actions; it never signs or broadcasts transactions.

The current curated catalogue is sourced from Base's official stocks listing
(`https://brand.base.org/stocks`) and includes NVDAc, METAc, AAPLc, GOOGLc and
AMZNc. NVDAc is the only asset currently marked with a verified Segue Chainlink
feed and Morpho Blue credit market; the other entries are portfolio-visible and
explicitly credit/sequence pending until their rails are independently verified.
