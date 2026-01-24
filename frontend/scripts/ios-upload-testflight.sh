#!/bin/bash
set -e

# Upload to TestFlight
# Requires: App Store Connect API Key

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND_DIR="$(dirname "$SCRIPT_DIR")"
BUILD_DIR="$FRONTEND_DIR/ios-build"
IPA_DIR="$BUILD_DIR/ipa"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

echo ""
log_info "========================================"
log_info "  TestFlight Upload"
log_info "========================================"
echo ""

# Find IPA file
IPA_FILE=$(find "$IPA_DIR" -name "*.ipa" -print -quit 2>/dev/null)

if [ -z "$IPA_FILE" ] || [ ! -f "$IPA_FILE" ]; then
    log_error "IPA not found in: $IPA_DIR"
    log_error "Run './scripts/ios-build.sh testflight' first"
    exit 1
fi

log_info "IPA: $IPA_FILE"

# App Store Connect API credentials (from environment)
API_KEY_ID="${APP_STORE_CONNECT_API_KEY_ID}"
API_ISSUER_ID="${APP_STORE_CONNECT_ISSUER_ID}"
API_KEY_PATH="${APP_STORE_CONNECT_API_KEY_PATH:-$HOME/.appstoreconnect/private_keys/AuthKey_${API_KEY_ID}.p8}"

# Validate credentials
if [ -z "$API_KEY_ID" ]; then
    log_error "APP_STORE_CONNECT_API_KEY_ID environment variable not set"
    log_error ""
    log_error "To set up App Store Connect API credentials:"
    log_error "1. Go to App Store Connect > Users and Access > Keys"
    log_error "2. Create a new API key with 'App Manager' role"
    log_error "3. Download the .p8 file and save it to:"
    log_error "   ~/.appstoreconnect/private_keys/AuthKey_<KEY_ID>.p8"
    log_error "4. Set environment variables:"
    log_error "   export APP_STORE_CONNECT_API_KEY_ID=<your key id>"
    log_error "   export APP_STORE_CONNECT_ISSUER_ID=<your issuer id>"
    exit 1
fi

if [ -z "$API_ISSUER_ID" ]; then
    log_error "APP_STORE_CONNECT_ISSUER_ID environment variable not set"
    exit 1
fi

if [ ! -f "$API_KEY_PATH" ]; then
    log_error "API key file not found: $API_KEY_PATH"
    log_error ""
    log_error "Download your .p8 key file from App Store Connect and save it to:"
    log_error "  $API_KEY_PATH"
    exit 1
fi

log_info "API Key ID: $API_KEY_ID"
log_info "Issuer ID: $API_ISSUER_ID"
log_info ""

# Validate the IPA
log_info "Validating IPA..."
xcrun altool --validate-app \
    --type ios \
    --file "$IPA_FILE" \
    --apiKey "$API_KEY_ID" \
    --apiIssuer "$API_ISSUER_ID"

log_info "Validation passed!"
log_info ""

# Upload to TestFlight
log_info "Uploading to TestFlight..."
xcrun altool --upload-app \
    --type ios \
    --file "$IPA_FILE" \
    --apiKey "$API_KEY_ID" \
    --apiIssuer "$API_ISSUER_ID"

echo ""
log_info "========================================"
log_info "  Upload Complete!"
log_info "========================================"
log_info ""
log_info "Your build has been submitted to App Store Connect."
log_info "Processing typically takes 10-30 minutes."
log_info ""
log_info "Check status at: https://appstoreconnect.apple.com"
echo ""
