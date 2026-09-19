# Deploying the Veltiosi search UI

The search app is a FastAPI server (`server.py`) + dark SPA (`static/index.html`)
that Jev-routes natural-language queries across all six Omni data sources.

## What's deployed

- **systemd user service** `veltiosi-search.service` → uvicorn on `127.0.0.1:8611`
- **Cloudflare tunnel** (`edoras`) ingress → `veltiosi.omnisatya.cc → localhost:8611`
  (in `~/.cloudflared/config.yml`)

## Local URL

`http://127.0.0.1:8611` — search vault + whoop + edoras + raga + itihasa + atma.

## Public URL — one manual DNS step

The `omnisatya.cc` zone is managed in the Cloudflare dashboard (not by this
tunnel's cert), so the DNS record must be added by hand once:

- **Type:** CNAME
- **Name:** `veltiosi`
- **Target:** `e25d1dbb-8ed8-4b04-ab19-5c3113e8f839.cfargotunnel.com`
- **Proxy:** ON (orange cloud)

Then `https://veltiosi.omnisatya.cc` serves the app.

> Note: `cloudflared tunnel route dns` cannot touch the `omnisatya.cc` zone — it
> only owns `edorasapp.com`, and mistakenly created a junk `veltiosi.omnisatya.cc.edorasapp.com`
> record there. Harmless; delete it in the dashboard if you like.

## Reinstall / update

```bash
cp deploy/veltiosi-search.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now veltiosi-search.service
```