# 🚀 Quick Start: Install Mortgage Guidelines Browser Extension

## ✅ What This Does

This browser extension lets you extract guideline updates from **my.mortgageguidelines.com** (your paid subscription) and automatically sync them to your CRM database.

**No coding needed** - just click and it works!

---

## 📦 Installation (5 minutes)

### Step 1: Open Chrome Extensions

1. Open **Google Chrome**
2. Go to: `chrome://extensions/`
3. Turn on **"Developer mode"** (toggle in top-right corner)

### Step 2: Load the Extension

1. Click **"Load unpacked"** button
2. Navigate to and select this folder:
   ```
   /Users/timothyloss/my-project/mortgage-crm/browser-extension/
   ```
3. The extension will appear with the title:
   **"Mortgage Guidelines Scraper for CRM"**

### Step 3: Pin to Toolbar (Optional but Recommended)

1. Click the **puzzle piece icon** (🧩) in Chrome toolbar
2. Find **"Mortgage Guidelines Scraper for CRM"**
3. Click the **pin icon** to keep it visible

---

## 🎯 How to Use

### Quick Method: Scrape Current Page

1. **Log into** https://my.mortgageguidelines.com
   - Username: `tloss@cmghomeloans.com`
   - Password: [SET VIA ENVIRONMENT VARIABLE]

2. **Navigate to any update page:**
   - Fannie Mae Updates
   - Freddie Mac Updates
   - FHA Updates
   - VA Updates
   - USDA Updates

3. **Click the extension icon** in your toolbar

4. **Click "🚀 Extract & Sync to CRM"**

5. ✅ **Done!** The updates from that page are now in your CRM

### Comprehensive Method: Scrape All Sources

1. **Log into** https://my.mortgageguidelines.com

2. **Click the extension icon**

3. **Click "📚 Scrape All Sources"**

4. **Wait** as the extension:
   - Opens each source page in background
   - Extracts top 5 updates from each
   - Sends all data to your CRM

5. ✅ **Done!** All 5 sources synced to CRM

---

## 🔍 Where to See the Results

After scraping, the updates will appear in your CRM:

1. Go to: https://mortgage-crm-nine.vercel.app
2. Navigate to: **AI Underwriter** page
3. Look at the **right sidebar** - "Guideline Updates"
4. You'll see the latest updates organized by source:
   - 🏦 Fannie Mae
   - 🏛️ Freddie Mac
   - 🏠 FHA
   - 🎖️ VA
   - 🌾 USDA

---

## 📊 What Gets Extracted

From each page, the extension captures:
- ✅ **Title** - Full title of the guideline update
- ✅ **Section Code** - e.g., "SEL-2024-08", "ML 2024-11"
- ✅ **Description** - Summary or excerpt
- ✅ **URL** - Direct link to full guideline
- ✅ **Published Date** - When it was released
- ✅ **Source** - Which agency (Fannie Mae, FHA, etc.)

---

## ⚡ Best Practices

### When to Run

- **Weekly**: Set a reminder to scrape all sources once per week
- **After Announcements**: When you hear about a new guideline, run the scraper
- **Before Important Loans**: Get the latest info before underwriting

### Tips

- ✅ **Run "Scrape All"** on Mondays to start the week with fresh data
- ✅ **Safe to run multiple times** - duplicates are automatically skipped
- ✅ **Stays logged in** - Your browser session is used, no password needed
- ✅ **Works in background** - You can keep browsing while it scrapes

---

## 🔧 Troubleshooting

### Extension doesn't show up
- Make sure **Developer mode** is enabled
- Click **"Reload"** button on the extension card
- Close and reopen Chrome

### "Not on mortgageguidelines.com" message
- Navigate to https://my.mortgageguidelines.com first
- Make sure you're logged in
- Refresh the page

### No updates extracted
- Ensure you're on an updates page (not homepage)
- Wait for page to fully load
- Try refreshing and extracting again

### API Error
- Check that CRM backend is running
- Verify internet connection
- Press F12 → Console tab to see detailed error

---

## 📝 Quick Reference

### Extension Files Location
```
/Users/timothyloss/my-project/mortgage-crm/browser-extension/
```

### API Endpoint (Auto-configured)
```
https://app.perenniaai.com/api/v1/migrations/import-browser-guidelines
```

### Login Credentials
```
Site: https://my.mortgageguidelines.com/account-login/
Username: tloss@cmghomeloans.com
Password: [SET VIA ENVIRONMENT VARIABLE]
```

---

## 🎉 You're All Set!

The extension is now ready to use. Here's your workflow:

1. **Monday morning**: Log into mortgageguidelines.com
2. **Click extension** → **"Scrape All Sources"**
3. **Wait 1-2 minutes** for all sources to be scraped
4. **Check CRM** to see new updates in the sidebar

That's it! Your CRM will always have the latest guideline updates.

---

## 📞 Need Help?

- Check the detailed README: `browser-extension/README.md`
- View browser console: Press **F12** → **Console** tab
- Check Railway logs for backend errors

**Happy Scraping!** 🚀
