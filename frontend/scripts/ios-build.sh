#!/bin/bash
set -e

# iOS Build Script for Perennia AI
# Usage: ./scripts/ios-build.sh [debug|release|testflight|appstore]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND_DIR="$(dirname "$SCRIPT_DIR")"
IOS_DIR="$FRONTEND_DIR/ios"
PROJECT_DIR="$IOS_DIR/App"
SCHEME="App"
BUILD_DIR="$FRONTEND_DIR/ios-build"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Parse arguments
BUILD_TYPE="${1:-debug}"
SKIP_WEB_BUILD="${SKIP_WEB_BUILD:-false}"

# Get version from package.json
VERSION=$(node -p "require('$FRONTEND_DIR/package.json').version")
# Build number: use environment variable or timestamp-based for uniqueness
BUILD_NUMBER="${BUILD_NUMBER:-$(date +%Y%m%d%H%M)}"

echo ""
log_info "========================================"
log_info "  Perennia AI iOS Build"
log_info "========================================"
log_info "Build Type: $BUILD_TYPE"
log_info "Version: $VERSION"
log_info "Build Number: $BUILD_NUMBER"
echo ""

# Validate build type
case "$BUILD_TYPE" in
    debug|release|testflight|appstore)
        ;;
    *)
        log_error "Invalid build type: $BUILD_TYPE"
        log_error "Valid options: debug, release, testflight, appstore"
        exit 1
        ;;
esac

# Check for required tools
if ! command -v xcodebuild &> /dev/null; then
    log_error "xcodebuild not found. Please install Xcode."
    exit 1
fi

if ! command -v node &> /dev/null; then
    log_error "node not found. Please install Node.js."
    exit 1
fi

# Step 1: Build web assets
if [ "$SKIP_WEB_BUILD" != "true" ]; then
    log_info "Step 1: Building web assets..."
    cd "$FRONTEND_DIR"

    if [ "$BUILD_TYPE" != "debug" ]; then
        # Use production capacitor config
        if [ -f "capacitor.config.production.ts" ]; then
            log_info "Using production Capacitor config..."
            cp capacitor.config.ts capacitor.config.dev.ts.bak
            cp capacitor.config.production.ts capacitor.config.ts
        fi
    fi

    npm run build

    # Restore dev config if backed up
    if [ -f "capacitor.config.dev.ts.bak" ]; then
        mv capacitor.config.dev.ts.bak capacitor.config.ts
    fi
else
    log_info "Step 1: Skipping web build (SKIP_WEB_BUILD=true)"
fi

# Step 2: Sync Capacitor
log_info "Step 2: Syncing Capacitor..."
cd "$FRONTEND_DIR"
npx cap sync ios

# Step 3: Update version numbers in Xcode project
log_info "Step 3: Updating version numbers..."
cd "$PROJECT_DIR"

# Update Info.plist via PlistBuddy
/usr/libexec/PlistBuddy -c "Set :CFBundleShortVersionString $VERSION" "$PROJECT_DIR/App/Info.plist" 2>/dev/null || \
    /usr/libexec/PlistBuddy -c "Add :CFBundleShortVersionString string $VERSION" "$PROJECT_DIR/App/Info.plist"

/usr/libexec/PlistBuddy -c "Set :CFBundleVersion $BUILD_NUMBER" "$PROJECT_DIR/App/Info.plist" 2>/dev/null || \
    /usr/libexec/PlistBuddy -c "Add :CFBundleVersion string $BUILD_NUMBER" "$PROJECT_DIR/App/Info.plist"

# Also update project.pbxproj build settings
sed -i '' "s/MARKETING_VERSION = [^;]*/MARKETING_VERSION = $VERSION/" "$PROJECT_DIR/App.xcodeproj/project.pbxproj"
sed -i '' "s/CURRENT_PROJECT_VERSION = [^;]*/CURRENT_PROJECT_VERSION = $BUILD_NUMBER/" "$PROJECT_DIR/App.xcodeproj/project.pbxproj"

# Step 4: Handle entitlements for release builds
if [ "$BUILD_TYPE" != "debug" ]; then
    log_info "Step 4: Configuring production entitlements..."
    if [ -f "$PROJECT_DIR/App/App.entitlements.release" ]; then
        cp "$PROJECT_DIR/App/App.entitlements.release" "$PROJECT_DIR/App/App.entitlements"
    else
        log_warn "Production entitlements file not found, using development entitlements"
    fi
else
    log_info "Step 4: Using development entitlements"
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
log_info "Step 5: Preparing build directory..."
mkdir -p "$BUILD_DIR"
rm -rf "$BUILD_DIR"/*

# Step 7: Build iOS app
log_info "Step 6: Building iOS app ($CONFIGURATION)..."
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
        DEVELOPMENT_TEAM=V5ZA5FZ2J8 \
        $XCPRETTY_CMD" || true

    log_info "Debug build complete!"
else
    # Release builds: create archive
    log_info "Step 7: Creating archive..."
    ARCHIVE_PATH="$BUILD_DIR/PerenniaAI.xcarchive"

    eval "xcodebuild clean archive \
        -project App.xcodeproj \
        -scheme '$SCHEME' \
        -configuration Release \
        -archivePath '$ARCHIVE_PATH' \
        -destination 'generic/platform=iOS' \
        CODE_SIGN_STYLE=Automatic \
        DEVELOPMENT_TEAM=V5ZA5FZ2J8 \
        $XCPRETTY_CMD" || true

    if [ ! -d "$ARCHIVE_PATH" ]; then
        log_error "Archive creation failed!"
        exit 1
    fi

    # Step 8: Export IPA
    log_info "Step 8: Exporting IPA..."
    IPA_DIR="$BUILD_DIR/ipa"
    mkdir -p "$IPA_DIR"

    EXPORT_OPTIONS="$IOS_DIR/ExportOptions-appstore.plist"

    if [ ! -f "$EXPORT_OPTIONS" ]; then
        log_error "Export options file not found: $EXPORT_OPTIONS"
        exit 1
    fi

    eval "xcodebuild -exportArchive \
        -archivePath '$ARCHIVE_PATH' \
        -exportOptionsPlist '$EXPORT_OPTIONS' \
        -exportPath '$IPA_DIR' \
        $XCPRETTY_CMD" || true

    # Check if IPA was created
    IPA_FILE=$(find "$IPA_DIR" -name "*.ipa" -print -quit)
    if [ -z "$IPA_FILE" ]; then
        log_error "IPA export failed!"
        exit 1
    fi
fi

echo ""
log_info "========================================"
log_info "  Build Completed Successfully!"
log_info "========================================"
log_info "Version: $VERSION ($BUILD_NUMBER)"

if [ "$BUILD_TYPE" != "debug" ]; then
    log_info "Archive: $ARCHIVE_PATH"
    log_info "IPA: $IPA_FILE"
    echo ""
    log_info "To upload to TestFlight, run:"
    log_info "  ./scripts/ios-upload-testflight.sh"
fi
echo ""
