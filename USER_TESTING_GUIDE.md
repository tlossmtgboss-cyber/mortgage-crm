# 🧪 Guideline Updates Sidebar - User Testing Guide

## ✅ DEPLOYMENT COMPLETE - Ready for Testing!

**Deployed**: November 18, 2025 at 8:14 PM EST
**Production URL**: https://mortgage-crm-nine.vercel.app

---

## 🎯 Quick Testing Steps

### Step 1: Clear Your Browser Cache
**This is CRITICAL - the new components won't load without clearing cache!**

- **Windows/Linux**: Press `Ctrl + Shift + R`
- **Mac**: Press `Cmd + Shift + R`
- **Or**: Clear cache manually in browser settings

### Step 2: Log In and Navigate
1. Go to: https://mortgage-crm-nine.vercel.app
2. Log in with your credentials
3. Click on **"AI Underwriter"** in the navigation menu

### Step 3: Look for the Sidebar
You should see a **sidebar on the right side** of the AI Underwriter page:

```
┌─────────────────────────────┬──────────────────────┐
│                             │ 📋 Guideline Updates │
│                             │                      │
│  AI Underwriter Chat        │ 🏦 Fannie Mae (2)   │
│                             │ 🏛️ Freddie Mac (2)   │
│                             │ 🏠 FHA (2)           │
│                             │ 🎖️ VA (2)            │
│                             │ 🌾 USDA (2)          │
│                             │                      │
└─────────────────────────────┴──────────────────────┘
```

### Step 4: Look for the Notification Badge
In the header next to "Smart AI Underwriter" title, you should see:
- ⭐ **Glowing red star icon**
- **Small badge** showing "10" (number of unread updates)

---

## ✅ What to Test

### Test 1: Sidebar Visibility
- [ ] Sidebar appears on the right side (320px wide)
- [ ] Sidebar has title "📋 Guideline Updates"
- [ ] All 5 source sections are visible:
  - [ ] 🏦 Fannie Mae
  - [ ] 🏛️ Freddie Mac
  - [ ] 🏠 FHA
  - [ ] 🎖️ VA
  - [ ] 🌾 USDA
- [ ] Each source shows number of updates in parentheses

### Test 2: Notification Badge
- [ ] Glowing star icon appears next to "Smart AI Underwriter" title
- [ ] Badge shows "10" unread updates
- [ ] Tooltip appears when hovering over the star

### Test 3: Expand/Collapse Sources
- [ ] Click on "Fannie Mae" - section expands to show 2 updates
- [ ] Click again - section collapses
- [ ] Try expanding multiple sources at once - all work independently

### Test 4: View Updates
- [ ] Expand a source (e.g., "FHA")
- [ ] See update titles displayed (e.g., "Mortgagee Letter 2024-11")
- [ ] See section codes displayed (e.g., "ML 2024-11")
- [ ] See published dates
- [ ] Click on an update title
- [ ] New tab opens with official guideline URL (e.g., www.hud.gov)
- [ ] Badge count decreases by 1 after viewing

### Test 5: Official Sources Only
- [ ] Ask AI Underwriter a question like: "What are FHA credit requirements?"
- [ ] Check the sources returned in the response
- [ ] Should see links to official sites:
  - ✅ www.hud.gov
  - ✅ selling-guide.fanniemae.com
  - ✅ guide.freddiemac.com
  - ✅ www.benefits.va.gov
  - ✅ www.rd.usda.gov
- [ ] Should NOT see:
  - ❌ my.mortgageguidelines.com
  - ❌ Mortgage Currency
  - ❌ Any third-party aggregator sites

---

## 🚨 Troubleshooting

### Problem: Sidebar Not Showing

**Solution 1: Hard Refresh**
1. Press `Ctrl + Shift + R` (Windows) or `Cmd + Shift + R` (Mac)
2. This forces browser to download new code

**Solution 2: Clear All Cache**
1. Chrome: Settings → Privacy and security → Clear browsing data
2. Safari: Develop menu → Empty Caches
3. Firefox: Settings → Privacy & Security → Clear Data

**Solution 3: Check You're on AI Underwriter Page**
1. Sidebar ONLY appears on AI Underwriter page
2. Navigate to: https://mortgage-crm-nine.vercel.app/ai-underwriter

**Solution 4: Check Browser Console**
1. Press F12 to open Developer Tools
2. Go to Console tab
3. Look for any errors related to "GuidelineUpdatesSidebar"
4. Share screenshot if you see errors

### Problem: Notification Badge Not Showing

**Solution**: Same as above - hard refresh and clear cache

### Problem: Updates Don't Open When Clicked

**Possible Causes**:
1. Pop-up blocker is enabled - allow pop-ups for this site
2. Browser security settings - try different browser
3. API authentication issue - try logging out and back in

### Problem: Still Seeing Mortgage Currency Sources

**Solution**:
1. Hard refresh (Ctrl+Shift+R or Cmd+Shift+R)
2. Clear browser cache completely
3. Close all browser tabs and reopen
4. If still seeing Mortgage Currency, take screenshot and report issue

---

## 📸 What Success Looks Like

### Expected Sidebar View
```
┌──────────────────────────┐
│ 📋 Guideline Updates     │
│ ─────────────────────── │
│                          │
│ 🏦 Fannie Mae (2) ▼     │
│   ├─ SEL-2024-08:       │
│   │  Selling Guide      │
│   │  Announcement       │
│   │  Nov 15, 2024       │
│   │                      │
│   └─ SEL-2024-09:       │
│      Updated DU         │
│      Validation         │
│      Nov 10, 2024       │
│                          │
│ 🏛️ Freddie Mac (2) ▶    │
│ 🏠 FHA (2) ▶             │
│ 🎖️ VA (2) ▶              │
│ 🌾 USDA (2) ▶            │
│                          │
└──────────────────────────┘
```

### Expected Header View
```
┌─────────────────────────────────────┐
│ 🧠 Smart AI Underwriter ⭐ 10       │
│        (glowing star with badge)    │
└─────────────────────────────────────┘
```

---

## ✅ Success Criteria

The deployment is successful if you can check ALL of these boxes:

- [ ] Sidebar appears on AI Underwriter page (after hard refresh)
- [ ] Notification badge appears in header
- [ ] All 5 source sections are visible
- [ ] Can expand and collapse source sections
- [ ] Can click on update titles to open official URLs
- [ ] Badge count decreases after viewing updates
- [ ] AI responses show official sources only (no Mortgage Currency)
- [ ] All source links go to government/GSE websites

---

## 📋 Testing Checklist

Print this checklist and mark each item as you test:

### Visual Elements
- [ ] Sidebar visible on right side
- [ ] Sidebar width approximately 320px
- [ ] Title "📋 Guideline Updates" displayed
- [ ] Glowing star badge in header
- [ ] Badge count shows "10"

### Functionality
- [ ] Can expand Fannie Mae section
- [ ] Can expand Freddie Mac section
- [ ] Can expand FHA section
- [ ] Can expand VA section
- [ ] Can expand USDA section
- [ ] Can collapse any expanded section
- [ ] Can click on update titles
- [ ] Updates open in new tab
- [ ] URLs go to official websites only

### Data Verification
- [ ] Fannie Mae shows 2 updates
- [ ] Freddie Mac shows 2 updates
- [ ] FHA shows 2 updates
- [ ] VA shows 2 updates
- [ ] USDA shows 2 updates
- [ ] Total unread count = 10

### Official Sources Verification
- [ ] AI responses link to fanniemae.com
- [ ] AI responses link to freddiemac.com
- [ ] AI responses link to hud.gov
- [ ] AI responses link to va.gov
- [ ] AI responses link to usda.gov
- [ ] NO links to mortgageguidelines.com

---

## 🎉 If Everything Works

**Congratulations!** The guideline updates feature is working correctly.

You now have:
- ✅ Real-time guideline updates from 5 official sources
- ✅ Notification system for new updates
- ✅ Direct links to authoritative government/GSE websites
- ✅ Automatic tracking of viewed updates
- ✅ No more third-party aggregator sources

---

## 🐛 If Something Doesn't Work

### Report the Issue
Please provide:
1. **Screenshot** of the AI Underwriter page
2. **Browser** (Chrome, Safari, Firefox, etc.) and version
3. **Operating System** (Windows, Mac, Linux)
4. **Steps you took** before the issue occurred
5. **What you expected** to happen
6. **What actually happened**
7. **Browser console errors** (F12 → Console tab)

### Quick Diagnostics
Check these technical details:

**Frontend Bundle:**
- Open browser console (F12)
- Run: `console.log('Bundle loaded:', !!window.React)`
- Should show: `Bundle loaded: true`

**Component Loaded:**
- In console, run: `console.log('Components:', Object.keys(window))`
- Look for React-related entries

**API Connectivity:**
- Open Network tab in DevTools (F12 → Network)
- Refresh page
- Look for calls to `/api/v1/guideline-updates/sidebar`
- Should show status 200 (success)

---

## 📞 Support

If you need help:
1. Try all troubleshooting steps above
2. Take screenshots of any errors
3. Report issue with detailed information

---

**Production URL**: https://mortgage-crm-nine.vercel.app
**Deployment Date**: November 18, 2025 - 8:14 PM EST
**Status**: ✅ LIVE AND READY FOR TESTING

---

*Happy testing! The guideline updates feature is now live.*
