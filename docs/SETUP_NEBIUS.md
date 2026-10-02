# Nebius setup guide

Everything needed before week 2. Total time: ~30–45 minutes.

## 1. Accounts & credits

1. **Token Factory** — sign in at https://tokenfactory.nebius.com (Google/GitHub).
2. **Claim $25 credits** — fill the form linked on the Devpost *Resources* page,
   activation code: `NEBIUS-DEVPOST-GLOBAL26`.
3. **Nebius Builders Program** (also linked in Devpost Resources) — another $25
   Token Factory credits plus AI Cloud / Tavily credits, office hours and the
   builder community. Recommended: it also covers the VM hosting cost.
4. *(Optional)* Attend a **Builders & Brews** event (nearest cities to Indonesia:
   Singapore, Kuala Lumpur, Da Nang, Taipei) — extra credits and $500 City Winner
   eligibility. Not required to compete.

## 2. Token Factory API key

1. Token Factory console → **API keys** → Create API key.
   Copy it immediately — it cannot be viewed again.
2. In this repo:

   ```bash
   cp .env.example .env
   # edit .env → NEBIUS_API_KEY=...
   ```

3. Verify connectivity (needs Python 3.11+):

   ```bash
   python3 -m venv .venv && source .venv/bin/activate
   pip install -e ".[dev]"
   python scripts/smoke_test.py --all
   ```

   Expected: 4 models respond, each with latency + token usage.
   - `401` → key wrong or not saved in `.env`
   - `404` on a model → model id changed; refresh from
     https://tokenfactory.nebius.com/model-catalog.md and update `.env`

## 3. Tavily (web search tool — bonus award)

1. Sign up at https://tavily.com — the free tier (~1k calls/month) is enough for
   development; Builders Program credits can top it up.
2. Put `TAVILY_API_KEY=...` in `.env`. First runtime call lands in week 2.

## 4. VM on Nebius AI Cloud (always-on hosting)

Only needed by week 2/3 — not day 1. The web console is the easiest path.

### Web console (recommended)

1. Open https://console.nebius.com → **Compute → Virtual machines** →
   **Create resource → Virtual machine**.
2. **Compute:** platform **Regular** (CPU only — inference happens on Token
   Factory, no GPU needed). Preset: the smallest comfortable one shown in the
   wizard (on the order of 2–4 vCPU / 8–16 GiB is plenty for this agent).
3. **Storage:** image **Ubuntu 24.04 LTS**, disk type Network SSD, 30–50 GiB.
4. **Network:** default subnet; **Public IP: auto-assign (static)**.
5. **Configuration:** username (not `root`/`admin` — reserved), upload your SSH
   public key.
6. **Review → Create VM.** Copy the public IP from the VM page.

### First login & bootstrap

```bash
ssh <username>@<public_ip>

sudo apt-get update
sudo apt-get install -y docker.io docker-compose-v2 git
git clone <repo-url>   # clone once the GitHub repo exists
cd <repo>
cp .env.example .env   # fill NEBIUS_API_KEY, TELEGRAM_BOT_TOKEN
```

### CLI alternative (optional)

```bash
# install the Nebius AI Cloud CLI, then:
nebius profile create          # opens browser sign-in
nebius compute instance create --help   # full reference: docs.nebius.com/compute/virtual-machines/manage
```

The Compute quickstart (docs.nebius.com/compute/quickstart) has copy-pasteable
commands; for a CPU VM use image family `ubuntu24.04-driverless`.

### Ports & security

- Now: SSH (22) — ideally restricted to your IP in **VPC → Security groups**.
- Week 3 (dashboard deploy): allow inbound **80/443**.
- Alternative to a public dashboard: Nebius **Tunnels**.

### Cost control

- A small CPU VM is billed per hour — stop the VM when not in use until week 3.
- Check **Billing** in the console; Builders Program credits should cover it.

## 5. Telegram bot (needed in week 3 — can set up now)

1. Chat with **@BotFather** → `/newbot` → follow prompts.
2. Save the token → `.env`: `TELEGRAM_BOT_TOKEN=...`.
3. Send `/start` to your new bot once from your own account (so it can message
   you proactively later).

## 6. Week-1 verification checklist

- [ ] `python scripts/smoke_test.py --all` → all models OK
- [ ] `pytest -q` → green
- [ ] SSH to the VM works
- [ ] GitHub repo public, MIT license visible at the top of the page
- [ ] `TAVILY_API_KEY` and `TELEGRAM_BOT_TOKEN` stored in `.env`