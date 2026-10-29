# Deploying Mitra on a VPS behind Cloudflare Tunnel

The live instance: **<https://mitra.pavernor.tech>**

It runs in Docker on `vps-alvn` (43.228.214.64), published on
`127.0.0.1:8099`, reached only through an existing `cloudflared` tunnel
(`pavernor`, ingress → `http://127.0.0.1:8099`). Port 8099 is not reachable from
the internet; the tunnel is the only way in. That is what makes
`CF-Connecting-IP` trustworthy, and therefore what makes per-visitor rate limits
actually per-visitor.

## Layout on the server

```
/home/alvn/mitra/                 # this repo (rsynced, no .git, no data)
/home/alvn/mitra/.env             # mode 600, holds the Nebius key
/home/alvn/mitra/reseed.sh        # mode 700, nightly reseed via the admin API
/home/alvn/.cloudflared/config.yml # tunnel ingress (specific hostname first)
docker compose -p mitra           # project name isolates it from other stacks
```

## First deploy

```bash
# from your machine, in the repo root
rsync -az --exclude '.git' --exclude '.venv' --exclude 'data' \
  --exclude '.design' --exclude '__pycache__' --exclude 'docs/media' \
  --exclude '.ruff_cache' --exclude '.pytest_cache' --exclude '.env' \
  ./ vps-alvn:/home/alvn/mitra/

# on the server: .env (600), then build
ssh vps-alvn
cd ~/mitra && docker compose -p mitra up -d --build
curl -s http://127.0.0.1:8099/api/health          # expect "provider":"nebius"
```

`.env` (never committed, mode `600`):

```ini
NEBIUS_API_KEY=…                                   # the only real secret
MITRA_PROVIDER=auto                                # Nebius, else labelled local model
MITRA_DEMO_MODE=1                                  # banner + admin reset
MITRA_BIND=127.0.0.1                               # loopback only
MITRA_PORT=8099
MITRA_TRUST_PROXY=1                                # trust CF-Connecting-IP
MITRA_DAILY_BUDGET_USD=0.30                        # hard money ceiling
MITRA_CHAT_PER_HOUR=6  MITRA_CHAT_PER_DAY=20
MITRA_GLOBAL_CHATS_PER_DAY=40  MITRA_CHAT_COOLDOWN_S=5
MITRA_WRITES_PER_MINUTE=15  MITRA_GLOBAL_WRITES_PER_MINUTE=40
MITRA_ADMIN_TOKEN=…                                # openssl rand -hex 24
MITRA_TIMEZONE=Asia/Jakarta
```

## Tunnel ingress

`~/.cloudflared/config.yml` — the specific hostname must come **before** the
`*.pavernor.tech` wildcard, or Traefik answers instead:

```yaml
ingress:
  - hostname: "mitra.pavernor.tech"
    service: http://127.0.0.1:8099
    originRequest:
      connectTimeout: 30s
      httpHostHeader: "mitra.pavernor.tech"
```

```bash
cloudflared tunnel --config ~/.cloudflared/config.yml ingress validate
systemctl --user restart cloudflared-pavernor.service
```

DNS is already covered by the zone's `*.pavernor.tech` record, so no new record
is needed. Verify:

```bash
curl -s https://mitra.pavernor.tech/api/health
```

## Nightly reseed

The demo's dates are relative to "today", so it is reseeded at 03:17. The script
goes through the API (not the database file) because the app has to rebind every
component to the fresh ledger:

```cron
17 3 * * * /home/alvn/mitra/reseed.sh >> /home/alvn/mitra/reseed.log 2>&1
```

`reseed.sh` reads `MITRA_ADMIN_TOKEN` from the same `.env` and posts it as
`x-mitra-admin`. Without that header the endpoint returns `403`.

## Admin access from a browser

```
https://mitra.pavernor.tech/?admin=<MITRA_ADMIN_TOKEN>
```

The app sets an HttpOnly, `Secure`, `SameSite=Strict` cookie, 303-redirects to
the same path without the query string, and the "Reset demo data" control
appears in the rail. Close the tab's cookies to drop it.

## Rotating the key

```bash
ssh vps-alvn
cd ~/mitra
sed -i 's/^NEBIUS_API_KEY=.*/NEBIUS_API_KEY=NEW_KEY/' .env   # mode stays 600
docker compose -p mitra up -d                                # recreate, not rebuild
curl -s http://127.0.0.1:8099/api/health                     # "provider":"nebius"
```

If the key is rejected the router probes at startup, flips to `provider: demo`
and the UI says so — the site stays up rather than showing a broken chat.

## What to check after any deploy

```bash
curl -s  https://mitra.pavernor.tech/api/health
curl -s -o /dev/null -w '%{http_code}\n' -X POST https://mitra.pavernor.tech/api/demo/reset      # 403
curl -s https://mitra.pavernor.tech/ | grep -o 'app.js?v=[0-9-]*'                                # cache-buster present
docker logs mitra 2>&1 | grep -c 'sk-\|Bearer'                                                  # 0

# from another machine: the port must refuse
timeout 5 bash -c 'cat < /dev/null > /dev/tcp/43.228.214.64/8099' || echo "closed (good)"
```

Then run the interaction suite against the public URL:

```bash
.venv/bin/python scripts/smoke_ui.py https://mitra.pavernor.tech
```

## Failure modes worth knowing

| Symptom | Cause | Fix |
|---|---|---|
| `502` from Cloudflare | container down or wrong port | `docker compose -p mitra ps`, `docker logs mitra` |
| UI looks like an older version | CDN cached a stale asset | the shell links `app.js?v=<mtime>-<size>`, so bump the file; `Cache-Control: no-cache` is set on `/` and `/static/{js,css}` |
| Chat answers "local demo model" | key rejected at startup | check `router.degraded_reason` in `/api/bootstrap` |
| `429` on chat | rate limit (4s cooldown, 6/h, 20/day, 40/day global) | wait; the response carries `retry_after_s` |
| `BudgetExceeded` in a run | `MITRA_DAILY_BUDGET_USD` reached | raise it or wait for the UTC day to roll over |
| Reset button missing | no admin cookie | open `/?admin=<token>` |
