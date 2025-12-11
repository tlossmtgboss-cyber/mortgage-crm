# Phase 2 Deployment Guide

## Pre-Deployment Checklist

### 1. Environment Variables

Ensure these are set in Railway:

```bash
# Required for AI features
ANTHROPIC_API_KEY=sk-ant-api03-...

# Existing (should already be set)
DATABASE_URL=postgresql://...
JWT_SECRET=...
```

### 2. Verify Files

Confirm these files exist:

**Backend:**
- [ ] `backend/services/ai_insights_service.py`
- [ ] `backend/services/weekly_digest_service.py`
- [ ] `backend/ai_insights_routes.py`

**Frontend:**
- [ ] `frontend/src/components/AIInsightsPanel.jsx`
- [ ] `frontend/src/components/AIInsightsPanel.css`
- [ ] `frontend/src/components/SmartRecommendations.jsx`
- [ ] `frontend/src/components/SmartRecommendations.css`
- [ ] `frontend/src/components/CostToCloseChart.js`
- [ ] `frontend/src/components/CostToCloseChart.css`

## Deployment Steps

### Backend (Railway)

```bash
cd /Users/timothyloss/my-project/mortgage-crm/backend

# Deploy to Railway
railway up --detach

# View logs
railway logs
```

### Frontend (Vercel)

```bash
cd /Users/timothyloss/my-project/mortgage-crm/frontend

# Build
npm run build

# Deploy
vercel --prod --yes
```

## Post-Deployment Verification

### 1. Test API Endpoints

```bash
# Get auth token
TOKEN=$(curl -s -X POST "https://mortgage-crm-production-7a9a.up.railway.app/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"username": "admin@perenniaai.com", "password": "password"}' | jq -r '.access_token')

# Test AI query
curl -X POST "https://mortgage-crm-production-7a9a.up.railway.app/api/v1/profitability/ai/query" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"question": "What is our cost per loan?"}'

# Test recommendations
curl "https://mortgage-crm-production-7a9a.up.railway.app/api/v1/profitability/ai/recommendations" \
  -H "Authorization: Bearer $TOKEN"

# Test suggested questions
curl "https://mortgage-crm-production-7a9a.up.railway.app/api/v1/profitability/ai/suggested-questions" \
  -H "Authorization: Bearer $TOKEN"
```

### 2. Test Frontend

1. Go to https://mortgage-crm-nine.vercel.app
2. Log in as admin@perenniaai.com
3. Navigate to Profitability (in toolbar)
4. Verify dashboard loads
5. Click "AI Assistant" tab
6. Test a query
7. Generate recommendations

### 3. Verify Components

- [ ] Cost to Close chart displays with live indicator
- [ ] AI query input accepts text
- [ ] Suggested questions are clickable
- [ ] Recommendations generate successfully
- [ ] Hiring analysis form works
- [ ] Navigation link appears for admin users

## Troubleshooting

### "AI query failed" Error

1. Check ANTHROPIC_API_KEY in Railway:
   ```bash
   railway variables
   ```

2. Verify key is valid and has credits

3. Check Railway logs:
   ```bash
   railway logs --tail 100
   ```

### Dashboard Not Loading

1. Check browser console for errors
2. Verify API is responding:
   ```bash
   curl https://mortgage-crm-production-7a9a.up.railway.app/health
   ```

3. Clear browser cache and retry

### No Data Showing

1. Verify profitability data exists:
   - Go to dashboard
   - Check if metrics show zeros

2. Add sample data if needed

### Navigation Link Not Showing

1. Verify user role is "management" or "admin"
2. Check localStorage for user data
3. Re-login if needed

## Rollback Procedure

If issues occur:

### Revert Backend
```bash
git log --oneline -10  # Find previous commit
git revert HEAD        # Revert last commit
git push origin main
railway up
```

### Revert Frontend
```bash
git revert HEAD
git push origin main
cd frontend && npm run build && vercel --prod
```

## Monitoring

### Railway Dashboard
- Monitor CPU/memory usage
- Check error rates
- View response times

### Vercel Dashboard
- Check deployment status
- View build logs
- Monitor analytics

## Email Digest Setup (Optional)

To enable weekly email digests:

1. Set SMTP variables in Railway:
   ```
   SMTP_SERVER=smtp.gmail.com
   SMTP_PORT=587
   SMTP_USER=your_email@gmail.com
   SMTP_PASSWORD=your_app_password
   FROM_EMAIL=noreply@yourcompany.com
   ```

2. Create a cron job or scheduled task to call:
   ```bash
   curl -X POST "https://your-api/api/v1/profitability/ai/send-digest" \
     -H "Authorization: Bearer $ADMIN_TOKEN" \
     -d '{"recipients": ["ceo@company.com"]}'
   ```

## Support

For issues:
1. Check Railway logs
2. Check browser console
3. Review this guide
4. Contact development team

---

**Deployment Guide Version**: 1.0
**Last Updated**: November 22, 2025
