# 📋 Mortgage Guidelines Scraper - Browser Extension

A Chrome/Firefox extension that extracts guideline updates from my.mortgageguidelines.com and automatically syncs them to your CRM.

## 🚀 Installation

### Chrome

1. **Download this folder** to your computer
2. Open Chrome and go to `chrome://extensions/`
3. Enable **Developer mode** (toggle in top-right corner)
4. Click **"Load unpacked"**
5. Select the `browser-extension` folder
6. The extension icon will appear in your toolbar

### Firefox

1. **Download this folder** to your computer
2. Open Firefox and go to `about:debugging`
3. Click **"This Firefox"**
4. Click **"Load Temporary Add-on"**
5. Select the `manifest.json` file from the `browser-extension` folder

## 📖 How to Use

### Method 1: Scrape Current Page (Quick)

1. **Log into** https://my.mortgageguidelines.com with your credentials
2. **Navigate** to any update page:
   - Fannie Mae Updates
   - Freddie Mac Updates
   - FHA Updates
   - VA Updates
   - USDA Updates
3. **Click the extension icon** in your browser toolbar
4. **Click "Extract & Sync to CRM"**
5. ✅ Done! The guideline updates on that page are now in your CRM

### Method 2: Scrape All Sources (Comprehensive)

1. **Log into** https://my.mortgageguidelines.com
2. **Click the extension icon**
3. **Click "Scrape All Sources"**
4. The extension will:
   - Automatically visit each source page
   - Extract the top 5 most recent updates
   - Send everything to your CRM database
5. ✅ All 5 sources scraped and synced!

## 🎯 What Gets Extracted

From each page, the extension extracts:
- **Title** - The full title of the guideline update
- **Section Code** - e.g., "SEL-2024-08", "ML 2024-11"
- **Description** - Brief summary or excerpt
- **URL** - Direct link to the full guideline
- **Published Date** - When the update was released
- **Source** - Fannie Mae, Freddie Mac, FHA, VA, or USDA

## 🔄 Data Flow

```
Your Browser (logged in)
    ↓
Extension extracts data from mortgageguidelines.com
    ↓
Sends to CRM API: https://mortgage-crm-production-7a9a.up.railway.app
    ↓
Saved to database
    ↓
Appears in CRM sidebar (AI Underwriter page)
```

## ⚙️ Configuration

The extension is pre-configured to work with your production CRM. No additional setup needed!

### API Endpoint
```
https://mortgage-crm-production-7a9a.up.railway.app/api/v1/migrations/import-browser-guidelines
```

### Source URLs
- Fannie Mae: `/fannie-mae-updates/`
- Freddie Mac: `/freddie-mac-updates/`
- FHA: `/fha-updates/`
- VA: `/va-updates/`
- USDA: `/usda-updates/`

## 🛠️ Troubleshooting

### Extension doesn't appear
- Make sure you're in Developer Mode
- Reload the extension from `chrome://extensions/`
- Check that all files are in the folder

### "Not on mortgageguidelines.com" warning
- Navigate to https://my.mortgageguidelines.com first
- Make sure you're logged in
- Refresh the page

### No updates extracted
- Check that you're on an updates page (not homepage)
- Make sure the page has loaded completely
- Try refreshing the page and extracting again

### "API Error" message
- Check your internet connection
- Make sure the CRM backend is running
- Check browser console for detailed errors (F12 → Console)

## 📊 Extension UI

The popup shows:
- **Current Page** - Which page you're on
- **Extract Button** - Scrape current page
- **Scrape All Button** - Visit and scrape all 5 sources
- **Progress Bar** - Shows progress when scraping all
- **Results** - Shows how many updates were found per source
- **Status Messages** - Success/error feedback

## 🔒 Security & Privacy

- Extension only runs on `my.mortgageguidelines.com`
- Only sends data to your CRM API
- No data is stored in the extension
- Uses secure HTTPS connections
- Your login credentials are never accessed or transmitted

## 🎨 Customization

### Change CRM API URL
Edit `popup.js` line 2:
```javascript
const CRM_API_URL = 'https://your-crm-url.com/api/v1/migrations';
```

### Adjust Number of Updates Per Page
Edit `popup.js` in the `extractGuidelinesFromPage` function, last line:
```javascript
return guidelines.slice(0, 5);  // Change 5 to any number
```

## 📝 File Structure

```
browser-extension/
├── manifest.json          # Extension configuration
├── popup.html            # Extension popup UI
├── popup.js              # Popup logic & scraping orchestration
├── content.js            # Content script (runs on pages)
├── background.js         # Background service worker
├── icon16.png            # 16x16 icon
├── icon48.png            # 48x48 icon
├── icon128.png           # 128x128 icon
└── README.md             # This file
```

## 🐛 Known Issues

- **Slow on "Scrape All"**: Opening 5 tabs takes time. Be patient!
- **Some updates missed**: If a page uses complex JavaScript, some updates might not be detected
- **Temporary tabs**: When using "Scrape All", you'll see tabs briefly open and close

## 💡 Tips

- **Run weekly**: Set a reminder to scrape all sources once per week
- **After major announcements**: When a new guideline is announced, run the scraper
- **Check duplicates**: The system automatically skips duplicates, so it's safe to run multiple times
- **Verify in CRM**: After scraping, check your CRM's AI Underwriter page to see the new updates

## 🆘 Support

If you encounter issues:
1. Check the browser console (F12 → Console)
2. Check the CRM API logs on Railway
3. Make sure you're logged into mortgageguidelines.com
4. Try refreshing the extension (chrome://extensions/ → Reload)

## 📄 License

Proprietary - for internal use only

---

**Version**: 1.0.0
**Last Updated**: November 19, 2025
**Author**: CRM Development Team
