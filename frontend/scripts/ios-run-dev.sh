#!/bin/bash
set -e

# Quick development build and run for iOS
# Usage: ./scripts/ios-run-dev.sh [--open]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND_DIR="$(dirname "$SCRIPT_DIR")"
PROJECT_DIR="$FRONTEND_DIR/ios/App"

# Colors
GREEN='\033[0;32m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }

cd "$FRONTEND_DIR"

# Build web assets in development mode
log_info "Building web assets..."
npm run build

# Sync to iOS
log_info "Syncing Capacitor..."
npx cap sync ios

if [ "$1" = "--open" ]; then
    # Open in Xcode
    log_info "Opening Xcode..."
    npx cap open ios
else
    # Build and run on simulator
    log_info "Building for simulator..."
    cd "$PROJECT_DIR"

    # Check if xcpretty is available
    XCPRETTY_CMD=""
    if command -v xcpretty &> /dev/null; then
        XCPRETTY_CMD="| xcpretty"
    fi

    # Get available simulators and pick iPhone 15 Pro or first available
    SIMULATOR=$(xcrun simctl list devices available | grep -E "iPhone (15|14|13)" | head -1 | sed -E 's/.*\(([A-F0-9-]+)\).*/\1/')

    if [ -z "$SIMULATOR" ]; then
        SIMULATOR_NAME="iPhone 15 Pro"
    else
        SIMULATOR_NAME=$(xcrun simctl list devices available | grep "$SIMULATOR" | head -1 | sed -E 's/^[[:space:]]*//' | cut -d'(' -f1 | xargs)
    fi

    log_info "Target simulator: $SIMULATOR_NAME"

    eval "xcodebuild build \
        -project App.xcodeproj \
        -scheme App \
        -configuration Debug \
        -destination \"platform=iOS Simulator,name=$SIMULATOR_NAME\" \
        CODE_SIGN_STYLE=Automatic \
        DEVELOPMENT_TEAM=V5ZA5FZ2J8 \
        $XCPRETTY_CMD" || true

    log_info "Build complete!"
    log_info ""
    log_info "To run on a physical device, use: ./scripts/ios-run-dev.sh --open"
fi
