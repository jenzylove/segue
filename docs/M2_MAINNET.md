# M2 — Base Mainnet Transaction Gate

M2 is the first irreversible milestone. The purpose is to prove the production path with a tiny real trade before frontend work begins.

## Current provider decision

The original 0x route was tested against real Base mainnet infrastructure on 2026-09-05. Base RPC, official NVDAc, and the configured Chainlink feeds were reachable, but 0x returned:

`BUY_TOKEN_NOT_AUTHORIZED_FOR_TRADE` — buy token not authorized due to legal restrictions.

That is a provider-side RWA authorization blocker, not a Segue parameter bug. M2 therefore switches only the routing adapter to **1inch Classic Swap**, which publicly supports Coinbase B20 stocks on Base. The vault/factory security boundary remains unchanged: one fixed execution target, exact temporary sell allowance, worker-supplied calldata, and post-balance verification.

## Required local values

Keep the existing `.env` and add/fill:

```text
BASE_RPC_URL=
EXECUTOR_PRIVATE_KEY=
EXECUTOR_ADDRESS=
ONEINCH_API_KEY=
EXECUTION_TARGET_ADDRESS=
```

`EXECUTION_TARGET_ADDRESS` is public. Leave it blank for the first preflight. The preflight queries 1inch's live `approve/spender` endpoint and prints the exact address to place there before deployment.

The public Base addresses for USDC, USDC/USD, NVDAc, and the Coinbase NVDA total-return feed are already present in `.env.example`.

Never paste the private key, API key, or a private RPC URL into chat, GitHub, or a commit.

## Windows / PowerShell note

The Python scripts load `.env` themselves. Do **not** use Bash-only `set -a` or `source .env` in PowerShell.

If the private Coinbase RPC is unreachable from the local network, a Base mainnet RPC that passes `eth_chainId == 8453` and the required read calls may be used for M2 verification. Production worker RPC reliability is a later deployment concern.

## Gate A — non-spending readiness

PowerShell:

```powershell
python scripts/m2_preflight.py
forge build
forge test -vv
```

`m2_preflight.py` verifies:

- RPC is Base mainnet (`8453`);
- executor ETH balance is visible;
- USDC and the configured B20 token answer ERC-20 `decimals()`;
- the exact Chainlink feeds return valid data;
- feed freshness matches Segue's contract limits: USDC <= 2h, equity <= 6h;
- the 1inch API key is accepted;
- 1inch returns a real USDC → B20 quote;
- 1inch's live `approve/spender` execution target has Base bytecode;
- any already-configured `EXECUTION_TARGET_ADDRESS` matches the live value.

The script intentionally checks the 1inch route **before** feed freshness. This lets us prove whether the replacement rail supports NVDAc even when the equity feed is stale over a weekend.

A preflight PASS is **not** B1-B4. No transaction is broadcast.

### Known current blockers

- The executor address reported `0.00000000` Base ETH in the first real preflight. It needs a deliberately small Base ETH gas buffer before deployment/execution.
- The NVDA total-return feed can be stale outside its update window. Segue fails closed rather than weakening the 6-hour contract limit.

## Gate B — lock the live execution target

After preflight returns a 1inch route, copy the **public** printed address into local `.env`:

```text
EXECUTION_TARGET_ADDRESS=0x...
```

Run preflight once more. It must confirm that the configured address still equals 1inch `approve/spender`.

Do not guess or hardcode a router from documentation: the live API response is the deployment source of truth.

## Gate C — deployment

Only after:

- the live 1inch route is proven;
- `EXECUTION_TARGET_ADDRESS` matches live 1inch;
- the executor has a deliberately small Base ETH gas balance;
- the Chainlink feeds are within Segue's freshness limits;

run:

```powershell
forge script script/DeployMainnet.s.sol:DeployMainnet --rpc-url $env:BASE_RPC_URL --broadcast -vvvv
python scripts/m2_extract_deploy.py
```

Copy the printed `ASSET_REGISTRY_ADDRESS` and `FACTORY_ADDRESS` into local `.env`. The broadcast artifact is gitignored.

The deployment script fails closed unless:

- chain id is exactly 8453;
- `EXECUTOR_ADDRESS` matches the address derived from `EXECUTOR_PRIVATE_KEY`;
- all configured public addresses are nonzero;
- the factory's immutable execution target is the preflight-resolved `EXECUTION_TARGET_ADDRESS`.

## Gate D — demo vault + firm 1inch transaction

After a demo vault exists and contains the exact tiny USDC amount chosen for M2, set:

```text
DEMO_VAULT_ADDRESS=0x...
M2_BUY_USDC_ATOMIC=1000000
M2_ONEINCH_SLIPPAGE_BPS=50
```

Then:

```powershell
python scripts/m2_firm_quote.py
```

This requests a 1inch Classic Swap transaction with:

- `from = DEMO_VAULT_ADDRESS`;
- `receiver = DEMO_VAULT_ADDRESS`;
- `origin = EXECUTOR_ADDRESS`;
- exact USDC sell amount;
- bounded slippage;
- `forceApprove=true` only so 1inch simulation does not demand a pre-existing allowance, because the Segue vault grants the exact allowance atomically inside `executeStep`.

It validates:

- source token = configured USDC;
- destination token = configured Coinbase B20;
- positive destination amount;
- `tx.from` = vault;
- `tx.to` = the same live execution target frozen into the factory;
- calldata is present;
- ERC-20 → ERC-20 transaction value is zero.

It writes `.local/m2-quote.json` and **does not broadcast the swap**.

## B1-B4 completion evidence

M2 is complete only after all four are recorded:

- **B1:** firm executable 1inch transaction for the deployed/funded vault;
- **B2:** real Base mainnet USDC → official B20 buy, B20 output held by the vault;
- **B3:** real B20 → USDC sell through the same bounded path;
- **B4:** deployed vault reads the official total-return feed and demonstrably rejects a false/unsafe condition while permitting a true one.

For every real transaction record:

- tx hash;
- block number;
- vault address;
- sell/buy assets;
- before/after balances;
- active step before and after;
- exact git commit deployed.

Do not call M2 complete from unit tests, an indicative quote, or a simulated transaction.

## Upstream sources

- Base Coinbase Tokenized Stocks directory: https://base.org/stocks
- Base B20 engineering / total-return feed background: https://blog.base.dev/b20-tokenized-stocks-on-base
- Chainlink feed explorer: https://data.chain.link/feeds
- 1inch Coinbase Tokenized Stocks support: https://1inch.com/blog/post/coinbase-tokenized-stocks
- 1inch Classic Swap API v6.1: https://business.1inch.com/portal/documentation/apis/swap/classic-swap/introduction
- 1inch API authentication: https://business.1inch.com/portal/documentation/apis/authentication
