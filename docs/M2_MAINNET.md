# M2 — Base Mainnet Transaction Gate

M2 is the first irreversible milestone. The purpose is to prove the production path with a tiny real trade before frontend work begins.

## Current provider decision

The original 0x route was tested against real Base mainnet infrastructure on 2026-09-05. Base RPC, official NVDAc, and the configured Chainlink feeds were reachable, but 0x returned:

`BUY_TOKEN_NOT_AUTHORIZED_FOR_TRADE` — buy token not authorized due to legal restrictions.

That is a provider-side RWA authorization blocker, not a Segue parameter bug. M2 therefore switches only the routing adapter to **1inch Classic Swap**, which publicly supports Coinbase B20 stocks on Base. The vault/factory security boundary remains unchanged: one fixed execution target, exact temporary sell allowance, worker-supplied calldata, and post-balance verification.

## Private local roles

Keep secrets only in local `.env`.

- `EXECUTOR_PRIVATE_KEY` / `EXECUTOR_ADDRESS`: dedicated gas-only automation/deployer wallet.
- `DEMO_OWNER_PRIVATE_KEY` / `DEMO_OWNER_ADDRESS`: a separate tiny demo/user wallet that owns the vault and strategy funds.
- `ONEINCH_API_KEY`: server/provider credential.

Do **not** make the executor the demo vault owner just to shorten M2. The trust boundary being proved is that the worker can execute but cannot withdraw user funds.

The public Base addresses for USDC, USDC/USD, NVDAc, and the Coinbase NVDA total-return feed are already in `.env.example`. Never paste private keys, API keys, or private RPC URLs into chat, GitHub, commits, or screenshots.

## Gate A — route + deployment readiness (non-spending)

The Python scripts load `.env` themselves. In PowerShell:

```powershell
python scripts/m2_preflight.py
```

The preflight checks, in order:

- Base mainnet RPC (`8453`);
- executor Base ETH balance;
- official token/feed interfaces;
- 1inch USDC → B20 route availability;
- live 1inch `approve/spender` execution target;
- configured target equality if `EXECUTION_TARGET_ADDRESS` is already set;
- current Chainlink feed age.

Feed age is reported separately from deployment readiness. A stale equity feed blocks policy creation/trading, but it does **not** make deploying the immutable registry/factory unsafe. The contract itself will fail closed if anyone tries to consume stale price data.

On the first successful route lookup, copy the printed **public** target into local `.env`:

```text
EXECUTION_TARGET_ADDRESS=0x...
```

Then rerun preflight. `M2 DEPLOYMENT PREFLIGHT: PASS` requires the live target to match and the executor to have Base ETH for gas.

No preflight result is B1-B4 and no transaction is broadcast.

## Gate B — deploy + verify immutable configuration

Once deployment preflight passes:

```powershell
forge build
forge test -vv
forge script script/DeployMainnet.s.sol:DeployMainnet --rpc-url $env:BASE_RPC_URL --broadcast -vvvv
python scripts/m2_extract_deploy.py
```

Copy the printed `ASSET_REGISTRY_ADDRESS` and `FACTORY_ADDRESS` into local `.env`, then verify the deployed configuration read-only:

```powershell
forge script script/VerifyM2Deployment.s.sol:VerifyM2Deployment --rpc-url $env:BASE_RPC_URL -vvvv
```

The verifier checks the registry owner, factory registry/USDC/frozen execution target, both registered feeds, B20 marker, active flags, and exact 2h/6h staleness limits.

## Gate C — create a real user-owned demo vault

The demo owner is intentionally separate from the automation executor. It needs a small Base ETH gas balance and at least the tiny USDC amount configured by `M2_BUY_USDC_ATOMIC` (default 1 USDC).

Run:

```powershell
forge script script/PrepareM2Vault.s.sol:PrepareM2Vault --rpc-url $env:BASE_RPC_URL --broadcast -vvvv
```

The script:

- verifies the demo-owner key/address pair;
- creates that owner's one canonical Segue vault if needed;
- sets the dedicated executor on creation;
- funds the vault only up to the configured tiny M2 USDC amount;
- never gives the executor ownership/withdrawal authority;
- does not read the equity price, so it can run while the market feed is stale.

Resolve the public vault address from the factory and save it locally:

```powershell
cast call $env:FACTORY_ADDRESS "vaultOf(address)(address)" $env:DEMO_OWNER_ADDRESS --rpc-url $env:BASE_RPC_URL
```

Set the returned address as `DEMO_VAULT_ADDRESS` in `.env`.

## Gate D — fresh feed + two-step round-trip policy

Immediately before creating the policy/trading, require the same freshness limits enforced by the contract:

```powershell
python scripts/m2_preflight.py --require-fresh-feeds
```

Only after `M2 TRADE READINESS: PASS`, create the real two-step policy:

```powershell
forge script script/CreateM2RoundTripPolicy.s.sol:CreateM2RoundTripPolicy --rpc-url $env:BASE_RPC_URL --broadcast -vvvv
```

The policy is deliberately tiny and deterministic for evidence:

1. if the live NVDAc total-return feed remains above a bounded threshold just below its policy-creation price, spend exactly `M2_BUY_USDC_ATOMIC` USDC to buy NVDAc;
2. only after step 1 succeeds, sell 100% of the acquired NVDAc back to USDC through the same fixed execution target.

`M2_TRIGGER_BUFFER_BPS`, `M2_MAX_DEVIATION_BPS`, and `M2_POLICY_TTL_SECONDS` are explicit local parameters. The default trigger buffer is 5%, the max execution deviation is 5%, and the proof policy expires after one hour. The vault still re-reads the Chainlink feed at each execution.

For the first demo vault `M2_POLICY_ID=1`. Verify the active policy id if needed:

```powershell
cast call $env:DEMO_VAULT_ADDRESS "activePolicyId()(uint256)" --rpc-url $env:BASE_RPC_URL
```

## Gate E — B1/B2 real buy

Fetch and validate the firm 1inch transaction:

```powershell
python scripts/m2_firm_quote.py --direction buy
```

This validates the exact token pair, `from=vault`, `origin=executor`, `receiver=vault`, frozen `tx.to`, non-empty calldata, zero native value, and disables partial fill. It writes:

- `.local/m2-quote-buy.json`
- `.local/m2-calldata-buy.txt`

Load only the public router calldata into the shell and broadcast through the vault:

```powershell
$env:M2_ROUTE_CALLDATA=(Get-Content .local/m2-calldata-buy.txt -Raw).Trim()
forge script script/ExecuteM2Quote.s.sol:ExecuteM2Quote --rpc-url $env:BASE_RPC_URL --broadcast -vvvv
Remove-Item Env:M2_ROUTE_CALLDATA
```

The executor EOA never calls 1inch directly. `ExecuteM2Quote` verifies the vault executor, frozen target and `previewExecution`, then calls `vault.executeStep`. The vault itself grants the exact allowance, calls the fixed target, checks exact sell + minimum B20 receipt, and only then activates step 2.

A firm provider response alone is **B1 evidence**, not B2. B2 requires the successful Base receipt plus before/after vault balances.

## Gate F — B3 real sell

After B2 succeeds, fetch the reverse route. By default the helper reads the vault's actual NVDAc balance, so no guessed sell amount is needed:

```powershell
python scripts/m2_firm_quote.py --direction sell
$env:M2_ROUTE_CALLDATA=(Get-Content .local/m2-calldata-sell.txt -Raw).Trim()
forge script script/ExecuteM2Quote.s.sol:ExecuteM2Quote --rpc-url $env:BASE_RPC_URL --broadcast -vvvv
Remove-Item Env:M2_ROUTE_CALLDATA
```

This must complete the same onchain policy and return the B20 exposure to USDC through the same bounded path.

## B4 — real condition evidence

The round-trip policy proves the true condition path because both executions re-read the deployed Chainlink-backed registry before they can move funds. B4 is not complete until we also record a deployed false-condition `previewExecution` result (or equivalent failed execution) against the same official feed. Do not weaken the condition just to manufacture this proof.

## M2 evidence required

M2 is complete only after all four are recorded in the PRD/integration ledger:

- **B1:** firm executable 1inch transaction for the deployed/funded vault;
- **B2:** real Base mainnet USDC → official B20 buy, B20 output held by the vault;
- **B3:** real B20 → USDC sell through the same bounded path;
- **B4:** deployed vault reads the official total-return feed and demonstrably rejects a false condition / accepts a true condition, failing safely on stale data.

For every real transaction record:

- tx hash;
- block number;
- vault address;
- sell/buy assets;
- before/after balances;
- active step before and after;
- exact git commit deployed.

Do not call M2 complete from unit tests, an indicative quote, simulation, or a provider response without the Base transaction.

## Upstream sources

- Base Coinbase Tokenized Stocks directory: https://base.org/stocks
- Base B20 engineering / total-return feed background: https://blog.base.dev/b20-tokenized-stocks-on-base
- Chainlink feed explorer: https://data.chain.link/feeds
- 1inch Coinbase Tokenized Stocks support: https://1inch.com/blog/post/coinbase-tokenized-stocks
- 1inch Classic Swap API v6.1: https://business.1inch.com/portal/documentation/apis/swap/classic-swap/introduction
- 1inch API authentication: https://business.1inch.com/portal/documentation/apis/authentication
