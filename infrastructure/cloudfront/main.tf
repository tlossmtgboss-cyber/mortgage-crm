# =============================================================================
# CloudFront CDN Infrastructure for Perennia CRM
# =============================================================================
# This Terraform configuration sets up CloudFront distribution for:
# - S3 document/media delivery with edge caching
# - API caching for read-heavy endpoints
# - Custom domain with SSL certificate
#
# Prerequisites:
# - AWS credentials configured
# - Domain registered in Route 53 (optional, for custom domain)
# - terraform >= 1.0
# =============================================================================

terraform {
  required_version = ">= 1.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # Configure remote state (recommended for production)
  # backend "s3" {
  #   bucket = "perennia-terraform-state"
  #   key    = "cloudfront/terraform.tfstate"
  #   region = "us-east-1"
  # }
}

# =============================================================================
# Variables
# =============================================================================

variable "environment" {
  description = "Environment name (dev, staging, production)"
  type        = string
  default     = "production"
}

variable "project_name" {
  description = "Project name for resource naming"
  type        = string
  default     = "perennia-crm"
}

variable "s3_bucket_name" {
  description = "Name of the S3 bucket for documents"
  type        = string
  default     = "perennia-docs"
}

variable "custom_domain" {
  description = "Custom domain for CloudFront (leave empty to use CloudFront domain)"
  type        = string
  default     = ""
}

variable "custom_domain_cert_arn" {
  description = "ACM certificate ARN for custom domain (must be in us-east-1)"
  type        = string
  default     = ""
}

variable "backend_origin" {
  description = "Backend API origin URL"
  type        = string
  default     = "api.perenniaai.com"
}

variable "price_class" {
  description = "CloudFront price class"
  type        = string
  default     = "PriceClass_100" # US, Canada, Europe only (cheapest)
  # Options: PriceClass_100, PriceClass_200, PriceClass_All
}

variable "enable_waf" {
  description = "Enable AWS WAF for CloudFront"
  type        = bool
  default     = false
}

variable "log_bucket" {
  description = "S3 bucket for CloudFront access logs (leave empty to disable)"
  type        = string
  default     = ""
}

# =============================================================================
# Provider Configuration
# =============================================================================

provider "aws" {
  region = "us-east-1" # CloudFront requires us-east-1 for certificates

  default_tags {
    tags = {
      Project     = var.project_name
      Environment = var.environment
      ManagedBy   = "Terraform"
    }
  }
}

# =============================================================================
# Data Sources
# =============================================================================

# Get the existing S3 bucket
data "aws_s3_bucket" "documents" {
  bucket = var.s3_bucket_name
}

# =============================================================================
# CloudFront Origin Access Control (OAC)
# =============================================================================

resource "aws_cloudfront_origin_access_control" "s3_oac" {
  name                              = "${var.project_name}-${var.environment}-s3-oac"
  description                       = "OAC for ${var.s3_bucket_name}"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

# =============================================================================
# S3 Bucket Policy for CloudFront Access
# =============================================================================

resource "aws_s3_bucket_policy" "cloudfront_access" {
  bucket = data.aws_s3_bucket.documents.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowCloudFrontServicePrincipal"
        Effect = "Allow"
        Principal = {
          Service = "cloudfront.amazonaws.com"
        }
        Action   = "s3:GetObject"
        Resource = "${data.aws_s3_bucket.documents.arn}/*"
        Condition = {
          StringEquals = {
            "AWS:SourceArn" = aws_cloudfront_distribution.main.arn
          }
        }
      }
    ]
  })
}

# =============================================================================
# CloudFront Cache Policies
# =============================================================================

# Cache policy for static assets (images, PDFs, documents)
resource "aws_cloudfront_cache_policy" "static_assets" {
  name        = "${var.project_name}-${var.environment}-static-assets"
  comment     = "Cache policy for static assets with long TTL"
  default_ttl = 86400    # 1 day
  max_ttl     = 31536000 # 1 year
  min_ttl     = 3600     # 1 hour

  parameters_in_cache_key_and_forwarded_to_origin {
    cookies_config {
      cookie_behavior = "none"
    }
    headers_config {
      header_behavior = "none"
    }
    query_strings_config {
      query_string_behavior = "none"
    }
    enable_accept_encoding_brotli = true
    enable_accept_encoding_gzip   = true
  }
}

# Cache policy for API responses (short TTL, vary by query string)
resource "aws_cloudfront_cache_policy" "api_cache" {
  name        = "${var.project_name}-${var.environment}-api-cache"
  comment     = "Cache policy for API responses"
  default_ttl = 60   # 1 minute
  max_ttl     = 300  # 5 minutes
  min_ttl     = 0

  parameters_in_cache_key_and_forwarded_to_origin {
    cookies_config {
      cookie_behavior = "none"
    }
    headers_config {
      header_behavior = "whitelist"
      headers {
        items = ["Authorization", "Accept", "Origin"]
      }
    }
    query_strings_config {
      query_string_behavior = "all"
    }
    enable_accept_encoding_brotli = true
    enable_accept_encoding_gzip   = true
  }
}

# =============================================================================
# CloudFront Origin Request Policies
# =============================================================================

# Origin request policy for API (forward all headers)
resource "aws_cloudfront_origin_request_policy" "api_origin" {
  name    = "${var.project_name}-${var.environment}-api-origin"
  comment = "Forward necessary headers to API origin"

  cookies_config {
    cookie_behavior = "all"
  }
  headers_config {
    header_behavior = "whitelist"
    headers {
      items = [
        "Authorization",
        "Accept",
        "Accept-Language",
        "Content-Type",
        "Origin",
        "Referer",
        "User-Agent",
        "X-Forwarded-For"
      ]
    }
  }
  query_strings_config {
    query_string_behavior = "all"
  }
}

# =============================================================================
# CloudFront Response Headers Policy
# =============================================================================

resource "aws_cloudfront_response_headers_policy" "security_headers" {
  name    = "${var.project_name}-${var.environment}-security-headers"
  comment = "Security headers for all responses"

  security_headers_config {
    content_type_options {
      override = true
    }
    frame_options {
      frame_option = "SAMEORIGIN"
      override     = true
    }
    referrer_policy {
      referrer_policy = "strict-origin-when-cross-origin"
      override        = true
    }
    strict_transport_security {
      access_control_max_age_sec = 31536000
      include_subdomains         = true
      preload                    = true
      override                   = true
    }
    xss_protection {
      mode_block = true
      protection = true
      override   = true
    }
  }

  cors_config {
    access_control_allow_credentials = false
    access_control_allow_headers {
      items = ["*"]
    }
    access_control_allow_methods {
      items = ["GET", "HEAD", "OPTIONS"]
    }
    access_control_allow_origins {
      items = ["*"]
    }
    access_control_max_age_sec = 86400
    origin_override            = false
  }

  custom_headers_config {
    items {
      header   = "Cache-Control"
      value    = "public, max-age=31536000, immutable"
      override = false
    }
  }
}

# =============================================================================
# CloudFront Distribution
# =============================================================================

resource "aws_cloudfront_distribution" "main" {
  enabled             = true
  is_ipv6_enabled     = true
  comment             = "${var.project_name} CDN (${var.environment})"
  default_root_object = ""
  price_class         = var.price_class
  http_version        = "http2and3"

  # Custom domain configuration
  aliases = var.custom_domain != "" ? [var.custom_domain] : []

  # SSL certificate
  viewer_certificate {
    cloudfront_default_certificate = var.custom_domain_cert_arn == ""
    acm_certificate_arn            = var.custom_domain_cert_arn != "" ? var.custom_domain_cert_arn : null
    ssl_support_method             = var.custom_domain_cert_arn != "" ? "sni-only" : null
    minimum_protocol_version       = "TLSv1.2_2021"
  }

  # Logging configuration (optional)
  dynamic "logging_config" {
    for_each = var.log_bucket != "" ? [1] : []
    content {
      bucket          = "${var.log_bucket}.s3.amazonaws.com"
      prefix          = "cloudfront/${var.environment}/"
      include_cookies = false
    }
  }

  # ==========================================================================
  # Origin: S3 Documents
  # ==========================================================================
  origin {
    domain_name              = data.aws_s3_bucket.documents.bucket_regional_domain_name
    origin_id                = "S3-${var.s3_bucket_name}"
    origin_access_control_id = aws_cloudfront_origin_access_control.s3_oac.id
  }

  # ==========================================================================
  # Origin: Backend API
  # ==========================================================================
  origin {
    domain_name = var.backend_origin
    origin_id   = "Backend-API"

    custom_origin_config {
      http_port              = 80
      https_port             = 443
      origin_protocol_policy = "https-only"
      origin_ssl_protocols   = ["TLSv1.2"]
    }

    custom_header {
      name  = "X-CDN-Secret"
      value = "perennia-cdn-${var.environment}"
    }
  }

  # ==========================================================================
  # Default Behavior (S3 Documents)
  # ==========================================================================
  default_cache_behavior {
    allowed_methods  = ["GET", "HEAD", "OPTIONS"]
    cached_methods   = ["GET", "HEAD"]
    target_origin_id = "S3-${var.s3_bucket_name}"

    cache_policy_id            = aws_cloudfront_cache_policy.static_assets.id
    response_headers_policy_id = aws_cloudfront_response_headers_policy.security_headers.id

    viewer_protocol_policy = "redirect-to-https"
    compress               = true
  }

  # ==========================================================================
  # Behavior: Documents path (S3)
  # ==========================================================================
  ordered_cache_behavior {
    path_pattern     = "/documents/*"
    allowed_methods  = ["GET", "HEAD", "OPTIONS"]
    cached_methods   = ["GET", "HEAD"]
    target_origin_id = "S3-${var.s3_bucket_name}"

    cache_policy_id            = aws_cloudfront_cache_policy.static_assets.id
    response_headers_policy_id = aws_cloudfront_response_headers_policy.security_headers.id

    viewer_protocol_policy = "redirect-to-https"
    compress               = true
  }

  # ==========================================================================
  # Behavior: Videos path (S3, longer cache)
  # ==========================================================================
  ordered_cache_behavior {
    path_pattern     = "/videos/*"
    allowed_methods  = ["GET", "HEAD", "OPTIONS"]
    cached_methods   = ["GET", "HEAD"]
    target_origin_id = "S3-${var.s3_bucket_name}"

    cache_policy_id            = aws_cloudfront_cache_policy.static_assets.id
    response_headers_policy_id = aws_cloudfront_response_headers_policy.security_headers.id

    viewer_protocol_policy = "redirect-to-https"
    compress               = true
  }

  # ==========================================================================
  # Behavior: Images path (S3)
  # ==========================================================================
  ordered_cache_behavior {
    path_pattern     = "/images/*"
    allowed_methods  = ["GET", "HEAD", "OPTIONS"]
    cached_methods   = ["GET", "HEAD"]
    target_origin_id = "S3-${var.s3_bucket_name}"

    cache_policy_id            = aws_cloudfront_cache_policy.static_assets.id
    response_headers_policy_id = aws_cloudfront_response_headers_policy.security_headers.id

    viewer_protocol_policy = "redirect-to-https"
    compress               = true
  }

  # ==========================================================================
  # Behavior: API endpoints (Backend)
  # ==========================================================================
  ordered_cache_behavior {
    path_pattern     = "/api/*"
    allowed_methods  = ["DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"]
    cached_methods   = ["GET", "HEAD"]
    target_origin_id = "Backend-API"

    cache_policy_id          = aws_cloudfront_cache_policy.api_cache.id
    origin_request_policy_id = aws_cloudfront_origin_request_policy.api_origin.id

    viewer_protocol_policy = "redirect-to-https"
    compress               = true
  }

  # ==========================================================================
  # Geo Restrictions (optional)
  # ==========================================================================
  restrictions {
    geo_restriction {
      restriction_type = "none"
      # To restrict: restriction_type = "whitelist", locations = ["US", "CA", "GB"]
    }
  }

  tags = {
    Name = "${var.project_name}-cdn-${var.environment}"
  }
}

# =============================================================================
# Outputs
# =============================================================================

output "cloudfront_distribution_id" {
  description = "CloudFront distribution ID"
  value       = aws_cloudfront_distribution.main.id
}

output "cloudfront_domain_name" {
  description = "CloudFront distribution domain name"
  value       = aws_cloudfront_distribution.main.domain_name
}

output "cloudfront_arn" {
  description = "CloudFront distribution ARN"
  value       = aws_cloudfront_distribution.main.arn
}

output "cdn_url" {
  description = "CDN URL for accessing assets"
  value       = "https://${var.custom_domain != "" ? var.custom_domain : aws_cloudfront_distribution.main.domain_name}"
}

output "s3_bucket_name" {
  description = "S3 bucket name for documents"
  value       = data.aws_s3_bucket.documents.id
}
