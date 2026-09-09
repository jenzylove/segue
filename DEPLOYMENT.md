# Segue deployment

The repository ships as one FastAPI service: `/` serves the frozen landing
surface and `/health` plus `/v1/*` serve the live Morpho API. The service never
holds a wallet key and never signs or broadcasts transactions.

Build and run locally with a real Base RPC endpoint:

```powershell
docker build -t segue .
docker run --rm -p 8000:8000 -v segue-data:/data `
  -e BASE_RPC_URL="https://base-mainnet.g.alchemy.com/v2/<YOUR_RPC_KEY>" segue
```

For a public host, provide `BASE_RPC_URL` as a server-side secret and attach a
persistent volume for `/data`. Do not put the RPC key, wallet keys or provider
keys in the image or frontend. The current repository has no public-host
credential configured, so deployment remains a release command rather than a
claimed public URL.

After the host is live, verify:

```text
GET https://<host>/health
GET https://<host>/v1/credit/position?wallet=0x48C8B4D40dE216C652ED4D67f6466CeBA90054CA
GET https://<host>/app.html?wallet=0x48C8B4D40dE216C652ED4D67f6466CeBA90054CA
```

The second response must show locked market
`0x91360eea2686ef7ce4966b4e82cf6ff712af02baf0f7211459780d9f5af1612a`, direct
oracle state, the live position, and `live_state_stale: false` before calling
the host browser-verified. The workspace URL must render the same live values
and expose only unsigned plan preparation at the wallet boundary.
