#!/bin/bash
set -euo pipefail

# iOS Build Script for Perennia AI
# Usage: ./scripts/ios-build.sh [debug|release|testflight|appstore]
#
# Environment variables:
#   DEVELOPMENT_TEAM  - Apple Developer Team ID (default: V5ZA5FZ2J8)
#   BUNDLE_ID         - App bundle identifier (default: com.perenniaai.crm)
#   BUILD_NUMBER      - Explicit build number (default: auto-increment)
#   SKIP_WEB_BUILD    - Skip npm build step (default: false)
#   SKIP_PREFLIGHT    - Skip ios-validate.sh pre-flight check (default: false)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND_DIR="$(dirname "$SCRIPT_DIR")"
IOS_DIR="$FRONTEND_DIR/ios"
PROJECT_DIR="$IOS_DIR/App"
SCHEME="App"
BUILD_DIR="$FRONTEND_DIR/ios-build"

# Configurable via environment with sensible defaults
DEVELOPMENT_TEAM="${DEVELOPMENT_TEAM:-V5ZA5FZ2J8}"
BUNDLE_ID="${BUNDLE_ID:-com.perenniaai.crm}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

BUILD_START_TIME=$(date +%s)
BUILD_TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S %Z')

log_info() { echo -e "${GREEN}[INFO]${NC} $(date '+%H:%M:%S') $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $(date '+%H:%M:%S') $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $(date '+%H:%M:%S') $1"; }
log_step() { echo -e "${BLUE}[STEP]${NC} $(date '+%H:%M:%S') $1"; }

# Exit codes
EXIT_INVALID_ARGS=1
EXIT_MISSING_TOOL=2
EXIT_PREFLIGHT_FAIL=3
EXIT_WEB_BUILD_FAIL=4
EXIT_CAP_SYNC_FAIL=5
EXIT_VERSION_UPDATE_FAIL=6
EXIT_XCODE_BUILD_FAIL=7
EXIT_ARCHIVE_FAIL=8
EXIT_EXPORT_FAIL=9

# Parse arguments
BUILD_TYPE="${1:-debug}"
SKIP_WEB_BUILD="${SKIP_WEB_BUILD:-false}"
SKIP_PREFLIGHT="${SKIP_PREFLIGHT:-false}"

# Get version from package.json
VERSION=$(node -p "require('$FRONTEND_DIR/package.json').version")

# Build number: use environment variable or auto-increment sequentially
if [ -z "${BUILD_NUMBER:-}" ]; then
    CURRENT_BUILD=$(/usr/libexec/PlistBuddy -c "Print :CFBundleVersion" "$PROJECT_DIR/App/Info.plist" 2>/dev/null || echo "0")
    # Ensure current build is a valid integer; default to 0 if not
    if ! [[ "$CURRENT_BUILD" =~ ^[0-9]+$ ]]; then
        CURRENT_BUILD=0
    fi
    BUILD_NUMBER=$((CURRENT_BUILD + 1))
fi

echo ""
log_info "========================================"
log_info "  Perennia AI iOS Build"
log_info "========================================"
log_info "Build Started:    $BUILD_TIMESTAMP"
log_info "Build Type:       $BUILD_TYPE"
log_info "Version:          $VERSION"
log_info "Build Number:     $BUILD_NUMBER"
log_info "Team ID:          $DEVELOPMENT_TEAM"
log_info "Bundle ID:        $BUNDLE_ID"
echo ""

# Validate build type
case "$BUILD_TYPE" in
    debug|release|testflight|appstore)
        ;;
    *)
        log_error "Invalid build type: $BUILD_TYPE"
        log_error "Valid options: debug, release, testflight, appstore"
        exit $EXIT_INVALID_ARGS
        ;;
esac

# Check for required tools
if ! command -v xcodebuild &> /dev/null; then
    log_error "xcodebuild not found. Please install Xcode."
    exit $EXIT_MISSING_TOOL
fi

if ! command -v node &> /dev/null; then
    log_error "node not found. Please install Node.js."
    exit $EXIT_MISSING_TOOL
fi

# Pre-flight validation
if [ "$SKIP_PREFLIGHT" != "true" ]; then
    log_step "Pre-flight: Running ios-validate.sh..."
    VALIDATE_SCRIPT="$SCRIPT_DIR/ios-validate.sh"
    if [ -f "$VALIDATE_SCRIPT" ]; then
        if ! bash "$VALIDATE_SCRIPT"; then
            log_error "Pre-flight validation failed. Fix issues above or set SKIP_PREFLIGHT=true to bypass."
            exit $EXIT_PREFLIGHT_FAIL
        fi
        log_info "Pre-flight validation passed."
    else
        log_warn "ios-validate.sh not found at $VALIDATE_SCRIPT -- skipping pre-flight."
    fi
else
    log_info "Pre-flight: Skipped (SKIP_PREFLIGHT=true)"
fi

# Step 1: Build web assets
if [ "$SKIP_WEB_BUILD" != "true" ]; then
    log_step "Step 1/8: Building web assets..."
    cd "$FRONTEND_DIR"

    if [ "$BUILD_TYPE" != "debug" ]; then
        # Use production capacitor config
        if [ -f "capacitor.config.production.ts" ]; then
            log_info "Using production Capacitor config..."
            cp capacitor.config.ts capacitor.config.dev.ts.bak
            cp capacitor.config.production.ts capacitor.config.ts
        fi
    fi

    if ! npm run build; then
        # Restore dev config before exiting on failure
        if [ -f "capacitor.config.dev.ts.bak" ]; then
            mv capacitor.config.dev.ts.bak capacitor.config.ts
        fi
        log_error "Web build failed."
        exit $EXIT_WEB_BUILD_FAIL
    fi

    # Restore dev config if backed up
    if [ -f "capacitor.config.dev.ts.bak" ]; then
        mv capacitor.config.dev.ts.bak capacitor.config.ts
    fi
else
    log_step "Step 1/8: Skipping web build (SKIP_WEB_BUILD=true)"
fi

# Step 2: Sync Capacitor
log_step "Step 2/8: Syncing Capacitor..."
cd "$FRONTEND_DIR"
if ! npx cap sync ios; then
    log_error "Capacitor sync failed."
    exit $EXIT_CAP_SYNC_FAIL
fi

# Step 3: Update version numbers in Xcode project
log_step "Step 3/8: Updating version numbers..."
cd "$PROJECT_DIR"

# Update Info.plist via PlistBuddy
/usr/libexec/PlistBuddy -c "Set :CFBundleShortVersionString $VERSION" "$PROJECT_DIR/App/Info.plist" 2>/dev/null || \
    /usr/libexec/PlistBuddy -c "Add :CFBundleShortVersionString string $VERSION" "$PROJECT_DIR/App/Info.plist"

/usr/libexec/PlistBuddy -c "Set :CFBundleVersion $BUILD_NUMBER" "$PROJECT_DIR/App/Info.plist" 2>/dev/null || \
    /usr/libexec/PlistBuddy -c "Add :CFBundleVersion string $BUILD_NUMBER" "$PROJECT_DIR/App/Info.plist"

# Also update project.pbxproj build settings
sed -i '' "s/MARKETING_VERSION = [^;]*/MARKETING_VERSION = $VERSION/" "$PROJECT_DIR/App.xcodeproj/project.pbxproj"
sed -i '' "s/CURRENT_PROJECT_VERSION = [^;]*/CURRENT_PROJECT_VERSION = $BUILD_NUMBER/" "$PROJECT_DIR/App.xcodeproj/project.pbxproj"

log_info "Info.plist and project.pbxproj updated: v$VERSION ($BUILD_NUMBER)"

# Step 4: Handle entitlements for release builds
if [ "$BUILD_TYPE" != "debug" ]; then
    log_step "Step 4/8: Configuring production entitlements..."
    if [ -f "$PROJECT_DIR/App/App.entitlements.release" ]; then
        cp "$PROJECT_DIR/App/App.entitlements.release" "$PROJECT_DIR/App/App.entitlements"
    else
        log_warn "Production entitlements file not found, using development entitlements"
    fi
else
    log_step "Step 4/8: Using development entitlements"
fi

# Step 5: Determine build configuration
case "$BUILD_TYPE" in
    debug)
        CONFIGURATION="Debug"
        ;;
    *)
        CONFIGURATION="Release"
        ;;
esac

# Step 6: Clean and create build directory
log_step "Step 5/8: Preparing build directory..."
mkdir -p "$BUILD_DIR"
rm -rf "$BUILD_DIR"/*

# Step 7: Build iOS app
log_step "Step 6/8: Building iOS app ($CONFIGURATION)..."
cd "$PROJECT_DIR"

# Check if xcpretty is available for nicer output
XCPRETTY_CMD=""
if command -v xcpretty &> /dev/null; then
    XCPRETTY_CMD="| xcpretty"
fi

if [ "$BUILD_TYPE" = "debug" ]; then
    # Debug build only
    eval "xcodebuild clean build \
        -project App.xcodeproj \
        -scheme '$SCHEME' \
        -configuration '$CONFIGURATION' \
        -destination 'generic/platform=iOS' \
        -derivedDataPath '$BUILD_DIR/DerivedData' \
        CODE_SIGN_STYLE=Automatic \
        DEVELOPMENT_TEAM='$DEVELOPMENT_TEAM' \
        PRODUCT_BUNDLE_IDENTIFIER='$BUNDLE_ID' \
        $XCPRETTY_CMD"

    if [ $? -ne 0 ]; then
        log_error "Debug build failed."
        exit $EXIT_XCODE_BUILD_FAIL
    fi

    log_info "Debug build complete!"
else
    # Release builds: create archive
    log_step "Step 7/8: Creating archive..."
    ARCHIVE_PATH="$BUILD_DIR/PerenniaAI.xcarchive"

    eval "xcodebuild clean archive \
        -project App.xcodeproj \
        -scheme '$SCHEME' \
        -configuration Release \
        -archivePath '$ARCHIVE_PATH' \
        -destination 'generic/platform=iOS' \
        CODE_SIGN_STYLE=Automatic \
        DEVELOPMENT_TEAM='$DEVELOPMENT_TEAM' \
        PRODUCT_BUNDLE_IDENTIFIER='$BUNDLE_ID' \
        $XCPRETTY_CMD"

    if [ ! -d "$ARCHIVE_PATH" ]; then
        log_error "Archive creation failed! No archive found at $ARCHIVE_PATH"
        exit $EXIT_ARCHIVE_FAIL
    fi

    # Report archive size
    ARCHIVE_SIZE=$(du -sh "$ARCHIVE_PATH" | cut -f1)
    log_info "Archive created: $ARCHIVE_PATH ($ARCHIVE_SIZE)"

    # Step 8: Export IPA
    log_step "Step 8/8: Exporting IPA..."
    IPA_DIR="$BUILD_DIR/ipa"
    mkdir -p "$IPA_DIR"

    EXPORT_OPTIONS="$IOS_DIR/ExportOptions-appstore.plist"

    if [ ! -f "$EXPORT_OPTIONS" ]; then
        log_error "Export options file not found: $EXPORT_OPTIONS"
        exit $EXIT_EXPORT_FAIL
    fi

    eval "xcodebuild -exportArchive \
        -archivePath '$ARCHIVE_PATH' \
        -exportOptionsPlist '$EXPORT_OPTIONS' \
        -exportPath '$IPA_DIR' \
        $XCPRETTY_CMD"

    # Check if IPA was created
    IPA_FILE=$(find "$IPA_DIR" -name "*.ipa" -print -quit)
    if [ -z "$IPA_FILE" ]; then
        log_error "IPA export failed! No .ipa file found in $IPA_DIR"
        exit $EXIT_EXPORT_FAIL
    fi

    # Report IPA size
    IPA_SIZE=$(du -sh "$IPA_FILE" | cut -f1)
    log_info "IPA exported: $IPA_FILE ($IPA_SIZE)"
fi

# Build timing
BUILD_END_TIME=$(date +%s)
BUILD_DURATION=$((BUILD_END_TIME - BUILD_START_TIME))
BUILD_MINUTES=$((BUILD_DURATION / 60))
BUILD_SECONDS=$((BUILD_DURATION % 60))

echo ""
log_info "========================================"
log_info "  Build Completed Successfully!"
log_info "========================================"
log_info "Version:       $VERSION ($BUILD_NUMBER)"
log_info "Team ID:       $DEVELOPMENT_TEAM"
log_info "Bundle ID:     $BUNDLE_ID"
log_info "Duration:      ${BUILD_MINUTES}m ${BUILD_SECONDS}s"
log_info "Finished at:   $(date '+%Y-%m-%d %H:%M:%S %Z')"

if [ "$BUILD_TYPE" != "debug" ]; then
    log_info "Archive:       $ARCHIVE_PATH ($ARCHIVE_SIZE)"
    log_info "IPA:           $IPA_FILE ($IPA_SIZE)"
    echo ""
    log_info "To upload to TestFlight, run:"
    log_info "  ./scripts/ios-upload-testflight.sh"
fi
echo ""
