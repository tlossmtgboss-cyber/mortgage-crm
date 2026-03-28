#!/bin/bash
set -e

# Android Build Script for Perennia AI
# Usage: ./scripts/android-build.sh [debug|release]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND_DIR="$(dirname "$SCRIPT_DIR")"
ANDROID_DIR="$FRONTEND_DIR/android"

GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

BUILD_TYPE="${1:-debug}"

echo ""
log_info "========================================"
log_info "  Perennia AI Android Build"
log_info "========================================"
log_info "Build Type: $BUILD_TYPE"
echo ""

# Check for required tools
if ! command -v java &> /dev/null; then
    log_error "Java not found. Install JDK 17+."
    exit 1
fi

cd "$FRONTEND_DIR"

# Step 1: Build web assets
log_info "Step 1: Building web assets..."
npm run build

# Step 2: Sync Capacitor
log_info "Step 2: Syncing Capacitor..."
npx cap sync android

# Step 3: Build Android
cd "$ANDROID_DIR"

if [ "$BUILD_TYPE" = "release" ]; then
    log_info "Step 3: Building release APK..."
    ./gradlew assembleRelease

    APK_PATH="app/build/outputs/apk/release/app-release.apk"
    if [ -f "$APK_PATH" ]; then
        log_info "Release APK: $ANDROID_DIR/$APK_PATH"
    else
        log_error "Release APK not found!"
        exit 1
    fi
else
    log_info "Step 3: Building debug APK..."
    ./gradlew assembleDebug

    APK_PATH="app/build/outputs/apk/debug/app-debug.apk"
    if [ -f "$APK_PATH" ]; then
        log_info "Debug APK: $ANDROID_DIR/$APK_PATH"
    else
        log_error "Debug APK not found!"
        exit 1
    fi
fi

echo ""
log_info "========================================"
log_info "  Build Complete!"
log_info "========================================"
echo ""
