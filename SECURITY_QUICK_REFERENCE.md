# Security Quick Reference

## 🔒 Security Protection Summary

Your Mortgage CRM is now protected with enterprise-grade security measures:

---

## ✅ What's Protected

### 1. **Rate Limiting**
- ✅ 100 requests/minute per IP
- ✅ 2000 requests/hour per IP
- ✅ Automatic blocking on violation
- **Protects against:** Brute force, DDoS, API abuse

### 2. **Automatic IP Blocking**
- ✅ Blocks after 5 failed login attempts
- ✅ Detects SQL injection attempts
- ✅ Detects XSS attack patterns
- ✅ Blocks path traversal attacks
- **Protects against:** Malicious actors, automated attacks

### 3. **Security Headers**
- ✅ Content Security Policy (CSP)
- ✅ X-Frame-Options (prevents clickjacking)
- ✅ Strict-Transport-Security (HTTPS enforcement)
- ✅ X-XSS-Protection
- **Protects against:** XSS, clickjacking, MITM attacks

### 4. **Authentication Security**
- ✅ Short-lived access tokens (30 min)
- ✅ Refresh tokens (7 days)
- ✅ Token type validation
- ✅ User status verification
- **Protects against:** Token theft, session hijacking

### 5. **Input Validation**
- ✅ Request size limits (10 MB max)
- ✅ Content-Type validation
- ✅ SQL injection pattern blocking
- ✅ XSS payload blocking
- **Protects against:** Injection attacks, malformed data

### 6. **Password Security**
- ✅ Bcrypt hashing
- ✅ Automatic salting
- ✅ No plaintext storage
- **Protects against:** Password cracking, rainbow tables

### 7. **CORS Protection**
- ✅ Restricted origins
- ✅ Specific methods only
- ✅ Specific headers only
- **Protects against:** Unauthorized cross-origin requests

### 8. **Security Logging**
- ✅ All auth attempts logged
- ✅ Failed requests logged
- ✅ Suspicious activity logged
- ✅ IP blocking events logged
- **Protects against:** Enables forensics and monitoring

---

## 🚨 Threat Detection & Response

### Automatic Responses

| Threat | Detection | Response | Time |
|--------|-----------|----------|------|
| **Brute Force** | 5 failed logins | IP blocked | Instant |
| **DDoS** | >100 req/min | Rate limited | Instant |
| **SQL Injection** | Attack pattern | IP blocked | Instant |
| **XSS Attack** | Script tags | IP blocked | Instant |
| **Path Traversal** | ../  patterns | IP blocked | Instant |

---

## 🔑 Authentication Flow

### Login
```
POST /token
→ Returns: access_token + refresh_token
→ Access token expires: 30 minutes
→ Refresh token expires: 7 days
```

### API Requests
```
Authorization: Bearer <access_token>
→ Validated on every request
→ User status checked
→ Token type verified
```

### Token Refresh
```
POST /token/refresh
Body: { "refresh_token": "<token>" }
→ Returns: new access_token
→ Old access token invalidated
```

---

## 📊 Security Monitoring

### Check Security Logs (Railway)
```bash
railway logs | grep "WARNING\|ERROR\|Blocked\|Failed"
```

### What to Look For
- ⚠️ Multiple failed logins from same IP
- ⚠️ Rate limit violations
- ⚠️ IP blocking events
- ⚠️ Slow requests (>5 seconds)
- ⚠️ SQL injection attempts

---

## 🛠️ Configuration

### Rate Limits
Location: `backend/main.py:1914`
```python
RateLimitMiddleware(
    requests_per_minute=100,
    requests_per_hour=2000
)
```

### Token Expiration
Location: `backend/main.py:68-69`
```python
ACCESS_TOKEN_EXPIRE_MINUTES = 30
REFRESH_TOKEN_EXPIRE_DAYS = 7
```

### Allowed Origins
Location: `backend/main.py:1917-1920`
```python
allowed_origins = [
    "http://localhost:3000",
    "http://localhost:3001",
    "https://mortgage-crm-nine.vercel.app"
]
```

---

## 🚀 Deployment Checklist

Before deploying to production:

- [ ] Set strong `SECRET_KEY` in Railway environment variables
- [ ] Verify `DATABASE_URL` is set correctly
- [ ] Add production domain to `allowed_origins`
- [ ] Test authentication flow
- [ ] Test rate limiting (send 101+ requests quickly)
- [ ] Verify HTTPS is working
- [ ] Check security headers in browser dev tools
- [ ] Review security logs

---

## 🔍 Testing Security

### Test Rate Limiting
```bash
# Send 101 requests quickly
for i in {1..101}; do curl https://your-api.railway.app/api/v1/leads; done
# Should see 429 error after 100 requests
```

### Test Security Headers
```bash
curl -I https://your-api.railway.app
# Look for: X-Frame-Options, Content-Security-Policy, etc.
```

### Test Failed Login Blocking
```bash
# Try 6 failed logins
for i in {1..6}; do
  curl -X POST https://your-api.railway.app/token \
    -d "username=test@test.com&password=wrong"
done
# 6th attempt should be blocked (403 or 429)
```

---

## ⚡ Emergency Actions

### If Under Attack

1. **Check logs immediately**
   ```bash
   railway logs --tail 100
   ```

2. **Identify pattern**
   - Same IP repeated?
   - SQL injection attempts?
   - DDoS pattern?

3. **System will auto-protect**
   - Rate limiting kicks in automatically
   - IPs get blocked automatically
   - No manual action needed for most attacks

4. **Manual actions (if needed)**
   - Temporarily lower rate limits in code
   - Deploy update to Railway
   - Contact Railway support if needed

---

## 📈 Security Levels

### Current Protection Level: **ENTERPRISE**

| Feature | Status | Protection Level |
|---------|--------|------------------|
| Rate Limiting | ✅ | High |
| IP Blocking | ✅ | High |
| Security Headers | ✅ | High |
| JWT Security | ✅ | High |
| Input Validation | ✅ | High |
| SQL Injection Prevention | ✅ | High |
| XSS Prevention | ✅ | High |
| CORS Protection | ✅ | Medium |
| Security Logging | ✅ | Medium |

---

## 📞 Support

**Security Questions?**
- Review full documentation: `SECURITY.md`
- Check FastAPI security docs
- Review OWASP guidelines

**Found a Vulnerability?**
1. Don't create public issue
2. Report privately
3. Include reproduction steps

---

## 🎯 Key Takeaways

✅ **Your CRM is protected** against common web attacks
✅ **Automatic blocking** handles threats without manual intervention
✅ **Rate limiting** prevents abuse and DDoS
✅ **Security logging** enables monitoring and forensics
✅ **Token security** prevents unauthorized access
✅ **Input validation** blocks injection attacks

**Your application is ready for production deployment!**

---

*Security Version: 1.0 | Last Updated: January 15, 2025*
