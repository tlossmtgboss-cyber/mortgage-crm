#!/bin/bash
# Blue-Green Deployment Script for Mortgage CRM
# Usage: ./deploy.sh <new-image-tag> [--skip-validation] [--auto-rollback]

set -euo pipefail

# Configuration
NAMESPACE="mortgage-crm-bluegreen"
APP_NAME="mortgage-crm-api"
REGISTRY="your-registry.com/mortgage-crm"
HEALTH_CHECK_RETRIES=30
HEALTH_CHECK_INTERVAL=10
SMOKE_TEST_TIMEOUT=60

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Get current active color
get_active_color() {
    kubectl get configmap deployment-state -n "$NAMESPACE" -o jsonpath='{.data.active-color}' 2>/dev/null || echo "blue"
}

# Get inactive color
get_inactive_color() {
    local active=$(get_active_color)
    if [ "$active" == "blue" ]; then
        echo "green"
    else
        echo "blue"
    fi
}

# Update deployment image
update_deployment_image() {
    local color=$1
    local image_tag=$2

    log_info "Updating ${color} deployment to image: ${REGISTRY}/api:${image_tag}"

    kubectl set image deployment/${APP_NAME}-${color} \
        api=${REGISTRY}/api:${image_tag} \
        -n "$NAMESPACE"
}

# Scale deployment
scale_deployment() {
    local color=$1
    local replicas=$2

    log_info "Scaling ${color} deployment to ${replicas} replicas"

    kubectl scale deployment/${APP_NAME}-${color} \
        --replicas=${replicas} \
        -n "$NAMESPACE"
}

# Wait for deployment to be ready
wait_for_deployment() {
    local color=$1
    local timeout=${2:-300}

    log_info "Waiting for ${color} deployment to be ready (timeout: ${timeout}s)"

    kubectl rollout status deployment/${APP_NAME}-${color} \
        -n "$NAMESPACE" \
        --timeout=${timeout}s
}

# Health check function
health_check() {
    local service=$1
    local retries=${2:-$HEALTH_CHECK_RETRIES}
    local interval=${3:-$HEALTH_CHECK_INTERVAL}

    log_info "Running health checks on ${service}..."

    local endpoint
    if [ "$service" == "preview" ]; then
        endpoint="https://preview-api.mortgagecrm.com/api/v1/enterprise/health"
    else
        endpoint="https://api.mortgagecrm.com/api/v1/enterprise/health"
    fi

    for ((i=1; i<=retries; i++)); do
        if curl -sf "$endpoint" > /dev/null 2>&1; then
            log_success "Health check passed (attempt $i/$retries)"
            return 0
        fi
        log_warning "Health check failed (attempt $i/$retries), retrying in ${interval}s..."
        sleep "$interval"
    done

    log_error "Health checks failed after $retries attempts"
    return 1
}

# Run smoke tests
run_smoke_tests() {
    local color=$1

    log_info "Running smoke tests against ${color} deployment..."

    local service_ip
    service_ip=$(kubectl get service ${APP_NAME}-${color} -n "$NAMESPACE" -o jsonpath='{.spec.clusterIP}')

    # Basic API endpoint tests
    local tests=(
        "/api/v1/enterprise/health"
        "/api/v1/enterprise/health/live"
        "/api/v1/enterprise/health/ready"
    )

    for test in "${tests[@]}"; do
        log_info "Testing endpoint: ${test}"

        if ! kubectl run smoke-test-$(date +%s) \
            --image=curlimages/curl:latest \
            --rm --restart=Never \
            -n "$NAMESPACE" \
            --timeout="${SMOKE_TEST_TIMEOUT}s" \
            -- curl -sf "http://${service_ip}:80${test}" > /dev/null 2>&1; then
            log_error "Smoke test failed for ${test}"
            return 1
        fi

        log_success "Smoke test passed: ${test}"
    done

    return 0
}

# Switch traffic
switch_traffic() {
    local target_color=$1

    log_info "Switching traffic to ${target_color} deployment"

    # Update service selector
    kubectl patch service ${APP_NAME} \
        -n "$NAMESPACE" \
        -p "{\"spec\":{\"selector\":{\"deployment-color\":\"${target_color}\"}}}"

    # Update ConfigMap
    kubectl patch configmap deployment-state \
        -n "$NAMESPACE" \
        --type merge \
        -p "{\"data\":{\"active-color\":\"${target_color}\",\"last-switch\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"}}"

    log_success "Traffic switched to ${target_color}"
}

# Rollback function
rollback() {
    local target_color=$1

    log_warning "Initiating rollback to ${target_color}..."

    switch_traffic "$target_color"

    # Scale down failed deployment
    local failed_color=$(get_inactive_color)
    scale_deployment "$failed_color" 0

    log_success "Rollback complete"
}

# Main deployment function
deploy() {
    local image_tag=$1
    local skip_validation=${2:-false}
    local auto_rollback=${3:-true}

    log_info "Starting blue-green deployment"
    log_info "Image tag: ${image_tag}"

    # Get current state
    local active_color=$(get_active_color)
    local inactive_color=$(get_inactive_color)

    log_info "Current active: ${active_color}, deploying to: ${inactive_color}"

    # Step 1: Update inactive deployment with new image
    update_deployment_image "$inactive_color" "$image_tag"

    # Step 2: Scale up inactive deployment
    local current_replicas
    current_replicas=$(kubectl get deployment ${APP_NAME}-${active_color} \
        -n "$NAMESPACE" \
        -o jsonpath='{.spec.replicas}')

    scale_deployment "$inactive_color" "$current_replicas"

    # Step 3: Wait for deployment to be ready
    if ! wait_for_deployment "$inactive_color" 300; then
        log_error "Deployment failed to become ready"
        if [ "$auto_rollback" == "true" ]; then
            scale_deployment "$inactive_color" 0
        fi
        exit 1
    fi

    # Step 4: Run validation (unless skipped)
    if [ "$skip_validation" != "true" ]; then
        log_info "Running validation checks..."

        # Health check via preview
        if ! health_check "preview"; then
            log_error "Health check failed"
            if [ "$auto_rollback" == "true" ]; then
                scale_deployment "$inactive_color" 0
            fi
            exit 1
        fi

        # Smoke tests
        if ! run_smoke_tests "$inactive_color"; then
            log_error "Smoke tests failed"
            if [ "$auto_rollback" == "true" ]; then
                scale_deployment "$inactive_color" 0
            fi
            exit 1
        fi
    fi

    # Step 5: Switch traffic
    switch_traffic "$inactive_color"

    # Step 6: Verify production health
    sleep 10  # Allow DNS/cache to update
    if ! health_check "production" 10 5; then
        log_error "Production health check failed after switch"
        if [ "$auto_rollback" == "true" ]; then
            rollback "$active_color"
        fi
        exit 1
    fi

    # Step 7: Scale down old deployment (keep 1 for quick rollback)
    log_info "Scaling down old ${active_color} deployment"
    scale_deployment "$active_color" 1

    # Step 8: Update version info
    kubectl patch configmap deployment-state \
        -n "$NAMESPACE" \
        --type merge \
        -p "{\"data\":{\"${inactive_color}-version\":\"${image_tag}\"}}"

    log_success "Deployment complete!"
    log_info "Active color: ${inactive_color}"
    log_info "Image: ${REGISTRY}/api:${image_tag}"
}

# Rollback to previous version
rollback_to_previous() {
    local active_color=$(get_active_color)
    local previous_color=$(get_inactive_color)

    log_info "Rolling back from ${active_color} to ${previous_color}"

    # Scale up previous deployment
    local current_replicas
    current_replicas=$(kubectl get deployment ${APP_NAME}-${active_color} \
        -n "$NAMESPACE" \
        -o jsonpath='{.spec.replicas}')

    scale_deployment "$previous_color" "$current_replicas"

    if ! wait_for_deployment "$previous_color" 180; then
        log_error "Previous deployment failed to scale up"
        exit 1
    fi

    # Switch traffic
    switch_traffic "$previous_color"

    # Scale down current
    scale_deployment "$active_color" 1

    log_success "Rollback complete"
}

# Get deployment status
get_status() {
    local active_color=$(get_active_color)
    local blue_version=$(kubectl get configmap deployment-state -n "$NAMESPACE" -o jsonpath='{.data.blue-version}' 2>/dev/null || echo "N/A")
    local green_version=$(kubectl get configmap deployment-state -n "$NAMESPACE" -o jsonpath='{.data.green-version}' 2>/dev/null || echo "N/A")
    local last_switch=$(kubectl get configmap deployment-state -n "$NAMESPACE" -o jsonpath='{.data.last-switch}' 2>/dev/null || echo "N/A")

    echo "========================================"
    echo "Blue-Green Deployment Status"
    echo "========================================"
    echo "Active Color: ${active_color}"
    echo "Blue Version: ${blue_version}"
    echo "Green Version: ${green_version}"
    echo "Last Switch: ${last_switch}"
    echo ""
    echo "Blue Deployment:"
    kubectl get deployment ${APP_NAME}-blue -n "$NAMESPACE" -o wide 2>/dev/null || echo "Not found"
    echo ""
    echo "Green Deployment:"
    kubectl get deployment ${APP_NAME}-green -n "$NAMESPACE" -o wide 2>/dev/null || echo "Not found"
    echo ""
    echo "Pods:"
    kubectl get pods -n "$NAMESPACE" -l app.kubernetes.io/name=${APP_NAME} -o wide
}

# Parse arguments
IMAGE_TAG=""
SKIP_VALIDATION="false"
AUTO_ROLLBACK="true"
COMMAND=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --skip-validation)
            SKIP_VALIDATION="true"
            shift
            ;;
        --no-auto-rollback)
            AUTO_ROLLBACK="false"
            shift
            ;;
        status)
            COMMAND="status"
            shift
            ;;
        rollback)
            COMMAND="rollback"
            shift
            ;;
        deploy)
            COMMAND="deploy"
            shift
            ;;
        *)
            if [ -z "$IMAGE_TAG" ]; then
                IMAGE_TAG="$1"
            fi
            shift
            ;;
    esac
done

# Execute command
case $COMMAND in
    status)
        get_status
        ;;
    rollback)
        rollback_to_previous
        ;;
    deploy|"")
        if [ -z "$IMAGE_TAG" ]; then
            echo "Usage: $0 deploy <image-tag> [--skip-validation] [--no-auto-rollback]"
            echo "       $0 status"
            echo "       $0 rollback"
            exit 1
        fi
        deploy "$IMAGE_TAG" "$SKIP_VALIDATION" "$AUTO_ROLLBACK"
        ;;
    *)
        echo "Unknown command: $COMMAND"
        exit 1
        ;;
esac
