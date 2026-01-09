#!/bin/bash
# =============================================================================
# CloudFront CDN Deployment Script
# =============================================================================
# Usage:
#   ./deploy.sh [command] [environment]
#
# Commands:
#   init        - Initialize Terraform
#   plan        - Show deployment plan
#   apply       - Apply changes
#   destroy     - Destroy infrastructure
#   invalidate  - Invalidate CloudFront cache
#   status      - Show distribution status
#   output      - Show Terraform outputs
#
# Environments:
#   dev, staging, production (default: production)
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Default values
COMMAND=${1:-"plan"}
ENVIRONMENT=${2:-"production"}

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check prerequisites
check_prerequisites() {
    log_info "Checking prerequisites..."

    if ! command -v terraform &> /dev/null; then
        log_error "Terraform is not installed. Please install it first."
        echo "  brew install terraform  # macOS"
        echo "  Or visit: https://www.terraform.io/downloads"
        exit 1
    fi

    if ! command -v aws &> /dev/null; then
        log_error "AWS CLI is not installed. Please install it first."
        echo "  brew install awscli  # macOS"
        echo "  Or visit: https://aws.amazon.com/cli/"
        exit 1
    fi

    # Check AWS credentials
    if ! aws sts get-caller-identity &> /dev/null; then
        log_error "AWS credentials not configured. Run 'aws configure' first."
        exit 1
    fi

    log_success "Prerequisites check passed"
}

# Initialize Terraform
init() {
    log_info "Initializing Terraform..."
    terraform init -upgrade
    log_success "Terraform initialized"
}

# Plan deployment
plan() {
    log_info "Planning deployment for ${ENVIRONMENT}..."

    if [ -f "environments/${ENVIRONMENT}.tfvars" ]; then
        terraform plan -var-file="environments/${ENVIRONMENT}.tfvars" -out=tfplan
    elif [ -f "terraform.tfvars" ]; then
        terraform plan -var="environment=${ENVIRONMENT}" -out=tfplan
    else
        terraform plan -var="environment=${ENVIRONMENT}" -out=tfplan
    fi

    log_success "Plan complete. Review above and run './deploy.sh apply' to apply changes."
}

# Apply deployment
apply() {
    log_info "Applying deployment for ${ENVIRONMENT}..."

    if [ -f "tfplan" ]; then
        terraform apply tfplan
        rm -f tfplan
    else
        log_warn "No plan file found. Creating and applying..."
        if [ -f "environments/${ENVIRONMENT}.tfvars" ]; then
            terraform apply -var-file="environments/${ENVIRONMENT}.tfvars" -auto-approve
        else
            terraform apply -var="environment=${ENVIRONMENT}" -auto-approve
        fi
    fi

    log_success "Deployment complete!"
    output
}

# Destroy infrastructure
destroy() {
    log_warn "This will destroy all CloudFront infrastructure!"
    read -p "Are you sure? (yes/no): " confirm
    if [ "$confirm" != "yes" ]; then
        log_info "Aborted."
        exit 0
    fi

    log_info "Destroying infrastructure..."
    if [ -f "environments/${ENVIRONMENT}.tfvars" ]; then
        terraform destroy -var-file="environments/${ENVIRONMENT}.tfvars"
    else
        terraform destroy -var="environment=${ENVIRONMENT}"
    fi

    log_success "Infrastructure destroyed"
}

# Invalidate CloudFront cache
invalidate() {
    DISTRIBUTION_ID=$(terraform output -raw cloudfront_distribution_id 2>/dev/null || echo "")

    if [ -z "$DISTRIBUTION_ID" ]; then
        log_error "Could not get distribution ID. Is infrastructure deployed?"
        exit 1
    fi

    PATHS=${3:-"/*"}
    log_info "Invalidating cache for: ${PATHS}"

    INVALIDATION_ID=$(aws cloudfront create-invalidation \
        --distribution-id "$DISTRIBUTION_ID" \
        --paths "$PATHS" \
        --query 'Invalidation.Id' \
        --output text)

    log_success "Invalidation created: ${INVALIDATION_ID}"
    log_info "Checking status..."

    aws cloudfront wait invalidation-completed \
        --distribution-id "$DISTRIBUTION_ID" \
        --id "$INVALIDATION_ID" &

    log_info "Invalidation in progress (ID: ${INVALIDATION_ID})"
    log_info "Run 'aws cloudfront get-invalidation --distribution-id ${DISTRIBUTION_ID} --id ${INVALIDATION_ID}' to check status"
}

# Show distribution status
status() {
    DISTRIBUTION_ID=$(terraform output -raw cloudfront_distribution_id 2>/dev/null || echo "")

    if [ -z "$DISTRIBUTION_ID" ]; then
        log_error "Could not get distribution ID. Is infrastructure deployed?"
        exit 1
    fi

    log_info "CloudFront Distribution Status"
    echo "================================"

    aws cloudfront get-distribution --id "$DISTRIBUTION_ID" \
        --query 'Distribution.{
            Id: Id,
            Status: Status,
            DomainName: DomainName,
            Enabled: DistributionConfig.Enabled,
            PriceClass: DistributionConfig.PriceClass,
            Aliases: DistributionConfig.Aliases.Items
        }' \
        --output table
}

# Show outputs
output() {
    log_info "Terraform Outputs"
    echo "=================="
    terraform output
}

# Show help
help() {
    echo "CloudFront CDN Deployment Script"
    echo ""
    echo "Usage: ./deploy.sh [command] [environment]"
    echo ""
    echo "Commands:"
    echo "  init        Initialize Terraform"
    echo "  plan        Show deployment plan"
    echo "  apply       Apply changes"
    echo "  destroy     Destroy infrastructure"
    echo "  invalidate  Invalidate CloudFront cache (optional: path)"
    echo "  status      Show distribution status"
    echo "  output      Show Terraform outputs"
    echo "  help        Show this help"
    echo ""
    echo "Environments: dev, staging, production (default: production)"
    echo ""
    echo "Examples:"
    echo "  ./deploy.sh plan production"
    echo "  ./deploy.sh apply"
    echo "  ./deploy.sh invalidate production /documents/*"
    echo ""
}

# Main
case $COMMAND in
    init)
        check_prerequisites
        init
        ;;
    plan)
        check_prerequisites
        init
        plan
        ;;
    apply)
        check_prerequisites
        apply
        ;;
    destroy)
        check_prerequisites
        destroy
        ;;
    invalidate)
        check_prerequisites
        invalidate
        ;;
    status)
        check_prerequisites
        status
        ;;
    output)
        output
        ;;
    help|--help|-h)
        help
        ;;
    *)
        log_error "Unknown command: $COMMAND"
        help
        exit 1
        ;;
esac
