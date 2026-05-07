# Multi-Tenant Database System - Deployment Checklist

**Date:** January 30, 2026  
**System:** Database-per-Tenant Architecture  
**Status:** Ready for Deployment

---

## 📋 PRE-DEPLOYMENT CHECKLIST

### Phase 1: Environment Setup
- [ ] **Database Backup** - Backup your current master database
  ```bash
  pg_dump -U postgres -d your_master_db > backup_$(date +%Y%m%d).sql
  ```

- [ ] **Review Environment Variables**
  - [ ] Copy `.env.multi-tenant.example` to `.env` and fill in your values
  - [ ] Update `MASTER_DATABASE_URL` with your production database URL
  - [ ] Configure `TENANT_DB_PREFIX` (default: `tenant_`)
  - [ ] Set `MAX_TENANT_CONNECTIONS`, `TENANT_POOL_SIZE`, `TENANT_MAX_OVERFLOW`
  - [ ] Set `AUTO_CREATE_TENANT_ON_SIGNUP=true` if desired

- [ ] **Verify PostgreSQL Permissions**
  ```sql
  -- Your database user needs CREATE DATABASE permission
  ALTER USER your_db_user CREATEDB;
  ```

### Phase 2: Code Integration
- [ ] **Install Dependencies** (if any new ones)
  ```bash
  pip install -r requirements.txt
  ```

- [ ] **Review main.py Integration**
  - [ ] Open `backend/main_integration_example.py`
  - [ ] Copy relevant sections to your actual `main.py`:
    - [ ] Import statements (lines 12-18)
    - [ ] Lifespan function (lines 28-60)
    - [ ] Middleware setup (lines 71-76)
    - [ ] Route inclusion (lines 86-91)
  
- [ ] **Verify Model Imports**
  - [ ] Ensure `from models.tenant import Tenant` works in your codebase
  - [ ] Check that `User` model is imported correctly

### Phase 3: Database Migration
- [ ] **Run tenant_id Migration**
  ```bash
  cd backend
  python -m migrations.add_tenant_id_to_user_profile
  ```

- [ ] **Verify Migration Success**
  ```sql
  -- Check that tenant_id column exists
  SELECT column_name, data_type 
  FROM information_schema.columns 
  WHERE table_name = 'users' AND column_name = 'tenant_id';
  
  SELECT column_name, data_type 
  FROM information_schema.columns 
  WHERE table_name = 'onboarding_user_profiles' AND column_name = 'tenant_id';
  ```

- [ ] **Create tenants Table** (if not exists)
  ```bash
  # This should be created automatically by the Tenant model
  python -c "from database import Base, engine; from models.tenant import Tenant; Base.metadata.create_all(engine)"
  ```

---

## 🚀 DEPLOYMENT STEPS

### Step 1: Deploy Code Changes
- [ ] **Commit All Changes to Git**
  ```bash
  git add .
  git commit -m "Add multi-tenant database system"
  git push origin main
  ```

- [ ] **Deploy to Production**
  - [ ] Railway: Push to main branch (auto-deploys)
  - [ ] Vercel: Deploy via dashboard or CLI
  - [ ] Manual: Pull latest code on server and restart services

### Step 2: Create Tenant for Tim Loss
- [ ] **Run Tim Loss Setup Script**
  ```bash
  cd backend
  python setup_tim_loss_tenant.py
  ```

- [ ] **Verify Tim Loss Tenant Created**
  ```sql
  -- Check tenant record
  SELECT * FROM tenants WHERE subdomain = 'timloss_cmg';
  
  -- List all databases
  \l  -- or SELECT datname FROM pg_database;
  
  -- Should see: tenant_timloss_cmg
  ```

- [ ] **Test Tim Loss Database Connection**
  ```bash
  psql -d tenant_timloss_cmg -c "SELECT NOW();"
  ```

### Step 3: Update Existing Users (Optional)
- [ ] **Decide Migration Strategy**
  - Option A: Keep existing users in shared database
  - Option B: Migrate existing users to their own tenants
  
- [ ] **If Migrating Existing Users:**
  ```python
  # Create a migration script to provision tenants for existing users
  # See setup_tim_loss_tenant.py as template
  ```

### Step 4: Test Multi-Tenant System
- [ ] **Test Tenant API Endpoints**
  ```bash
  # List all tenants
  curl http://localhost:8000/api/v1/tenants
  
  # Get specific tenant
  curl http://localhost:8000/api/v1/tenants/timloss_cmg
  ```

- [ ] **Test User Creation with Tenant**
  ```bash
  # Create a new test user - should auto-create tenant
  curl -X POST http://localhost:8000/api/v1/admin/users/create \
    -H "Content-Type: application/json" \
    -d '{"first_name":"Test","last_name":"User","email":"test@example.com","role_id":1}'
  ```

- [ ] **Verify Subdomain Routing** (if using subdomains)
  ```bash
  # Access via subdomain
  curl -H "Host: timloss.yourdomain.com" http://localhost:8000/health
  ```

### Step 5: Monitor and Validate
- [ ] **Check Application Logs**
  ```bash
  # Look for:
  # ✅ Multi-tenant system initialized successfully
  # ✅ Created tenant database for user X
  # ✅ Tenant detected: timloss_cmg
  ```

- [ ] **Verify Health Endpoint**
  ```bash
  curl http://localhost:8000/health
  # Should show: "multi_tenant_system": "initialized"
  ```

- [ ] **Test Database Connections**
  ```sql
  -- Check active connections to tenant databases
  SELECT datname, count(*) 
  FROM pg_stat_activity 
  WHERE datname LIKE 'tenant_%' 
  GROUP BY datname;
  ```

---

## 🔍 POST-DEPLOYMENT VALIDATION

### Functional Tests
- [ ] **Tim Loss Login Test**
  - [ ] Log in as Tim Loss (tloss@cmgfi.com)
  - [ ] Create a test lead/loan
  - [ ] Verify data is in `tenant_timloss_cmg` database
  - [ ] Verify data is NOT visible to other users

- [ ] **New User Signup Test**
  - [ ] Create a new user via onboarding
  - [ ] Verify new tenant database created
  - [ ] Verify `tenant_id` set in user profile
  - [ ] Test login and basic operations

- [ ] **Cross-Tenant Isolation Test**
  - [ ] Login as User A, create data
  - [ ] Login as User B, verify cannot see User A's data
  - [ ] Check database directly to confirm isolation

### Performance Tests
- [ ] **Connection Pool Test**
  ```bash
  # Monitor connection count under load
  watch -n 1 "psql -c 'SELECT count(*) FROM pg_stat_activity;'"
  ```

- [ ] **Response Time Test**
  - [ ] Measure API response times with multiple tenants
  - [ ] Verify no significant degradation

---

## ⚠️ ROLLBACK PLAN

If issues arise, follow these steps:

### Rollback Step 1: Disable Multi-Tenant Features
```python
# In main.py, comment out:
# - Tenant middleware
# - Tenant routes
# - Tenant initialization in lifespan
```

### Rollback Step 2: Restore Database
```bash
# If migration caused issues:
psql -U postgres -d your_master_db < backup_YYYYMMDD.sql
```

### Rollback Step 3: Revert Code
```bash
git revert HEAD
git push origin main
```

---

## 📊 MONITORING

### Key Metrics to Track
- **Tenant Count**: Number of active tenants
- **Database Connections**: Per-tenant connection usage
- **Tenant Creation Time**: How long to provision new tenant
- **API Response Times**: By tenant (identify slow tenants)
- **Storage Growth**: Monitor tenant database sizes

### Monitoring Queries
```sql
-- Tenant count
SELECT COUNT(*) as total_tenants FROM tenants WHERE status = 'active';

-- Database sizes
SELECT 
  pg_database.datname,
  pg_size_pretty(pg_database_size(pg_database.datname)) AS size
FROM pg_database
WHERE datname LIKE 'tenant_%'
ORDER BY pg_database_size(pg_database.datname) DESC;

-- Connection usage by tenant
SELECT 
  datname,
  count(*) as connections,
  max(state) as max_state
FROM pg_stat_activity
WHERE datname LIKE 'tenant_%'
GROUP BY datname
ORDER BY connections DESC;
```

---

## 🎯 SUCCESS CRITERIA

✅ **Deployment is successful when:**
1. All existing users can log in and access their data
2. Tim Loss has his own database (`tenant_timloss_cmg`) with complete data isolation
3. New user signups automatically create tenant databases
4. Health endpoint shows multi-tenant system initialized
5. No database connection errors in logs
6. API response times remain within acceptable limits
7. Zero cross-tenant data leaks (verified by tests)

---

## 📞 SUPPORT

**Issues or Questions?**
- Check `MULTI_TENANT_DATABASE_IMPLEMENTATION_GUIDE.md` for detailed documentation
- Review logs in `/var/log/` or Railway/Vercel dashboard
- Check `main_integration_example.py` for integration examples

**Common Issues:**
- **"CREATE DATABASE" permission denied**: Grant CREATEDB to database user
- **Tenant middleware not working**: Ensure middleware added before CORS
- **No tenant detected**: Check subdomain configuration or tenant_id in session

---

## ✅ DEPLOYMENT COMPLETE!

**Final Steps:**
- [ ] Mark this checklist as complete
- [ ] Document any custom changes made during deployment
- [ ] Update team on new multi-tenant architecture
- [ ] Schedule follow-up review in 1 week

**Deployment Date:** _____________  
**Deployed By:** _____________  
**Notes:** 

_____________________________________________
_____________________________________________
_____________________________________________
