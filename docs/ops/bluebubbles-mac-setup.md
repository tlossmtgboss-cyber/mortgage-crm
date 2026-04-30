# Perennia iMessage — Mac Mini Setup

This is the one-time hardware/software setup for the Mac mini that hosts
BlueBubbles Server and acts as Perennia's iMessage relay.

## Hardware

- **Mac mini** (M2 base or newer, 8GB+ RAM). Used M1 minis off Backmarket
  ($300–$500) work fine. Avoid Intel — Big Sur EOL'd many private API hooks.
- **UPS** (CyberPower CP1500 or similar). Power loss = downtime + Apple ID
  re-verification headaches. Non-optional.
- **Wired Ethernet**. Wi-Fi disconnects manifest as silent message-send timeouts.
- **Static internal IP** assigned by your router via DHCP reservation.

## macOS prep

1. Install latest macOS (Sequoia 15.x or newer).
2. Create a dedicated local user `perennia` (admin). Never use a personal
   Apple ID — register a fresh one tied to a TL Development email and a
   throwaway phone number you control. Keep credentials in 1Password under
   the team vault.
3. Sign into iMessage **and** FaceTime with that Apple ID:
   - Messages → Settings → iMessage → enable, sign in
   - FaceTime → Preferences → enable, sign in
   - Add the cell number used to register if you want SMS-from-Mac
     fallback (System Settings → AirDrop & Handoff → "Allow Phone Calls
     on Other Devices" requires an iPhone signed into the same iCloud).
4. Disable sleep entirely:
   ```bash
   sudo pmset -a sleep 0 disksleep 0 displaysleep 0 powernap 0 standby 0 \
                  autopoweroff 0 hibernatemode 0
   ```
5. Disable software updates auto-restart:
   ```bash
   sudo softwareupdate --schedule off
   ```
6. Enable auto-login for the `perennia` user (System Settings → Users &
   Groups → Automatic login). This is what makes the server come back up
   on power restore.
7. Disable screen lock and password-after-screensaver (System Settings →
   Lock Screen).
8. Turn off Spotlight indexing of the home folder for performance:
   ```bash
   sudo mdutil -i off /Users/perennia
   ```

## Install BlueBubbles Server

1. Download the latest release from
   https://github.com/BlueBubblesApp/bluebubbles-server/releases — grab the
   `.dmg` matching your Mac architecture (`arm64` for Apple Silicon).
2. Drag `BlueBubbles.app` into `/Applications`.
3. Launch it. macOS will prompt for permissions; grant ALL of them:
   - Full Disk Access (for Messages.app database)
   - Accessibility
   - Automation → Messages, Contacts, FaceTime
   - Contacts (for participant resolution in group threads)
   - Notifications (silence them after granting)
4. **Set a strong server password.** This is the value of `password=` on
   every BlueBubbles API call. Generate with `openssl rand -hex 32`. Store
   in 1Password and paste into Settings → API & Webhooks → Password.
5. Enable **Private API** in Settings. This unlocks tapbacks, typing
   indicators, message effects, read receipts. Follow the in-app
   instructions to install the helper bundle (System Integrity Protection
   does NOT need to be disabled on Apple Silicon for the modern helper).
6. Settings → Backend → enable **HTTP Service** on port `1234` (default).
   Leave the local LAN port closed via firewall — we expose it through
   Cloudflare Tunnel only (see `cloudflare-tunnel.md`).

## Autostart on boot

`launchd` plist so BlueBubbles starts even after a kernel panic / power loss:

```xml
<!-- /Library/LaunchAgents/com.tldevelopment.bluebubbles.plist -->
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.tldevelopment.bluebubbles</string>
  <key>Program</key><string>/Applications/BlueBubbles.app/Contents/MacOS/BlueBubbles</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>/var/log/bluebubbles.out.log</string>
  <key>StandardErrorPath</key><string>/var/log/bluebubbles.err.log</string>
</dict>
</plist>
```

```bash
sudo launchctl load -w /Library/LaunchAgents/com.tldevelopment.bluebubbles.plist
```

## Phone number registration

iMessage delivers as blue bubble only if the sender's identity matches an
iMessage-registered handle. Two paths:

1. **Email-only Apple ID** — the LO sends from the Apple ID's email
   address. Borrowers see the email handle in their Messages app. Less
   ideal for branding.
2. **Phone-number-attached Apple ID** — register a real phone number
   (Twilio/Telnyx unsupported by Apple; you need a SIM). Cheapest route
   is a $10/mo Mint Mobile plan with a SIM in a spare iPhone signed into
   the same Apple ID, then "Allow Phone Calls on Other Devices" lets the
   Mac use that number. Apple periodically forces re-verification — plan
   for it.

For TL Development's first deployment, start with email-only. Add the SIM
path before opening iMessage to all LOs.

## Health checks the Mac itself should pass daily

Add a cron (or `launchd` agent) on the Mac that posts `GET /api/v1/ping`
to itself and pings `https://api.perennia.ai/internal/health/imessage`
with the result. The Perennia health dashboard surfaces the line as
DEGRADED if no ping in the last 5 minutes.
