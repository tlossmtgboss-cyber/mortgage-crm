"""
API Developer Experience Routes
================================

Enterprise Readiness Domain 11: API Gateway & Developer Experience.

Provides:
- API changelog with structured versioning
- SDK client stubs (Python + JavaScript)
- Postman/Insomnia collection export
- Sandbox environment documentation
- Webhook event catalog with payload schemas
- Code examples for common operations
"""

import json
import logging
from datetime import datetime
from fastapi import Depends, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


def register_api_developer_routes(app, get_db, get_current_user):
    """Register API developer experience routes."""

    # =========================================================================
    # API CHANGELOG (Domain 11, Check 11.10)
    # =========================================================================
    @app.get("/api/v1/developer/changelog", tags=["Developer"])
    async def get_api_changelog():
        """
        Structured API changelog with versioning, breaking changes,
        and migration guides.
        """
        changelog = [
            {
                "version": "1.7.0",
                "date": "2026-02-21",
                "type": "minor",
                "changes": [
                    {
                        "category": "feature",
                        "description": "Added scheduled report delivery with PDF/Excel/CSV export",
                        "endpoints": ["POST /api/v1/reports/schedule", "GET /api/v1/reports/schedules"],
                        "breaking": False,
                    },
                    {
                        "category": "feature",
                        "description": "Performance monitoring endpoints for token usage, AI capacity, deadlocks",
                        "endpoints": [
                            "GET /api/v1/monitoring/performance",
                            "GET /api/v1/monitoring/token-usage",
                            "GET /api/v1/monitoring/ai-capacity",
                        ],
                        "breaking": False,
                    },
                    {
                        "category": "feature",
                        "description": "API developer portal with SDK stubs, Postman collection, webhook catalog",
                        "endpoints": ["GET /api/v1/developer/*"],
                        "breaking": False,
                    },
                ],
            },
            {
                "version": "1.6.0",
                "date": "2026-02-20",
                "type": "minor",
                "changes": [
                    {
                        "category": "feature",
                        "description": "Multi-tenant hardening: storage quotas, tenant performance monitoring, AI isolation",
                        "endpoints": [
                            "GET /api/v1/admin/storage-quotas",
                            "GET /api/v1/admin/tenant-performance",
                        ],
                        "breaking": False,
                    },
                    {
                        "category": "feature",
                        "description": "Billing admin routes with Stripe integration",
                        "endpoints": ["GET /api/v1/admin/billing/*"],
                        "breaking": False,
                    },
                    {
                        "category": "enhancement",
                        "description": "SSE notification routes for real-time event streaming",
                        "endpoints": ["GET /api/v1/notifications/stream"],
                        "breaking": False,
                    },
                ],
            },
            {
                "version": "1.5.0",
                "date": "2026-02-18",
                "type": "minor",
                "changes": [
                    {
                        "category": "feature",
                        "description": "Salesforce smart sync with status-based routing to CRM tables",
                        "endpoints": ["POST /api/v1/salesforce/sync"],
                        "breaking": False,
                    },
                    {
                        "category": "fix",
                        "description": "Fixed login 500 error from missing enterprise security columns",
                        "endpoints": ["POST /api/v1/auth/login"],
                        "breaking": False,
                    },
                ],
            },
            {
                "version": "1.4.0",
                "date": "2026-02-15",
                "type": "minor",
                "changes": [
                    {
                        "category": "feature",
                        "description": "Call intelligence platform with 6 AI agents and artifact pipeline",
                        "endpoints": [
                            "POST /api/v1/call-intelligence/process",
                            "GET /api/v1/call-intelligence/sessions",
                        ],
                        "breaking": False,
                    },
                    {
                        "category": "feature",
                        "description": "Power dialer with click-to-call, DNC enforcement, and caller ID verification",
                        "endpoints": ["POST /api/v1/dialer/sessions", "POST /api/v1/click-to-call"],
                        "breaking": False,
                    },
                ],
            },
            {
                "version": "1.3.0",
                "date": "2026-02-10",
                "type": "minor",
                "changes": [
                    {
                        "category": "feature",
                        "description": "SCIM 2.0 user provisioning (RFC 7644 compliant)",
                        "endpoints": [
                            "GET /scim/v2/Users",
                            "POST /scim/v2/Users",
                            "PATCH /scim/v2/Users/{id}",
                        ],
                        "breaking": False,
                    },
                    {
                        "category": "feature",
                        "description": "Video personalization engine (VideoOS)",
                        "endpoints": ["POST /api/v1/video/render"],
                        "breaking": False,
                    },
                ],
            },
            {
                "version": "1.2.0",
                "date": "2026-02-01",
                "type": "minor",
                "changes": [
                    {
                        "category": "feature",
                        "description": "White-label branding with custom colors, logos, and email templates",
                        "endpoints": ["GET /api/v1/company/branding", "PUT /api/v1/company/branding"],
                        "breaking": False,
                    },
                ],
            },
            {
                "version": "1.1.0",
                "date": "2026-01-15",
                "type": "minor",
                "changes": [
                    {
                        "category": "feature",
                        "description": "Data import with CSV preview, validation, rollback, and field mapping templates",
                        "endpoints": [
                            "POST /api/v1/imports/preview",
                            "POST /api/v1/imports/execute",
                            "POST /api/v1/imports/{id}/rollback",
                        ],
                        "breaking": False,
                    },
                ],
            },
            {
                "version": "1.0.0",
                "date": "2025-12-01",
                "type": "major",
                "changes": [
                    {
                        "category": "release",
                        "description": "Initial release: CRM, pipeline management, SLA tracking, AI agents",
                        "endpoints": ["/api/v1/*"],
                        "breaking": False,
                        "migration_guide": "Initial release — no migration required.",
                    },
                ],
            },
        ]

        return {
            "api_version": "1.7.0",
            "changelog": changelog,
            "total_versions": len(changelog),
        }

    # =========================================================================
    # SDK CLIENT STUBS (Domain 11, Check 11.11)
    # =========================================================================
    @app.get("/api/v1/developer/sdk/python", tags=["Developer"])
    async def get_python_sdk():
        """Python SDK client stub with installation instructions and examples."""
        sdk_code = '''"""
Perennia AI Python SDK
======================

Installation:
    pip install perennia-ai

Quick Start:
    from perennia import PerenniaClient
    client = PerenniaClient(api_key="your-api-key", base_url="https://api.perenniaai.com")

    # Get pipeline metrics
    metrics = client.pipeline.get_metrics()

    # Search leads
    leads = client.leads.search(query="John", status="new")

    # Create a lead
    lead = client.leads.create(first_name="Jane", last_name="Doe", email="jane@example.com")
"""

import httpx
from typing import Any, Dict, List, Optional
from dataclasses import dataclass


@dataclass
class PerenniaConfig:
    api_key: str
    base_url: str = "https://api.perenniaai.com"
    timeout: float = 30.0
    api_version: str = "v1"


class PerenniaClient:
    """Perennia AI API Client."""

    def __init__(self, api_key: str, base_url: str = "https://api.perenniaai.com", timeout: float = 30.0):
        self.config = PerenniaConfig(api_key=api_key, base_url=base_url, timeout=timeout)
        self._client = httpx.Client(
            base_url=f"{base_url}/api/{self.config.api_version}",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            timeout=timeout,
        )
        self.leads = LeadsAPI(self._client)
        self.loans = LoansAPI(self._client)
        self.pipeline = PipelineAPI(self._client)
        self.contacts = ContactsAPI(self._client)
        self.reports = ReportsAPI(self._client)

    def close(self):
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class _BaseAPI:
    def __init__(self, client: httpx.Client):
        self._client = client

    def _get(self, path: str, params: Dict = None) -> Dict:
        resp = self._client.get(path, params=params)
        resp.raise_for_status()
        return resp.json()

    def _post(self, path: str, data: Dict = None) -> Dict:
        resp = self._client.post(path, json=data)
        resp.raise_for_status()
        return resp.json()

    def _put(self, path: str, data: Dict = None) -> Dict:
        resp = self._client.put(path, json=data)
        resp.raise_for_status()
        return resp.json()

    def _delete(self, path: str) -> Dict:
        resp = self._client.delete(path)
        resp.raise_for_status()
        return resp.json()


class LeadsAPI(_BaseAPI):
    def list(self, status: str = None, limit: int = 50) -> List[Dict]:
        return self._get("/leads/", params={"status": status, "limit": limit})

    def get(self, lead_id: int) -> Dict:
        return self._get(f"/leads/{lead_id}")

    def create(self, **kwargs) -> Dict:
        return self._post("/leads/", data=kwargs)

    def update(self, lead_id: int, **kwargs) -> Dict:
        return self._put(f"/leads/{lead_id}", data=kwargs)

    def search(self, query: str, status: str = None) -> List[Dict]:
        return self._get("/leads/search", params={"q": query, "status": status})


class LoansAPI(_BaseAPI):
    def list(self, status: str = None, limit: int = 50) -> List[Dict]:
        return self._get("/loans", params={"status": status, "limit": limit})

    def get(self, loan_id: int) -> Dict:
        return self._get(f"/loans/{loan_id}")


class PipelineAPI(_BaseAPI):
    def get_metrics(self, days: int = 30) -> Dict:
        return self._get("/pipeline/metrics", params={"days": days})


class ContactsAPI(_BaseAPI):
    def list(self, limit: int = 50) -> List[Dict]:
        return self._get("/contacts", params={"limit": limit})

    def get(self, contact_id: int) -> Dict:
        return self._get(f"/contacts/{contact_id}")

    def create(self, **kwargs) -> Dict:
        return self._post("/contacts", data=kwargs)


class ReportsAPI(_BaseAPI):
    def sla_compliance(self, format: str = "json") -> Dict:
        return self._get("/reports/sla-compliance", params={"format": format})

    def export_pdf(self, report_type: str, data: Dict) -> bytes:
        resp = self._client.post("/reports/export/pdf", json={"report_type": report_type, "data": data})
        resp.raise_for_status()
        return resp.content

    def export_excel(self, report_type: str, data: Dict) -> bytes:
        resp = self._client.post("/reports/export/excel", json={"report_type": report_type, "data": data})
        resp.raise_for_status()
        return resp.content
'''

        return {
            "language": "python",
            "package_name": "perennia-ai",
            "install_command": "pip install perennia-ai",
            "source_code": sdk_code,
            "requirements": ["httpx>=0.25.0"],
            "supported_python": ">=3.9",
        }

    @app.get("/api/v1/developer/sdk/javascript", tags=["Developer"])
    async def get_javascript_sdk():
        """JavaScript/TypeScript SDK client stub."""
        sdk_code = '''/**
 * Perennia AI JavaScript SDK
 *
 * Installation:
 *   npm install @perennia/sdk
 *
 * Quick Start:
 *   import { PerenniaClient } from '@perennia/sdk';
 *   const client = new PerenniaClient({ apiKey: 'your-api-key' });
 *   const leads = await client.leads.list();
 */

export interface PerenniaConfig {
  apiKey: string;
  baseUrl?: string;
  timeout?: number;
}

export class PerenniaClient {
  private config: PerenniaConfig;
  public leads: LeadsAPI;
  public loans: LoansAPI;
  public pipeline: PipelineAPI;
  public contacts: ContactsAPI;
  public reports: ReportsAPI;

  constructor(config: PerenniaConfig) {
    this.config = {
      baseUrl: 'https://api.perenniaai.com',
      timeout: 30000,
      ...config,
    };
    const base = `${this.config.baseUrl}/api/v1`;
    const headers = {
      'Authorization': `Bearer ${this.config.apiKey}`,
      'Content-Type': 'application/json',
    };
    this.leads = new LeadsAPI(base, headers, this.config.timeout!);
    this.loans = new LoansAPI(base, headers, this.config.timeout!);
    this.pipeline = new PipelineAPI(base, headers, this.config.timeout!);
    this.contacts = new ContactsAPI(base, headers, this.config.timeout!);
    this.reports = new ReportsAPI(base, headers, this.config.timeout!);
  }
}

class BaseAPI {
  constructor(
    protected base: string,
    protected headers: Record<string, string>,
    protected timeout: number,
  ) {}

  protected async get<T>(path: string, params?: Record<string, any>): Promise<T> {
    const url = new URL(`${this.base}${path}`);
    if (params) Object.entries(params).forEach(([k, v]) => v != null && url.searchParams.set(k, String(v)));
    const resp = await fetch(url.toString(), { headers: this.headers, signal: AbortSignal.timeout(this.timeout) });
    if (!resp.ok) throw new Error(`API error: ${resp.status} ${resp.statusText}`);
    return resp.json();
  }

  protected async post<T>(path: string, body?: any): Promise<T> {
    const resp = await fetch(`${this.base}${path}`, {
      method: 'POST', headers: this.headers, body: JSON.stringify(body),
      signal: AbortSignal.timeout(this.timeout),
    });
    if (!resp.ok) throw new Error(`API error: ${resp.status} ${resp.statusText}`);
    return resp.json();
  }
}

class LeadsAPI extends BaseAPI {
  list(params?: { status?: string; limit?: number }) { return this.get('/leads/', params); }
  get(id: number) { return this.get(`/leads/${id}`); }
  create(data: any) { return this.post('/leads/', data); }
  search(query: string, status?: string) { return this.get('/leads/search', { q: query, status }); }
}

class LoansAPI extends BaseAPI {
  list(params?: { status?: string }) { return this.get('/loans', params); }
  get(id: number) { return this.get(`/loans/${id}`); }
}

class PipelineAPI extends BaseAPI {
  getMetrics(days = 30) { return this.get('/pipeline/metrics', { days }); }
}

class ContactsAPI extends BaseAPI {
  list(limit = 50) { return this.get('/contacts', { limit }); }
  get(id: number) { return this.get(`/contacts/${id}`); }
  create(data: any) { return this.post('/contacts', data); }
}

class ReportsAPI extends BaseAPI {
  slaCompliance(format = 'json') { return this.get('/reports/sla-compliance', { format }); }
  exportPdf(reportType: string, data: any) { return this.post('/reports/export/pdf', { report_type: reportType, data }); }
  exportExcel(reportType: string, data: any) { return this.post('/reports/export/excel', { report_type: reportType, data }); }
}

export default PerenniaClient;
'''
        return {
            "language": "javascript",
            "package_name": "@perennia/sdk",
            "install_command": "npm install @perennia/sdk",
            "source_code": sdk_code,
            "requirements": ["Node.js >= 18 (native fetch)"],
            "typescript": True,
        }

    # =========================================================================
    # POSTMAN COLLECTION (Domain 11, Check 11.12)
    # =========================================================================
    @app.get("/api/v1/developer/postman-collection", tags=["Developer"])
    async def get_postman_collection():
        """
        Postman/Insomnia collection with all endpoints,
        authentication pre-configured, and example payloads.
        """
        collection = {
            "info": {
                "name": "Perennia AI API",
                "_postman_id": "perennia-ai-api-v1",
                "description": "Complete API collection for Perennia AI Mortgage CRM",
                "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
                "version": "1.7.0",
            },
            "auth": {
                "type": "bearer",
                "bearer": [{"key": "token", "value": "{{api_token}}", "type": "string"}],
            },
            "variable": [
                {"key": "base_url", "value": "https://api.perenniaai.com", "type": "string"},
                {"key": "api_token", "value": "", "type": "string"},
            ],
            "item": [
                {
                    "name": "Authentication",
                    "item": [
                        {
                            "name": "Login",
                            "request": {
                                "method": "POST",
                                "url": "{{base_url}}/api/v1/auth/login",
                                "header": [{"key": "Content-Type", "value": "application/json"}],
                                "body": {
                                    "mode": "raw",
                                    "raw": json.dumps({"email": "user@example.com", "password": "your-password"}),
                                },
                            },
                        },
                        {
                            "name": "Refresh Token",
                            "request": {
                                "method": "POST",
                                "url": "{{base_url}}/api/v1/auth/refresh",
                                "header": [{"key": "Content-Type", "value": "application/json"}],
                                "body": {"mode": "raw", "raw": json.dumps({"refresh_token": "{{refresh_token}}"})},
                            },
                        },
                    ],
                },
                {
                    "name": "Leads",
                    "item": [
                        {
                            "name": "List Leads",
                            "request": {"method": "GET", "url": "{{base_url}}/api/v1/leads/?limit=50"},
                        },
                        {
                            "name": "Create Lead",
                            "request": {
                                "method": "POST",
                                "url": "{{base_url}}/api/v1/leads/",
                                "body": {
                                    "mode": "raw",
                                    "raw": json.dumps({
                                        "first_name": "Jane",
                                        "last_name": "Doe",
                                        "email": "jane@example.com",
                                        "phone": "+15551234567",
                                        "source": "website",
                                    }),
                                },
                            },
                        },
                        {
                            "name": "Search Leads",
                            "request": {"method": "GET", "url": "{{base_url}}/api/v1/leads/search?q=Jane"},
                        },
                    ],
                },
                {
                    "name": "Pipeline",
                    "item": [
                        {
                            "name": "Get Pipeline Metrics",
                            "request": {"method": "GET", "url": "{{base_url}}/api/v1/pipeline/metrics?days=30"},
                        },
                        {
                            "name": "Get Loans by Status",
                            "request": {"method": "GET", "url": "{{base_url}}/api/v1/loans?status=processing"},
                        },
                    ],
                },
                {
                    "name": "Reports",
                    "item": [
                        {
                            "name": "SLA Compliance Report",
                            "request": {"method": "GET", "url": "{{base_url}}/api/v1/reports/sla-compliance"},
                        },
                        {
                            "name": "Export PDF",
                            "request": {
                                "method": "POST",
                                "url": "{{base_url}}/api/v1/reports/export/pdf",
                                "body": {
                                    "mode": "raw",
                                    "raw": json.dumps({"report_type": "pipeline", "title": "Pipeline Report"}),
                                },
                            },
                        },
                        {
                            "name": "Schedule Report",
                            "request": {
                                "method": "POST",
                                "url": "{{base_url}}/api/v1/reports/schedule",
                                "body": {
                                    "mode": "raw",
                                    "raw": json.dumps({
                                        "report_type": "sla_compliance",
                                        "export_format": "pdf",
                                        "frequency": "weekly",
                                        "recipients": ["admin@company.com"],
                                        "hour_utc": 8,
                                        "day_of_week": 1,
                                    }),
                                },
                            },
                        },
                    ],
                },
                {
                    "name": "Data Import",
                    "item": [
                        {
                            "name": "Preview Import",
                            "request": {
                                "method": "POST",
                                "url": "{{base_url}}/api/v1/imports/preview",
                                "body": {"mode": "formdata", "formdata": [{"key": "file", "type": "file"}]},
                            },
                        },
                        {
                            "name": "Execute Import",
                            "request": {
                                "method": "POST",
                                "url": "{{base_url}}/api/v1/imports/execute",
                                "body": {
                                    "mode": "raw",
                                    "raw": json.dumps({"import_id": "abc123", "field_mapping": {}}),
                                },
                            },
                        },
                        {
                            "name": "Rollback Import",
                            "request": {
                                "method": "POST",
                                "url": "{{base_url}}/api/v1/imports/abc123/rollback",
                            },
                        },
                    ],
                },
                {
                    "name": "Monitoring",
                    "item": [
                        {
                            "name": "Performance Report",
                            "request": {"method": "GET", "url": "{{base_url}}/api/v1/monitoring/performance"},
                        },
                        {
                            "name": "Token Usage",
                            "request": {"method": "GET", "url": "{{base_url}}/api/v1/monitoring/token-usage"},
                        },
                        {
                            "name": "AI Capacity",
                            "request": {"method": "GET", "url": "{{base_url}}/api/v1/monitoring/ai-capacity"},
                        },
                    ],
                },
                {
                    "name": "SCIM Provisioning",
                    "item": [
                        {
                            "name": "List Users (SCIM)",
                            "request": {"method": "GET", "url": "{{base_url}}/scim/v2/Users"},
                        },
                        {
                            "name": "Create User (SCIM)",
                            "request": {
                                "method": "POST",
                                "url": "{{base_url}}/scim/v2/Users",
                                "body": {
                                    "mode": "raw",
                                    "raw": json.dumps({
                                        "schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"],
                                        "userName": "jdoe@company.com",
                                        "name": {"givenName": "Jane", "familyName": "Doe"},
                                        "emails": [{"value": "jdoe@company.com", "primary": True}],
                                        "active": True,
                                    }),
                                },
                            },
                        },
                    ],
                },
            ],
        }

        return JSONResponse(
            content=collection,
            headers={"Content-Disposition": "attachment; filename=perennia-ai-api.postman_collection.json"},
        )

    # =========================================================================
    # SANDBOX ENVIRONMENT (Domain 11, Check 11.9)
    # =========================================================================
    @app.get("/api/v1/developer/sandbox", tags=["Developer"])
    async def get_sandbox_info():
        """
        Sandbox environment details for testing and development.
        """
        return {
            "sandbox": {
                "base_url": "https://sandbox.api.perenniaai.com",
                "description": "Isolated sandbox environment with pre-loaded test data. "
                               "All operations are non-destructive and reset nightly.",
                "features": [
                    "Pre-loaded test data: 100 leads, 50 loans, 10 users",
                    "All API endpoints available",
                    "Test telephony providers (no real calls)",
                    "Isolated from production data",
                    "Resets nightly at 2 AM UTC",
                ],
                "authentication": {
                    "method": "API Key",
                    "header": "Authorization: Bearer <sandbox-api-key>",
                    "how_to_get_key": "Request via admin panel: Settings > Developer > Sandbox API Key",
                },
                "test_credentials": {
                    "admin_email": "admin@sandbox.perenniaai.com",
                    "lo_email": "lo@sandbox.perenniaai.com",
                    "note": "Use 'POST /api/v1/auth/login' with sandbox credentials",
                },
                "limitations": [
                    "Rate limit: 100 requests/minute (vs 1000 in production)",
                    "Max 500 records per entity type",
                    "Emails are captured but not delivered",
                    "Telephony calls are simulated",
                    "File uploads limited to 5MB",
                ],
            },
        }

    # =========================================================================
    # WEBHOOK EVENT CATALOG (Domain 11, Check 11.7)
    # =========================================================================
    @app.get("/api/v1/developer/webhooks/catalog", tags=["Developer"])
    async def get_webhook_catalog():
        """
        Complete webhook event catalog with payload schemas
        and retry configuration.
        """
        return {
            "webhook_config": {
                "retry_policy": {
                    "max_retries": 5,
                    "backoff": "exponential",
                    "intervals": ["30s", "2m", "10m", "1h", "4h"],
                    "timeout": "10s per attempt",
                    "on_max_retries": "Alert admin, mark as failed",
                },
                "delivery": {
                    "method": "POST",
                    "content_type": "application/json",
                    "signature_header": "X-Perennia-Signature",
                    "signature_algorithm": "HMAC-SHA256",
                    "timestamp_header": "X-Perennia-Timestamp",
                },
                "management": {
                    "register": "POST /api/v1/webhooks",
                    "list": "GET /api/v1/webhooks",
                    "delete": "DELETE /api/v1/webhooks/{id}",
                    "test": "POST /api/v1/webhooks/{id}/test",
                    "logs": "GET /api/v1/webhooks/{id}/logs",
                },
            },
            "events": [
                {
                    "event": "lead.created",
                    "description": "New lead created",
                    "payload": {"id": "int", "first_name": "str", "last_name": "str", "email": "str", "source": "str", "created_at": "ISO-8601"},
                },
                {
                    "event": "lead.updated",
                    "description": "Lead data changed",
                    "payload": {"id": "int", "changed_fields": "dict", "updated_at": "ISO-8601"},
                },
                {
                    "event": "lead.status_changed",
                    "description": "Lead status transitioned",
                    "payload": {"id": "int", "old_status": "str", "new_status": "str", "changed_at": "ISO-8601"},
                },
                {
                    "event": "lead.converted",
                    "description": "Lead converted to loan application",
                    "payload": {"lead_id": "int", "loan_id": "int", "converted_at": "ISO-8601"},
                },
                {
                    "event": "loan.created",
                    "description": "New loan file created",
                    "payload": {"id": "int", "loan_number": "str", "borrower_name": "str", "loan_amount": "float"},
                },
                {
                    "event": "loan.status_changed",
                    "description": "Loan moved to new pipeline stage",
                    "payload": {"id": "int", "old_status": "str", "new_status": "str", "loan_number": "str"},
                },
                {
                    "event": "loan.funded",
                    "description": "Loan funded and closed",
                    "payload": {"id": "int", "loan_number": "str", "funded_amount": "float", "funded_at": "ISO-8601"},
                },
                {
                    "event": "loan.milestone_reached",
                    "description": "SLA milestone completed",
                    "payload": {"loan_id": "int", "milestone": "str", "completed_at": "ISO-8601", "was_on_time": "bool"},
                },
                {
                    "event": "document.uploaded",
                    "description": "Document uploaded to loan file",
                    "payload": {"loan_id": "int", "document_type": "str", "filename": "str", "uploaded_at": "ISO-8601"},
                },
                {
                    "event": "document.approved",
                    "description": "Document reviewed and approved",
                    "payload": {"loan_id": "int", "document_type": "str", "approved_by": "int", "approved_at": "ISO-8601"},
                },
                {
                    "event": "call.completed",
                    "description": "Call ended with summary available",
                    "payload": {"call_session_id": "str", "lead_id": "int", "duration_seconds": "int", "disposition": "str"},
                },
                {
                    "event": "call.transcript_ready",
                    "description": "Call transcript processed and available",
                    "payload": {"call_session_id": "str", "transcript_id": "str", "word_count": "int"},
                },
                {
                    "event": "task.created",
                    "description": "New task assigned",
                    "payload": {"id": "int", "title": "str", "assigned_to": "int", "due_date": "ISO-8601"},
                },
                {
                    "event": "task.completed",
                    "description": "Task marked complete",
                    "payload": {"id": "int", "title": "str", "completed_by": "int", "completed_at": "ISO-8601"},
                },
                {
                    "event": "sla.violation",
                    "description": "SLA deadline exceeded",
                    "payload": {"loan_id": "int", "milestone": "str", "days_overdue": "int", "severity": "str"},
                },
                {
                    "event": "sync.completed",
                    "description": "External sync cycle completed",
                    "payload": {"provider": "str", "records_synced": "int", "errors": "int", "duration_ms": "int"},
                },
                {
                    "event": "user.created",
                    "description": "New user provisioned",
                    "payload": {"id": "int", "email": "str", "role": "str", "method": "str"},
                },
            ],
            "total_events": 17,
        }

    # =========================================================================
    # WEBHOOK RETRY CONFIG (Domain 11, Check 11.8)
    # =========================================================================
    @app.get("/api/v1/developer/webhooks/retry-policy", tags=["Developer"])
    async def get_webhook_retry_policy():
        """Webhook retry policy with exponential backoff details."""
        return {
            "retry_policy": {
                "enabled": True,
                "max_retries": 5,
                "backoff_strategy": "exponential",
                "retry_intervals_seconds": [30, 120, 600, 3600, 14400],
                "retry_intervals_human": ["30 seconds", "2 minutes", "10 minutes", "1 hour", "4 hours"],
                "total_retry_window": "5 hours 42 minutes 30 seconds",
                "success_codes": [200, 201, 202, 204],
                "timeout_per_attempt_seconds": 10,
                "on_final_failure": {
                    "action": "disable_webhook",
                    "notification": "Admin notified via email and in-app alert",
                    "log": "Failed delivery logged with all attempt details",
                },
                "idempotency": {
                    "header": "X-Perennia-Delivery-ID",
                    "description": "Unique ID per delivery attempt. Use to deduplicate.",
                },
            },
        }

    # =========================================================================
    # CODE EXAMPLES (Domain 11, Check 11.3)
    # =========================================================================
    @app.get("/api/v1/developer/examples", tags=["Developer"])
    async def get_code_examples():
        """Code examples in Python, JavaScript, and cURL for top 10 operations."""
        return {
            "examples": [
                {
                    "operation": "Authenticate and get token",
                    "python": 'resp = httpx.post("https://api.perenniaai.com/api/v1/auth/login", json={"email": "user@co.com", "password": "pass"})\ntoken = resp.json()["access_token"]',
                    "javascript": 'const resp = await fetch("https://api.perenniaai.com/api/v1/auth/login", {\n  method: "POST", headers: {"Content-Type": "application/json"},\n  body: JSON.stringify({email: "user@co.com", password: "pass"})\n});\nconst { access_token } = await resp.json();',
                    "curl": 'curl -X POST https://api.perenniaai.com/api/v1/auth/login -H "Content-Type: application/json" -d \'{"email":"user@co.com","password":"pass"}\'',
                },
                {
                    "operation": "List leads with filter",
                    "python": 'leads = httpx.get("/api/v1/leads/", headers={"Authorization": f"Bearer {token}"}, params={"status": "new"}).json()',
                    "javascript": 'const leads = await fetch("/api/v1/leads/?status=new", {headers: {"Authorization": `Bearer ${token}`}}).then(r => r.json());',
                    "curl": 'curl -H "Authorization: Bearer $TOKEN" "https://api.perenniaai.com/api/v1/leads/?status=new"',
                },
                {
                    "operation": "Create a lead",
                    "python": 'lead = httpx.post("/api/v1/leads/", headers=auth, json={"first_name": "Jane", "last_name": "Doe", "email": "jane@example.com"}).json()',
                    "javascript": 'const lead = await fetch("/api/v1/leads/", {method: "POST", headers: {...auth, "Content-Type": "application/json"}, body: JSON.stringify({first_name: "Jane", last_name: "Doe", email: "jane@example.com"})}).then(r => r.json());',
                    "curl": 'curl -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d \'{"first_name":"Jane","last_name":"Doe","email":"jane@example.com"}\' https://api.perenniaai.com/api/v1/leads/',
                },
                {
                    "operation": "Get pipeline metrics",
                    "python": 'metrics = httpx.get("/api/v1/pipeline/metrics?days=30", headers=auth).json()',
                    "javascript": 'const metrics = await fetch("/api/v1/pipeline/metrics?days=30", {headers: auth}).then(r => r.json());',
                    "curl": 'curl -H "Authorization: Bearer $TOKEN" "https://api.perenniaai.com/api/v1/pipeline/metrics?days=30"',
                },
                {
                    "operation": "Export SLA compliance report as PDF",
                    "python": 'pdf = httpx.post("/api/v1/reports/export/pdf", headers=auth, json={"report_type": "sla_compliance"}).content\nwith open("report.pdf", "wb") as f: f.write(pdf)',
                    "javascript": 'const resp = await fetch("/api/v1/reports/export/pdf", {method: "POST", headers: {...auth, "Content-Type": "application/json"}, body: JSON.stringify({report_type: "sla_compliance"})});\nconst blob = await resp.blob();',
                    "curl": 'curl -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d \'{"report_type":"sla_compliance"}\' -o report.pdf https://api.perenniaai.com/api/v1/reports/export/pdf',
                },
                {
                    "operation": "Import leads from CSV",
                    "python": 'with open("leads.csv", "rb") as f:\n    preview = httpx.post("/api/v1/imports/preview", headers=auth, files={"file": f}).json()',
                    "javascript": 'const form = new FormData();\nform.append("file", fileInput.files[0]);\nconst preview = await fetch("/api/v1/imports/preview", {method: "POST", headers: auth, body: form}).then(r => r.json());',
                    "curl": 'curl -X POST -H "Authorization: Bearer $TOKEN" -F "file=@leads.csv" https://api.perenniaai.com/api/v1/imports/preview',
                },
                {
                    "operation": "Register a webhook",
                    "python": 'httpx.post("/api/v1/webhooks", headers=auth, json={"url": "https://your.app/webhook", "events": ["lead.created", "loan.funded"]})',
                    "javascript": 'await fetch("/api/v1/webhooks", {method: "POST", headers: {...auth, "Content-Type": "application/json"}, body: JSON.stringify({url: "https://your.app/webhook", events: ["lead.created", "loan.funded"]})});',
                    "curl": 'curl -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d \'{"url":"https://your.app/webhook","events":["lead.created","loan.funded"]}\' https://api.perenniaai.com/api/v1/webhooks',
                },
                {
                    "operation": "Provision user via SCIM",
                    "python": 'httpx.post("/scim/v2/Users", headers=auth, json={"schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"], "userName": "jdoe@co.com", "name": {"givenName": "Jane", "familyName": "Doe"}, "active": True})',
                    "javascript": 'await fetch("/scim/v2/Users", {method: "POST", headers: {...auth, "Content-Type": "application/json"}, body: JSON.stringify({schemas: ["urn:ietf:params:scim:schemas:core:2.0:User"], userName: "jdoe@co.com", name: {givenName: "Jane", familyName: "Doe"}, active: true})});',
                    "curl": 'curl -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d \'{"schemas":["urn:ietf:params:scim:schemas:core:2.0:User"],"userName":"jdoe@co.com","name":{"givenName":"Jane","familyName":"Doe"},"active":true}\' https://api.perenniaai.com/scim/v2/Users',
                },
                {
                    "operation": "Check system health",
                    "python": 'health = httpx.get("/health").json()',
                    "javascript": 'const health = await fetch("/health").then(r => r.json());',
                    "curl": 'curl https://api.perenniaai.com/health',
                },
                {
                    "operation": "Trigger Salesforce sync",
                    "python": 'result = httpx.post("/api/v1/salesforce/sync", headers=auth, json={"direction": "inbound"}).json()',
                    "javascript": 'const result = await fetch("/api/v1/salesforce/sync", {method: "POST", headers: {...auth, "Content-Type": "application/json"}, body: JSON.stringify({direction: "inbound"})}).then(r => r.json());',
                    "curl": 'curl -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d \'{"direction":"inbound"}\' https://api.perenniaai.com/api/v1/salesforce/sync',
                },
            ],
            "total_examples": 10,
            "languages": ["python", "javascript", "curl"],
        }

    # =========================================================================
    # API VERSIONING INFO (Domain 11, Check 11.6)
    # =========================================================================
    @app.get("/api/v1/developer/api-info", tags=["Developer"])
    async def get_api_info():
        """API versioning, deprecation policy, and rate limits."""
        return {
            "current_version": "v1",
            "supported_versions": ["v1"],
            "deprecation_policy": {
                "notice_period": "6 months before removal",
                "sunset_header": "Sunset: <date> — included on deprecated endpoints",
                "migration_guide": "Available at /api/v1/developer/changelog",
            },
            "rate_limits": {
                "default": "1000 requests/minute per API key",
                "auth_endpoints": "20 requests/minute per IP",
                "bulk_operations": "10 requests/minute per API key",
                "headers": {
                    "X-RateLimit-Limit": "Max requests in window",
                    "X-RateLimit-Remaining": "Remaining requests",
                    "X-RateLimit-Reset": "Window reset time (Unix timestamp)",
                    "Retry-After": "Seconds to wait (on 429)",
                },
            },
            "content_types": {
                "request": "application/json",
                "response": "application/json",
                "file_upload": "multipart/form-data",
                "file_download": "application/octet-stream, application/pdf, text/csv",
            },
        }

    logger.info(
        "Registered API developer routes: changelog, SDK stubs (Python+JS), "
        "Postman collection, sandbox, webhook catalog, code examples"
    )
