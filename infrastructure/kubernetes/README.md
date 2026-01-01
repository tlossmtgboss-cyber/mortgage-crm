# Kubernetes Deployment Configurations for Mortgage CRM

This directory contains Kubernetes manifests for deploying the mortgage CRM
in a production-ready, enterprise-grade configuration.

## Directory Structure

```
kubernetes/
├── base/                    # Base configurations
│   ├── namespace.yaml
│   ├── configmap.yaml
│   ├── secrets.yaml
│   └── rbac.yaml
├── apps/                    # Application deployments
│   ├── api/
│   ├── frontend/
│   ├── worker/
│   └── ai-orchestrator/
├── infrastructure/          # Infrastructure components
│   ├── postgres/
│   ├── redis/
│   ├── rabbitmq/
│   └── monitoring/
├── networking/              # Network configurations
│   ├── ingress.yaml
│   ├── services.yaml
│   └── network-policies.yaml
├── autoscaling/            # HPA and VPA configs
│   ├── hpa.yaml
│   └── vpa.yaml
└── overlays/               # Environment-specific overlays
    ├── development/
    ├── staging/
    └── production/
```

## Quick Start

```bash
# Create namespace
kubectl apply -f base/namespace.yaml

# Apply base configurations
kubectl apply -k base/

# Deploy to production
kubectl apply -k overlays/production/
```

## Prerequisites

- Kubernetes 1.25+
- kubectl configured
- Helm 3.x (for some components)
- cert-manager (for TLS)
- External Secrets Operator (optional)
