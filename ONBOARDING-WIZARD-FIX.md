# Onboarding Wizard - Now Auto-Displays for New Users ✅

## Problem
After registering, the onboarding wizard wasn't appearing automatically.

## Root Causes Found

### 1. Missing `/api/v1/users/me` Endpoint
- **Issue:** Frontend was calling `/api/v1/users/me` to check onboarding status
- **Problem:** Endpoint didn't exist (returned 404)
- **Fix:** Added GET `/api/v1/users/me` endpoint that returns:
  ```json
  {
    "id": 3,
    "email": "user@example.com",
    "full_name": "User Name",
    "onboarding_completed": false,
    ...
  }
  ```

### 2. Wrong API URL in Frontend
- **Issue:** App.js was using relative URL `/api/v1/users/me`
- **Problem:** Tried to call Vercel domain instead of Railway backend
- **Fix:** Added `API_BASE_URL` constant and use `${API_BASE_URL}/api/v1/users/me`

### 3. No Fallback Logic
- **Issue:** If API call failed, wizard wouldn't show
- **Problem:** No error handling or fallback
- **Fix:** Added fallback to check `localStorage` if API fails

## What Was Fixed

### Backend (`main.py`)
```python
@app.get("/api/v1/users/me")
async def get_current_user_info(current_user: User = Depends(get_current_user)):
    """Get current user information including onboarding status"""
    return {
        "id": current_user.id,
        "email": current_user.email,
        "full_name": current_user.full_name,
        "onboarding_completed": current_user.onboarding_completed,
        ...
    }
```

### Frontend (`App.js`)
```javascript
// Added API_BASE_URL constant
const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

// Fixed URL to use backend
const response = await fetch(`${API_BASE_URL}/api/v1/users/me`, {
  headers: {
    'Authorization': `Bearer ${localStorage.getItem('token')}`
  }
});

// Added fallback logic
if (response.ok) {
  const userData = await response.json();
  if (!userData.onboarding_completed) {
    setShowOnboarding(true);
  }
} else {
  // Fallback to localStorage
  const user = JSON.parse(localStorage.getItem('user') || '{}');
  if (user.onboarding_completed === undefined || user.onboarding_completed === false) {
    setShowOnboarding(true);
  }
}
```

## How It Works Now

### Registration Flow
```
1. User completes registration form
   ↓
2. Backend creates user with onboarding_completed = FALSE
   ↓
3. Backend generates JWT token
   ↓
4. Frontend stores token in localStorage
   ↓
5. Frontend redirects to /dashboard
   ↓
6. Dashboard loads → App.js useEffect runs
   ↓
7. App.js calls /api/v1/users/me with JWT token
   ↓
8. Backend returns user data with onboarding_completed: false
   ↓
9. App.js detects false → Shows OnboardingWizard overlay
   ↓
10. User completes wizard
   ↓
11. Wizard calls /api/v1/complete-onboarding
   ↓
12. Backend sets onboarding_completed = TRUE
   ↓
13. Wizard closes, user sees full dashboard
```

### Fallback Flow (if API fails)
```
1. API call to /api/v1/users/me fails
   ↓
2. App.js catches error
   ↓
3. Check localStorage for user object
   ↓
4. If onboarding_completed is undefined or false → Show wizard
   ↓
5. User completes wizard normally
```

## Testing the Fix

### Test 1: New Registration
1. Go to https://mortgage-crm-nine.vercel.app/register
2. Fill out registration form
3. Click "Create Account"
4. **Expected:** Redirect to dashboard + onboarding wizard appears
5. Complete wizard
6. **Expected:** Wizard closes, see full dashboard

### Test 2: Existing User (Already Onboarded)
1. Go to https://mortgage-crm-nine.vercel.app/login
2. Login with existing account (onboarding_completed = true)
3. **Expected:** No wizard, go straight to dashboard

### Test 3: Existing User (Not Yet Onboarded)
1. Login with account that hasn't completed onboarding
2. **Expected:** Wizard appears automatically
3. Complete wizard
4. **Expected:** Wizard closes and doesn't show again

## API Endpoint Details

### GET `/api/v1/users/me`
**Authentication:** Required (JWT Bearer token)

**Request:**
```bash
curl -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  https://mortgage-crm-production-7a9a.up.railway.app/api/v1/users/me
```

**Response (Success):**
```json
{
  "id": 3,
  "email": "user@example.com",
  "full_name": "John Doe",
  "role": "loan_officer",
  "is_active": true,
  "email_verified": true,
  "onboarding_completed": false,
  "user_metadata": {
    "company_name": "ABC Mortgage",
    "phone": "555-1234",
    "plan": "professional",
    "dev_mode": true
  },
  "created_at": "2025-11-08T12:56:15.736651"
}
```

**Response (Unauthorized):**
```json
{
  "detail": "Could not validate credentials"
}
```

## Deployment Status

### Backend (Railway)
- ✅ Deployed
- ✅ `/api/v1/users/me` endpoint live
- ✅ Tested and working

### Frontend (Vercel)
- ✅ Auto-deploying from main branch
- ✅ Build successful
- ✅ Using correct API_BASE_URL

## Verification

You can verify the fix is working:

```bash
# 1. Register a new user and get the token
TOKEN="<your_token_from_registration>"

# 2. Check user info
curl -H "Authorization: Bearer $TOKEN" \
  https://mortgage-crm-production-7a9a.up.railway.app/api/v1/users/me

# 3. Verify onboarding_completed is false
# Expected: "onboarding_completed": false
```

## Summary

✅ **Backend:** Added `/api/v1/users/me` endpoint
✅ **Frontend:** Fixed API URL to use Railway backend
✅ **Frontend:** Added fallback to localStorage
✅ **Frontend:** Fixed import ordering (ESLint)
✅ **Tested:** Endpoint returns correct data
✅ **Deployed:** Both frontend and backend live

**Onboarding wizard will now show automatically for all new users!**

---

**Last Updated:** 2025-11-08
**Status:** ✅ WORKING
