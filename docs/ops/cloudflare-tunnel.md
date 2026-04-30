# Perennia iMessage — Cloudflare Tunnel

The Mac mini's BlueBubbles HTTP service must be reachable from Railway
(where Perennia's FastAPI backend runs) without exposing it on the
public internet directly. We use Cloudflare Tunnel — free, stable URL
that survives Mac reboots and IP changes.

## Why not ngrok?

The free ngrok URL changes every restart. BlueBubbles webhooks become
stale. Cloudflare Tunnel gives a permanent `imessage-1.tldevelopment.dev`
hostname tied to a tunnel ID, not an IP.

## One-time setup on Cloudflare

1. Add `tldevelopment.dev` (or any domain you own) to Cloudflare.
2. Cloudflare Zero Trust dashboard → Networks → Tunnels → Create a tunnel.
3. Name: `perennia-imessage-mac1`. Save tunnel token in 1Password.

## Install the connector on the Mac mini

```bash
# Apple Silicon
brew install cloudflared

# Authenticate to your CF account
cloudflared tunnel login

# Create the tunnel locally and bind it to the token from the dashboard
cloudflared service install <TUNNEL_TOKEN>
```

## Tunnel config

`/Users/perennia/.cloudflared/config.yml`:

```yaml
tunnel: <TUNNEL_UUID>
credentials-file: /Users/perennia/.cloudflared/<TUNNEL_UUID>.json

ingress:
  # BlueBubbles HTTP API
  - hostname: imessage-1.tldevelopment.dev
    service: http://localhost:1234
    originRequest:
      connectTimeout: 30s
      noTLSVerify: false
  # Catch-all
  - service: http_status:404
```

DNS for `imessage-1.tldevelopment.dev` is set automatically by the
tunnel — it becomes a CNAME to `<TUNNEL_UUID>.cfargotunnel.com`.

## Lock down the tunnel

In Cloudflare Zero Trust → Access:

1. Create an Application: `imessage-1.tldevelopment.dev`.
2. Policy: **Service Auth** only.
3. Add a Service Token. Copy the `CF-Access-Client-Id` and
   `CF-Access-Client-Secret` headers — Perennia's BlueBubbles client
   sends these on every request (config keys
   `IMESSAGE_CF_ACCESS_CLIENT_ID` and `IMESSAGE_CF_ACCESS_CLIENT_SECRET`).

This means even if the BlueBubbles server password leaks, an attacker
can't reach the endpoint without the Cloudflare service token.

## Webhook delivery from BlueBubbles → Perennia

The reverse direction (BlueBubbles posting webhooks to Perennia) goes
through normal HTTPS to `https://api.perennia.ai/webhooks/imessage/<token>`.
The Mac initiates the connection, so no inbound exposure is needed.
