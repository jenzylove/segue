# M2 — Base Mainnet Transaction Gate

M2 is the first irreversible milestone. The purpose is to prove the production path with a tiny real trade before frontend work begins.

## Current provider decision

The original 0x route was tested against real Base mainnet infrastructure on 2026-09-05. Base RPC, official NVDAc, and the configured Chainlink feeds were reachable, but 0x returned `BUY_TOKEN_NOT_AUTHORIZED_FOR_TRADE`. That is a provider-side RWA authorization blocker, not a Segue parameter bug. M2 therefore switches only the routing adapter to **1inch Classic Swap**. The vault/factory security boundary remains one fixed execution target, exact temporary sell allowance, worker-supplied calldata, and post-balance verification.

## Private local roles

Keep secrets only in local `.env`.

- `EXECUTOR_PRIVATE_KEY` / `EXECUTOR_ADDRESS`: dedicated gas-only automation/deployer wallet.
- `DEMO_OWNER_PRIVATE_KEY` / `DEMO_OWNER_ADDRESS`: separate tiny demo/user wallet that owns the vault and strategy funds.
- `ONEINCH_API_KEY`: server/provider credential.

Do **not** make the executor the demo vault owner just to shorten M2. The trust boundary being proved is that the worker can execute but cannot withdraw user funds. Never paste private keys, API keys, or private RPC URLs into chat, GitHub, commits, or screenshots.

## Gate A — route + deployment readiness

```powershell
python scripts/m2_preflight.py
```

This checks Base RPC, executor gas, token/feed interfaces, a live 1inch USDC → B20 route, the live `approve/spender` target, configured-target equality, and feed age. Feed age is separate from deployment readiness: stale equity data blocks policy creation/trading, not immutable registry/factory deployment.

On the first route lookup, copy the printed public target into local `.env` as `EXECUTION_TARGET_ADDRESS`, then rerun. `M2 DEPLOYMENT PREFLIGHT: PASS` requires the target to match and the executor to have Base ETH for gas. No transaction is broadcast.

## Gate B — deploy + verify

```powershell
forge build
forge test -vv
forge script script/DeployMainnet.s.sol:DeployMainnet --rpc-url $env:BASE_RPC_URL --broadcast -vvvv
python scripts/m2_extract_deploy.py
```

Copy `ASSET_REGISTRY_ADDRESS` and `FACTORY_ADDRESS` into local `.env`, then verify read-only:

```powershell
forge script script/VerifyM2Deployment.s.sol:VerifyM2Deployment --rpc-url $env:BASE_RPC_URL -vvvv
```

## Gate C — create the separate-owner demo vault

The demo owner needs a small Base ETH gas balance and at least `M2_BUY_USDC_ATOMIC` (default 1 USDC).

```powershell
forge script script/PrepareM2Vault.s.sol:PrepareM2Vault --rpc-url $env:BASE_RPC_URL --broadcast -vvvv
cast call $env:FACTORY_ADDRESS "vaultOf(address)(address)" $env:DEMO_OWNER_ADDRESS --rpc-url $env:BASE_RPC_URL
```

Save the returned public address as `DEMO_VAULT_ADDRESS`. The script creates the owner's canonical vault if needed, sets the dedicated executor, and funds only the tiny proof amount. It does not read the equity price, so this can happen while the feed is stale.

## Gate D — fresh feed + real two-step policy

```powershell
python scripts/m2_preflight.py --require-fresh-feeds
forge script script/CreateM2RoundTripPolicy.s.sol:CreateM2RoundTripPolicy --rpc-url $env:BASE_RPC_URL --broadcast -vvvv
python scripts/m2_condition_probe.py --policy-id 1 --expect ready
python scripts/m2_snapshot.py --label before-buy --policy-id 1
```

The policy is: (1) bounded true NVDAc condition → spend exactly the tiny USDC amount to buy NVDAc; (2) only after step 1 succeeds, sell 100% of that B20 back to USDC. Both executions re-read the official Chainlink-backed registry.

The condition probe saves `.local/m2-condition-1.json`; the snapshot saves the exact block, local git SHA, owner/executor, policy/current-step state, deployed-cap state and USDC/B20 vault balances.

## Gate E — B1/B2 real buy

```powershell
python scripts/m2_firm_quote.py --direction buy
$env:M2_ROUTE_CALLDATA=(Get-Content .local/m2-calldata-buy.txt -Raw).Trim()
forge script script/ExecuteM2Quote.s.sol:ExecuteM2Quote --rpc-url $env:BASE_RPC_URL --broadcast -vvvv
Remove-Item Env:M2_ROUTE_CALLDATA
python scripts/m2_snapshot.py --label after-buy --policy-id 1
```

The firm helper validates the pair, `from=vault`, `origin=executor`, `receiver=vault`, frozen `tx.to`, calldata, zero native value, and no partial fill. The executor EOA never calls 1inch directly. A firm provider response is **B1**; the successful Base receipt and changed balances are **B2**.

## Gate F — B3 real sell

The reverse helper defaults to the vault's actual NVDAc balance:

```powershell
python scripts/m2_firm_quote.py --direction sell
$env:M2_ROUTE_CALLDATA=(Get-Content .local/m2-calldata-sell.txt -Raw).Trim()
forge script script/ExecuteM2Quote.s.sol:ExecuteM2Quote --rpc-url $env:BASE_RPC_URL --broadcast -vvvv
Remove-Item Env:M2_ROUTE_CALLDATA
python scripts/m2_snapshot.py --label after-sell --policy-id 1
```

The second execution must complete the same policy and return the B20 exposure to USDC. The three snapshots provide the exact before/after balance and active-step evidence required by M2.

## Gate G — B4 false-condition evidence

After policy 1 is `COMPLETED`, `nextPolicyId` should be 2. Keep `M2_FALSE_POLICY_ID=2` unless chain state proves otherwise.

```powershell
forge script script/CreateM2FalseConditionPolicy.s.sol:CreateM2FalseConditionPolicy --rpc-url $env:BASE_RPC_URL --broadcast -vvvv
python scripts/m2_condition_probe.py --policy-id 2 --expect false
forge script script/CancelM2FalsePolicy.s.sol:CancelM2FalsePolicy --rpc-url $env:BASE_RPC_URL --broadcast -vvvv
```

The false policy puts its `PRICE_ABOVE` threshold above the current official feed. The read-only probe must return `executable: false` / `CONDITION_FALSE` and saves `.local/m2-condition-2.json`. Together with the pre-buy `READY` capture, that closes the true/false B4 condition proof without mocks or weakening the contract.

## M2 evidence required

M2 is complete only after all four are recorded in the PRD/integration ledger:

- **B1:** firm executable 1inch transaction for the deployed/funded vault;
- **B2:** real Base mainnet USDC → official B20 buy, B20 output held by the vault;
- **B3:** real B20 → USDC sell through the same bounded path;
- **B4:** deployed vault reads the official total-return feed and demonstrably rejects a false condition / accepts a true condition, failing safely on stale data.

For every real transaction record: tx hash, block number, vault address, sell/buy assets, before/after balances, active step before/after, and exact git commit deployed.

Do not call M2 complete from unit tests, an indicative quote, simulation, or a provider response without the Base transaction.

## Upstream sources

- Base Coinbase Tokenized Stocks directory: https://base.org/stocks
- Base B20 engineering / total-return feed background: https://blog.base.dev/b20-tokenized-stocks-on-base
- Chainlink feed explorer: https://data.chain.link/feeds
- 1inch Coinbase Tokenized Stocks support: https://1inch.com/blog/post/coinbase-tokenized-stocks
- 1inch Classic Swap API v6.1: https://business.1inch.com/portal/documentation/apis/swap/classic-swap/introduction
- 1inch API authentication: https://business.1inch.com/portal/documentation/apis/authentication
