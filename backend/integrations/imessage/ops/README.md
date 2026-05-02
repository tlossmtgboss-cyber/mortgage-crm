# BlueBubbles Mac Mini — Operational Hardening

Scripts to keep the BlueBubbles server running reliably on the dedicated Mac Mini.

## 1. Caffeinate Launch Agent (Prevent Sleep)

Prevents the Mac from sleeping (display sleep, idle sleep, system sleep).

**Install:**

```bash
cp com.perenniaai.caffeinate.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.perenniaai.caffeinate.plist
```

**Verify it's running:**

```bash
launchctl list | grep caffeinate
```

**Unload (if needed):**

```bash
launchctl unload ~/Library/LaunchAgents/com.perenniaai.caffeinate.plist
```

## 2. BlueBubbles Health Check Cron

Pings the BlueBubbles API every 60 seconds. After 3 consecutive failures, logs a CRITICAL entry to `/tmp/bb_health.log`.

**Install:**

```bash
chmod +x bb_health_check.sh
echo "* * * * * $(pwd)/bb_health_check.sh" | crontab -
```

**Verify cron is set:**

```bash
crontab -l
```

**Check health log:**

```bash
cat /tmp/bb_health.log
```

To override the BlueBubbles password, export `IMESSAGE_BB_PASSWORD` before the cron runs (or edit the script default).

## 3. Disable macOS Auto-Update

Automatic OS updates can restart the machine and kill BlueBubbles.

1. Open **System Settings** -> **General** -> **Software Update**
2. Click the **(i)** next to **Automatic Updates**
3. Turn OFF all toggles:
   - Download new updates when available
   - Install macOS updates
   - Install application updates from the App Store
   - Install Security Responses and system files

## 4. Pin BlueBubbles Server Version

Do not enable auto-update in BlueBubbles. A bad update can break the API contract.

- In BlueBubbles settings, ensure **Auto-update** is OFF
- Test new versions manually before upgrading
- Document the current running version here for reference
