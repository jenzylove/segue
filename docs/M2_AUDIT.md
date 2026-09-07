# M2 continuation audit — 2026-09-07

Audited GitHub baseline: `6c3e036cf481de83f0aa219af007a35c9ba55389`.

## Outcome

The contract architecture remains unchanged. The audit fixed defects in the M2
operator/evidence path that could have weakened or blocked the required proof:

- snapshots pin every contract and balance read to the recorded block;
- the condition probe captures the exact deployed `StalePrice(address,uint256)`
  revert at a current or observed historical block without treating generic RPC
  errors as stale-feed evidence;
- false-condition and stale-condition evidence use distinct files;
- false-policy creation no longer requires replenishing round-trip loss for a
  policy that cannot trade while its condition is false;
- the false policy has a separate 24-hour lifetime so natural feed staleness can
  be observed before cancellation;
- preflight rejects invalid/non-contract feeds and execution targets, incomplete
  Chainlink rounds, normalized zero prices, and a missing/invalid Builder Code;
- firm quote validation rejects wrong-chain RPC and malformed hex calldata;
- all M2 state-changing script calls append an ERC-8021 schema-0 Builder Code
  suffix when the called contract supports trailing calldata;
- the runbook uses Foundry's local `base` RPC alias so private RPC URLs are not
  placed in process arguments and defaults to non-trace broadcast output;
- vault preparation explicitly rejects collapsing owner and executor roles.

## Local evidence

- `forge build`: PASS with Solidity 0.8.24.
- `forge test -vv`: PASS, 52 tests, 0 failures.
- `python -m unittest discover -s tests -p 'test_*.py' -v`: PASS, 21 tests.
- `python scripts/validate_repo.py`: PASS.
- `python -m compileall -q scripts tests`: PASS.
- `python scripts/verify_m2_artifacts.py`: PASS with Foundry `cast` available.

The script integration test exercises the documented local sequence with separate
test owner/executor identities: create/fund vault, create two-step policy, buy,
sell at a loss, create the false policy without a top-up, verify false, and cancel.
It is local EVM evidence only.

## Current external semantics checked

Official 1inch Classic Swap v6.1 documentation confirms `from` is the contract
caller, `origin` is the initiating EOA, `receiver` selects the recipient,
`slippage` is a percent, and Base plus the requested validation flags are
supported.

Source: <https://business.1inch.com/portal/documentation/apis/swap/classic-swap/methods/v6.1/1/swap/method/get>

Official Base documentation recommends ERC-8021 attribution through an encoded
`dataSuffix` and says contracts normally ignore appended calldata. The local
schema-0 encoder is regression-tested against the published `ox/erc8021` vector.
Real attribution remains unverified until an M2 receipt is inspected.

Sources:

- <https://docs.base.org/specifications/builder-codes/overview>
- <https://docs.base.org/specifications/builder-codes/for-app-developers>
- <https://github.com/wevm/ox/blob/main/src/erc8021/Attribution.ts>

## Evidence boundary

No 1inch credential was available to this audit, so no live firm route was
requested. No Base transaction was signed or broadcast. No deployment, provider,
Builder Code, browser, or autonomous-worker milestone is claimed.

B1, B2, B3, and B4 remain open. The exact next human action is Gate A in
`docs/M2_MAINNET.md` using protected local values.
