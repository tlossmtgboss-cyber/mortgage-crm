# Multi-Region Deployment Configuration for Mortgage CRM
# Terraform configuration for deploying across multiple cloud regions

terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.23"
    }
  }

  backend "s3" {
    bucket         = "mortgage-crm-terraform-state"
    key            = "multi-region/terraform.tfstate"
    region         = "us-east-1"
    encrypt        = true
    dynamodb_table = "terraform-state-lock"
  }
}

# Variables
variable "environment" {
  description = "Environment name (prod, staging, dr)"
  type        = string
  default     = "prod"
}

variable "primary_region" {
  description = "Primary AWS region"
  type        = string
  default     = "us-east-1"
}

variable "secondary_region" {
  description = "Secondary/DR AWS region"
  type        = string
  default     = "us-west-2"
}

variable "enable_multi_region" {
  description = "Enable multi-region deployment"
  type        = bool
  default     = true
}

variable "db_instance_class" {
  description = "RDS instance class"
  type        = string
  default     = "db.r6g.xlarge"
}

# Local values
locals {
  common_tags = {
    Project     = "mortgage-crm"
    Environment = var.environment
    ManagedBy   = "terraform"
    MultiRegion = var.enable_multi_region
  }

  regions = var.enable_multi_region ? {
    primary   = var.primary_region
    secondary = var.secondary_region
  } : {
    primary = var.primary_region
  }
}

# Provider configurations
provider "aws" {
  alias  = "primary"
  region = var.primary_region

  default_tags {
    tags = local.common_tags
  }
}

provider "aws" {
  alias  = "secondary"
  region = var.secondary_region

  default_tags {
    tags = local.common_tags
  }
}

# VPC Module - Primary Region
module "vpc_primary" {
  source = "../modules/vpc"

  providers = {
    aws = aws.primary
  }

  name               = "mortgage-crm-${var.environment}-primary"
  cidr               = "10.0.0.0/16"
  availability_zones = ["${var.primary_region}a", "${var.primary_region}b", "${var.primary_region}c"]

  private_subnets = ["10.0.1.0/24", "10.0.2.0/24", "10.0.3.0/24"]
  public_subnets  = ["10.0.101.0/24", "10.0.102.0/24", "10.0.103.0/24"]

  enable_nat_gateway   = true
  single_nat_gateway   = false
  enable_dns_hostnames = true

  tags = merge(local.common_tags, {
    Region = "primary"
  })
}

# VPC Module - Secondary Region
module "vpc_secondary" {
  count  = var.enable_multi_region ? 1 : 0
  source = "../modules/vpc"

  providers = {
    aws = aws.secondary
  }

  name               = "mortgage-crm-${var.environment}-secondary"
  cidr               = "10.1.0.0/16"
  availability_zones = ["${var.secondary_region}a", "${var.secondary_region}b", "${var.secondary_region}c"]

  private_subnets = ["10.1.1.0/24", "10.1.2.0/24", "10.1.3.0/24"]
  public_subnets  = ["10.1.101.0/24", "10.1.102.0/24", "10.1.103.0/24"]

  enable_nat_gateway   = true
  single_nat_gateway   = false
  enable_dns_hostnames = true

  tags = merge(local.common_tags, {
    Region = "secondary"
  })
}

# VPC Peering between regions
resource "aws_vpc_peering_connection" "primary_to_secondary" {
  count = var.enable_multi_region ? 1 : 0

  provider    = aws.primary
  vpc_id      = module.vpc_primary.vpc_id
  peer_vpc_id = module.vpc_secondary[0].vpc_id
  peer_region = var.secondary_region

  tags = merge(local.common_tags, {
    Name = "mortgage-crm-cross-region-peering"
  })
}

resource "aws_vpc_peering_connection_accepter" "secondary" {
  count = var.enable_multi_region ? 1 : 0

  provider                  = aws.secondary
  vpc_peering_connection_id = aws_vpc_peering_connection.primary_to_secondary[0].id
  auto_accept               = true

  tags = merge(local.common_tags, {
    Name = "mortgage-crm-cross-region-peering"
  })
}

# RDS Aurora Global Database
resource "aws_rds_global_cluster" "mortgage_crm" {
  count = var.enable_multi_region ? 1 : 0

  provider                  = aws.primary
  global_cluster_identifier = "mortgage-crm-global-${var.environment}"
  engine                    = "aurora-postgresql"
  engine_version            = "15.4"
  database_name             = "mortgage_crm"
  storage_encrypted         = true
}

# Primary Aurora Cluster
module "aurora_primary" {
  source = "../modules/aurora"

  providers = {
    aws = aws.primary
  }

  cluster_identifier = "mortgage-crm-${var.environment}-primary"
  engine             = "aurora-postgresql"
  engine_version     = "15.4"

  global_cluster_identifier = var.enable_multi_region ? aws_rds_global_cluster.mortgage_crm[0].id : null

  instance_class = var.db_instance_class
  instances      = 3

  vpc_id     = module.vpc_primary.vpc_id
  subnet_ids = module.vpc_primary.private_subnet_ids

  master_username = "mortgage_admin"
  database_name   = "mortgage_crm"

  backup_retention_period = 35
  preferred_backup_window = "03:00-04:00"

  enabled_cloudwatch_logs_exports = ["postgresql"]

  tags = merge(local.common_tags, {
    Region = "primary"
    Role   = "writer"
  })
}

# Secondary Aurora Cluster (Read Replica)
module "aurora_secondary" {
  count  = var.enable_multi_region ? 1 : 0
  source = "../modules/aurora"

  providers = {
    aws = aws.secondary
  }

  cluster_identifier = "mortgage-crm-${var.environment}-secondary"
  engine             = "aurora-postgresql"
  engine_version     = "15.4"

  global_cluster_identifier = aws_rds_global_cluster.mortgage_crm[0].id
  source_region             = var.primary_region

  instance_class = var.db_instance_class
  instances      = 2

  vpc_id     = module.vpc_secondary[0].vpc_id
  subnet_ids = module.vpc_secondary[0].private_subnet_ids

  # Secondary doesn't need master credentials
  skip_master_credentials = true

  tags = merge(local.common_tags, {
    Region = "secondary"
    Role   = "reader"
  })

  depends_on = [module.aurora_primary]
}

# ElastiCache Global Datastore (Redis)
resource "aws_elasticache_global_replication_group" "mortgage_crm" {
  count = var.enable_multi_region ? 1 : 0

  provider                           = aws.primary
  global_replication_group_id_suffix = "mortgage-crm-${var.environment}"
  primary_replication_group_id       = module.redis_primary.replication_group_id

  global_replication_group_description = "Mortgage CRM Global Redis"
}

# Primary Redis Cluster
module "redis_primary" {
  source = "../modules/elasticache"

  providers = {
    aws = aws.primary
  }

  cluster_id         = "mortgage-crm-${var.environment}-primary"
  engine             = "redis"
  engine_version     = "7.0"
  node_type          = "cache.r6g.large"
  num_cache_clusters = 3

  vpc_id     = module.vpc_primary.vpc_id
  subnet_ids = module.vpc_primary.private_subnet_ids

  automatic_failover_enabled = true
  multi_az_enabled           = true
  at_rest_encryption_enabled = true
  transit_encryption_enabled = true

  tags = merge(local.common_tags, {
    Region = "primary"
  })
}

# Secondary Redis Cluster
module "redis_secondary" {
  count  = var.enable_multi_region ? 1 : 0
  source = "../modules/elasticache"

  providers = {
    aws = aws.secondary
  }

  cluster_id                   = "mortgage-crm-${var.environment}-secondary"
  global_replication_group_id  = aws_elasticache_global_replication_group.mortgage_crm[0].global_replication_group_id

  engine             = "redis"
  node_type          = "cache.r6g.large"
  num_cache_clusters = 2

  vpc_id     = module.vpc_secondary[0].vpc_id
  subnet_ids = module.vpc_secondary[0].private_subnet_ids

  tags = merge(local.common_tags, {
    Region = "secondary"
  })

  depends_on = [aws_elasticache_global_replication_group.mortgage_crm]
}

# EKS Cluster - Primary Region
module "eks_primary" {
  source = "../modules/eks"

  providers = {
    aws = aws.primary
  }

  cluster_name    = "mortgage-crm-${var.environment}-primary"
  cluster_version = "1.28"

  vpc_id     = module.vpc_primary.vpc_id
  subnet_ids = module.vpc_primary.private_subnet_ids

  node_groups = {
    application = {
      desired_capacity = 3
      min_capacity     = 2
      max_capacity     = 10
      instance_types   = ["m6i.xlarge"]

      labels = {
        workload = "application"
      }
    }

    system = {
      desired_capacity = 2
      min_capacity     = 2
      max_capacity     = 4
      instance_types   = ["m6i.large"]

      labels = {
        workload = "system"
      }

      taints = [{
        key    = "CriticalAddonsOnly"
        value  = "true"
        effect = "NO_SCHEDULE"
      }]
    }
  }

  enable_cluster_autoscaler = true

  tags = merge(local.common_tags, {
    Region = "primary"
  })
}

# EKS Cluster - Secondary Region
module "eks_secondary" {
  count  = var.enable_multi_region ? 1 : 0
  source = "../modules/eks"

  providers = {
    aws = aws.secondary
  }

  cluster_name    = "mortgage-crm-${var.environment}-secondary"
  cluster_version = "1.28"

  vpc_id     = module.vpc_secondary[0].vpc_id
  subnet_ids = module.vpc_secondary[0].private_subnet_ids

  node_groups = {
    application = {
      desired_capacity = 2
      min_capacity     = 1
      max_capacity     = 8
      instance_types   = ["m6i.xlarge"]

      labels = {
        workload = "application"
      }
    }

    system = {
      desired_capacity = 2
      min_capacity     = 2
      max_capacity     = 3
      instance_types   = ["m6i.large"]

      labels = {
        workload = "system"
      }
    }
  }

  enable_cluster_autoscaler = true

  tags = merge(local.common_tags, {
    Region = "secondary"
  })
}

# Route53 Health Checks and Failover
resource "aws_route53_health_check" "primary" {
  fqdn              = "api-primary.mortgagecrm.com"
  port              = 443
  type              = "HTTPS"
  resource_path     = "/api/v1/enterprise/health"
  failure_threshold = "3"
  request_interval  = "10"

  tags = merge(local.common_tags, {
    Name = "primary-health-check"
  })
}

resource "aws_route53_health_check" "secondary" {
  count = var.enable_multi_region ? 1 : 0

  fqdn              = "api-secondary.mortgagecrm.com"
  port              = 443
  type              = "HTTPS"
  resource_path     = "/api/v1/enterprise/health"
  failure_threshold = "3"
  request_interval  = "10"

  tags = merge(local.common_tags, {
    Name = "secondary-health-check"
  })
}

# Route53 Failover Records
resource "aws_route53_record" "api_primary" {
  zone_id = data.aws_route53_zone.main.zone_id
  name    = "api.mortgagecrm.com"
  type    = "A"

  failover_routing_policy {
    type = "PRIMARY"
  }

  set_identifier  = "primary"
  health_check_id = aws_route53_health_check.primary.id

  alias {
    name                   = module.eks_primary.alb_dns_name
    zone_id                = module.eks_primary.alb_zone_id
    evaluate_target_health = true
  }
}

resource "aws_route53_record" "api_secondary" {
  count = var.enable_multi_region ? 1 : 0

  zone_id = data.aws_route53_zone.main.zone_id
  name    = "api.mortgagecrm.com"
  type    = "A"

  failover_routing_policy {
    type = "SECONDARY"
  }

  set_identifier  = "secondary"
  health_check_id = aws_route53_health_check.secondary[0].id

  alias {
    name                   = module.eks_secondary[0].alb_dns_name
    zone_id                = module.eks_secondary[0].alb_zone_id
    evaluate_target_health = true
  }
}

# S3 Cross-Region Replication for documents/assets
resource "aws_s3_bucket" "documents_primary" {
  provider = aws.primary
  bucket   = "mortgage-crm-documents-${var.environment}-primary"

  tags = merge(local.common_tags, {
    Region = "primary"
  })
}

resource "aws_s3_bucket_versioning" "documents_primary" {
  provider = aws.primary
  bucket   = aws_s3_bucket.documents_primary.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket" "documents_secondary" {
  count    = var.enable_multi_region ? 1 : 0
  provider = aws.secondary
  bucket   = "mortgage-crm-documents-${var.environment}-secondary"

  tags = merge(local.common_tags, {
    Region = "secondary"
  })
}

resource "aws_s3_bucket_versioning" "documents_secondary" {
  count    = var.enable_multi_region ? 1 : 0
  provider = aws.secondary
  bucket   = aws_s3_bucket.documents_secondary[0].id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_replication_configuration" "documents" {
  count = var.enable_multi_region ? 1 : 0

  provider   = aws.primary
  bucket     = aws_s3_bucket.documents_primary.id
  role       = aws_iam_role.replication.arn
  depends_on = [aws_s3_bucket_versioning.documents_primary]

  rule {
    id     = "replicate-documents"
    status = "Enabled"

    destination {
      bucket        = aws_s3_bucket.documents_secondary[0].arn
      storage_class = "STANDARD"

      encryption_configuration {
        replica_kms_key_id = aws_kms_key.secondary[0].arn
      }
    }

    source_selection_criteria {
      sse_kms_encrypted_objects {
        status = "Enabled"
      }
    }
  }
}

# KMS Keys for encryption
resource "aws_kms_key" "primary" {
  provider                = aws.primary
  description             = "Mortgage CRM encryption key - Primary"
  deletion_window_in_days = 30
  enable_key_rotation     = true
  multi_region            = true

  tags = merge(local.common_tags, {
    Region = "primary"
  })
}

resource "aws_kms_replica_key" "secondary" {
  count = var.enable_multi_region ? 1 : 0

  provider                = aws.secondary
  primary_key_arn         = aws_kms_key.primary.arn
  description             = "Mortgage CRM encryption key - Secondary replica"
  deletion_window_in_days = 30

  tags = merge(local.common_tags, {
    Region = "secondary"
  })
}

resource "aws_kms_key" "secondary" {
  count = var.enable_multi_region ? 1 : 0

  provider                = aws.secondary
  description             = "Mortgage CRM S3 replication key - Secondary"
  deletion_window_in_days = 30
  enable_key_rotation     = true

  tags = merge(local.common_tags, {
    Region = "secondary"
  })
}

# IAM Role for S3 replication
resource "aws_iam_role" "replication" {
  name = "mortgage-crm-s3-replication-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "s3.amazonaws.com"
      }
    }]
  })

  tags = local.common_tags
}

# Data sources
data "aws_route53_zone" "main" {
  provider     = aws.primary
  name         = "mortgagecrm.com"
  private_zone = false
}

# Outputs
output "primary_vpc_id" {
  description = "Primary VPC ID"
  value       = module.vpc_primary.vpc_id
}

output "secondary_vpc_id" {
  description = "Secondary VPC ID"
  value       = var.enable_multi_region ? module.vpc_secondary[0].vpc_id : null
}

output "primary_eks_cluster_endpoint" {
  description = "Primary EKS cluster endpoint"
  value       = module.eks_primary.cluster_endpoint
}

output "secondary_eks_cluster_endpoint" {
  description = "Secondary EKS cluster endpoint"
  value       = var.enable_multi_region ? module.eks_secondary[0].cluster_endpoint : null
}

output "global_database_endpoint" {
  description = "Global database writer endpoint"
  value       = module.aurora_primary.cluster_endpoint
}

output "global_database_reader_endpoint" {
  description = "Global database reader endpoint"
  value       = module.aurora_primary.reader_endpoint
}
