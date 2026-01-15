# E2E Testing Plan - CRM Save/Delete Buttons & Salesforce Integration

## Overview
Comprehensive end-to-end testing plan to verify all save and delete buttons work correctly across the CRM, and confirm Salesforce integrations are functional.

## Setup

### Install Playwright
```bash
npm install -D @playwright/test
npx playwright install
```

### Configuration
Create `playwright.config.js` in the project root:
```javascript
module.exports = {
  testDir: './tests',
  timeout: 30000,
  use: {
    baseURL: process.env.BASE_URL || 'http://localhost:3000',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure'
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } }
  ]
};
```

## Test Categories

### 1. Save Button Tests

#### Pages to Test:
- **Leads Page** - Test lead creation and update
- **Contacts Page** - Test contact save functionality  
- **Account Management** - Test account settings save
- **User Profile** - Test profile updates
- **Tasks/Todos** - Test task creation and updates
- **Notes** - Test note saving
- **Documents** - Test document metadata save
- **Settings Pages** - Test all settings forms
- **Pipeline Management** - Test pipeline stage updates
- **Email Templates** - Test template save
- **Calendar Events** - Test event creation
- **Properties** - Test property information save

#### Test Checklist for Each Save Button:
- [ ] Button is visible and enabled
- [ ] Form validation works (required fields)
- [ ] Data saves to database successfully
- [ ] Success message displays
- [ ] Saved data persists after page reload
- [ ] No console errors during save

### 2. Delete Button Tests

#### Pages to Test:
- **Leads** - Delete lead records
- **Contacts** - Delete contact records
- **Tasks** - Delete tasks
- **Notes** - Delete notes  
- **Documents** - Delete uploaded files
- **Calendar Events** - Delete events
- **Email Templates** - Delete templates
- **Pipeline Stages** - Delete custom stages
- **Team Members** - Remove team members

#### Test Checklist for Each Delete Button:
- [ ] Button is visible
- [ ] Confirmation modal appears
- [ ] Deletion executes after confirmation
- [ ] Item removed from list
- [ ] Database record deleted
- [ ] No orphaned data remains
- [ ] Success/confirmation message shown

### 3. Salesforce Integration Tests

#### Integration Points to Verify:

**A. Salesforce Core Integration**
- [ ] Salesforce section exists in Settings > Integrations
- [ ] OAuth connection flow works
- [ ] Connected status displays correctly
- [ ] Sync settings are configurable

**B. Salesforce Email Sync**  
- [ ] Email sync service is running
- [ ] Emails sync from Salesforce to CRM
- [ ] Email attachments transfer correctly
- [ ] Sync status updates in real-time
- [ ] Manual sync trigger works

**C. Salesforce Calendar Integration**
- [ ] Calendar sync setting exists
- [ ] Salesforce events appear in CRM calendar
- [ ] Event updates sync bidirectionally  
- [ ] Meeting invites sync correctly
- [ ] Calendar permissions are respected

## Sample Test Implementation

### Save Button Test Example
```javascript
test('Lead save button works correctly', async ({ page }) => {
  await page.goto('/leads');
  await page.click('button:has-text("New Lead")');
  
  await page.fill('input[name="first_name"]', 'John');
  await page.fill('input[name="last_name"]', 'Doe');
  await page.fill('input[name="email"]', 'john@example.com');
  
  await page.click('button:has-text("Save")');
  
  await expect(page.locator('text=/success|saved/i')).toBeVisible();
  
  // Verify persistence
  await page.reload();
  await expect(page.locator('text=John Doe')).toBeVisible();
});
```

### Delete Button Test Example
```javascript
test('Lead delete button works correctly', async ({ page }) => {
  await page.goto('/leads');
  
  const initialCount = await page.locator('tr[role="row"]').count();
  
  await page.locator('tr[role="row"]').first().click();
  await page.click('button:has-text("Delete")');
  await page.click('button:has-text("Confirm")');
  
  await expect(page.locator('text=/deleted|removed/i')).toBeVisible();
  
  const newCount = await page.locator('tr[role="row"]').count();
  expect(newCount).toBe(initialCount - 1);
});
```

## Running Tests

```bash
# Run all tests
npx playwright test

# Run specific test file
npx playwright test tests/save-buttons.spec.js

# Run tests in headed mode
npx playwright test --headed

# Run tests with UI
npx playwright test --ui

# Generate test report
npx playwright show-report
```

## Expected Results

### Success Criteria:
- ✅ All save buttons successfully persist data
- ✅ All delete buttons remove records correctly
- ✅ Salesforce integration settings accessible
- ✅ Salesforce email sync configured
- ✅ Salesforce calendar integration active
- ✅ No console errors during operations
- ✅ 100% test pass rate

### Known Issues to Document:
- Any buttons that don't work
- Missing confirmation modals
- Integration configuration gaps
- Permission-related failures

## Next Steps

1. Create test files in `/tests` directory
2. Implement automated test suite
3. Run initial test pass
4. Document failures
5. Fix identified issues
6. Re-run tests until 100% pass
7. Add to CI/CD pipeline

## Test Coverage Goals

- **Save Buttons**: 100% of forms tested
- **Delete Buttons**: 100% of delete operations tested  
- **Salesforce Integration**: All 3 components verified
- **Regression Prevention**: Tests run on every commit
