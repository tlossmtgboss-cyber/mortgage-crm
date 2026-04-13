# iOS Build and Distribution Guide

## Prerequisites

1. **macOS** with Xcode 15+ installed
2. **Node.js** 18+ and npm
3. **Apple Developer Account** with:
   - App ID registered: `com.perenniaai.crm`
   - Push Notifications capability enabled
   - Sign in with Apple capability enabled
4. **App Store Connect API Key** (for CI/CD and TestFlight uploads)

## Quick Start

### Local Development

```bash
cd frontend

# Build and open in Xcode (recommended for device testing)
npm run ios:open

# Or build for simulator
npm run ios:dev
```

### Production Builds

```bash
# Release build (creates archive and IPA)
npm run ios:build

# TestFlight build
npm run ios:build:testflight

# Upload to TestFlight (after building)
npm run ios:upload
```

## Build Scripts

### `ios-build.sh`

Main build script with multiple modes:

```bash
./scripts/ios-build.sh [debug|release|testflight|appstore]
```

| Mode | Description |
|------|-------------|
| `debug` | Development build (default) |
| `release` | Release build with archive |
| `testflight` | Same as release, ready for TestFlight |
| `appstore` | Same as release, ready for App Store |

**Environment Variables:**
- `BUILD_NUMBER` - Override build number (default: timestamp)
- `SKIP_WEB_BUILD` - Set to `true` to skip React build

### `ios-upload-testflight.sh`

Uploads the built IPA to TestFlight.

**Required Environment Variables:**
- `APP_STORE_CONNECT_API_KEY_ID` - API Key ID
- `APP_STORE_CONNECT_ISSUER_ID` - Issuer ID
- `APP_STORE_CONNECT_API_KEY_PATH` - Path to .p8 file (optional, defaults to ~/.appstoreconnect/private_keys/)

### `ios-run-dev.sh`

Quick development builds:

```bash
./scripts/ios-run-dev.sh         # Build for simulator
./scripts/ios-run-dev.sh --open  # Open in Xcode
```

## CI/CD (GitHub Actions)

The workflow is triggered by:
- **Version tags**: Push a tag like `v1.0.3` to automatically build and upload to TestFlight
- **Manual dispatch**: Go to Actions > iOS Build and Deploy > Run workflow

### Required GitHub Secrets

| Secret | Description |
|--------|-------------|
| `APP_STORE_CONNECT_API_KEY_ID` | API Key ID from App Store Connect |
| `APP_STORE_CONNECT_ISSUER_ID` | Issuer ID from App Store Connect |
| `APP_STORE_CONNECT_API_KEY_BASE64` | Base64-encoded .p8 key file |

### Creating App Store Connect API Key

1. Go to [App Store Connect](https://appstoreconnect.apple.com)
2. Navigate to **Users and Access** > **Integrations** > **App Store Connect API**
3. Click **+** to create a new key
4. Select **App Manager** role (minimum required for uploads)
5. Download the `.p8` file (only downloadable once!)
6. Note the **Key ID** and **Issuer ID**

### Encoding the API Key for GitHub

```bash
# macOS
base64 -i AuthKey_XXXXXXXXXX.p8 | pbcopy

# Linux
base64 AuthKey_XXXXXXXXXX.p8 | xclip -selection clipboard
```

Paste the result into the `APP_STORE_CONNECT_API_KEY_BASE64` secret.

### Triggering Builds

**Via tag (recommended for releases):**
```bash
# Update version in package.json first
npm version patch  # or minor, major

# Push the tag
git push && git push --tags
```

**Manual trigger:**
1. Go to **Actions** > **iOS Build and Deploy**
2. Click **Run workflow**
3. Select build type and options
4. Click **Run workflow**

## Version Management

- **Marketing Version**: Derived from `frontend/package.json` version field
- **Build Number**:
  - Local: Timestamp-based (YYYYMMDDHHMM)
  - CI: GitHub Actions run number

To bump versions:
```bash
cd frontend
npm version patch  # 1.0.2 -> 1.0.3
npm version minor  # 1.0.2 -> 1.1.0
npm version major  # 1.0.2 -> 2.0.0
```

## Build Output

After a successful build:

| Artifact | Location |
|----------|----------|
| Archive | `frontend/ios-build/PerenniaAI.xcarchive` |
| IPA | `frontend/ios-build/ipa/*.ipa` |
| dSYM | `frontend/ios-build/PerenniaAI.xcarchive/dSYMs/` |

## Configuration Files

| File | Purpose |
|------|---------|
| `ios/release.xcconfig` | Release build settings |
| `ios/ExportOptions-appstore.plist` | IPA export configuration |
| `ios/App/App/App.entitlements.release` | Production entitlements |

## Troubleshooting

### Code Signing Issues

```bash
# Verify team ID
grep DEVELOPMENT_TEAM frontend/ios/App/App.xcodeproj/project.pbxproj

# Should show: DEVELOPMENT_TEAM = V5ZA5FZ2J8
```

If signing fails:
1. Open Xcode: `npm run ios:open`
2. Select the App target
3. Go to Signing & Capabilities
4. Ensure "Automatically manage signing" is checked
5. Select the correct team

### Build Failures

```bash
# Check Capacitor setup
cd frontend
npx cap doctor

# Clear derived data
rm -rf ~/Library/Developer/Xcode/DerivedData

# Clean and rebuild
./scripts/ios-build.sh release
```

### TestFlight Upload Failures

- **Invalid credentials**: Verify API key ID and issuer ID match App Store Connect
- **Bundle ID mismatch**: Ensure `com.perenniaai.crm` is registered in Apple Developer portal
- **Duplicate build number**: Each build number must be unique per version

### Capacitor Sync Issues

```bash
cd frontend

# Full clean and sync
rm -rf ios/App/App/public
rm -rf ios/App/Pods
npx cap sync ios
```

## Architecture

```
Build Process:
1. npm run build          # React production build -> frontend/build/
2. npx cap sync ios       # Copy to iOS -> ios/App/App/public/
3. xcodebuild archive     # Create .xcarchive
4. xcodebuild export      # Create .ipa from archive
5. xcrun altool upload    # Upload to TestFlight
```

## Security Notes

- Never commit `.p8` API key files to the repository
- Use GitHub Secrets for all sensitive values
- The `.gitignore` excludes build artifacts and backup files
- Production entitlements use `production` APS environment (push notifications)
