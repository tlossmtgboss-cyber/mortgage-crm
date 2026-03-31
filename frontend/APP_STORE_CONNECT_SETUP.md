# iOS App Store Connect Setup Guide

## Current App Configuration ✅
- **Bundle ID**: `com.perenniaai.mortgage.crm` (NEW - unique identifier)
- **App Version**: `1.0.2`
- **Build Number**: `10`
- **App Name**: "Perennia AI"

## Step 1: Create New App in App Store Connect

1. **Go to App Store Connect**: https://appstoreconnect.apple.com
2. **Click "My Apps"** → **"+" (plus icon)** → **"New App"**
3. **Fill out the form**:
   - **Platforms**: iOS
   - **Name**: `Perennia AI`
   - **Primary Language**: English (U.S.)
   - **Bundle ID**: Select `com.perenniaai.mortgage.crm` from dropdown
   - **SKU**: `perennia-ai-mortgage-crm` (unique identifier)
   - **User Access**: Full Access

4. **Click "Create"**

## Step 2: Configure App Information

### Required Information:
- **Category**: Business or Finance
- **Content Rights**: Check if you own the rights
- **Age Rating**: Complete the questionnaire (likely 4+)
- **App Privacy**: Complete privacy details

### App Description:
```
Perennia AI is an AI-powered mortgage CRM and loan origination operating system designed for mortgage loan officers, brokers, and lending teams. Streamline your mortgage business with intelligent automation, comprehensive pipeline management, and advanced analytics.

Features:
• AI-powered lead qualification and nurturing
• Complete loan pipeline management
• Smart document processing and e-signature
• Automated follow-up systems
• Real-time analytics and reporting
• Mobile-optimized interface for on-the-go access
```

### Keywords:
```
mortgage, CRM, loan, origination, real estate, finance, lending, AI, automation, pipeline
```

## Step 3: Upload App Binary

After setting up the app in App Store Connect, you can upload the binary:

```bash
cd /Users/timothyloss/my-project/mortgage-crm/frontend
SKIP_WEB_BUILD=true npm run ios:build
```

## Step 4: Submit for Review

1. **Add Screenshots** (required):
   - iPhone 6.7" (1290x2796)
   - iPhone 6.5" (1242x2688) 
   - iPad Pro 12.9" (2048x2732)

2. **Complete App Review Information**:
   - Demo account credentials if needed
   - Review notes
   - Contact information

3. **Submit for Review**

## Troubleshooting

If you encounter "invalid binary" errors:
- Ensure bundle ID matches exactly: `com.perenniaai.mortgage.crm`
- Build number must be higher than any previous submission
- Version number format must be X.Y.Z (currently 1.0.2)

## Alternative: Restore Previous App

If you want to restore the previous `com.perennia.mobile` app:
1. Contact Apple Developer Support
2. Request restoration of deleted app
3. Update bundle ID back to `com.perennia.mobile`