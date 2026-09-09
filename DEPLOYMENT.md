# Segue deployment

The repository ships as one FastAPI service: `/` serves the frozen landing
surface and `/health` plus `/v1/*` serve the live Morpho API. The service never
holds a wallet key and never signs or broadcasts transactions.

Railway uses the root `Dockerfile` automatically. `railway.toml` pins the
Dockerfile builder and `/health` deployment check; no custom build or start
command is required. The image listens on Railway's injected `PORT` (with
`8000` as a local fallback). Do not add a Docker `VOLUME` instruction: Railway
mounts a persistent volume at runtime, after the image is built.

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

Railway service variables:

```text
BASE_RPC_URL=https://base-mainnet.g.alchemy.com/v2/<YOUR_RPC_KEY>
SEGUE_DB_PATH=/data/segue_missions.sqlite3
```

`PORT` is supplied by Railway and must not be hardcoded. `MORPHO_API_URL` is
optional because the service defaults to Morpho's official public API. Do not
set wallet private keys, `EXECUTOR_PRIVATE_KEY`, `DEMO_OWNER_PRIVATE_KEY`, or
provider API keys on this credit service.

Attach a Railway Volume to the service with the exact mount path `/data`.
Volumes are runtime storage, so they must be configured in the service rather
than declared in the Dockerfile. The image creates `/data` so a missing volume
does not crash startup, but a deployment without the volume only has ephemeral
mission data and is not persistence-ready.

If the service logs `sqlite3.OperationalError: unable to open database file`,
the volume is absent or mounted at a different path. Add/attach the volume at
`/data`, keep `SEGUE_DB_PATH` exactly as shown above, and redeploy.

Run a safe, read-only worker pass from the same persistent volume with:

```powershell
python scripts\segue_worker.py --wallet 0x48C8B4D40dE216C652ED4D67f6466CeBA90054CA
```

The worker refreshes live market/position state and reconciles submitted
receipts; it never signs or broadcasts.

After the host is live, verify:

```text
GET https://<host>/health
GET https://<host>/v1/credit/position?wallet=0x48C8B4D40dE216C652ED4D67f6466CeBA90054CA
GET https://<host>/app.html?demo=1
```

The demo workspace intentionally shows the verified reference position. A
normal visit to `/app.html` opens the wallet connection gate and only reads the
address returned by the browser wallet. The second response must show locked market
`0x91360eea2686ef7ce4966b4e82cf6ff712af02baf0f7211459780d9f5af1612a`, direct
oracle state, the live position, and `live_state_stale: false` before calling
the host browser-verified. The workspace URL must render the same live values
and expose only unsigned plan preparation at the wallet boundary.
