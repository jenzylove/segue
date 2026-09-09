# Segue

**Program what your portfolio does next.**

Segue is a self-managing credit and policy layer for **Coinbase Tokenized Stocks (B20) on Base**. A user can hold or acquire supported B20 stocks, borrow USDC against them through real Base credit markets, and precommit what should happen next when risk or opportunity conditions change.

The product does not predict stocks or invent trades. It reads real market/protocol state and executes rules the user already chose.

## Build status

- M0 repository/source of truth: **COMPLETE**
- M1 bounded contract state machine: **COMPLETE** — 24 Foundry tests passed on the locked contract milestone
- M2 real Base-mainnet B20 buy/sell: **IN PROGRESS**
- M2C Aave/B20 credit backend: **IN PROGRESS**

M2 has already verified Base mainnet RPC access, the configured official NVDAc contract and Chainlink feeds. The original 0x route was blocked by provider-side RWA authorization, so the dated PRD decision switches only the execution adapter to **1inch Classic Swap**, which supports Coinbase Tokenized Stocks on Base. The vault security boundary remains one immutable execution target plus exact temporary allowance and post-balance checks.

The next irreversible gates are a tiny real Base-mainnet USDC ↔ B20 round trip through a deployed Segue vault and a live Aave/B20 credit-market proof. Do not treat provider quotes, static docs, or simulations as that proof.

## Core loop

`B20 collateral → safe borrow → monitored credit mission → sequenced repay/de-risk action`

A later action is not active until the prior action or risk condition is verified. User-specific vaults and credit missions enforce allowed assets, exact amounts, capital caps, price/risk limits, sequence state, and withdrawal authority.

## Price and execution truth

- Coinbase B20 contracts are the assets Segue trades.
- Chainlink total-return feeds are the trigger/valuation truth.
- 1inch Classic Swap supplies routing calldata; the vault independently validates the economic result.
- Aave Base markets supply credit parameters where B20 collateral borrowing is used.
- Base contract state is authoritative for policies, balances and execution history.

B20 tokens may trade while an equity total-return feed is outside its update window. Segue fails closed on stale feed data rather than pretending a trigger is current.

## Hackathon

Built for the **Base Builder Quest — Tokenized Stocks**.

The authoritative build contract is `PRD.md`; implementation discipline is in `BUILD_RULES.md` and `AGENTS.md`.
Segue is an autopilot for tokenized-stock positions: unlock liquidity without selling, or program what your portfolio should do next, while Segue enforces the user's bounded policy after they leave.

The credit mission uses Morpho Blue on Base; the original dependent stock-sequence system remains the policy and treasury execution layer.
