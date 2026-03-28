# App Store Submission Checklist — Perennia AI

## App Store Connect Setup

- [ ] Create app in App Store Connect (bundle ID: com.perenniaai.crm)
- [ ] Set primary language: English (U.S.)
- [ ] Set primary category: Business
- [ ] Set secondary category: Finance

## App Information

- [ ] App name: "Perennia AI"
- [ ] Subtitle: "AI-Powered Mortgage CRM"
- [ ] Privacy policy URL: https://app.perenniaai.com/privacy
- [ ] Support URL: https://perenniaai.com/support

## App Store Listing

- [ ] Description (max 4000 chars)
- [ ] Keywords (max 100 chars, comma-separated)
- [ ] Screenshots: 6.7" (iPhone 15 Pro Max) — 3-5 screenshots required
- [ ] Screenshots: 6.5" (iPhone 14 Plus) — 3-5 screenshots required
- [ ] Screenshots: 5.5" (iPhone 8 Plus) — optional
- [ ] App icon: 1024x1024 PNG (no alpha, no rounded corners)

## Build & Upload

1. Increment version in package.json
2. Run: `cd frontend && npm run ios:build:testflight`
3. Run: `cd frontend && npm run ios:upload`
4. Wait for processing (10-30 min)

## Review Preparation

- [ ] Demo account credentials for App Review team
- [ ] Notes explaining any features requiring login
- [ ] Age rating questionnaire completed
- [ ] Export compliance (ITSAppUsesNonExemptEncryption = NO, already set in Info.plist)

## Pre-Submission Checks

- [ ] App loads on iPhone SE (smallest screen)
- [ ] App loads on iPhone 15 Pro Max (largest screen)
- [ ] Push notifications work on physical device
- [ ] Face ID / Touch ID login works
- [ ] All links open correctly (no broken routes)
- [ ] Offline indicator shows when airplane mode on
- [ ] App returns to foreground correctly after backgrounding
