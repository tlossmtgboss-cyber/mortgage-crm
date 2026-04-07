#!/bin/bash

# iOS App Store Validation Script
# This script checks for common App Store submission issues

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log_error() {
    echo -e "${RED}❌ ERROR: $1${NC}" >&2
}

log_success() {
    echo -e "${GREEN}✅ SUCCESS: $1${NC}"
}

log_warn() {
    echo -e "${YELLOW}⚠️  WARNING: $1${NC}"
}

log_info() {
    echo -e "${BLUE}ℹ️  INFO: $1${NC}"
}

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
IOS_DIR="$FRONTEND_DIR/ios"
PROJECT_DIR="$IOS_DIR/App"

echo ""
log_info "========================================"
log_info "  iOS App Store Validation Check"
log_info "========================================"
echo ""

# Check 1: Version consistency
log_info "Checking version consistency..."
PACKAGE_VERSION=$(node -p "require('$FRONTEND_DIR/package.json').version")
XCODE_VERSION=$(grep "MARKETING_VERSION" "$PROJECT_DIR/App.xcodeproj/project.pbxproj" | head -1 | sed 's/.*= \(.*\);/\1/')
XCODE_BUILD=$(grep "CURRENT_PROJECT_VERSION" "$PROJECT_DIR/App.xcodeproj/project.pbxproj" | head -1 | sed 's/.*= \(.*\);/\1/')

echo "Package.json version: $PACKAGE_VERSION"
echo "Xcode marketing version: $XCODE_VERSION"
echo "Xcode build version: $XCODE_BUILD"

if [[ "$PACKAGE_VERSION" == "$XCODE_VERSION" ]]; then
    log_success "Version numbers are consistent"
else
    log_error "Version mismatch between package.json ($PACKAGE_VERSION) and Xcode ($XCODE_VERSION)"
fi

# Check 2: Required files
log_info "Checking required files..."

required_files=(
    "$PROJECT_DIR/App/Info.plist"
    "$PROJECT_DIR/App/App.entitlements"
    "$PROJECT_DIR/App/App.entitlements.release"
    "$IOS_DIR/ExportOptions-appstore.plist"
)

for file in "${required_files[@]}"; do
    if [[ -f "$file" ]]; then
        log_success "Found: $(basename "$file")"
    else
        log_error "Missing: $file"
    fi
done

# Check 3: Info.plist validation
log_info "Validating Info.plist..."

# Check for required keys
plist_file="$PROJECT_DIR/App/Info.plist"

required_keys=(
    "CFBundleDisplayName"
    "CFBundleExecutable"
    "CFBundleIdentifier"
    "CFBundleShortVersionString"
    "CFBundleVersion"
    "NSCameraUsageDescription"
    "NSPhotoLibraryUsageDescription"
    "NSMicrophoneUsageDescription"
    "NSFaceIDUsageDescription"
    "ITSAppUsesNonExemptEncryption"
)

for key in "${required_keys[@]}"; do
    if /usr/libexec/PlistBuddy -c "Print :$key" "$plist_file" >/dev/null 2>&1; then
        log_success "Found required key: $key"
    else
        log_error "Missing required key: $key"
    fi
done

# Check 4: Device capabilities
log_info "Checking device capabilities..."
if /usr/libexec/PlistBuddy -c "Print :UIRequiredDeviceCapabilities" "$plist_file" | grep -q "arm64"; then
    log_success "arm64 device capability is set"
else
    log_warn "Consider setting arm64 as device capability (removes armv7 compatibility)"
fi

# Check 5: Deployment target
log_info "Checking deployment target..."
deployment_target=$(grep "IPHONEOS_DEPLOYMENT_TARGET" "$PROJECT_DIR/App.xcodeproj/project.pbxproj" | head -1 | sed 's/.*= \(.*\);/\1/')
echo "iOS Deployment Target: $deployment_target"

target_version=$(echo "$deployment_target" | sed 's/[^0-9.]//g')
if (( $(echo "$target_version >= 14.0" | bc -l) )); then
    log_success "Deployment target is iOS $target_version"
else
    log_warn "Deployment target is iOS $target_version - consider updating to iOS 14.0+"
fi

# Check 6: Bundle identifier
log_info "Checking bundle identifier..."
bundle_id=$(grep "PRODUCT_BUNDLE_IDENTIFIER" "$PROJECT_DIR/App.xcodeproj/project.pbxproj" | head -1 | sed 's/.*= \(.*\);/\1/')
echo "Bundle ID: $bundle_id"

if [[ "$bundle_id" == *".crm"* ]]; then
    log_success "Bundle identifier looks valid"
else
    log_warn "Bundle identifier format: $bundle_id"
fi

# Check 7: Export options validation
log_info "Validating export options..."
export_plist="$IOS_DIR/ExportOptions-appstore.plist"

if /usr/libexec/PlistBuddy -c "Print :method" "$export_plist" | grep -q "app-store"; then
    log_success "Export method is set to app-store"
else
    log_error "Export method should be 'app-store'"
fi

if /usr/libexec/PlistBuddy -c "Print :manageAppVersionAndBuildNumber" "$export_plist" | grep -q "true"; then
    log_success "App version and build number management is enabled"
else
    log_warn "Consider enabling automatic version/build number management"
fi

# Check 8: Entitlements validation
log_info "Validating entitlements..."
prod_entitlements="$PROJECT_DIR/App/App.entitlements.release"

if /usr/libexec/PlistBuddy -c "Print :aps-environment" "$prod_entitlements" | grep -q "production"; then
    log_success "Production entitlements configured for production APS environment"
else
    log_error "Production entitlements should use 'production' APS environment"
fi

# Check 8b: Required entitlements in BOTH .entitlements files
log_info "Checking required entitlements in both files..."

required_entitlements=(
    "aps-environment"
    "com.apple.developer.applesignin"
    "com.apple.developer.associated-domains"
    "keychain-access-groups"
)

for ent_file in "$PROJECT_DIR/App/App.entitlements" "$PROJECT_DIR/App/App.entitlements.release"; do
    ent_basename=$(basename "$ent_file")
    if [[ ! -f "$ent_file" ]]; then
        log_error "Missing entitlements file: $ent_basename"
        continue
    fi
    for ent_key in "${required_entitlements[@]}"; do
        if /usr/libexec/PlistBuddy -c "Print :$ent_key" "$ent_file" >/dev/null 2>&1; then
            log_success "$ent_basename has entitlement: $ent_key"
        else
            log_error "$ent_basename missing entitlement: $ent_key"
        fi
    done
done

# Check 9: Code signing validation
log_info "Checking code signing configuration..."
code_sign_style=$(grep "CODE_SIGN_STYLE" "$PROJECT_DIR/App.xcodeproj/project.pbxproj" | head -1 | sed 's/.*= \(.*\);/\1/')
if [[ "$code_sign_style" == *"Automatic"* ]]; then
    log_success "Code signing style is set to Automatic"
else
    log_warn "Code signing style: $code_sign_style"
fi

# Check 10: Privacy Manifest (required for iOS 17+)
log_info "Checking Privacy Manifest..."
PRIVACY_MANIFEST="$PROJECT_DIR/App/PrivacyInfo.xcprivacy"
if [[ -f "$PRIVACY_MANIFEST" ]]; then
    log_success "PrivacyInfo.xcprivacy exists"
else
    log_error "Missing PrivacyInfo.xcprivacy — required for iOS 17+ App Store submissions"
fi

# Check 11: Version in package.json matches MARKETING_VERSION in pbxproj
log_info "Checking package.json <-> pbxproj version sync..."
PKG_VER=$(node -p "require('$FRONTEND_DIR/package.json').version")
PBXPROJ_VER=$(grep "MARKETING_VERSION" "$PROJECT_DIR/App.xcodeproj/project.pbxproj" | head -1 | sed 's/.*= \(.*\);/\1/' | tr -d ' ')
if [[ "$PKG_VER" == "$PBXPROJ_VER" ]]; then
    log_success "package.json ($PKG_VER) matches pbxproj MARKETING_VERSION ($PBXPROJ_VER)"
else
    log_error "package.json version ($PKG_VER) does not match pbxproj MARKETING_VERSION ($PBXPROJ_VER)"
fi

# Check 12: CarPlay scene configuration in Info.plist
log_info "Checking CarPlay scene configuration..."
if /usr/libexec/PlistBuddy -c "Print :UIApplicationSceneManifest" "$plist_file" >/dev/null 2>&1; then
    log_success "UIApplicationSceneManifest found in Info.plist (scene configuration present)"
else
    log_warn "No UIApplicationSceneManifest in Info.plist — CarPlay scene delegate may not be invoked at runtime"
fi

# Check 13: NativeBiometric in Package.swift
log_info "Checking NativeBiometric in Package.swift..."
PACKAGE_SWIFT="$PROJECT_DIR/CapApp-SPM/Package.swift"
if [[ -f "$PACKAGE_SWIFT" ]]; then
    if grep -q "NativeBiometric\|capacitor-native-biometric" "$PACKAGE_SWIFT"; then
        log_success "NativeBiometric dependency found in Package.swift"
    else
        log_warn "NativeBiometric not found in Package.swift — biometric auth plugin may not be linked natively"
    fi
else
    log_error "Package.swift not found at $PACKAGE_SWIFT"
fi

echo ""
log_info "========================================"
log_info "  Validation Complete"
log_info "========================================"
echo ""

echo "Next steps to fix App Store submission:"
echo "1. Run: cd frontend && ./scripts/ios-build.sh appstore"
echo "2. Check the generated archive and IPA"
echo "3. Upload using: ./scripts/ios-upload-testflight.sh"
echo "4. Or upload directly through Xcode Organizer"
echo ""