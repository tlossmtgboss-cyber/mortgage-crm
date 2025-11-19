# Guideline Updates Sidebar - Complete Setup Guide

## 🎉 Feature Overview

The Guideline Updates Sidebar has been successfully integrated into your AI Underwriter page! This feature automatically tracks and displays the latest guideline updates from all 5 major mortgage lending sources:

1. **Fannie Mae** - Selling Guide Bulletins
2. **Freddie Mac** - Guide Bulletins
3. **FHA** - Mortgagee Letters
4. **VA** - Circulars
5. **USDA** - Rural Development Notices

## ✅ What's Been Implemented

### Backend Components

1. **Database Models** (`backend/guideline_updates_models.py`)
   - `GuidelineUpdate` - Stores guideline updates from all sources
   - `UserUpdateView` - Tracks which users have viewed which updates

2. **API Routes** (`backend/guideline_updates_routes.py`)
   - `GET /api/v1/guideline-updates/sidebar` - Get updates for sidebar display
   - `GET /api/v1/guideline-updates/check-new` - Check for unread updates
   - `POST /api/v1/guideline-updates/mark-viewed/{update_id}` - Mark update as viewed
   - `POST /api/v1/guideline-updates/mark-all-viewed` - Mark all as viewed

3. **Web Scraper** (`backend/guideline_updates_scraper.py`)
   - Automated scraper for all 5 sources
   - Deduplication using content hashes
   - Ready to run as a scheduled task

4. **Database Tables**
   - ✅ Tables created successfully
   - ✅ Sample data added (10 guideline updates)

### Frontend Components

1. **GuidelineUpdatesSidebar** (`frontend/src/components/GuidelineUpdatesSidebar.js`)
   - Displays recent updates grouped by source
   - Shows "NEW" badges for unread updates
   - Expandable/collapsible source sections
   - Auto-refreshes every 5 minutes

2. **GuidelineNotificationBadge** (`frontend/src/components/GuidelineNotificationBadge.js`)
   - Glowing star icon in header when new updates exist
   - Shows count of unread updates
   - Auto-checks every 2 minutes

3. **Updated AI Underwriter Page** (`frontend/src/pages/AIUnderwriter.js`)
   - Integrated sidebar on the right
   - Notification badge in header
   - Responsive layout (sidebar moves below on mobile)

## 🚀 How to Use

### For Users

1. **Navigate to AI Underwriter page**
   - The sidebar appears on the right side
   - If there are new updates, you'll see a glowing star icon in the header

2. **View Updates**
   - Click on any source name (Fannie Mae, Freddie Mac, etc.) to expand it
   - Click on any update to open it in a new tab
   - Updates are automatically marked as "viewed" when clicked

3. **Stay Updated**
   - The sidebar automatically checks for new updates every 5 minutes
   - New updates are marked with a red "NEW" badge
   - The notification badge shows total unread count

### For Administrators

#### Running the Scraper

To fetch new guideline updates from all sources:

```bash
# Activate virtual environment
source .venv/bin/activate

# Run the scraper manually
python backend/guideline_updates_scraper.py
```

#### Setting Up Automated Scraping

Add to your cron jobs to run daily:

```bash
# Edit crontab
crontab -e

# Add this line to run daily at 6 AM
0 6 * * * cd /path/to/mortgage-crm && source .venv/bin/activate && python backend/guideline_updates_scraper.py
```

Or use a task scheduler like Railway's Cron Jobs or Heroku Scheduler.

#### Adding Sample Data for Testing

```bash
# Activate virtual environment
source .venv/bin/activate

# Run seed script
python backend/seed_sample_guidelines.py
```

## 📁 Files Created/Modified

### New Backend Files
- `backend/guideline_updates_models.py` - Database models
- `backend/guideline_updates_routes.py` - API endpoints
- `backend/guideline_updates_scraper.py` - Web scraper
- `backend/migrations/add_guideline_updates_tables.py` - Database migration
- `backend/run_guideline_updates_migration.py` - Migration runner
- `backend/seed_sample_guidelines.py` - Sample data seeder

### New Frontend Files
- `frontend/src/components/GuidelineUpdatesSidebar.js` - Sidebar component
- `frontend/src/components/GuidelineUpdatesSidebar.css` - Sidebar styles
- `frontend/src/components/GuidelineNotificationBadge.js` - Notification badge
- `frontend/src/components/GuidelineNotificationBadge.css` - Badge styles

### Modified Files
- `backend/main.py` - Added guideline updates router
- `backend/requirements.txt` - Added beautifulsoup4
- `frontend/src/pages/AIUnderwriter.js` - Integrated new components
- `frontend/src/pages/AIUnderwriter.css` - Updated layout for sidebar

## 🎨 UI Features

### Sidebar Features
- **Source Grouping** - Updates grouped by source with expand/collapse
- **Visual Indicators** - Red borders and badges for new updates
- **Smooth Animations** - Pulsing border animation for sources with new updates
- **Responsive Design** - Sidebar moves below content on mobile devices
- **Auto-refresh** - Checks for updates every 5 minutes

### Notification Badge
- **Glowing Effect** - Animated glow to draw attention
- **Count Display** - Shows exact number of unread updates
- **Tooltip** - Hover to see update count

## 🔧 Customization

### Adjust Refresh Intervals

In `GuidelineUpdatesSidebar.js` (line 11):
```javascript
const interval = setInterval(fetchSidebarData, 5 * 60 * 1000); // 5 minutes
```

In `GuidelineNotificationBadge.js` (line 11):
```javascript
const interval = setInterval(checkForNewUpdates, 2 * 60 * 1000); // 2 minutes
```

### Change Number of Updates Shown

In `GuidelineUpdatesSidebar.js` (line 24):
```javascript
const response = await fetch(`/api/v1/guideline-updates/sidebar?user_id=${userId}&limit_per_source=5`);
```

Change `&limit_per_source=5` to your desired number.

### Customize Colors

Edit the CSS files to match your brand:
- Red accent: `#ef4444` (new update indicators)
- Blue accent: `#0ea5e9` (section codes)
- Primary: `#218D8D` (existing theme color)

## 🧪 Testing

1. **Test with Sample Data**
   ```bash
   source .venv/bin/activate
   python backend/seed_sample_guidelines.py
   ```

2. **Start the Backend**
   ```bash
   cd backend
   uvicorn main:app --reload
   ```

3. **Start the Frontend**
   ```bash
   cd frontend
   npm start
   ```

4. **Navigate to AI Underwriter Page**
   - You should see the sidebar on the right
   - Click to expand different sources
   - Click on updates to mark them as viewed

## 🔒 Security Features

- ✅ **Authentication Required** - All endpoints require valid JWT token
- ✅ **User Tracking** - Updates are tracked per user
- ✅ **Content Deduplication** - SHA-256 hashes prevent duplicates
- ✅ **Input Validation** - All inputs validated via Pydantic models

## 📊 Database Schema

### guideline_updates
| Column | Type | Description |
|--------|------|-------------|
| id | Integer | Primary key |
| source | String(50) | Source identifier |
| title | String(500) | Update title |
| section_code | String(100) | Document number |
| description | Text | Brief description |
| url | String(1000) | Link to update |
| published_date | DateTime | When published |
| scraped_date | DateTime | When scraped |
| is_new | Boolean | Is it a new update |
| content_hash | String(64) | SHA-256 for deduplication |

### user_update_views
| Column | Type | Description |
|--------|------|-------------|
| id | Integer | Primary key |
| user_id | Integer | User who viewed |
| update_id | Integer | Update that was viewed |
| viewed_at | DateTime | When viewed |

## 🛠️ Troubleshooting

### Sidebar Not Showing
1. Check browser console for errors
2. Verify backend is running
3. Check that user is logged in (JWT token exists)
4. Verify database tables exist

### No Updates Appearing
1. Run seed script to add sample data
2. Run scraper to fetch real updates
3. Check database: `SELECT * FROM guideline_updates;`

### Updates Not Marked as Viewed
1. Check browser console for API errors
2. Verify user_id is being passed correctly
3. Check network tab for failed requests

## 📝 Next Steps

1. **Set Up Scheduled Scraping**
   - Configure cron job or task scheduler
   - Recommended: Run daily at 6 AM

2. **Monitor Performance**
   - Check scraper logs for errors
   - Monitor database size
   - Optimize queries if needed

3. **Customize for Your Needs**
   - Adjust refresh intervals
   - Modify UI colors
   - Add additional sources if needed

## 🎯 Future Enhancements (Optional)

- Email notifications for new updates
- Export updates to PDF/Excel
- Filter updates by date range
- Search within updates
- Admin panel to manually add updates
- RSS feed integration
- Update categorization (credit, income, property, etc.)

## ✅ Feature is Ready to Use!

The Guideline Updates Sidebar is now fully integrated and ready for production use. All backend and frontend components are in place, sample data has been added, and the feature is live on your AI Underwriter page.

Enjoy staying up-to-date with the latest mortgage lending guidelines! 🎉
