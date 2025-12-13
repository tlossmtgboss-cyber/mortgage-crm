# Agent Governance UI Test Checklist

## Setup
- [ ] Backend running on http://localhost:8000
- [ ] Frontend running on http://localhost:3000
- [ ] Navigate to http://localhost:3000/settings

## Section 1: System Settings
- [ ] Click "Agent Governance" in sidebar → scrolls to section
- [ ] Toggle "Agent Governance Enabled" → switch animates
- [ ] Toggle "Automatic Health Checks" → switch animates
- [ ] Toggle "Cost Tracking" → switch animates
- [ ] Toggle "WebSocket Real-time Updates" → switch animates
- [ ] Toggle "Audit Log All Changes" → switch animates

## Section 2: Performance Thresholds
- [ ] Change "Minimum Success Rate" to 95 → accepts number
- [ ] Try to enter 120 → should not exceed 100
- [ ] Try to enter 70 → should not go below 80
- [ ] Change "Maximum Response Time" to 12000 → accepts
- [ ] Change "Maximum Cost Per Success" to 0.012 → accepts

## Section 3: Cost Budgets
- [ ] Set "Daily Budget" to $75 → accepts
- [ ] Set "Monthly Budget" to $45,000 → accepts
- [ ] Set "Cost Alert Threshold" to 85% → accepts

## Section 4: Alerts & Notifications
- [ ] Change "Alert Routing" dropdown to "Slack" → updates
- [ ] Enter Slack webhook URL → accepts
- [ ] Toggle "Daily Digest Notifications" → works
- [ ] Change "Digest Time" dropdown → updates

## Section 5: Compliance
- [ ] Toggle "Enforce Elite Status for Tier 3" → works
- [ ] Toggle "Fair Lending Monitoring" → works
- [ ] Toggle "Require Approval for Agent Changes" → works
- [ ] Set "Audit Log Retention" to 2555 days → accepts

## Section 6: Agent Gym Settings
- [ ] Toggle "Automatic Daily Testing" → works
- [ ] Set "Minimum Pass Rate" to 98% → accepts
- [ ] Toggle "Block Deployment on Failed Tests" → works

## Save & Persistence
- [ ] Click "Save Settings" button → shows loading state
- [ ] Success message appears (green, "Settings saved")
- [ ] Refresh page (F5)
- [ ] All values persisted correctly
- [ ] No console errors in DevTools

## Integration Test
- [ ] Navigate to /agents dashboard
- [ ] Agents display correctly
- [ ] Navigate to /agent-gym
- [ ] Gym scenarios load
- [ ] Navigate back to /settings
- [ ] Settings still show saved values

## Browser Console Check
- [ ] Open DevTools (F12)
- [ ] Check Console tab → no errors
- [ ] Check Network tab → all API calls 200 OK
- [ ] Check for WebSocket connection (if enabled)

## Final Checks
- [ ] All sections scroll smoothly
- [ ] No visual glitches
- [ ] Responsive on different screen sizes
- [ ] Settings apply to agent operations

---

✅ All tests passed → Ready for production!
❌ Any failures → Document and fix before deploying
