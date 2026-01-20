# CloudFront CDN Setup

This directory contains Terraform configuration and scripts for deploying a CloudFront CDN distribution for the Perennia CRM.

## Overview

The CloudFront distribution provides:
- **Edge caching** for S3 documents and media
- **Reduced latency** for users globally
- **Lower S3 transfer costs** through caching
- **Security headers** applied automatically
- **Optional signed URLs** for private content
- **API response caching** for read-heavy endpoints

## Architecture

```
                                    ┌─────────────────┐
                                    │   CloudFront    │
                                    │   Distribution  │
                                    └────────┬────────┘
                                             │
              ┌──────────────────────────────┼──────────────────────────────┐
              │                              │                              │
              ▼                              ▼                              ▼
     ┌────────────────┐           ┌─────────────────┐           ┌─────────────────┐
     │ /documents/*   │           │ /videos/*       │           │ /api/*          │
     │ /images/*      │           │                 │           │                 │
     └───────┬────────┘           └────────┬────────┘           └────────┬────────┘
             │                             │                             │
             ▼                             ▼                             ▼
     ┌────────────────┐           ┌────────────────┐           ┌────────────────┐
     │   S3 Bucket    │           │   S3 Bucket    │           │ Railway API    │
     │ (perennia-docs)│           │ (perennia-docs)│           │    Backend     │
     └────────────────┘           └────────────────┘           └────────────────┘
```

## Prerequisites

1. **Terraform** >= 1.0
   ```bash
   brew install terraform  # macOS
   ```

2. **AWS CLI** configured with credentials
   ```bash
   brew install awscli
   aws configure
   ```

3. **S3 Bucket** already created (perennia-docs)

4. **ACM Certificate** (optional, for custom domain)
   - Must be in `us-east-1` region

## Quick Start

### 1. Initialize

```bash
cd infrastructure/cloudfront
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars with your values
```

### 2. Review Plan

```bash
./deploy.sh plan production
```

### 3. Deploy

```bash
./deploy.sh apply production
```

### 4. Get CDN URL

```bash
./deploy.sh output
```

## Configuration

### terraform.tfvars

```hcl
# Environment
environment = "production"
project_name = "perennia-crm"

# S3 bucket (must exist)
s3_bucket_name = "perennia-docs"

# Backend API origin
backend_origin = "api.perenniaai.com"

# Optional: Custom domain
# custom_domain = "cdn.yourcompany.com"
# custom_domain_cert_arn = "arn:aws:acm:us-east-1:xxx:certificate/xxx"

# Price class (affects cost and edge locations)
price_class = "PriceClass_100"  # US, Canada, Europe
```

### Price Classes

| Price Class | Regions | Relative Cost |
|-------------|---------|---------------|
| `PriceClass_100` | US, Canada, Europe | $ |
| `PriceClass_200` | + Asia, Middle East, Africa | $$ |
| `PriceClass_All` | All edge locations | $$$ |

## Environment Variables

Add these to your backend `.env`:

```bash
# CloudFront Configuration
CLOUDFRONT_DISTRIBUTION_ID=E1234ABCD5678
CLOUDFRONT_DOMAIN_NAME=d1234abcd.cloudfront.net

# For signed URLs (optional)
CLOUDFRONT_KEY_PAIR_ID=K1234ABCD5678
CLOUDFRONT_PRIVATE_KEY_PATH=/path/to/private_key.pem
# OR
CLOUDFRONT_PRIVATE_KEY="-----BEGIN RSA PRIVATE KEY-----\n..."
```

## Usage

### Cache Invalidation

```bash
# Invalidate all
./deploy.sh invalidate production /*

# Invalidate specific path
./deploy.sh invalidate production /documents/123/*

# Invalidate via AWS CLI
aws cloudfront create-invalidation \
    --distribution-id E1234ABCD5678 \
    --paths "/documents/*"
```

### Check Status

```bash
./deploy.sh status
```

### Using CDN URLs in Code

```python
from services.cdn_service import get_cdn_service

cdn = get_cdn_service()

# Get CDN URL for a document
result = cdn.get_document_cdn_url(
    loan_id=123,
    storage_key="documents/123/paystub.pdf",
    expires_in=300
)
print(result["url"])

# Transform existing S3 URL
cdn_url = cdn.transform_s3_url_to_cdn(s3_presigned_url)

# Invalidate cache after update
cdn.invalidate_document("documents/123/paystub.pdf")
```

## Cache Behaviors

| Path Pattern | Origin | TTL | Notes |
|--------------|--------|-----|-------|
| `/documents/*` | S3 | 1 day | Loan documents |
| `/videos/*` | S3 | 1 day | Video content |
| `/images/*` | S3 | 1 day | Images/thumbnails |
| `/api/*` | Railway | 1 min | API responses |
| Default | S3 | 1 day | All other S3 content |

## Security

### Headers Added

- `Strict-Transport-Security`: HSTS with 1 year max-age
- `X-Content-Type-Options`: nosniff
- `X-Frame-Options`: SAMEORIGIN
- `X-XSS-Protection`: 1; mode=block
- `Referrer-Policy`: strict-origin-when-cross-origin

### Signed URLs

For private content, enable signed URLs:

1. Create CloudFront key pair in AWS Console
2. Download private key
3. Set environment variables (see above)
4. Use `signed=True` in CDN service calls

## Costs

Estimated monthly costs (varies by usage):

| Component | Cost |
|-----------|------|
| CloudFront requests (1M) | ~$0.85 |
| Data transfer (100GB) | ~$8.50 |
| SSL certificate | Free (ACM) |
| Cache invalidation (1000) | Free |

## Troubleshooting

### Distribution stuck in "In Progress"

Wait 5-10 minutes. First deployment can take up to 15 minutes.

### 403 Access Denied

Check S3 bucket policy allows CloudFront OAC access.

### Cache not updating

Run cache invalidation:
```bash
./deploy.sh invalidate production /path/to/file
```

### SSL certificate error

Ensure ACM certificate is in `us-east-1` region.

## Cleanup

To remove all CloudFront infrastructure:

```bash
./deploy.sh destroy production
```

## Files

```
infrastructure/cloudfront/
├── main.tf                    # Main Terraform configuration
├── terraform.tfvars.example   # Example variables file
├── deploy.sh                  # Deployment script
├── .gitignore                 # Git ignore for Terraform
└── README.md                  # This file
```
