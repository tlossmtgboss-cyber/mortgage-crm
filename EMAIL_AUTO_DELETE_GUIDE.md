# Email Auto-Delete Feature Guide

## Overview

The CRM now supports **automatic deletion** of emails from your Microsoft 365 inbox after they've been successfully imported into the CRM and tasks have been created.

## How It Works

### Workflow

1. **Email Sync**: Microsoft 365 emails are synced to the CRM
2. **Processing**: Email content is analyzed and classified
3. **Task Creation**: If relevant, tasks are created from the email content
4. **Auto-Delete** (Optional): Email is automatically deleted from your inbox after successful import

### When Emails Are Deleted

Emails are **only** deleted from your inbox when:
- ✅ Auto-delete is **enabled** in settings
- ✅ Email was **successfully processed** (data extracted)
- ✅ Email content was **classified** as relevant (not "unrelated")
- ✅ A task or data record was **created** in the CRM

Emails are **NOT** deleted if:
- ❌ Auto-delete is disabled
- ❌ Processing failed or encountered errors
- ❌ Email was classified as "unrelated"
- ❌ No extractable data was found

## How to Enable Auto-Delete

### Option 1: Via API (Recommended)

Update your Microsoft 365 settings:

```bash
curl -X PATCH https://your-api.com/api/v1/microsoft/settings \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "auto_delete_imported_emails": true
  }'
```

### Option 2: Via Frontend Settings

1. Navigate to **Settings > Integrations**
2. Find **Microsoft 365 / Outlook Email**
3. Click **Manage** or **Settings**
4. Toggle **Auto-delete imported emails**
5. Click **Save**

## Configuration Options

### Settings Available

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `sync_enabled` | Boolean | `true` | Enable/disable email sync |
| `sync_folder` | String | `"Inbox"` | Which folder to sync |
| `sync_frequency_minutes` | Integer | `15` | How often to sync (5-1440) |
| `auto_delete_imported_emails` | Boolean | `false` | Delete after import |

### Check Current Settings

```bash
curl -X GET https://your-api.com/api/v1/microsoft/status \
  -H "Authorization: Bearer YOUR_TOKEN"
```

Response:
```json
{
  "connected": true,
  "email_address": "you@example.com",
  "sync_enabled": true,
  "last_sync_at": "2025-01-15T10:30:00Z",
  "sync_folder": "Inbox",
  "sync_frequency_minutes": 15,
  "auto_delete_imported_emails": true
}
```

## Safety Features

### Built-in Protections

1. **Deletion Logging**: All deletions are logged with email subject and ID
2. **Error Handling**: If deletion fails, the import still succeeds (email stays in inbox)
3. **Transaction Safety**: Deletion only happens after successful database commit
4. **No Cascade**: Failed deletion doesn't affect CRM import

### What Happens If Deletion Fails?

- ✅ Email data is **already saved** in the CRM
- ✅ Tasks are **already created**
- ⚠️ Email **remains in inbox** (manual deletion needed)
- 📝 Error is **logged** for troubleshooting

## Database Migration

Before using this feature, run the migration to add required columns:

```bash
cd backend
python add_email_deletion_columns.py
```

This adds:
- `auto_delete_imported_emails` column to `microsoft_oauth_tokens` table
- `microsoft_message_id` column to `incoming_data_events` table

## Use Cases

### When to Enable Auto-Delete

✅ **Enable** if you:
- Want a clean inbox
- Process high volumes of automated emails
- Have confidence in the CRM's import accuracy
- Prefer CRM as single source of truth

### When to Keep Disabled

❌ **Disable** if you:
- Need email archive for compliance
- Want to manually review before deletion
- Use inbox for cross-reference
- Are testing the CRM integration

## Troubleshooting

### Emails Not Being Deleted

**Check these items:**

1. Is auto-delete enabled?
   ```bash
   curl -X GET .../api/v1/microsoft/status
   ```

2. Was the email successfully processed?
   - Check logs for "✅ Auto-deleted email" messages
   - Look for processing errors in logs

3. Was data extracted from the email?
   - Only emails with extracted data are deleted
   - Check reconciliation center for imported data

4. Is the email classified as relevant?
   - "Unrelated" emails are not deleted
   - Check email classification in logs

### View Deletion Logs

```bash
# Railway logs
railway logs | grep "Auto-deleted email"

# Local logs
tail -f logs/app.log | grep "Auto-deleted"
```

### Disable Auto-Delete

```bash
curl -X PATCH .../api/v1/microsoft/settings \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"auto_delete_imported_emails": false}'
```

## API Reference

### Update Settings

**Endpoint:** `PATCH /api/v1/microsoft/settings`

**Request Body:**
```json
{
  "sync_enabled": true,
  "sync_folder": "Inbox",
  "sync_frequency_minutes": 15,
  "auto_delete_imported_emails": true
}
```

**Response:**
```json
{
  "status": "success",
  "message": "Settings updated successfully"
}
```

### Get Status

**Endpoint:** `GET /api/v1/microsoft/status`

**Response:**
```json
{
  "connected": true,
  "email_address": "user@example.com",
  "sync_enabled": true,
  "last_sync_at": "2025-01-15T10:30:00Z",
  "sync_folder": "Inbox",
  "sync_frequency_minutes": 15,
  "auto_delete_imported_emails": true
}
```

### Manual Sync

**Endpoint:** `POST /api/v1/microsoft/sync-now`

Triggers immediate sync with auto-delete (if enabled).

## Security Considerations

### Permissions Required

- **Mail.Read**: Required to read emails
- **Mail.ReadWrite**: Required to delete emails (update your Azure app permissions)

### Update Azure App Registration

1. Go to [Azure Portal](https://portal.azure.com)
2. Navigate to **App Registrations**
3. Select your CRM app
4. Go to **API Permissions**
5. Add **Microsoft Graph > Mail.ReadWrite** (delegated permission)
6. Click **Grant admin consent**

### Audit Trail

All deletions are logged with:
- Email subject
- Microsoft message ID
- Timestamp
- Success/failure status

## Best Practices

1. **Test First**: Try with a test inbox before production
2. **Monitor Logs**: Watch deletion logs for the first few days
3. **Review Classification**: Check what emails are being classified as "relevant"
4. **Backup Strategy**: Consider using email archiving rules before enabling
5. **Compliance**: Verify this meets your data retention policies

## FAQ

**Q: Can I recover deleted emails?**
A: Yes, check your Microsoft 365 Deleted Items folder. Emails stay there for 30 days by default.

**Q: What if I accidentally delete important emails?**
A: The CRM imports the full email content, so you can view it in the CRM's reconciliation center.

**Q: Can I choose which emails to delete?**
A: Currently it's all-or-nothing. Future versions may support rules-based deletion.

**Q: Does this work with Gmail?**
A: Currently only Microsoft 365/Outlook is supported.

**Q: What about email attachments?**
A: Attachments are preserved in the CRM if they were processed during import.

## Changelog

- **v1.0** (2025-01-15): Initial release
  - Auto-delete emails after successful import
  - Configurable via API settings
  - Full logging and error handling

---

**Need Help?** Check the logs or contact support with your Railway logs.
