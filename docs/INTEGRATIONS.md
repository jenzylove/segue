# Segue Integration Ledger

This ledger stays live for the entire build. Do not let planned integrations silently disappear.

| Integration | Purpose | Required | Credential | Status | Completion evidence |
|---|---|---:|---|---|---|
| Base mainnet | execution network | YES | Base ETH | planned | deployed contracts + real tx |
| Coinbase B20 assets | tokenized stocks | YES | none | planned | verified official addresses in registry |
| Chainlink total-return feeds | trigger + valuation truth | YES | none | planned | contract reads official feed |
| 0x Swap API | B20 quote/routing | YES | `ZEROX_API_KEY` | planned | real quote + buy + sell |
| CDP/Base RPC | reliable chain access | YES | `BASE_RPC_URL` | planned | deployed services use private RPC |
| ERC-8021 Builder Code | Base attribution | YES | `BASE_BUILDER_CODE` | planned | attribution on evidence tx |
| PostgreSQL | worker checkpoints/history cache | YES | `DATABASE_URL` | planned | restart-safe worker reconciliation |
| Real chart source | trading context UI | YES for frontend | TBD | planned | labelled live chart renders |
| AI provider | optional rule parser | NO | none | deferred | not part of core submission |
| Telegram/Telegraph | none | NO | none | rejected | do not add |
| Firestore/Vertex | none | NO | none | rejected | do not add |
| Chainlink Automation | none for MVP | NO | none | rejected | worker handles automation |

## Status vocabulary

Use only:
- planned
- credentials obtained
- adapter implemented
- locally tested
- real provider tested
- mainnet verified
- deployed
- browser verified
- blocked
- deferred
- rejected

Update this file with exact evidence at each milestone.
