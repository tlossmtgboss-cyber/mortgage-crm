# Perennia iMessage — On-Call Runbook

## Heartbeat & alarms

| Signal                                | Source                          | Threshold                         |
| ------------------------------------- | ------------------------------- | --------------------------------- |
| Mac → Perennia health POST            | cron on Mac                     | Missing >5 min → page             |
| Perennia → BlueBubbles `/api/v1/ping` | hourly Celery beat              | 2 consecutive 5xx → page          |
| Outbound send error rate              | `imessage_messages.status`      | >5% errors over 30 min → warn     |
| Webhook lag                           | `imessage_webhook_log`          | >2 min between received_at events |
| Apple ID re-verification needed       | BlueBubbles UI alert            | Manual — page on-call             |

## Common incidents

### "Messages aren't sending"

1. Hit `/api/v1/ping?password=...` against the tunnel hostname. Expected:
   `{"status": 200, "message": "pong"}`.
2. If it 5xx's, SSH into the Mac (Tailscale) and check
   `/var/log/bluebubbles.err.log`. Most common: macOS forced a software
   update and Messages.app needs a fresh sign-in.
3. Open the BlueBubbles app on the Mac. Look for a banner — it surfaces
   iMessage auth errors clearly. Sign in again if prompted.
4. Send a test from the Mac's own Messages app to your phone. If that
   fails, it's an Apple-side issue; nothing to do but wait.

### "Webhooks stopped arriving"

1. Check `imessage_webhook_log.received_at` — newest row?
2. In BlueBubbles UI → API & Webhooks → confirm the Perennia URL is
   still listed and "active". macOS occasionally clears it on app crash.
3. Trigger a manual reset: `POST /api/v1/webhook` with the Perennia URL.

### "Some messages are green-bubble even though the borrower has iMessage"

Apple's downgrade behavior. BlueBubbles will silently route via SMS if:
- The Mac itself is offline (auto-fallback through the SIM)
- The recipient's iMessage handle changed (e.g., new phone)
- Apple's iMessage backend rate-limited the line

Force a re-lookup by clearing the row in `imessage_lookup_cache` for that
phone number, then resending.

### "Apple ID is locked"

Worst case. You'll need to reset via appleid.apple.com from the Mac
itself, re-verify with the SIM (if attached), then re-sign-in to
Messages and FaceTime. BlueBubbles autostart will pick the new session
up. Expect ~30 min of downtime; communicate to LOs.

## Capacity / scaling thresholds

- **One Mac mini comfortably handles ~3,000 outbound messages/day** with
  Private API enabled. Past that you'll see iMessage send timeouts.
- Add a second Mac when sustained daily volume exceeds 2,000.
- The `imessage_lines` table is already keyed by tenant; routing across
  multiple Macs happens automatically once you insert a second row.

## Rotating the BlueBubbles password

1. New password: `openssl rand -hex 32`.
2. BlueBubbles UI → Settings → API & Webhooks → update password.
3. `IMESSAGE_BB_PASSWORD` env var on Railway → update.
4. Trigger a Railway redeploy or `kill -HUP` the FastAPI workers.
