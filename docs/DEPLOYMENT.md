# Deploying TelecomInsight BW

Two Streamlit sites share one database:

| Site | File | Port | Who signs in |
|------|------|------|--------------|
| Provider site | `app.py` | 8501 | provider users: dashboard and their own uploads |
| Administration site | `admin_app.py` | 8502 | administrators: accounts, access, oversight |

## Option A: Docker (recommended)

1. `cp .env.example .env` and set `POSTGRES_PASSWORD`, `BOOTSTRAP_ADMIN_USERNAME`, `BOOTSTRAP_ADMIN_PASSWORD`.
2. `docker compose up -d --build`
3. Open `http://SERVER:8502`, sign in as the bootstrap administrator, create providers and users.
4. Remove `BOOTSTRAP_ADMIN_PASSWORD` from `.env`, then `docker compose up -d`.
5. Give providers the provider-site address (port 8501).

## Option B: hosting services (Streamlit Community Cloud, Render, Railway ...)

- Create one app from `app.py` and a second from `admin_app.py`, both pointing at the SAME PostgreSQL database.
- Set `DATABASE_URL`, `BOOTSTRAP_ADMIN_USERNAME`, `BOOTSTRAP_ADMIN_PASSWORD`, `SEED_DEMO_DATA=0`
  as environment variables / secrets.
- Do not use SQLite on a host whose disk is wiped on restart: use PostgreSQL.

## Before going live

- [ ] HTTPS: put both sites behind a reverse proxy or the hosting service's TLS (Caddy, nginx, Cloudflare).
- [ ] Ideally keep the administration site off the public internet (VPN or IP allow-list).
- [ ] Strong, unique `POSTGRES_PASSWORD`; `.env` is never committed.
- [ ] `BOOTSTRAP_ADMIN_PASSWORD` removed after first start.
- [ ] `SEED_DEMO_DATA=0`; remove any demo data on the Data overview tab.
- [ ] Backups: `docker compose exec db pg_dump -U telecom telecominsight > backup.sql` on a schedule.
- [ ] Run `python -m pytest` and get all green.

## Behaviour to know

- Sessions last 60 minutes. Disabling a user or a provider takes effect on their next click.
- 5 failed sign-ins on an account within 15 minutes locks that account for the rest of the window.
- Provider dashboards cache data for up to 60 seconds; a provider's own upload refreshes at once.
- A provider's CSV `provider` column must match their provider name (capitals ignored); other rows are rejected.