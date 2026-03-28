# APNS Setup Guide — Perennia AI iOS Push Notifications

## Prerequisites
- Apple Developer Account (Team ID: V5ZA5FZ2J8)
- Access to Apple Developer Portal

## Step 1: Create APNS Key

1. Go to https://developer.apple.com/account/resources/authkeys/list
2. Click "+" to create a new key
3. Name: "Perennia AI Push Key"
4. Check "Apple Push Notifications service (APNs)"
5. Click Continue → Register
6. **Download the .p8 file** (you can only download once!)
7. Note the **Key ID** (10-character string)

## Step 2: Store the Key

```bash
# On the server / Railway
mkdir -p /app/keys
# Upload your .p8 file to /app/keys/AuthKey_<KEY_ID>.p8
```

## Step 3: Set Environment Variables

Add these to Railway (or your deployment platform):

```
APNS_KEY_ID=<your 10-char key ID>
APNS_TEAM_ID=V5ZA5FZ2J8
APNS_KEY_PATH=/app/keys/AuthKey_<KEY_ID>.p8
APNS_BUNDLE_ID=com.perenniaai.crm
APNS_USE_SANDBOX=false
```

Set `APNS_USE_SANDBOX=true` for development/TestFlight builds.

## Step 4: Verify

```bash
curl -X POST https://api.perenniaai.com/api/v1/push/test \
  -H "Authorization: Bearer <your-token>"
```

Should return `{"success": true, "sent": 1, ...}`

## Troubleshooting

| Error | Fix |
|-------|-----|
| "APNS not configured" | Check env vars are set and .p8 file exists at APNS_KEY_PATH |
| "BadDeviceToken" | Device token is invalid or from wrong environment (sandbox vs production) |
| "TopicDisallowed" | Bundle ID doesn't match the APNS key's associated app |
