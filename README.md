# Segue

**Program what your portfolio does next.**

Segue is a conditional execution layer for **Coinbase Tokenized Stocks (B20) on Base**. A user defines a bounded sequence of stock actions once, then Segue monitors verified conditions and advances the sequence automatically without requiring the browser to stay open.

The product does not predict stocks. It executes rules the user already chose.

## Build status

- M0 repository/source of truth: **COMPLETE**
- M1 bounded contract state machine: **COMPLETE** — 24 Foundry tests passed on the locked contract milestone
- M2 real Base-mainnet B20 buy/sell: **IN PROGRESS**

M2 has already verified Base mainnet RPC access, the configured official NVDAc contract and Chainlink feeds. The original 0x route was blocked by provider-side RWA authorization, so the dated PRD decision switches only the execution adapter to **1inch Classic Swap**, which supports Coinbase Tokenized Stocks on Base. The vault security boundary remains one immutable execution target plus exact temporary allowance and post-balance checks.

The next irreversible gate is a tiny real Base-mainnet USDC ↔ B20 round trip through a deployed Segue vault. Do not treat provider quotes or simulations as that proof.

## Core loop

`condition → bounded trade → next condition → bounded trade`

A later step is not active until the previous step succeeds. User-specific vaults enforce allowed assets, exact amounts, capital caps, price-deviation limits, sequence state, and withdrawal authority onchain.

## Price and execution truth

- Coinbase B20 contracts are the assets Segue trades.
- Chainlink total-return feeds are the trigger/valuation truth.
- 1inch Classic Swap supplies routing calldata; the vault independently validates the economic result.
- Base contract state is authoritative for policies, balances and execution history.

B20 tokens may trade while an equity total-return feed is outside its update window. Segue fails closed on stale feed data rather than pretending a trigger is current.

## Hackathon

Built for the **Base Builder Quest — Tokenized Stocks**.

The authoritative build contract is `PRD.md`; implementation discipline is in `BUILD_RULES.md` and `AGENTS.md`.
