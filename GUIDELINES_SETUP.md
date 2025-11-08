# Mortgage Guidelines Integration - Setup Instructions

## ⚠️ IMPORTANT SECURITY NOTICE

**Your credentials were shared in plain text.** For security:
1. Follow the setup steps below to store credentials securely
2. **Change your password** at https://my.mortgageguidelines.com/ after setup
3. Consider using a dedicated service account instead of your personal account

---

## 🚀 Setup Instructions

### Step 1: Store Credentials Securely in Railway

1. Go to https://railway.app/dashboard
2. Select your `mortgage-crm` backend project
3. Click on the **Variables** tab
4. Add these environment variables:

```
GUIDELINES_URL=https://my.mortgageguidelines.com/
GUIDELINES_USERNAME=tloss@cmghomeloans.com
GUIDELINES_PASSWORD=Woodwindow00!
```

5. Click **Deploy** to restart the backend with new variables

### Step 2: Verify Deployment

Once Railway redeploys (2-3 minutes):
1. Go to https://mortgage-crm-nine.vercel.app/guidelines
2. The page should load and show the Guidelines iframe
3. You may need to log in manually at the guidelines site

---

## 🔒 Security Best Practices

### Immediate Actions
- [ ] Add environment variables to Railway (see Step 1)
- [ ] Change your password at mortgageguidelines.com
- [ ] Verify the new credentials work

### Long-term Recommendations
1. **Use a Service Account**: Create a dedicated account for the CRM integration
2. **Enable 2FA**: If mortgageguidelines.com supports it
3. **Rotate Passwords**: Change credentials every 90 days
4. **Monitor Access**: Check for unusual activity

### Never Do This Again
❌ Sharing passwords in chat, email, or documents
❌ Committing credentials to git
❌ Storing passwords in code

✅ Use environment variables
✅ Use password managers
✅ Use service accounts for integrations

---

## 🔧 Future Enhancements

The current implementation shows the guidelines site in an iframe. Future versions could include:

### Phase 1: Auto-Login (Coming Soon)
- Backend authenticates with stored credentials
- Returns authenticated session cookie
- Frontend loads guidelines pre-authenticated

### Phase 2: API Integration
- Direct API access (if mortgageguidelines.com provides one)
- Search functionality from within CRM
- Guideline caching for faster access

### Phase 3: AI Integration
- AI reads guidelines automatically
- Answers guideline questions in chat
- Flags loans that don't meet guidelines
- Suggests alternative loan products

---

## 📋 Environment Variables Reference

| Variable | Description | Example |
|----------|-------------|---------|
| `GUIDELINES_URL` | Base URL for guidelines site | `https://my.mortgageguidelines.com/` |
| `GUIDELINES_USERNAME` | Login email/username | `your-email@domain.com` |
| `GUIDELINES_PASSWORD` | Account password | Use Railway Variables tab |

---

## 🧪 Testing

### Manual Test
1. Visit https://mortgage-crm-nine.vercel.app/guidelines
2. Should see guidelines iframe
3. May need to log in manually (for now)

### API Test
```bash
# Get your auth token
curl -X POST https://mortgage-crm-production-7a9a.up.railway.app/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=demo@example.com&password=demo123"

# Test guidelines endpoint
curl -X GET https://mortgage-crm-production-7a9a.up.railway.app/api/v1/guidelines/session \
  -H "Authorization: Bearer YOUR_TOKEN_HERE"
```

Expected response:
```json
{
  "url": "https://my.mortgageguidelines.com/",
  "authenticated": false,
  "message": "Please log in at the guidelines site"
}
```

---

## 🐛 Troubleshooting

### Issue: Guidelines page is blank
**Solution**: Check if the iframe is blocked by browser security. Try opening in a new tab using the button.

### Issue: Can't see Guidelines in navigation
**Solution**: Hard refresh your browser (Ctrl+Shift+R or Cmd+Shift+R) to get latest code.

### Issue: 401 Unauthorized error
**Solution**: Log in to the CRM first. Guidelines requires authentication.

---

## 📞 Support

If you need help:
1. Check Railway logs for backend errors
2. Check browser console for frontend errors
3. Verify environment variables are set correctly

---

**Status**: ✅ Basic iframe integration complete
**Next**: Add auto-login with stored credentials (requires testing)
