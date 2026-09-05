# Segue

**Program what your portfolio does next.**

Segue is a 24/7 conditional execution layer for Coinbase Tokenized Stocks on Base. A user defines a bounded sequence of stock actions once, then Segue monitors verified conditions and advances the sequence automatically without requiring the browser to stay open.

The product does not predict stocks. It executes rules the user already chose.

## Build status

Milestone 0 — repository and source of truth: **IN PROGRESS**

The authoritative product and execution documents are `PRD.md`, `BUILD_RULES.md`, and `AGENTS.md`.

## Core loop

`condition → bounded trade → next condition → next trade`

A later step is not active until the previous step succeeds. User-specific vaults enforce the allowed assets, amounts, execution limits, sequence state, and withdrawal authority onchain.

## Hackathon

Built for the Base Builder Quest — Tokenized Stocks.
