# M2 — Base Mainnet Transaction Gate

M2 is the first irreversible milestone. The purpose is to prove the production path with a tiny real trade before frontend work begins.

## Required local values

Copy `.env.example` to `.env` and fill only these private/user-specific values:

```bash
BASE_RPC_URL=
EXECUTOR_PRIVATE_KEY=
EXECUTOR_ADDRESS=
ZEROX_API_KEY=
```

The public Base addresses for USDC, the USDC/USD feed, NVDAc, and the Coinbase NVDA total-return feed are already present in `.env.example`. Re-check them against the linked upstream sources immediately before broadcast.

Never paste the private key or API key into chat, GitHub, a commit, or a shell-history command.

## Gate A — non-spending readiness

```bash
set -a
source .env
set +a
python3 scripts/m2_preflight.py
forge build
forge test -vv
```

`m2_preflight.py` verifies:

- RPC is Base mainnet (`8453`);
- executor address is readable and reports its ETH balance;
- USDC and the B20 token respond to ERC-20 `decimals()`;
- both Chainlink feeds return valid `latestRoundData()`;
- the saved 0x API key can discover an indicative USDC → B20 route.

A preflight PASS is **not** B1-B4. No transaction is broadcast.

## Gate B — deployment (requires explicit mainnet approval)

Only after Gate A passes and the deployer has a deliberately small amount of Base ETH:

```bash
forge script script/DeployMainnet.s.sol:DeployMainnet \
  --rpc-url "$BASE_RPC_URL" \
  --broadcast \
  -vvvv

python3 scripts/m2_extract_deploy.py
```

Copy the printed `ASSET_REGISTRY_ADDRESS` and `FACTORY_ADDRESS` into local `.env`. The broadcast artifact is gitignored.

The deployment script fails closed unless:

- chain id is exactly 8453;
- `EXECUTOR_ADDRESS` matches the address derived from `EXECUTOR_PRIVATE_KEY`;
- all configured public addresses are nonzero.

## Gate C — demo vault + real quote

After a demo vault exists and contains the exact tiny USDC amount chosen for M2, set:

```bash
DEMO_VAULT_ADDRESS=0x...
M2_BUY_USDC_ATOMIC=1000000   # default 1 USDC
```

Then:

```bash
python3 scripts/m2_firm_quote.py
```

This requests a firm quote with the vault as both `taker` and `recipient`, validates the token pair, amount, 0x entry point and calldata, and writes `.local/m2-quote.json`.

It **does not broadcast the swap**.

## B1-B4 completion evidence

M2 is complete only after all four are recorded in the PRD:

- **B1:** firm executable 0x quote for the deployed/funded vault;
- **B2:** real Base mainnet USDC → official B20 buy, B20 output held by the vault;
- **B3:** real B20 → USDC sell through the same bounded path;
- **B4:** deployed vault reads the configured total-return feed and demonstrably rejects a false/unsafe execution condition while permitting a true one.

For every real transaction record:

- tx hash;
- block number;
- vault address;
- sell/buy assets;
- before/after balances;
- active step before and after;
- exact git commit deployed.

Do not call M2 complete from unit tests, an indicative quote, or a simulated transaction.

## Upstream address sources

- Base stock registry / token list: https://base.org/stocks
- Base B20 integration background: https://blog.base.dev/b20-tokenized-stocks-on-base
- Chainlink feed explorer: https://data.chain.link/feeds
- 0x Swap API v2: https://docs.0x.org/docs/introduction/quickstart/swap-tokens-with-0x-swap-api
- 0x AllowanceHolder contracts: https://docs.0x.org/docs/core-concepts/contracts
