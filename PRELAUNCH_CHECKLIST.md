# Pre-Launch Testing Checklist

## Overview
This document outlines all pre-launch tests required before deploying the Mortgage CRM application to production.

---

## 1. Borrower Flow (End-to-End)

### Social Login
- [ ] Google OAuth - redirect and callback working
- [ ] Facebook OAuth - redirect and callback working
- [ ] LinkedIn OAuth - redirect and callback working
- [ ] Apple Sign In - redirect and callback working
- [ ] Invalid token handling for all providers
- [ ] Account linking for existing users

### Magic Link
- [ ] Magic link request generates email
- [ ] Email arrives within 30 seconds
- [ ] Link is valid for 15 minutes
- [ ] Expired link shows proper error
- [ ] Invalid email format rejected

### Form Application
- [ ] Start new application
- [ ] Save personal info step
- [ ] Save property info step (with address autocomplete)
- [ ] Save income info step (with employer autocomplete)
- [ ] Save assets info step
- [ ] Progress tracking accurate
- [ ] Validation errors displayed properly
- [ ] Draft auto-save working

### AI Concierge Mode
- [ ] Start concierge session
- [ ] Message exchange working
- [ ] Data extraction accurate
- [ ] Name parsing correct
- [ ] Address parsing correct
- [ ] Income parsing handles various formats
- [ ] Context maintained across turns
- [ ] Voice input functional (where supported)
- [ ] Switch to form mode preserves data

### Document Upload
- [ ] PDF upload successful
- [ ] Image upload successful (JPG, PNG)
- [ ] AI verification runs on upload
- [ ] Document type detection accurate
- [ ] Incorrect file type rejected
- [ ] File size limits enforced (10MB max)
- [ ] Document list displays correctly

### Co-Borrower Flow
- [ ] Send invitation via email
- [ ] Invitation email received
- [ ] Accept invitation creates account
- [ ] Co-borrower can complete their section
- [ ] Primary borrower sees co-borrower status

### Review Call Scheduling
- [ ] Available slots API returns data
- [ ] Time slots respect timezone
- [ ] Schedule call successfully
- [ ] Reschedule functionality works
- [ ] Cancel functionality works
- [ ] Calendar confirmation email sent

### Final Submission
- [ ] Pre-submission validation runs
- [ ] Incomplete applications blocked
- [ ] Applications without review call blocked
- [ ] Submit with all data complete
- [ ] Status changes to "submitted"

### Confirmation Notifications
- [ ] Borrower receives confirmation email
- [ ] Borrower receives confirmation SMS
- [ ] Email contains application reference
- [ ] SMS is properly formatted (<160 chars)
- [ ] LO receives new application alert

---

## 2. LO Dashboard

### Application Management
- [ ] View all applications
- [ ] Filter by status works
- [ ] Filter by date range works
- [ ] Search by borrower name works
- [ ] Pagination works correctly
- [ ] Sort by date works

### MISMO XML Export
- [ ] Export single application
- [ ] XML contains required sections (DEAL, PARTY, LOAN)
- [ ] Borrower info correct in XML
- [ ] Property info correct in XML
- [ ] File downloads properly
- [ ] Non-existent app returns 404

### Social Content Generation
- [ ] Generate market update
- [ ] Generate homebuyer tip
- [ ] Generate rate alert
- [ ] Generate success story
- [ ] Generate for all platforms
- [ ] Content respects character limits
- [ ] Hashtags appropriate
- [ ] Copy to clipboard works

### Analytics Dashboard
- [ ] Pipeline count accurate
- [ ] Pipeline volume accurate
- [ ] Recent activity displays
- [ ] Activity in correct order

### Application Detail
- [ ] Full application loads
- [ ] Borrower info visible
- [ ] Property info visible
- [ ] Documents listed
- [ ] Timeline/history visible
- [ ] Update status works
- [ ] Add notes works

---

## 3. Mobile Testing

### iOS Safari
- [ ] iPhone SE - content fits without scroll
- [ ] iPhone 12 - navigation works
- [ ] iPhone 14 Pro Max - forms usable
- [ ] No zoom on input focus (16px+ fonts)
- [ ] Safe area insets respected

### Android Chrome
- [ ] Pixel 6 - content fits viewport
- [ ] Samsung S21 - buttons touch-friendly
- [ ] Samsung Galaxy A52 - forms visible
- [ ] Text readable without zoom

### Tablet
- [ ] iPad Mini portrait - two column layout
- [ ] iPad Mini landscape - content adapts
- [ ] iPad Pro 12.9 - desktop-like experience
- [ ] Samsung Tab S7 - responsive grid
- [ ] Orientation change - layout reflows

### Touch & Voice
- [ ] Swipe navigation (if applicable)
- [ ] Tap targets properly spaced
- [ ] Smooth scroll behavior
- [ ] Pinch-to-zoom enabled
- [ ] Speech recognition (where supported)
- [ ] Microphone button accessible

---

## 4. Notifications

### Email (SendGrid)
- [ ] Welcome email on app start
- [ ] Document upload confirmation
- [ ] 24h reminder for incomplete apps
- [ ] Submission confirmation
- [ ] LO new app alert
- [ ] All emails have unsubscribe link
- [ ] HTML formatting correct
- [ ] Bounce handling works

### SMS (Twilio)
- [ ] Submission confirmation SMS
- [ ] SMS under 160 characters (or segmented)
- [ ] Phone number formatting correct
- [ ] Opt-out respected
- [ ] Error handling graceful
- [ ] Sender ID correct

---

## 5. AI Features

### Document Analysis (Claude Vision)
- [ ] Paystub recognition accurate
- [ ] W-2 recognition accurate
- [ ] Bank statement recognition accurate
- [ ] Driver's license recognition accurate
- [ ] Document mismatch detection works
- [ ] Poor quality handling (low confidence)
- [ ] Extracted data accurate

### Conversational Mode
- [ ] Name extraction accurate
- [ ] Address extraction accurate
- [ ] Income extraction accurate
- [ ] Currency parsing handles variations
- [ ] Ambiguous input gets clarification
- [ ] Context maintained across turns

### Summary Review
- [ ] All sections included
- [ ] Missing data highlighted
- [ ] Completion percentage accurate
- [ ] Validation errors shown

### Social Content
- [ ] Content relevant to mortgage industry
- [ ] Platform-appropriate tone
- [ ] Hashtags appropriate count
- [ ] No specific rate mentions
- [ ] Character limits respected
- [ ] Fallback content works

---

## 6. Performance

### Page Load (<3s)
- [ ] Home page
- [ ] Login page
- [ ] Application page
- [ ] LO Dashboard
- [ ] Concurrent loads handled

### API Response (<500ms)
- [ ] GET applications
- [ ] GET single application
- [ ] POST application
- [ ] PUT application
- [ ] Search/filter
- [ ] Under load (20 concurrent)

### External Services
- [ ] Google Places autocomplete (<300ms)
- [ ] S3 file upload (<5s for 5MB)
- [ ] Claude API (<10s)
- [ ] SendGrid email delivery
- [ ] Twilio SMS delivery

### Database
- [ ] Queries optimized (<100ms)
- [ ] Pagination used for lists
- [ ] N+1 queries avoided
- [ ] Proper indexing
- [ ] Connection pooling configured

### Caching
- [ ] Dashboard stats cached
- [ ] Cache invalidation on updates

---

## Running Tests

### Backend Tests (pytest)
```bash
cd backend
pip install pytest pytest-json-report
python -m pytest tests/ -v
```

### Frontend Tests (Jest)
```bash
cd frontend
npm test
```

### Full Pre-Launch Suite
```bash
cd backend/tests
python run_prelaunch_tests.py
```

---

## Sign-Off

| Area | Tester | Date | Status |
|------|--------|------|--------|
| Borrower Flow | | | |
| LO Dashboard | | | |
| Mobile Testing | | | |
| Notifications | | | |
| AI Features | | | |
| Performance | | | |

**Final Approval:** _________________ Date: _________

---

## Notes

- All tests should pass before production deployment
- Performance tests should be run against production-like environment
- Mobile tests require actual devices or reliable emulators
- AI tests may need real API keys for accuracy testing
- Notification tests should verify actual delivery, not just API calls
