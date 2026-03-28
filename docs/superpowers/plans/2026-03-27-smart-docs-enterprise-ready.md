# Smart Docs Enterprise-Ready Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Surface the 88% of Smart Docs backend capabilities that have no frontend UI — analytics dashboards, review queue, bank analysis, income workflows, security/audit, and admin configuration — making Smart Docs a complete enterprise document management platform.

**Architecture:** The backend already has 290+ endpoints across 27 route files (22,135 LOC). This plan builds the **frontend layer** — new React pages, components, API service modules, and CSS — that connects to these existing endpoints. Each task produces a self-contained, testable feature. No backend changes needed.

**Tech Stack:** React 18 (CRA), CSS custom properties (project design system from `index.css`), fetch API, react-hot-toast, existing auth via `localStorage` token, existing permission system via `usePermissions()` hook.

---

## File Structure

### New Files (Create)

| File | Responsibility |
|------|---------------|
| `frontend/src/services/docAnalyticsApi.js` | API client for `/api/v1/smart-docs/doc-analytics/*` endpoints |
| `frontend/src/services/docReviewApi.js` | API client for `/api/v1/smart-docs/doc-review/*` endpoints |
| `frontend/src/services/docSecurityApi.js` | API client for `/api/v1/smart-docs/doc-security/*` endpoints |
| `frontend/src/services/docBankAnalysisApi.js` | API client for `/api/v1/smart-docs/bank-analysis/*` endpoints |
| `frontend/src/services/docIncomeApi.js` | API client for `/api/v1/smart-docs/income/*` endpoints |
| `frontend/src/pages/SmartDocsAnalytics.js` | Analytics dashboard page |
| `frontend/src/pages/SmartDocsAnalytics.css` | Analytics dashboard styles |
| `frontend/src/pages/SmartDocsReviewQueue.js` | Review queue page |
| `frontend/src/pages/SmartDocsReviewQueue.css` | Review queue styles |
| `frontend/src/pages/SmartDocsSecurity.js` | Security & audit page |
| `frontend/src/pages/SmartDocsSecurity.css` | Security & audit styles |
| `frontend/src/pages/SmartDocsBankAnalysis.js` | Bank analysis page |
| `frontend/src/pages/SmartDocsBankAnalysis.css` | Bank analysis styles |
| `frontend/src/pages/SmartDocsIncome.js` | Income calculation page |
| `frontend/src/pages/SmartDocsIncome.css` | Income calculation styles |
| `frontend/src/pages/SmartDocsAdmin.js` | Admin configuration page |
| `frontend/src/pages/SmartDocsAdmin.css` | Admin configuration styles |
| `frontend/src/components/smart-docs/AnalyticsCard.jsx` | Reusable metric card |
| `frontend/src/components/smart-docs/AnalyticsCard.css` | Metric card styles |
| `frontend/src/components/smart-docs/ReviewQueueItem.jsx` | Queue item row |
| `frontend/src/components/smart-docs/ReviewQueueItem.css` | Queue item styles |
| `frontend/src/components/smart-docs/DocumentTimeline.jsx` | Loan document timeline |
| `frontend/src/components/smart-docs/DocumentTimeline.css` | Timeline styles |
| `frontend/src/components/smart-docs/BankAnalysisPanel.jsx` | Bank analysis detail panel |
| `frontend/src/components/smart-docs/BankAnalysisPanel.css` | Bank analysis styles |
| `frontend/src/components/smart-docs/IncomeWorksheet.jsx` | Income calculation worksheet |
| `frontend/src/components/smart-docs/IncomeWorksheet.css` | Income worksheet styles |
| `frontend/src/hooks/useDocAnalytics.js` | Analytics data hook |
| `frontend/src/hooks/useReviewQueue.js` | Review queue state hook |

### Modified Files

| File | Change |
|------|--------|
| `frontend/src/App.js` | Add routes for 6 new pages |
| `frontend/src/components/smart-docs/index.js` | Export new components |
| `frontend/src/services/smartDocsApi.js` | Add missing API functions (bulk approval, version history) |

---

## Task 1: Analytics API Service

**Files:**
- Create: `frontend/src/services/docAnalyticsApi.js`
- Test: `frontend/src/services/__tests__/docAnalyticsApi.test.js`

- [ ] **Step 1: Write the failing test**

```javascript
// frontend/src/services/__tests__/docAnalyticsApi.test.js
import * as api from '../docAnalyticsApi';

// Mock fetch globally
beforeEach(() => {
  global.fetch = jest.fn();
  localStorage.setItem('token', 'test-token');
});

afterEach(() => {
  jest.restoreAllMocks();
  localStorage.clear();
});

function mockFetchOk(data) {
  global.fetch.mockResolvedValueOnce({
    ok: true,
    json: () => Promise.resolve(data),
  });
}

describe('docAnalyticsApi', () => {
  test('getDashboard calls correct endpoint with days param', async () => {
    mockFetchOk({ total_documents: 42 });
    const result = await api.getDashboard(30);
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/doc-analytics/dashboard?days=30'),
      expect.objectContaining({
        headers: expect.objectContaining({
          Authorization: 'Bearer test-token',
        }),
      })
    );
    expect(result.total_documents).toBe(42);
  });

  test('getPipelineCompleteness calls correct endpoint', async () => {
    mockFetchOk({ loans: [] });
    await api.getPipelineCompleteness();
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/doc-analytics/pipeline-completeness'),
      expect.anything()
    );
  });

  test('getSlaCompliance calls correct endpoint', async () => {
    mockFetchOk({ compliance_rate: 0.95 });
    await api.getSlaCompliance(60);
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/doc-analytics/sla-compliance?days=60'),
      expect.anything()
    );
  });

  test('getAiPerformance calls correct endpoint', async () => {
    mockFetchOk({ accuracy: 0.92 });
    await api.getAiPerformance();
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/doc-analytics/ai-performance'),
      expect.anything()
    );
  });

  test('getTrends calls correct endpoint with period', async () => {
    mockFetchOk({ trends: [] });
    await api.getTrends('weekly');
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/doc-analytics/trends?period=weekly'),
      expect.anything()
    );
  });

  test('getBottlenecks calls correct endpoint', async () => {
    mockFetchOk({ bottlenecks: [] });
    await api.getBottlenecks();
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/doc-analytics/bottlenecks'),
      expect.anything()
    );
  });

  test('getProcessorProductivity calls correct endpoint', async () => {
    mockFetchOk({ processors: [] });
    await api.getProcessorProductivity(30);
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/doc-analytics/processor-productivity?days=30'),
      expect.anything()
    );
  });

  test('getLoanTimeline calls correct endpoint', async () => {
    mockFetchOk({ events: [] });
    await api.getLoanTimeline(123);
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/doc-analytics/loan/123/timeline'),
      expect.anything()
    );
  });

  test('getFollowupEffectiveness calls correct endpoint', async () => {
    mockFetchOk({ campaigns: [] });
    await api.getFollowupEffectiveness(90);
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/doc-analytics/followup-effectiveness?days=90'),
      expect.anything()
    );
  });

  test('getEsignMetrics calls correct endpoint', async () => {
    mockFetchOk({ sent: 10 });
    await api.getEsignMetrics(30);
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/doc-analytics/esign-metrics?days=30'),
      expect.anything()
    );
  });

  test('getIncomeSummary calls correct endpoint', async () => {
    mockFetchOk({ total: 0 });
    await api.getIncomeSummary(30);
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/doc-analytics/income-summary?days=30'),
      expect.anything()
    );
  });

  test('getBankAnalysisSummary calls correct endpoint', async () => {
    mockFetchOk({ total: 0 });
    await api.getBankAnalysisSummary(30);
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/doc-analytics/bank-analysis-summary?days=30'),
      expect.anything()
    );
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx react-scripts test --watchAll=false --testPathPattern="docAnalyticsApi" 2>&1 | head -40`
Expected: FAIL — module not found

- [ ] **Step 3: Write the API service**

```javascript
// frontend/src/services/docAnalyticsApi.js
import { API_BASE_URL } from './api';

const BASE = `${API_BASE_URL}/api/v1/smart-docs`;

function headers() {
  const token = localStorage.getItem('token');
  return {
    Authorization: token ? `Bearer ${token}` : '',
    'Content-Type': 'application/json',
  };
}

async function get(url) {
  const res = await fetch(url, { headers: headers() });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Request failed' }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

export function getDashboard(days = 30) {
  return get(`${BASE}/doc-analytics/dashboard?days=${days}`);
}

export function getPipelineCompleteness(minPct, maxPct) {
  let url = `${BASE}/doc-analytics/pipeline-completeness`;
  const params = [];
  if (minPct != null) params.push(`min_completeness=${minPct}`);
  if (maxPct != null) params.push(`max_completeness=${maxPct}`);
  if (params.length) url += `?${params.join('&')}`;
  return get(url);
}

export function getSlaCompliance(days = 30) {
  return get(`${BASE}/doc-analytics/sla-compliance?days=${days}`);
}

export function getAiPerformance(days = 30) {
  return get(`${BASE}/doc-analytics/ai-performance?days=${days}`);
}

export function getFollowupEffectiveness(days = 30) {
  return get(`${BASE}/doc-analytics/followup-effectiveness?days=${days}`);
}

export function getIncomeSummary(days = 30) {
  return get(`${BASE}/doc-analytics/income-summary?days=${days}`);
}

export function getBankAnalysisSummary(days = 30) {
  return get(`${BASE}/doc-analytics/bank-analysis-summary?days=${days}`);
}

export function getEsignMetrics(days = 30) {
  return get(`${BASE}/doc-analytics/esign-metrics?days=${days}`);
}

export function getProcessorProductivity(days = 30) {
  return get(`${BASE}/doc-analytics/processor-productivity?days=${days}`);
}

export function getLoanTimeline(loanId) {
  return get(`${BASE}/doc-analytics/loan/${loanId}/timeline`);
}

export function getTrends(period = 'weekly', days = 90) {
  return get(`${BASE}/doc-analytics/trends?period=${period}&days=${days}`);
}

export function getBottlenecks(days = 30) {
  return get(`${BASE}/doc-analytics/bottlenecks?days=${days}`);
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx react-scripts test --watchAll=false --testPathPattern="docAnalyticsApi" 2>&1 | head -40`
Expected: PASS — all 12 tests green

- [ ] **Step 5: Commit**

```bash
git add frontend/src/services/docAnalyticsApi.js frontend/src/services/__tests__/docAnalyticsApi.test.js
git commit -m "feat(smart-docs): add analytics API service for 12 dashboard endpoints"
```

---

## Task 2: Review Queue API Service

**Files:**
- Create: `frontend/src/services/docReviewApi.js`
- Test: `frontend/src/services/__tests__/docReviewApi.test.js`

- [ ] **Step 1: Write the failing test**

```javascript
// frontend/src/services/__tests__/docReviewApi.test.js
import * as api from '../docReviewApi';

beforeEach(() => {
  global.fetch = jest.fn();
  localStorage.setItem('token', 'test-token');
});
afterEach(() => { jest.restoreAllMocks(); localStorage.clear(); });

function mockFetchOk(data) {
  global.fetch.mockResolvedValueOnce({ ok: true, json: () => Promise.resolve(data) });
}

describe('docReviewApi', () => {
  test('getQueue calls correct endpoint with filters', async () => {
    mockFetchOk({ items: [], total: 0 });
    await api.getQueue({ priority: 'HIGH', limit: 25, offset: 0 });
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/doc-review/queue?priority=HIGH&limit=25&offset=0'),
      expect.anything()
    );
  });

  test('getQueueStats calls stats endpoint', async () => {
    mockFetchOk({ total: 5 });
    await api.getQueueStats();
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/doc-review/queue/stats'),
      expect.anything()
    );
  });

  test('claimDocument sends POST', async () => {
    mockFetchOk({ claimed: true });
    await api.claimDocument(42, 'reviewer-1');
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/doc-review/queue/42/claim'),
      expect.objectContaining({ method: 'POST' })
    );
  });

  test('releaseDocument sends POST', async () => {
    mockFetchOk({ released: true });
    await api.releaseDocument(42);
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/doc-review/queue/42/release'),
      expect.objectContaining({ method: 'POST' })
    );
  });

  test('aiReview sends POST with document id', async () => {
    mockFetchOk({ decision: 'ACCEPT' });
    await api.aiReview(99);
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/doc-review/ai-review/99'),
      expect.objectContaining({ method: 'POST' })
    );
  });

  test('batchAiReview sends POST with loan id', async () => {
    mockFetchOk({ total: 3, approved: 2, rejected: 1 });
    await api.batchAiReview(101);
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/doc-review/ai-review/batch/101'),
      expect.objectContaining({ method: 'POST' })
    );
  });

  test('crossValidate sends POST', async () => {
    mockFetchOk({ consistent: true });
    await api.crossValidate(101);
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/doc-review/cross-validate/101'),
      expect.objectContaining({ method: 'POST' })
    );
  });

  test('getReviewHistory calls GET', async () => {
    mockFetchOk({ history: [] });
    await api.getReviewHistory(42);
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/doc-review/document/42/review-history'),
      expect.anything()
    );
  });

  test('getAutoReviewSettings calls GET', async () => {
    mockFetchOk({ enabled: true });
    await api.getAutoReviewSettings();
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/doc-review/auto-review-settings'),
      expect.anything()
    );
  });

  test('updateAutoReviewSettings sends POST', async () => {
    mockFetchOk({ updated: true });
    await api.updateAutoReviewSettings({ enabled: true, threshold: 85 });
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/doc-review/auto-review-settings'),
      expect.objectContaining({ method: 'POST' })
    );
  });

  test('getReviewStats calls GET', async () => {
    mockFetchOk({ total_reviewed: 100 });
    await api.getReviewStats(30);
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/doc-review/stats?days=30'),
      expect.anything()
    );
  });

  test('getLoanCompleteness calls GET', async () => {
    mockFetchOk({ completeness: 0.75 });
    await api.getLoanCompleteness(101);
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/doc-review/loan/101/completeness'),
      expect.anything()
    );
  });

  test('aiExtractAndReview sends POST', async () => {
    mockFetchOk({ extraction: {} });
    await api.aiExtractAndReview(42);
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/doc-review/document/42/ai-extract-and-review'),
      expect.objectContaining({ method: 'POST' })
    );
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx react-scripts test --watchAll=false --testPathPattern="docReviewApi" 2>&1 | head -30`
Expected: FAIL — module not found

- [ ] **Step 3: Write the API service**

```javascript
// frontend/src/services/docReviewApi.js
import { API_BASE_URL } from './api';

const BASE = `${API_BASE_URL}/api/v1/smart-docs/doc-review`;

function headers() {
  const token = localStorage.getItem('token');
  return {
    Authorization: token ? `Bearer ${token}` : '',
    'Content-Type': 'application/json',
  };
}

async function request(url, options = {}) {
  const res = await fetch(url, { headers: headers(), ...options });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Request failed' }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

export function getQueue({ priority, docType, limit = 50, offset = 0 } = {}) {
  const params = new URLSearchParams();
  if (priority) params.set('priority', priority);
  if (docType) params.set('doc_type', docType);
  params.set('limit', limit);
  params.set('offset', offset);
  return request(`${BASE}/queue?${params}`);
}

export function getQueueStats() {
  return request(`${BASE}/queue/stats`);
}

export function claimDocument(documentId, reviewerId) {
  return request(`${BASE}/queue/${documentId}/claim`, {
    method: 'POST',
    body: JSON.stringify({ reviewer_id: reviewerId }),
  });
}

export function releaseDocument(documentId) {
  return request(`${BASE}/queue/${documentId}/release`, { method: 'POST' });
}

export function aiReview(documentId) {
  return request(`${BASE}/ai-review/${documentId}`, { method: 'POST' });
}

export function batchAiReview(loanId, options = {}) {
  return request(`${BASE}/ai-review/batch/${loanId}`, {
    method: 'POST',
    body: JSON.stringify(options),
  });
}

export function crossValidate(loanId) {
  return request(`${BASE}/cross-validate/${loanId}`, { method: 'POST' });
}

export function getReviewHistory(documentId) {
  return request(`${BASE}/document/${documentId}/review-history`);
}

export function getAutoReviewSettings() {
  return request(`${BASE}/auto-review-settings`);
}

export function updateAutoReviewSettings(settings) {
  return request(`${BASE}/auto-review-settings`, {
    method: 'POST',
    body: JSON.stringify(settings),
  });
}

export function getReviewStats(days = 30) {
  return request(`${BASE}/stats?days=${days}`);
}

export function getLoanCompleteness(loanId) {
  return request(`${BASE}/loan/${loanId}/completeness`);
}

export function aiExtractAndReview(documentId) {
  return request(`${BASE}/document/${documentId}/ai-extract-and-review`, {
    method: 'POST',
  });
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx react-scripts test --watchAll=false --testPathPattern="docReviewApi" 2>&1 | head -30`
Expected: PASS — all 13 tests green

- [ ] **Step 5: Commit**

```bash
git add frontend/src/services/docReviewApi.js frontend/src/services/__tests__/docReviewApi.test.js
git commit -m "feat(smart-docs): add review queue API service for 13 review endpoints"
```

---

## Task 3: Security & Bank Analysis API Services

**Files:**
- Create: `frontend/src/services/docSecurityApi.js`
- Create: `frontend/src/services/docBankAnalysisApi.js`
- Create: `frontend/src/services/docIncomeApi.js`
- Test: `frontend/src/services/__tests__/docSecurityApi.test.js`

- [ ] **Step 1: Write the failing test**

```javascript
// frontend/src/services/__tests__/docSecurityApi.test.js
import * as secApi from '../docSecurityApi';
import * as bankApi from '../docBankAnalysisApi';
import * as incomeApi from '../docIncomeApi';

beforeEach(() => {
  global.fetch = jest.fn();
  localStorage.setItem('token', 'test-token');
});
afterEach(() => { jest.restoreAllMocks(); localStorage.clear(); });

function mockFetchOk(data) {
  global.fetch.mockResolvedValueOnce({ ok: true, json: () => Promise.resolve(data) });
}

describe('docSecurityApi', () => {
  test('getAuditLog calls correct endpoint', async () => {
    mockFetchOk({ entries: [] });
    await secApi.getAuditLog({ days: 7 });
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/doc-security/audit-log'),
      expect.anything()
    );
  });

  test('getComplianceReport calls correct endpoint', async () => {
    mockFetchOk({ report: {} });
    await secApi.getComplianceReport();
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/doc-security/compliance-report'),
      expect.anything()
    );
  });

  test('getFraudAnalysis calls correct endpoint', async () => {
    mockFetchOk({ risk: 'LOW' });
    await secApi.getFraudAnalysis(101);
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/doc-security/fraud-analysis/101'),
      expect.anything()
    );
  });

  test('getRetentionPolicies calls correct endpoint', async () => {
    mockFetchOk({ policies: [] });
    await secApi.getRetentionPolicies();
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/doc-security/retention-policies'),
      expect.anything()
    );
  });

  test('getSuspiciousActivity calls correct endpoint', async () => {
    mockFetchOk({ alerts: [] });
    await secApi.getSuspiciousActivity();
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/doc-security/suspicious-activity'),
      expect.anything()
    );
  });
});

describe('docBankAnalysisApi', () => {
  test('analyzeBankStatement sends POST', async () => {
    mockFetchOk({ analysis: {} });
    await bankApi.analyzeBankStatement(42);
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/bank-analysis/analyze/42'),
      expect.objectContaining({ method: 'POST' })
    );
  });

  test('getLargeDeposits calls correct endpoint', async () => {
    mockFetchOk({ deposits: [] });
    await bankApi.getLargeDeposits(101);
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/bank-analysis/large-deposits/101'),
      expect.anything()
    );
  });

  test('getRiskScore calls correct endpoint', async () => {
    mockFetchOk({ score: 85 });
    await bankApi.getRiskScore(101);
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/bank-analysis/risk-score/101'),
      expect.anything()
    );
  });
});

describe('docIncomeApi', () => {
  test('calculateIncome sends POST', async () => {
    mockFetchOk({ income: {} });
    await incomeApi.calculateIncome(101);
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/income/calculate/101'),
      expect.objectContaining({ method: 'POST' })
    );
  });

  test('getIncomeHistory calls correct endpoint', async () => {
    mockFetchOk({ history: [] });
    await incomeApi.getIncomeHistory(101);
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/income/history/101'),
      expect.anything()
    );
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx react-scripts test --watchAll=false --testPathPattern="docSecurityApi" 2>&1 | head -30`
Expected: FAIL — modules not found

- [ ] **Step 3: Write docSecurityApi.js**

```javascript
// frontend/src/services/docSecurityApi.js
import { API_BASE_URL } from './api';

const BASE = `${API_BASE_URL}/api/v1/smart-docs/doc-security`;

function headers() {
  const token = localStorage.getItem('token');
  return {
    Authorization: token ? `Bearer ${token}` : '',
    'Content-Type': 'application/json',
  };
}

async function request(url, options = {}) {
  const res = await fetch(url, { headers: headers(), ...options });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Request failed' }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

export function getAuditLog({ days = 30, documentId, action, limit = 100, offset = 0 } = {}) {
  const params = new URLSearchParams({ days, limit, offset });
  if (documentId) params.set('document_id', documentId);
  if (action) params.set('action', action);
  return request(`${BASE}/audit-log?${params}`);
}

export function getDocumentAuditLog(documentId) {
  return request(`${BASE}/audit-log/${documentId}`);
}

export function logAccess(documentId, action, details = '') {
  return request(`${BASE}/log-access`, {
    method: 'POST',
    body: JSON.stringify({ document_id: documentId, action, details }),
  });
}

export function checkIntegrity(documentId) {
  return request(`${BASE}/integrity-check/${documentId}`);
}

export function batchIntegrityCheck(documentIds) {
  return request(`${BASE}/integrity-check/batch`, {
    method: 'POST',
    body: JSON.stringify({ document_ids: documentIds }),
  });
}

export function getIntegrityHistory(documentId) {
  return request(`${BASE}/integrity-history/${documentId}`);
}

export function getFraudAnalysis(loanId) {
  return request(`${BASE}/fraud-analysis/${loanId}`);
}

export function getFraudSummary(loanId) {
  return loanId
    ? request(`${BASE}/fraud/${loanId}/summary`)
    : request(`${BASE}/fraud-summary`);
}

export function getRetentionPolicies() {
  return request(`${BASE}/retention-policies`);
}

export function createRetentionPolicy(policy) {
  return request(`${BASE}/retention-policies`, {
    method: 'POST',
    body: JSON.stringify(policy),
  });
}

export function updateRetentionPolicy(policyId, policy) {
  return request(`${BASE}/retention-policies/${policyId}`, {
    method: 'PUT',
    body: JSON.stringify(policy),
  });
}

export function getExpiringRetentions(days = 30) {
  return request(`${BASE}/retention-expiring?days=${days}`);
}

export function watermarkDocument(documentId, options = {}) {
  return request(`${BASE}/watermark/${documentId}`, {
    method: 'POST',
    body: JSON.stringify(options),
  });
}

export function getEncryptionStatus(documentId) {
  return request(`${BASE}/encryption-status/${documentId}`);
}

export function encryptDocument(documentId) {
  return request(`${BASE}/encrypt/${documentId}`, { method: 'POST' });
}

export function getComplianceReport(days = 30) {
  return request(`${BASE}/compliance-report?days=${days}`);
}

export function getSuspiciousActivity(days = 30) {
  return request(`${BASE}/suspicious-activity?days=${days}`);
}
```

- [ ] **Step 4: Write docBankAnalysisApi.js**

```javascript
// frontend/src/services/docBankAnalysisApi.js
import { API_BASE_URL } from './api';

const BASE = `${API_BASE_URL}/api/v1/smart-docs/bank-analysis`;

function headers() {
  const token = localStorage.getItem('token');
  return {
    Authorization: token ? `Bearer ${token}` : '',
    'Content-Type': 'application/json',
  };
}

async function request(url, options = {}) {
  const res = await fetch(url, { headers: headers(), ...options });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Request failed' }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

export function analyzeBankStatement(documentId) {
  return request(`${BASE}/analyze/${documentId}`, { method: 'POST' });
}

export function getLargeDeposits(loanId, threshold) {
  const params = threshold ? `?threshold=${threshold}` : '';
  return request(`${BASE}/large-deposits/${loanId}${params}`);
}

export function getNsfOverdrafts(loanId) {
  return request(`${BASE}/nsf-overdrafts/${loanId}`);
}

export function getUndisclosedDebts(loanId) {
  return request(`${BASE}/undisclosed-debts/${loanId}`);
}

export function getIrsPayments(loanId) {
  return request(`${BASE}/irs-payments/${loanId}`);
}

export function getRiskScore(loanId) {
  return request(`${BASE}/risk-score/${loanId}`);
}

export function getBankSummary(loanId) {
  return request(`${BASE}/summary/${loanId}`);
}

export function sourceDeposit(depositId, sourcing) {
  return request(`${BASE}/source-deposit/${depositId}`, {
    method: 'POST',
    body: JSON.stringify(sourcing),
  });
}
```

- [ ] **Step 5: Write docIncomeApi.js**

```javascript
// frontend/src/services/docIncomeApi.js
import { API_BASE_URL } from './api';

const BASE = `${API_BASE_URL}/api/v1/smart-docs/income`;

function headers() {
  const token = localStorage.getItem('token');
  return {
    Authorization: token ? `Bearer ${token}` : '',
    'Content-Type': 'application/json',
  };
}

async function request(url, options = {}) {
  const res = await fetch(url, { headers: headers(), ...options });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Request failed' }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

export function calculateIncome(loanId, options = {}) {
  return request(`${BASE}/calculate/${loanId}`, {
    method: 'POST',
    body: JSON.stringify(options),
  });
}

export function getIncomeHistory(loanId) {
  return request(`${BASE}/history/${loanId}`);
}

export function getIncomeSources(loanId) {
  return request(`${BASE}/sources/${loanId}`);
}

export function overrideSource(sourceId, override) {
  return request(`${BASE}/sources/${sourceId}/override`, {
    method: 'POST',
    body: JSON.stringify(override),
  });
}

export function submitForApproval(loanId) {
  return request(`${BASE}/submit/${loanId}`, { method: 'POST' });
}

export function approveIncome(loanId, notes) {
  return request(`${BASE}/approve/${loanId}`, {
    method: 'POST',
    body: JSON.stringify({ notes }),
  });
}

export function rejectIncome(loanId, reason) {
  return request(`${BASE}/reject/${loanId}`, {
    method: 'POST',
    body: JSON.stringify({ reason }),
  });
}
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd frontend && npx react-scripts test --watchAll=false --testPathPattern="docSecurityApi" 2>&1 | head -30`
Expected: PASS — all tests green

- [ ] **Step 7: Commit**

```bash
git add frontend/src/services/docSecurityApi.js frontend/src/services/docBankAnalysisApi.js frontend/src/services/docIncomeApi.js frontend/src/services/__tests__/docSecurityApi.test.js
git commit -m "feat(smart-docs): add security, bank analysis, and income API services"
```

---

## Task 4: AnalyticsCard Reusable Component

**Files:**
- Create: `frontend/src/components/smart-docs/AnalyticsCard.jsx`
- Create: `frontend/src/components/smart-docs/AnalyticsCard.css`
- Test: `frontend/src/components/smart-docs/__tests__/AnalyticsCard.test.jsx`

- [ ] **Step 1: Write the failing test**

```jsx
// frontend/src/components/smart-docs/__tests__/AnalyticsCard.test.jsx
import React from 'react';
import { render, screen } from '@testing-library/react';
import AnalyticsCard from '../AnalyticsCard';

describe('AnalyticsCard', () => {
  test('renders title and value', () => {
    render(<AnalyticsCard title="Total Documents" value={142} />);
    expect(screen.getByText('Total Documents')).toBeInTheDocument();
    expect(screen.getByText('142')).toBeInTheDocument();
  });

  test('renders subtitle when provided', () => {
    render(<AnalyticsCard title="SLA" value="95%" subtitle="Last 30 days" />);
    expect(screen.getByText('Last 30 days')).toBeInTheDocument();
  });

  test('renders trend indicator when positive', () => {
    render(<AnalyticsCard title="Approved" value={85} trend={12} />);
    expect(screen.getByText('+12%')).toBeInTheDocument();
  });

  test('renders trend indicator when negative', () => {
    render(<AnalyticsCard title="Rejected" value={3} trend={-5} />);
    expect(screen.getByText('-5%')).toBeInTheDocument();
  });

  test('applies status class', () => {
    const { container } = render(
      <AnalyticsCard title="Overdue" value={7} status="error" />
    );
    expect(container.firstChild).toHaveClass('analytics-card--error');
  });

  test('renders children when provided', () => {
    render(
      <AnalyticsCard title="Custom" value={0}>
        <span data-testid="child">Detail</span>
      </AnalyticsCard>
    );
    expect(screen.getByTestId('child')).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx react-scripts test --watchAll=false --testPathPattern="AnalyticsCard" 2>&1 | head -30`
Expected: FAIL — module not found

- [ ] **Step 3: Write the component**

```jsx
// frontend/src/components/smart-docs/AnalyticsCard.jsx
import React from 'react';
import './AnalyticsCard.css';

export default function AnalyticsCard({
  title,
  value,
  subtitle,
  trend,
  status,
  icon,
  children,
}) {
  const statusClass = status ? ` analytics-card--${status}` : '';
  const trendDirection = trend > 0 ? 'up' : trend < 0 ? 'down' : null;

  return (
    <div className={`analytics-card${statusClass}`}>
      <div className="analytics-card__header">
        {icon && <span className="analytics-card__icon">{icon}</span>}
        <span className="analytics-card__title">{title}</span>
      </div>
      <div className="analytics-card__value">{value}</div>
      <div className="analytics-card__footer">
        {subtitle && (
          <span className="analytics-card__subtitle">{subtitle}</span>
        )}
        {trend != null && (
          <span className={`analytics-card__trend analytics-card__trend--${trendDirection}`}>
            {trend > 0 ? '+' : ''}{trend}%
          </span>
        )}
      </div>
      {children && <div className="analytics-card__body">{children}</div>}
    </div>
  );
}
```

- [ ] **Step 4: Write the CSS**

```css
/* frontend/src/components/smart-docs/AnalyticsCard.css */
.analytics-card {
  background: var(--color-bg-surface);
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-md);
  padding: var(--space-lg);
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
  transition: all 250ms ease;
}

.analytics-card:hover {
  box-shadow: var(--shadow-md);
}

.analytics-card--success {
  border-left: 3px solid var(--color-success);
}

.analytics-card--warning {
  border-left: 3px solid var(--color-warning);
}

.analytics-card--error {
  border-left: 3px solid var(--color-error);
}

.analytics-card__header {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
}

.analytics-card__icon {
  font-size: var(--font-lg);
  opacity: 0.7;
}

.analytics-card__title {
  font-size: var(--font-sm);
  font-weight: var(--weight-medium);
  color: var(--color-text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.analytics-card__value {
  font-size: var(--font-3xl);
  font-weight: var(--weight-bold);
  color: var(--color-text-primary);
  line-height: var(--line-tight);
}

.analytics-card__footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-sm);
}

.analytics-card__subtitle {
  font-size: var(--font-xs);
  color: var(--color-text-tertiary);
}

.analytics-card__trend {
  font-size: var(--font-sm);
  font-weight: var(--weight-semibold);
  padding: 2px var(--space-sm);
  border-radius: var(--radius-full);
}

.analytics-card__trend--up {
  color: var(--color-success);
  background: rgba(33, 127, 141, 0.1);
}

.analytics-card__trend--down {
  color: var(--color-error);
  background: rgba(192, 21, 47, 0.1);
}

.analytics-card__body {
  margin-top: var(--space-sm);
  padding-top: var(--space-sm);
  border-top: 1px solid var(--color-border-light);
}

@media (max-width: 480px) {
  .analytics-card {
    padding: var(--space-md);
  }

  .analytics-card__value {
    font-size: var(--font-2xl);
  }
}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd frontend && npx react-scripts test --watchAll=false --testPathPattern="AnalyticsCard" 2>&1 | head -30`
Expected: PASS — all 6 tests green

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/smart-docs/AnalyticsCard.jsx frontend/src/components/smart-docs/AnalyticsCard.css frontend/src/components/smart-docs/__tests__/AnalyticsCard.test.jsx
git commit -m "feat(smart-docs): add AnalyticsCard reusable metric component"
```

---

## Task 5: useDocAnalytics Hook

**Files:**
- Create: `frontend/src/hooks/useDocAnalytics.js`
- Test: `frontend/src/hooks/__tests__/useDocAnalytics.test.js`

- [ ] **Step 1: Write the failing test**

```javascript
// frontend/src/hooks/__tests__/useDocAnalytics.test.js
import { renderHook, act } from '@testing-library/react-hooks';
import useDocAnalytics from '../useDocAnalytics';
import * as api from '../../services/docAnalyticsApi';

jest.mock('../../services/docAnalyticsApi');

describe('useDocAnalytics', () => {
  beforeEach(() => jest.clearAllMocks());

  test('loads dashboard data on mount', async () => {
    api.getDashboard.mockResolvedValue({ total_documents: 42, pending_review: 5 });
    api.getSlaCompliance.mockResolvedValue({ compliance_rate: 0.95 });
    api.getBottlenecks.mockResolvedValue({ bottlenecks: [] });

    const { result, waitForNextUpdate } = renderHook(() => useDocAnalytics(30));
    expect(result.current.loading).toBe(true);

    await waitForNextUpdate();
    expect(result.current.loading).toBe(false);
    expect(result.current.dashboard.total_documents).toBe(42);
    expect(result.current.sla.compliance_rate).toBe(0.95);
  });

  test('refresh reloads data', async () => {
    api.getDashboard.mockResolvedValue({ total_documents: 1 });
    api.getSlaCompliance.mockResolvedValue({});
    api.getBottlenecks.mockResolvedValue({});

    const { result, waitForNextUpdate } = renderHook(() => useDocAnalytics(30));
    await waitForNextUpdate();

    api.getDashboard.mockResolvedValue({ total_documents: 2 });
    await act(async () => { await result.current.refresh(); });
    expect(result.current.dashboard.total_documents).toBe(2);
  });

  test('sets error on failure', async () => {
    api.getDashboard.mockRejectedValue(new Error('Network error'));
    api.getSlaCompliance.mockResolvedValue({});
    api.getBottlenecks.mockResolvedValue({});

    const { result, waitForNextUpdate } = renderHook(() => useDocAnalytics(30));
    await waitForNextUpdate();
    expect(result.current.error).toBe('Network error');
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx react-scripts test --watchAll=false --testPathPattern="useDocAnalytics" 2>&1 | head -30`
Expected: FAIL — module not found

- [ ] **Step 3: Write the hook**

```javascript
// frontend/src/hooks/useDocAnalytics.js
import { useState, useEffect, useCallback } from 'react';
import * as api from '../services/docAnalyticsApi';

export default function useDocAnalytics(days = 30) {
  const [dashboard, setDashboard] = useState(null);
  const [sla, setSla] = useState(null);
  const [bottlenecks, setBottlenecks] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [dashData, slaData, bottleData] = await Promise.all([
        api.getDashboard(days),
        api.getSlaCompliance(days),
        api.getBottlenecks(days),
      ]);
      setDashboard(dashData);
      setSla(slaData);
      setBottlenecks(bottleData);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [days]);

  useEffect(() => { load(); }, [load]);

  return { dashboard, sla, bottlenecks, loading, error, refresh: load };
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx react-scripts test --watchAll=false --testPathPattern="useDocAnalytics" 2>&1 | head -30`
Expected: PASS — all 3 tests green

- [ ] **Step 5: Commit**

```bash
git add frontend/src/hooks/useDocAnalytics.js frontend/src/hooks/__tests__/useDocAnalytics.test.js
git commit -m "feat(smart-docs): add useDocAnalytics hook for dashboard data"
```

---

## Task 6: useReviewQueue Hook

**Files:**
- Create: `frontend/src/hooks/useReviewQueue.js`
- Test: `frontend/src/hooks/__tests__/useReviewQueue.test.js`

- [ ] **Step 1: Write the failing test**

```javascript
// frontend/src/hooks/__tests__/useReviewQueue.test.js
import { renderHook, act } from '@testing-library/react-hooks';
import useReviewQueue from '../useReviewQueue';
import * as api from '../../services/docReviewApi';

jest.mock('../../services/docReviewApi');

describe('useReviewQueue', () => {
  beforeEach(() => jest.clearAllMocks());

  test('loads queue on mount', async () => {
    api.getQueue.mockResolvedValue({ items: [{ id: 1 }, { id: 2 }], total: 2 });
    api.getQueueStats.mockResolvedValue({ total: 2, high_priority: 1 });

    const { result, waitForNextUpdate } = renderHook(() => useReviewQueue());
    await waitForNextUpdate();

    expect(result.current.items).toHaveLength(2);
    expect(result.current.stats.total).toBe(2);
    expect(result.current.loading).toBe(false);
  });

  test('claim marks document as claimed', async () => {
    api.getQueue.mockResolvedValue({ items: [{ id: 1, claimed_by: null }], total: 1 });
    api.getQueueStats.mockResolvedValue({ total: 1 });
    api.claimDocument.mockResolvedValue({ claimed: true });

    const { result, waitForNextUpdate } = renderHook(() => useReviewQueue());
    await waitForNextUpdate();

    api.getQueue.mockResolvedValue({ items: [{ id: 1, claimed_by: 'me' }], total: 1 });
    api.getQueueStats.mockResolvedValue({ total: 1 });
    await act(async () => { await result.current.claim(1, 'me'); });
    expect(api.claimDocument).toHaveBeenCalledWith(1, 'me');
  });

  test('setFilters triggers reload', async () => {
    api.getQueue.mockResolvedValue({ items: [], total: 0 });
    api.getQueueStats.mockResolvedValue({ total: 0 });

    const { result, waitForNextUpdate } = renderHook(() => useReviewQueue());
    await waitForNextUpdate();

    await act(async () => { result.current.setFilters({ priority: 'HIGH' }); });
    expect(api.getQueue).toHaveBeenCalledWith(expect.objectContaining({ priority: 'HIGH' }));
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx react-scripts test --watchAll=false --testPathPattern="useReviewQueue" 2>&1 | head -30`
Expected: FAIL — module not found

- [ ] **Step 3: Write the hook**

```javascript
// frontend/src/hooks/useReviewQueue.js
import { useState, useEffect, useCallback } from 'react';
import * as api from '../services/docReviewApi';

export default function useReviewQueue() {
  const [items, setItems] = useState([]);
  const [stats, setStats] = useState(null);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [filters, setFiltersState] = useState({ limit: 50, offset: 0 });

  const load = useCallback(async (f) => {
    const activeFilters = f || filters;
    setLoading(true);
    setError(null);
    try {
      const [queueData, statsData] = await Promise.all([
        api.getQueue(activeFilters),
        api.getQueueStats(),
      ]);
      setItems(queueData.items || []);
      setTotal(queueData.total || 0);
      setStats(statsData);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [filters]);

  useEffect(() => { load(); }, [load]);

  const setFilters = useCallback((newFilters) => {
    const merged = { ...filters, ...newFilters, offset: 0 };
    setFiltersState(merged);
    load(merged);
  }, [filters, load]);

  const nextPage = useCallback(() => {
    const next = { ...filters, offset: filters.offset + filters.limit };
    setFiltersState(next);
    load(next);
  }, [filters, load]);

  const prevPage = useCallback(() => {
    const prev = { ...filters, offset: Math.max(0, filters.offset - filters.limit) };
    setFiltersState(prev);
    load(prev);
  }, [filters, load]);

  const claim = useCallback(async (documentId, reviewerId) => {
    await api.claimDocument(documentId, reviewerId);
    await load();
  }, [load]);

  const release = useCallback(async (documentId) => {
    await api.releaseDocument(documentId);
    await load();
  }, [load]);

  return {
    items, stats, total, loading, error,
    filters, setFilters, nextPage, prevPage,
    claim, release, refresh: load,
  };
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx react-scripts test --watchAll=false --testPathPattern="useReviewQueue" 2>&1 | head -30`
Expected: PASS — all 3 tests green

- [ ] **Step 5: Commit**

```bash
git add frontend/src/hooks/useReviewQueue.js frontend/src/hooks/__tests__/useReviewQueue.test.js
git commit -m "feat(smart-docs): add useReviewQueue hook for document review queue"
```

---

## Task 7: Analytics Dashboard Page

**Files:**
- Create: `frontend/src/pages/SmartDocsAnalytics.js`
- Create: `frontend/src/pages/SmartDocsAnalytics.css`

- [ ] **Step 1: Write the page component**

```jsx
// frontend/src/pages/SmartDocsAnalytics.js
import React, { useState, useEffect } from 'react';
import { toast } from 'react-hot-toast';
import AnalyticsCard from '../components/smart-docs/AnalyticsCard';
import useDocAnalytics from '../hooks/useDocAnalytics';
import * as analyticsApi from '../services/docAnalyticsApi';
import './SmartDocsAnalytics.css';

const PERIOD_OPTIONS = [
  { label: '7 days', value: 7 },
  { label: '30 days', value: 30 },
  { label: '90 days', value: 90 },
];

export default function SmartDocsAnalytics() {
  const [days, setDays] = useState(30);
  const [activeTab, setActiveTab] = useState('overview');
  const { dashboard, sla, bottlenecks, loading, error, refresh } = useDocAnalytics(days);
  const [aiPerf, setAiPerf] = useState(null);
  const [processorData, setProcessorData] = useState(null);
  const [trends, setTrends] = useState(null);

  useEffect(() => {
    async function loadExtended() {
      try {
        const [ai, proc, trendData] = await Promise.all([
          analyticsApi.getAiPerformance(days),
          analyticsApi.getProcessorProductivity(days),
          analyticsApi.getTrends('weekly', days),
        ]);
        setAiPerf(ai);
        setProcessorData(proc);
        setTrends(trendData);
      } catch (err) {
        toast.error(`Failed to load extended analytics: ${err.message}`);
      }
    }
    loadExtended();
  }, [days]);

  if (loading && !dashboard) {
    return <div className="loading">Loading analytics...</div>;
  }

  if (error) {
    return <div className="error">{error}</div>;
  }

  const tabs = [
    { id: 'overview', label: 'Overview' },
    { id: 'sla', label: 'SLA Compliance' },
    { id: 'ai', label: 'AI Performance' },
    { id: 'processors', label: 'Team Productivity' },
    { id: 'bottlenecks', label: 'Bottlenecks' },
  ];

  return (
    <div className="sd-analytics">
      <div className="sd-analytics__header">
        <div>
          <h1 className="sd-analytics__title">Document Analytics</h1>
          <p className="sd-analytics__subtitle">
            Smart Docs performance metrics and insights
          </p>
        </div>
        <div className="sd-analytics__controls">
          <select
            value={days}
            onChange={(e) => setDays(Number(e.target.value))}
            className="sd-analytics__period-select"
          >
            {PERIOD_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>
          <button onClick={refresh} className="btn-secondary">Refresh</button>
        </div>
      </div>

      <div className="sd-analytics__tabs">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            className={`sd-analytics__tab${activeTab === tab.id ? ' sd-analytics__tab--active' : ''}`}
            onClick={() => setActiveTab(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {activeTab === 'overview' && dashboard && (
        <div className="sd-analytics__grid">
          <AnalyticsCard
            title="Total Documents"
            value={dashboard.total_documents || 0}
            subtitle={`Last ${days} days`}
          />
          <AnalyticsCard
            title="Pending Review"
            value={dashboard.pending_review || 0}
            status={dashboard.pending_review > 20 ? 'warning' : 'success'}
          />
          <AnalyticsCard
            title="Approved"
            value={dashboard.approved || 0}
            status="success"
          />
          <AnalyticsCard
            title="Rejected"
            value={dashboard.rejected || 0}
            status={dashboard.rejected > 10 ? 'error' : undefined}
          />
          <AnalyticsCard
            title="Avg Review Time"
            value={dashboard.avg_review_hours ? `${dashboard.avg_review_hours}h` : 'N/A'}
            subtitle="Hours to review"
          />
          <AnalyticsCard
            title="Auto-Approved"
            value={dashboard.auto_approved || 0}
            subtitle="By AI review"
          />
        </div>
      )}

      {activeTab === 'sla' && sla && (
        <div className="sd-analytics__section">
          <div className="sd-analytics__grid sd-analytics__grid--2">
            <AnalyticsCard
              title="SLA Compliance Rate"
              value={sla.compliance_rate != null ? `${Math.round(sla.compliance_rate * 100)}%` : 'N/A'}
              status={sla.compliance_rate >= 0.9 ? 'success' : sla.compliance_rate >= 0.7 ? 'warning' : 'error'}
            />
            <AnalyticsCard
              title="SLA Breaches"
              value={sla.breaches || 0}
              status={sla.breaches > 0 ? 'error' : 'success'}
            />
          </div>
          {sla.by_doc_type && (
            <div className="sd-analytics__table-container">
              <table className="sd-analytics__table">
                <thead>
                  <tr>
                    <th>Document Type</th>
                    <th>Total</th>
                    <th>On Time</th>
                    <th>Breached</th>
                    <th>Rate</th>
                  </tr>
                </thead>
                <tbody>
                  {sla.by_doc_type.map((row) => (
                    <tr key={row.doc_type}>
                      <td>{row.doc_type}</td>
                      <td>{row.total}</td>
                      <td>{row.on_time}</td>
                      <td className={row.breached > 0 ? 'sd-analytics__cell--error' : ''}>
                        {row.breached}
                      </td>
                      <td>{Math.round((row.on_time / (row.total || 1)) * 100)}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {activeTab === 'ai' && aiPerf && (
        <div className="sd-analytics__grid">
          <AnalyticsCard
            title="AI Accuracy"
            value={aiPerf.accuracy != null ? `${Math.round(aiPerf.accuracy * 100)}%` : 'N/A'}
            status={aiPerf.accuracy >= 0.9 ? 'success' : 'warning'}
          />
          <AnalyticsCard
            title="Total Reviewed"
            value={aiPerf.total_reviewed || 0}
          />
          <AnalyticsCard
            title="Auto-Approved"
            value={aiPerf.auto_approved || 0}
          />
          <AnalyticsCard
            title="Escalated"
            value={aiPerf.escalated || 0}
            status={aiPerf.escalated > 20 ? 'warning' : undefined}
          />
          <AnalyticsCard
            title="Avg Confidence"
            value={aiPerf.avg_confidence != null ? `${Math.round(aiPerf.avg_confidence)}%` : 'N/A'}
          />
          <AnalyticsCard
            title="False Rejections"
            value={aiPerf.false_rejections || 0}
            status={aiPerf.false_rejections > 5 ? 'error' : 'success'}
          />
        </div>
      )}

      {activeTab === 'processors' && processorData && (
        <div className="sd-analytics__section">
          <div className="sd-analytics__table-container">
            <table className="sd-analytics__table">
              <thead>
                <tr>
                  <th>Processor</th>
                  <th>Reviewed</th>
                  <th>Approved</th>
                  <th>Rejected</th>
                  <th>Avg Time</th>
                </tr>
              </thead>
              <tbody>
                {(processorData.processors || []).map((p) => (
                  <tr key={p.user_id || p.name}>
                    <td>{p.name}</td>
                    <td>{p.reviewed}</td>
                    <td>{p.approved}</td>
                    <td>{p.rejected}</td>
                    <td>{p.avg_review_minutes ? `${Math.round(p.avg_review_minutes)}m` : 'N/A'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {activeTab === 'bottlenecks' && bottlenecks && (
        <div className="sd-analytics__section">
          {(bottlenecks.bottlenecks || []).length === 0 ? (
            <p className="sd-analytics__empty">No bottlenecks detected</p>
          ) : (
            <div className="sd-analytics__bottleneck-list">
              {bottlenecks.bottlenecks.map((b, i) => (
                <div key={i} className={`sd-analytics__bottleneck sd-analytics__bottleneck--${b.severity || 'low'}`}>
                  <div className="sd-analytics__bottleneck-header">
                    <span className="sd-analytics__bottleneck-stage">{b.stage || b.doc_type}</span>
                    <span className={`badge badge-${b.severity === 'high' ? 'error' : b.severity === 'medium' ? 'warning' : 'success'}`}>
                      {b.severity}
                    </span>
                  </div>
                  <p className="sd-analytics__bottleneck-desc">{b.description || `${b.count} documents stuck`}</p>
                  <div className="sd-analytics__bottleneck-stats">
                    <span>Count: {b.count}</span>
                    <span>Avg Days: {b.avg_days ? Math.round(b.avg_days) : 'N/A'}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Write the CSS**

```css
/* frontend/src/pages/SmartDocsAnalytics.css */
.sd-analytics {
  padding: var(--space-lg);
  max-width: 1200px;
  margin: 0 auto;
}

.sd-analytics__header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: var(--space-lg);
}

.sd-analytics__title {
  font-size: var(--font-2xl);
  font-weight: var(--weight-bold);
  color: var(--color-text-primary);
  margin-bottom: var(--space-xs);
}

.sd-analytics__subtitle {
  font-size: var(--font-sm);
  color: var(--color-text-secondary);
}

.sd-analytics__controls {
  display: flex;
  gap: var(--space-sm);
  align-items: center;
}

.sd-analytics__period-select {
  min-width: 120px;
}

.sd-analytics__tabs {
  display: flex;
  gap: var(--space-xs);
  border-bottom: 1px solid var(--color-border-light);
  margin-bottom: var(--space-lg);
  overflow-x: auto;
}

.sd-analytics__tab {
  padding: var(--space-sm) var(--space-md);
  background: none;
  border: none;
  border-bottom: 2px solid transparent;
  color: var(--color-text-secondary);
  font-size: var(--font-sm);
  white-space: nowrap;
  cursor: pointer;
}

.sd-analytics__tab--active {
  color: var(--color-primary);
  border-bottom-color: var(--color-primary);
}

.sd-analytics__grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: var(--space-md);
}

.sd-analytics__grid--2 {
  grid-template-columns: repeat(2, 1fr);
}

.sd-analytics__section {
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
}

.sd-analytics__table-container {
  overflow-x: auto;
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-md);
}

.sd-analytics__table {
  width: 100%;
  border-collapse: collapse;
}

.sd-analytics__table th,
.sd-analytics__table td {
  padding: var(--space-sm) var(--space-md);
  text-align: left;
  font-size: var(--font-sm);
  border-bottom: 1px solid var(--color-border-light);
}

.sd-analytics__table th {
  background: var(--color-bg-secondary);
  font-weight: var(--weight-semibold);
  color: var(--color-text-secondary);
  text-transform: uppercase;
  font-size: var(--font-xs);
  letter-spacing: 0.5px;
}

.sd-analytics__cell--error {
  color: var(--color-error);
  font-weight: var(--weight-semibold);
}

.sd-analytics__empty {
  text-align: center;
  color: var(--color-text-tertiary);
  padding: var(--space-xl);
}

.sd-analytics__bottleneck-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
}

.sd-analytics__bottleneck {
  padding: var(--space-md);
  border-radius: var(--radius-md);
  border: 1px solid var(--color-border-light);
  border-left: 3px solid var(--color-info);
}

.sd-analytics__bottleneck--high {
  border-left-color: var(--color-error);
}

.sd-analytics__bottleneck--medium {
  border-left-color: var(--color-warning);
}

.sd-analytics__bottleneck-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--space-xs);
}

.sd-analytics__bottleneck-stage {
  font-weight: var(--weight-semibold);
}

.sd-analytics__bottleneck-desc {
  font-size: var(--font-sm);
  color: var(--color-text-secondary);
  margin-bottom: var(--space-sm);
}

.sd-analytics__bottleneck-stats {
  display: flex;
  gap: var(--space-lg);
  font-size: var(--font-xs);
  color: var(--color-text-tertiary);
}

@media (max-width: 768px) {
  .sd-analytics__header {
    flex-direction: column;
    gap: var(--space-md);
  }

  .sd-analytics__grid {
    grid-template-columns: repeat(2, 1fr);
  }

  .sd-analytics__grid--2 {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 480px) {
  .sd-analytics {
    padding: var(--space-md);
  }

  .sd-analytics__grid {
    grid-template-columns: 1fr;
  }
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/SmartDocsAnalytics.js frontend/src/pages/SmartDocsAnalytics.css
git commit -m "feat(smart-docs): add analytics dashboard page with 5 tabs"
```

---

## Task 8: Review Queue Page

**Files:**
- Create: `frontend/src/pages/SmartDocsReviewQueue.js`
- Create: `frontend/src/pages/SmartDocsReviewQueue.css`
- Create: `frontend/src/components/smart-docs/ReviewQueueItem.jsx`
- Create: `frontend/src/components/smart-docs/ReviewQueueItem.css`

- [ ] **Step 1: Write ReviewQueueItem component**

```jsx
// frontend/src/components/smart-docs/ReviewQueueItem.jsx
import React from 'react';
import './ReviewQueueItem.css';

const PRIORITY_CLASSES = {
  CRITICAL: 'rqi--critical',
  HIGH: 'rqi--high',
  NORMAL: 'rqi--normal',
  LOW: 'rqi--low',
};

export default function ReviewQueueItem({
  document,
  onClaim,
  onRelease,
  onAiReview,
  onViewDetail,
  currentUserId,
}) {
  const isClaimed = document.claimed_by != null;
  const isClaimedByMe = document.claimed_by === currentUserId;
  const priorityClass = PRIORITY_CLASSES[document.priority] || 'rqi--normal';

  return (
    <div className={`rqi ${priorityClass}${isClaimed ? ' rqi--claimed' : ''}`}>
      <div className="rqi__priority">
        <span className={`rqi__priority-badge badge badge-${document.priority === 'CRITICAL' || document.priority === 'HIGH' ? 'error' : document.priority === 'NORMAL' ? 'warning' : 'success'}`}>
          {document.priority}
        </span>
      </div>

      <div className="rqi__info">
        <div className="rqi__doc-type">{document.doc_type}</div>
        <div className="rqi__borrower">{document.borrower_name}</div>
        <div className="rqi__loan">Loan #{document.loan_number}</div>
      </div>

      <div className="rqi__meta">
        <span className="rqi__uploaded">
          Uploaded {document.uploaded_at ? new Date(document.uploaded_at).toLocaleDateString() : 'N/A'}
        </span>
        {document.confidence != null && (
          <span className="rqi__confidence">
            AI: {document.confidence}%
          </span>
        )}
      </div>

      <div className="rqi__status">
        {isClaimed && !isClaimedByMe && (
          <span className="rqi__claimed-by">Claimed by {document.claimed_by_name || 'another'}</span>
        )}
        {isClaimedByMe && (
          <span className="rqi__claimed-by rqi__claimed-by--mine">Claimed by you</span>
        )}
      </div>

      <div className="rqi__actions">
        {!isClaimed && (
          <button className="btn-primary" onClick={() => onClaim(document.id)}>
            Claim
          </button>
        )}
        {isClaimedByMe && (
          <>
            <button className="btn-primary" onClick={() => onViewDetail(document)}>
              Review
            </button>
            <button className="btn-secondary" onClick={() => onRelease(document.id)}>
              Release
            </button>
          </>
        )}
        {!isClaimed && (
          <button className="btn-secondary" onClick={() => onAiReview(document.id)}>
            AI Review
          </button>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Write ReviewQueueItem CSS**

```css
/* frontend/src/components/smart-docs/ReviewQueueItem.css */
.rqi {
  display: grid;
  grid-template-columns: 80px 1fr 150px 140px auto;
  align-items: center;
  gap: var(--space-md);
  padding: var(--space-md);
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-base);
  background: var(--color-bg-surface);
  transition: all 150ms ease;
}

.rqi:hover {
  box-shadow: var(--shadow-sm);
}

.rqi--claimed {
  opacity: 0.7;
}

.rqi--critical {
  border-left: 3px solid var(--color-error);
}

.rqi--high {
  border-left: 3px solid var(--color-warning);
}

.rqi__doc-type {
  font-weight: var(--weight-semibold);
  font-size: var(--font-sm);
}

.rqi__borrower {
  font-size: var(--font-sm);
  color: var(--color-text-primary);
}

.rqi__loan {
  font-size: var(--font-xs);
  color: var(--color-text-tertiary);
}

.rqi__meta {
  display: flex;
  flex-direction: column;
  gap: 2px;
  font-size: var(--font-xs);
  color: var(--color-text-secondary);
}

.rqi__confidence {
  font-weight: var(--weight-semibold);
  color: var(--color-primary);
}

.rqi__status {
  font-size: var(--font-xs);
}

.rqi__claimed-by {
  color: var(--color-text-tertiary);
}

.rqi__claimed-by--mine {
  color: var(--color-primary);
  font-weight: var(--weight-semibold);
}

.rqi__actions {
  display: flex;
  gap: var(--space-xs);
}

.rqi__actions .btn-primary,
.rqi__actions .btn-secondary {
  padding: var(--space-xs) var(--space-sm);
  font-size: var(--font-xs);
}

@media (max-width: 768px) {
  .rqi {
    grid-template-columns: 1fr;
    gap: var(--space-sm);
  }

  .rqi__actions {
    justify-content: flex-end;
  }
}
```

- [ ] **Step 3: Write SmartDocsReviewQueue page**

```jsx
// frontend/src/pages/SmartDocsReviewQueue.js
import React, { useState } from 'react';
import { toast } from 'react-hot-toast';
import useReviewQueue from '../hooks/useReviewQueue';
import ReviewQueueItem from '../components/smart-docs/ReviewQueueItem';
import AnalyticsCard from '../components/smart-docs/AnalyticsCard';
import * as reviewApi from '../services/docReviewApi';
import './SmartDocsReviewQueue.css';

const PRIORITY_FILTERS = ['ALL', 'CRITICAL', 'HIGH', 'NORMAL', 'LOW'];

export default function SmartDocsReviewQueue() {
  const [priorityFilter, setPriorityFilter] = useState('ALL');
  const [selectedDoc, setSelectedDoc] = useState(null);
  const {
    items, stats, total, loading, error,
    setFilters, nextPage, prevPage, claim, release, refresh, filters,
  } = useReviewQueue();

  const currentUserId = localStorage.getItem('userId');

  const handlePriorityFilter = (priority) => {
    setPriorityFilter(priority);
    setFilters(priority === 'ALL' ? {} : { priority });
  };

  const handleClaim = async (docId) => {
    try {
      await claim(docId, currentUserId);
      toast.success('Document claimed');
    } catch (err) {
      toast.error(`Claim failed: ${err.message}`);
    }
  };

  const handleRelease = async (docId) => {
    try {
      await release(docId);
      toast.success('Document released');
    } catch (err) {
      toast.error(`Release failed: ${err.message}`);
    }
  };

  const handleAiReview = async (docId) => {
    try {
      const result = await reviewApi.aiReview(docId);
      toast.success(`AI decision: ${result.decision} (${result.confidence}% confidence)`);
      refresh();
    } catch (err) {
      toast.error(`AI review failed: ${err.message}`);
    }
  };

  const handleBatchAiReview = async () => {
    const unclaimed = items.filter((i) => !i.claimed_by);
    if (unclaimed.length === 0) {
      toast.error('No unclaimed documents to review');
      return;
    }
    const loanIds = [...new Set(unclaimed.map((i) => i.loan_id))];
    try {
      for (const loanId of loanIds) {
        await reviewApi.batchAiReview(loanId);
      }
      toast.success(`Batch AI review complete for ${loanIds.length} loans`);
      refresh();
    } catch (err) {
      toast.error(`Batch review failed: ${err.message}`);
    }
  };

  if (error) {
    return <div className="error">{error}</div>;
  }

  return (
    <div className="sd-review-queue">
      <div className="sd-review-queue__header">
        <div>
          <h1 className="sd-review-queue__title">Document Review Queue</h1>
          <p className="sd-review-queue__subtitle">
            Claim, review, and approve uploaded documents
          </p>
        </div>
        <div className="sd-review-queue__actions">
          <button onClick={handleBatchAiReview} className="btn-secondary">
            Batch AI Review
          </button>
          <button onClick={refresh} className="btn-secondary">Refresh</button>
        </div>
      </div>

      {stats && (
        <div className="sd-review-queue__stats">
          <AnalyticsCard title="In Queue" value={stats.total || 0} />
          <AnalyticsCard title="High Priority" value={stats.high_priority || 0} status={stats.high_priority > 0 ? 'error' : undefined} />
          <AnalyticsCard title="Claimed" value={stats.claimed || 0} />
          <AnalyticsCard title="Avg Wait" value={stats.avg_wait_hours ? `${Math.round(stats.avg_wait_hours)}h` : 'N/A'} />
        </div>
      )}

      <div className="sd-review-queue__filters">
        {PRIORITY_FILTERS.map((p) => (
          <button
            key={p}
            className={`sd-review-queue__filter-btn${priorityFilter === p ? ' sd-review-queue__filter-btn--active' : ''}`}
            onClick={() => handlePriorityFilter(p)}
          >
            {p}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="loading">Loading queue...</div>
      ) : items.length === 0 ? (
        <div className="sd-review-queue__empty">
          <p>No documents in queue</p>
        </div>
      ) : (
        <div className="sd-review-queue__list">
          {items.map((doc) => (
            <ReviewQueueItem
              key={doc.id}
              document={doc}
              onClaim={handleClaim}
              onRelease={handleRelease}
              onAiReview={handleAiReview}
              onViewDetail={setSelectedDoc}
              currentUserId={currentUserId}
            />
          ))}
        </div>
      )}

      <div className="sd-review-queue__pagination">
        <button
          onClick={prevPage}
          disabled={filters.offset === 0}
          className="btn-secondary"
        >
          Previous
        </button>
        <span className="sd-review-queue__page-info">
          Showing {filters.offset + 1}–{Math.min(filters.offset + filters.limit, total)} of {total}
        </span>
        <button
          onClick={nextPage}
          disabled={filters.offset + filters.limit >= total}
          className="btn-secondary"
        >
          Next
        </button>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Write SmartDocsReviewQueue CSS**

```css
/* frontend/src/pages/SmartDocsReviewQueue.css */
.sd-review-queue {
  padding: var(--space-lg);
  max-width: 1200px;
  margin: 0 auto;
}

.sd-review-queue__header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: var(--space-lg);
}

.sd-review-queue__title {
  font-size: var(--font-2xl);
  font-weight: var(--weight-bold);
  margin-bottom: var(--space-xs);
}

.sd-review-queue__subtitle {
  font-size: var(--font-sm);
  color: var(--color-text-secondary);
}

.sd-review-queue__actions {
  display: flex;
  gap: var(--space-sm);
}

.sd-review-queue__stats {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: var(--space-md);
  margin-bottom: var(--space-lg);
}

.sd-review-queue__filters {
  display: flex;
  gap: var(--space-xs);
  margin-bottom: var(--space-md);
  border-bottom: 1px solid var(--color-border-light);
  padding-bottom: var(--space-sm);
}

.sd-review-queue__filter-btn {
  padding: var(--space-xs) var(--space-md);
  background: none;
  border: 1px solid transparent;
  border-radius: var(--radius-full);
  font-size: var(--font-sm);
  color: var(--color-text-secondary);
  cursor: pointer;
}

.sd-review-queue__filter-btn--active {
  background: var(--color-primary);
  color: white;
  border-color: var(--color-primary);
}

.sd-review-queue__list {
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
}

.sd-review-queue__empty {
  text-align: center;
  padding: var(--space-xl);
  color: var(--color-text-tertiary);
}

.sd-review-queue__pagination {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: var(--space-md);
  margin-top: var(--space-lg);
  padding-top: var(--space-md);
  border-top: 1px solid var(--color-border-light);
}

.sd-review-queue__page-info {
  font-size: var(--font-sm);
  color: var(--color-text-secondary);
}

@media (max-width: 768px) {
  .sd-review-queue__header {
    flex-direction: column;
    gap: var(--space-md);
  }

  .sd-review-queue__stats {
    grid-template-columns: repeat(2, 1fr);
  }

  .sd-review-queue__filters {
    overflow-x: auto;
  }
}

@media (max-width: 480px) {
  .sd-review-queue {
    padding: var(--space-md);
  }

  .sd-review-queue__stats {
    grid-template-columns: 1fr;
  }
}
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/SmartDocsReviewQueue.js frontend/src/pages/SmartDocsReviewQueue.css frontend/src/components/smart-docs/ReviewQueueItem.jsx frontend/src/components/smart-docs/ReviewQueueItem.css
git commit -m "feat(smart-docs): add review queue page with claim/release/AI review"
```

---

## Task 9: Security & Audit Page

**Files:**
- Create: `frontend/src/pages/SmartDocsSecurity.js`
- Create: `frontend/src/pages/SmartDocsSecurity.css`

- [ ] **Step 1: Write the page component**

```jsx
// frontend/src/pages/SmartDocsSecurity.js
import React, { useState, useEffect } from 'react';
import { toast } from 'react-hot-toast';
import AnalyticsCard from '../components/smart-docs/AnalyticsCard';
import * as securityApi from '../services/docSecurityApi';
import './SmartDocsSecurity.css';

export default function SmartDocsSecurity() {
  const [activeTab, setActiveTab] = useState('audit');
  const [auditLog, setAuditLog] = useState(null);
  const [compliance, setCompliance] = useState(null);
  const [suspicious, setSuspicious] = useState(null);
  const [retentionPolicies, setRetentionPolicies] = useState([]);
  const [loading, setLoading] = useState(true);
  const [days, setDays] = useState(30);

  useEffect(() => {
    async function load() {
      setLoading(true);
      try {
        const [auditData, complianceData, suspiciousData, policies] = await Promise.all([
          securityApi.getAuditLog({ days }),
          securityApi.getComplianceReport(days),
          securityApi.getSuspiciousActivity(days),
          securityApi.getRetentionPolicies(),
        ]);
        setAuditLog(auditData);
        setCompliance(complianceData);
        setSuspicious(suspiciousData);
        setRetentionPolicies(policies.policies || []);
      } catch (err) {
        toast.error(`Failed to load security data: ${err.message}`);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [days]);

  const tabs = [
    { id: 'audit', label: 'Audit Log' },
    { id: 'compliance', label: 'Compliance Report' },
    { id: 'suspicious', label: 'Suspicious Activity' },
    { id: 'retention', label: 'Retention Policies' },
  ];

  if (loading) {
    return <div className="loading">Loading security data...</div>;
  }

  return (
    <div className="sd-security">
      <div className="sd-security__header">
        <div>
          <h1 className="sd-security__title">Security & Compliance</h1>
          <p className="sd-security__subtitle">Document audit trail, integrity, and retention</p>
        </div>
        <select value={days} onChange={(e) => setDays(Number(e.target.value))}>
          <option value={7}>7 days</option>
          <option value={30}>30 days</option>
          <option value={90}>90 days</option>
          <option value={365}>1 year</option>
        </select>
      </div>

      <div className="sd-security__tabs">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            className={`sd-security__tab${activeTab === tab.id ? ' sd-security__tab--active' : ''}`}
            onClick={() => setActiveTab(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {activeTab === 'audit' && auditLog && (
        <div className="sd-security__section">
          <div className="sd-security__table-container">
            <table className="sd-security__table">
              <thead>
                <tr>
                  <th>Timestamp</th>
                  <th>User</th>
                  <th>Action</th>
                  <th>Document</th>
                  <th>Details</th>
                </tr>
              </thead>
              <tbody>
                {(auditLog.entries || []).map((entry, i) => (
                  <tr key={i}>
                    <td>{entry.timestamp ? new Date(entry.timestamp).toLocaleString() : 'N/A'}</td>
                    <td>{entry.user_name || entry.user_id}</td>
                    <td>
                      <span className={`badge badge-${entry.action === 'DELETE' ? 'error' : entry.action === 'DOWNLOAD' ? 'warning' : 'success'}`}>
                        {entry.action}
                      </span>
                    </td>
                    <td>{entry.document_name || entry.document_id}</td>
                    <td className="sd-security__details-cell">{entry.details}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {activeTab === 'compliance' && compliance && (
        <div className="sd-security__section">
          <div className="sd-security__grid">
            <AnalyticsCard
              title="Compliance Score"
              value={compliance.score != null ? `${Math.round(compliance.score)}%` : 'N/A'}
              status={compliance.score >= 90 ? 'success' : compliance.score >= 70 ? 'warning' : 'error'}
            />
            <AnalyticsCard
              title="Encrypted Documents"
              value={compliance.encrypted || 0}
              subtitle={`of ${compliance.total_documents || 0} total`}
            />
            <AnalyticsCard
              title="Integrity Verified"
              value={compliance.integrity_verified || 0}
            />
            <AnalyticsCard
              title="Retention Compliant"
              value={compliance.retention_compliant || 0}
            />
          </div>
          {compliance.issues && compliance.issues.length > 0 && (
            <div className="sd-security__issues">
              <h3>Open Issues</h3>
              {compliance.issues.map((issue, i) => (
                <div key={i} className="sd-security__issue">
                  <span className={`badge badge-${issue.severity === 'high' ? 'error' : 'warning'}`}>
                    {issue.severity}
                  </span>
                  <span>{issue.description}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {activeTab === 'suspicious' && suspicious && (
        <div className="sd-security__section">
          {(suspicious.alerts || []).length === 0 ? (
            <p className="sd-security__empty">No suspicious activity detected</p>
          ) : (
            <div className="sd-security__alerts">
              {suspicious.alerts.map((alert, i) => (
                <div key={i} className={`sd-security__alert sd-security__alert--${alert.severity || 'low'}`}>
                  <div className="sd-security__alert-header">
                    <span className="sd-security__alert-type">{alert.type}</span>
                    <span className={`badge badge-${alert.severity === 'high' ? 'error' : 'warning'}`}>
                      {alert.severity}
                    </span>
                  </div>
                  <p>{alert.description}</p>
                  <div className="sd-security__alert-meta">
                    <span>{alert.timestamp ? new Date(alert.timestamp).toLocaleString() : ''}</span>
                    <span>{alert.user_name}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {activeTab === 'retention' && (
        <div className="sd-security__section">
          <div className="sd-security__table-container">
            <table className="sd-security__table">
              <thead>
                <tr>
                  <th>Policy Name</th>
                  <th>Doc Type</th>
                  <th>Retention Days</th>
                  <th>Action</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {retentionPolicies.map((policy) => (
                  <tr key={policy.id}>
                    <td>{policy.name}</td>
                    <td>{policy.doc_type || 'All'}</td>
                    <td>{policy.retention_days}</td>
                    <td>{policy.action}</td>
                    <td>
                      <span className={`badge badge-${policy.active ? 'success' : 'warning'}`}>
                        {policy.active ? 'Active' : 'Inactive'}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Write the CSS**

```css
/* frontend/src/pages/SmartDocsSecurity.css */
.sd-security {
  padding: var(--space-lg);
  max-width: 1200px;
  margin: 0 auto;
}

.sd-security__header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: var(--space-lg);
}

.sd-security__title {
  font-size: var(--font-2xl);
  font-weight: var(--weight-bold);
  margin-bottom: var(--space-xs);
}

.sd-security__subtitle {
  font-size: var(--font-sm);
  color: var(--color-text-secondary);
}

.sd-security__tabs {
  display: flex;
  gap: var(--space-xs);
  border-bottom: 1px solid var(--color-border-light);
  margin-bottom: var(--space-lg);
}

.sd-security__tab {
  padding: var(--space-sm) var(--space-md);
  background: none;
  border: none;
  border-bottom: 2px solid transparent;
  color: var(--color-text-secondary);
  font-size: var(--font-sm);
  cursor: pointer;
}

.sd-security__tab--active {
  color: var(--color-primary);
  border-bottom-color: var(--color-primary);
}

.sd-security__section {
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
}

.sd-security__grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: var(--space-md);
}

.sd-security__table-container {
  overflow-x: auto;
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-md);
}

.sd-security__table {
  width: 100%;
  border-collapse: collapse;
}

.sd-security__table th,
.sd-security__table td {
  padding: var(--space-sm) var(--space-md);
  text-align: left;
  font-size: var(--font-sm);
  border-bottom: 1px solid var(--color-border-light);
}

.sd-security__table th {
  background: var(--color-bg-secondary);
  font-weight: var(--weight-semibold);
  color: var(--color-text-secondary);
  text-transform: uppercase;
  font-size: var(--font-xs);
  letter-spacing: 0.5px;
}

.sd-security__details-cell {
  max-width: 300px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.sd-security__issues {
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
}

.sd-security__issues h3 {
  font-size: var(--font-md);
  font-weight: var(--weight-semibold);
}

.sd-security__issue {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  padding: var(--space-sm) var(--space-md);
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-base);
  font-size: var(--font-sm);
}

.sd-security__empty {
  text-align: center;
  padding: var(--space-xl);
  color: var(--color-text-tertiary);
}

.sd-security__alerts {
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
}

.sd-security__alert {
  padding: var(--space-md);
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-md);
  border-left: 3px solid var(--color-info);
}

.sd-security__alert--high {
  border-left-color: var(--color-error);
}

.sd-security__alert--medium {
  border-left-color: var(--color-warning);
}

.sd-security__alert-header {
  display: flex;
  justify-content: space-between;
  margin-bottom: var(--space-xs);
}

.sd-security__alert-type {
  font-weight: var(--weight-semibold);
}

.sd-security__alert-meta {
  display: flex;
  gap: var(--space-lg);
  font-size: var(--font-xs);
  color: var(--color-text-tertiary);
  margin-top: var(--space-sm);
}

@media (max-width: 768px) {
  .sd-security__grid {
    grid-template-columns: repeat(2, 1fr);
  }

  .sd-security__header {
    flex-direction: column;
    gap: var(--space-md);
  }
}

@media (max-width: 480px) {
  .sd-security {
    padding: var(--space-md);
  }

  .sd-security__grid {
    grid-template-columns: 1fr;
  }
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/SmartDocsSecurity.js frontend/src/pages/SmartDocsSecurity.css
git commit -m "feat(smart-docs): add security & compliance page with audit log, fraud, retention"
```

---

## Task 10: Bank Analysis Page

**Files:**
- Create: `frontend/src/pages/SmartDocsBankAnalysis.js`
- Create: `frontend/src/pages/SmartDocsBankAnalysis.css`
- Create: `frontend/src/components/smart-docs/BankAnalysisPanel.jsx`
- Create: `frontend/src/components/smart-docs/BankAnalysisPanel.css`

- [ ] **Step 1: Write BankAnalysisPanel component**

```jsx
// frontend/src/components/smart-docs/BankAnalysisPanel.jsx
import React from 'react';
import './BankAnalysisPanel.css';

export default function BankAnalysisPanel({ analysis, onSourceDeposit }) {
  if (!analysis) return null;

  return (
    <div className="bap">
      <div className="bap__header">
        <h3 className="bap__title">Bank Statement Analysis</h3>
        {analysis.risk_level && (
          <span className={`badge badge-${analysis.risk_level === 'HIGH' ? 'error' : analysis.risk_level === 'MEDIUM' ? 'warning' : 'success'}`}>
            Risk: {analysis.risk_level}
          </span>
        )}
      </div>

      {analysis.summary && (
        <div className="bap__summary">
          <div className="bap__summary-item">
            <span className="bap__label">Avg Monthly Balance</span>
            <span className="bap__value">${(analysis.summary.avg_balance || 0).toLocaleString()}</span>
          </div>
          <div className="bap__summary-item">
            <span className="bap__label">Avg Monthly Income</span>
            <span className="bap__value">${(analysis.summary.avg_income || 0).toLocaleString()}</span>
          </div>
          <div className="bap__summary-item">
            <span className="bap__label">Avg Monthly Expenses</span>
            <span className="bap__value">${(analysis.summary.avg_expenses || 0).toLocaleString()}</span>
          </div>
        </div>
      )}

      {analysis.large_deposits && analysis.large_deposits.length > 0 && (
        <div className="bap__section">
          <h4>Large Deposits</h4>
          <table className="bap__table">
            <thead>
              <tr>
                <th>Date</th>
                <th>Amount</th>
                <th>Description</th>
                <th>Sourced</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {analysis.large_deposits.map((dep) => (
                <tr key={dep.id}>
                  <td>{dep.date ? new Date(dep.date).toLocaleDateString() : 'N/A'}</td>
                  <td className="bap__amount">${(dep.amount || 0).toLocaleString()}</td>
                  <td>{dep.description}</td>
                  <td>
                    <span className={`badge badge-${dep.sourced ? 'success' : 'error'}`}>
                      {dep.sourced ? 'Yes' : 'No'}
                    </span>
                  </td>
                  <td>
                    {!dep.sourced && onSourceDeposit && (
                      <button
                        className="btn-secondary"
                        style={{ padding: '2px 8px', fontSize: 'var(--font-xs)' }}
                        onClick={() => onSourceDeposit(dep)}
                      >
                        Source
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {analysis.nsf_overdrafts && analysis.nsf_overdrafts.length > 0 && (
        <div className="bap__section">
          <h4>NSF / Overdrafts</h4>
          <div className="bap__flag-list">
            {analysis.nsf_overdrafts.map((nsf, i) => (
              <div key={i} className="bap__flag bap__flag--error">
                <span>{nsf.date ? new Date(nsf.date).toLocaleDateString() : ''}</span>
                <span>${(nsf.amount || 0).toLocaleString()}</span>
                <span>{nsf.description}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {analysis.undisclosed_debts && analysis.undisclosed_debts.length > 0 && (
        <div className="bap__section">
          <h4>Undisclosed Debts</h4>
          <div className="bap__flag-list">
            {analysis.undisclosed_debts.map((debt, i) => (
              <div key={i} className="bap__flag bap__flag--warning">
                <span>{debt.payee}</span>
                <span>${(debt.monthly_amount || 0).toLocaleString()}/mo</span>
                <span>{debt.category}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Write BankAnalysisPanel CSS**

```css
/* frontend/src/components/smart-docs/BankAnalysisPanel.css */
.bap {
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-md);
  background: var(--color-bg-surface);
}

.bap__header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--space-md) var(--space-lg);
  border-bottom: 1px solid var(--color-border-light);
}

.bap__title {
  font-size: var(--font-md);
  font-weight: var(--weight-semibold);
}

.bap__summary {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: var(--space-md);
  padding: var(--space-md) var(--space-lg);
  background: var(--color-bg-secondary);
}

.bap__summary-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.bap__label {
  font-size: var(--font-xs);
  color: var(--color-text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.bap__value {
  font-size: var(--font-lg);
  font-weight: var(--weight-bold);
}

.bap__section {
  padding: var(--space-md) var(--space-lg);
  border-top: 1px solid var(--color-border-light);
}

.bap__section h4 {
  font-size: var(--font-sm);
  font-weight: var(--weight-semibold);
  margin-bottom: var(--space-sm);
}

.bap__table {
  width: 100%;
  border-collapse: collapse;
}

.bap__table th,
.bap__table td {
  padding: var(--space-xs) var(--space-sm);
  text-align: left;
  font-size: var(--font-sm);
  border-bottom: 1px solid var(--color-border-light);
}

.bap__table th {
  font-weight: var(--weight-semibold);
  color: var(--color-text-secondary);
  font-size: var(--font-xs);
  text-transform: uppercase;
}

.bap__amount {
  font-weight: var(--weight-semibold);
}

.bap__flag-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-xs);
}

.bap__flag {
  display: flex;
  gap: var(--space-md);
  padding: var(--space-xs) var(--space-sm);
  border-radius: var(--radius-base);
  font-size: var(--font-sm);
}

.bap__flag--error {
  background: rgba(192, 21, 47, 0.05);
  border-left: 2px solid var(--color-error);
}

.bap__flag--warning {
  background: rgba(168, 75, 47, 0.05);
  border-left: 2px solid var(--color-warning);
}

@media (max-width: 480px) {
  .bap__summary {
    grid-template-columns: 1fr;
  }
}
```

- [ ] **Step 3: Write SmartDocsBankAnalysis page**

```jsx
// frontend/src/pages/SmartDocsBankAnalysis.js
import React, { useState, useEffect } from 'react';
import { toast } from 'react-hot-toast';
import AnalyticsCard from '../components/smart-docs/AnalyticsCard';
import BankAnalysisPanel from '../components/smart-docs/BankAnalysisPanel';
import * as bankApi from '../services/docBankAnalysisApi';
import * as analyticsApi from '../services/docAnalyticsApi';
import './SmartDocsBankAnalysis.css';

export default function SmartDocsBankAnalysis() {
  const [loanSearch, setLoanSearch] = useState('');
  const [selectedLoan, setSelectedLoan] = useState(null);
  const [analysis, setAnalysis] = useState(null);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    analyticsApi.getBankAnalysisSummary(30).then(setSummary).catch(() => {});
  }, []);

  const handleSearch = async () => {
    if (!loanSearch.trim()) return;
    setLoading(true);
    try {
      const data = await bankApi.getBankSummary(loanSearch.trim());
      setSelectedLoan(loanSearch.trim());
      setAnalysis(data);
    } catch (err) {
      toast.error(`Failed to load bank analysis: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleSourceDeposit = async (deposit) => {
    const source = window.prompt('Enter deposit source description:');
    if (!source) return;
    try {
      await bankApi.sourceDeposit(deposit.id, { source, verified: false });
      toast.success('Deposit sourcing saved');
      handleSearch();
    } catch (err) {
      toast.error(`Failed to source deposit: ${err.message}`);
    }
  };

  return (
    <div className="sd-bank">
      <div className="sd-bank__header">
        <div>
          <h1 className="sd-bank__title">Bank Statement Analysis</h1>
          <p className="sd-bank__subtitle">
            Large deposits, NSF/overdrafts, undisclosed debts, risk scoring
          </p>
        </div>
      </div>

      {summary && (
        <div className="sd-bank__summary-grid">
          <AnalyticsCard title="Total Analyzed" value={summary.total_analyzed || 0} subtitle="Last 30 days" />
          <AnalyticsCard title="Flagged" value={summary.flagged || 0} status={summary.flagged > 0 ? 'warning' : 'success'} />
          <AnalyticsCard title="Unsourced Deposits" value={summary.unsourced_deposits || 0} status={summary.unsourced_deposits > 0 ? 'error' : 'success'} />
          <AnalyticsCard title="Avg Risk Score" value={summary.avg_risk_score || 'N/A'} />
        </div>
      )}

      <div className="sd-bank__search">
        <input
          type="text"
          placeholder="Enter Loan ID to analyze..."
          value={loanSearch}
          onChange={(e) => setLoanSearch(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
        />
        <button onClick={handleSearch} className="btn-primary" disabled={loading}>
          {loading ? 'Loading...' : 'Analyze'}
        </button>
      </div>

      {analysis && (
        <BankAnalysisPanel
          analysis={analysis}
          onSourceDeposit={handleSourceDeposit}
        />
      )}
    </div>
  );
}
```

- [ ] **Step 4: Write SmartDocsBankAnalysis CSS**

```css
/* frontend/src/pages/SmartDocsBankAnalysis.css */
.sd-bank {
  padding: var(--space-lg);
  max-width: 1200px;
  margin: 0 auto;
}

.sd-bank__header {
  margin-bottom: var(--space-lg);
}

.sd-bank__title {
  font-size: var(--font-2xl);
  font-weight: var(--weight-bold);
  margin-bottom: var(--space-xs);
}

.sd-bank__subtitle {
  font-size: var(--font-sm);
  color: var(--color-text-secondary);
}

.sd-bank__summary-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: var(--space-md);
  margin-bottom: var(--space-lg);
}

.sd-bank__search {
  display: flex;
  gap: var(--space-sm);
  margin-bottom: var(--space-lg);
}

.sd-bank__search input {
  flex: 1;
  max-width: 400px;
}

@media (max-width: 768px) {
  .sd-bank__summary-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 480px) {
  .sd-bank {
    padding: var(--space-md);
  }

  .sd-bank__summary-grid {
    grid-template-columns: 1fr;
  }

  .sd-bank__search {
    flex-direction: column;
  }

  .sd-bank__search input {
    max-width: none;
  }
}
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/SmartDocsBankAnalysis.js frontend/src/pages/SmartDocsBankAnalysis.css frontend/src/components/smart-docs/BankAnalysisPanel.jsx frontend/src/components/smart-docs/BankAnalysisPanel.css
git commit -m "feat(smart-docs): add bank statement analysis page with risk scoring"
```

---

## Task 11: Income Calculation Page

**Files:**
- Create: `frontend/src/pages/SmartDocsIncome.js`
- Create: `frontend/src/pages/SmartDocsIncome.css`
- Create: `frontend/src/components/smart-docs/IncomeWorksheet.jsx`
- Create: `frontend/src/components/smart-docs/IncomeWorksheet.css`

- [ ] **Step 1: Write IncomeWorksheet component**

```jsx
// frontend/src/components/smart-docs/IncomeWorksheet.jsx
import React from 'react';
import './IncomeWorksheet.css';

export default function IncomeWorksheet({ income, onApprove, onReject, onOverrideSource }) {
  if (!income) return null;

  const totalMonthly = (income.sources || []).reduce(
    (sum, s) => sum + (s.monthly_amount || 0),
    0
  );

  return (
    <div className="iw">
      <div className="iw__header">
        <div>
          <h3 className="iw__title">Income Calculation</h3>
          <span className="iw__status">
            <span className={`badge badge-${income.status === 'APPROVED' ? 'success' : income.status === 'REJECTED' ? 'error' : 'warning'}`}>
              {income.status || 'PENDING'}
            </span>
          </span>
        </div>
        <div className="iw__total">
          <span className="iw__total-label">Total Monthly Income</span>
          <span className="iw__total-value">${totalMonthly.toLocaleString()}</span>
        </div>
      </div>

      <table className="iw__table">
        <thead>
          <tr>
            <th>Source</th>
            <th>Type</th>
            <th>Monthly Amount</th>
            <th>Confidence</th>
            <th>Verified</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {(income.sources || []).map((source) => (
            <tr key={source.id}>
              <td className="iw__source-name">{source.name || source.employer}</td>
              <td>{source.income_type}</td>
              <td className="iw__amount">${(source.monthly_amount || 0).toLocaleString()}</td>
              <td>
                <span className={`iw__confidence iw__confidence--${source.confidence >= 90 ? 'high' : source.confidence >= 70 ? 'medium' : 'low'}`}>
                  {source.confidence || 0}%
                </span>
              </td>
              <td>
                <span className={`badge badge-${source.verified ? 'success' : 'warning'}`}>
                  {source.verified ? 'Yes' : 'No'}
                </span>
              </td>
              <td>
                {onOverrideSource && (
                  <button
                    className="btn-secondary"
                    style={{ padding: '2px 8px', fontSize: 'var(--font-xs)' }}
                    onClick={() => onOverrideSource(source)}
                  >
                    Override
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {income.status !== 'APPROVED' && income.status !== 'REJECTED' && (
        <div className="iw__actions">
          {onApprove && (
            <button className="btn-primary" onClick={onApprove}>
              Approve Income
            </button>
          )}
          {onReject && (
            <button className="btn-secondary" onClick={onReject}>
              Reject
            </button>
          )}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Write IncomeWorksheet CSS**

```css
/* frontend/src/components/smart-docs/IncomeWorksheet.css */
.iw {
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-md);
  background: var(--color-bg-surface);
  overflow: hidden;
}

.iw__header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--space-md) var(--space-lg);
  background: var(--color-bg-secondary);
  border-bottom: 1px solid var(--color-border-light);
}

.iw__title {
  font-size: var(--font-md);
  font-weight: var(--weight-semibold);
  margin-bottom: var(--space-xs);
}

.iw__total {
  text-align: right;
}

.iw__total-label {
  display: block;
  font-size: var(--font-xs);
  color: var(--color-text-tertiary);
  text-transform: uppercase;
}

.iw__total-value {
  font-size: var(--font-xl);
  font-weight: var(--weight-bold);
  color: var(--color-primary);
}

.iw__table {
  width: 100%;
  border-collapse: collapse;
}

.iw__table th,
.iw__table td {
  padding: var(--space-sm) var(--space-md);
  text-align: left;
  font-size: var(--font-sm);
  border-bottom: 1px solid var(--color-border-light);
}

.iw__table th {
  font-weight: var(--weight-semibold);
  color: var(--color-text-secondary);
  font-size: var(--font-xs);
  text-transform: uppercase;
}

.iw__source-name {
  font-weight: var(--weight-medium);
}

.iw__amount {
  font-weight: var(--weight-semibold);
}

.iw__confidence {
  font-weight: var(--weight-semibold);
}

.iw__confidence--high { color: var(--color-success); }
.iw__confidence--medium { color: var(--color-warning); }
.iw__confidence--low { color: var(--color-error); }

.iw__actions {
  display: flex;
  gap: var(--space-sm);
  padding: var(--space-md) var(--space-lg);
  justify-content: flex-end;
  border-top: 1px solid var(--color-border-light);
}

@media (max-width: 768px) {
  .iw__header {
    flex-direction: column;
    gap: var(--space-sm);
    align-items: flex-start;
  }

  .iw__total {
    text-align: left;
  }
}
```

- [ ] **Step 3: Write SmartDocsIncome page**

```jsx
// frontend/src/pages/SmartDocsIncome.js
import React, { useState, useEffect } from 'react';
import { toast } from 'react-hot-toast';
import AnalyticsCard from '../components/smart-docs/AnalyticsCard';
import IncomeWorksheet from '../components/smart-docs/IncomeWorksheet';
import * as incomeApi from '../services/docIncomeApi';
import * as analyticsApi from '../services/docAnalyticsApi';
import './SmartDocsIncome.css';

export default function SmartDocsIncome() {
  const [loanSearch, setLoanSearch] = useState('');
  const [incomeData, setIncomeData] = useState(null);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    analyticsApi.getIncomeSummary(30).then(setSummary).catch(() => {});
  }, []);

  const handleSearch = async () => {
    if (!loanSearch.trim()) return;
    setLoading(true);
    try {
      const data = await incomeApi.getIncomeSources(loanSearch.trim());
      setIncomeData(data);
    } catch (err) {
      toast.error(`Failed to load income data: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleCalculate = async () => {
    if (!loanSearch.trim()) return;
    setLoading(true);
    try {
      const data = await incomeApi.calculateIncome(loanSearch.trim());
      setIncomeData(data);
      toast.success('Income calculated');
    } catch (err) {
      toast.error(`Calculation failed: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleApprove = async () => {
    try {
      await incomeApi.approveIncome(loanSearch.trim(), 'Approved via Smart Docs');
      toast.success('Income approved');
      handleSearch();
    } catch (err) {
      toast.error(`Approval failed: ${err.message}`);
    }
  };

  const handleReject = async () => {
    const reason = window.prompt('Rejection reason:');
    if (!reason) return;
    try {
      await incomeApi.rejectIncome(loanSearch.trim(), reason);
      toast.success('Income rejected');
      handleSearch();
    } catch (err) {
      toast.error(`Rejection failed: ${err.message}`);
    }
  };

  const handleOverrideSource = async (source) => {
    const newAmount = window.prompt(`Override monthly amount for ${source.name}:`, source.monthly_amount);
    if (!newAmount) return;
    try {
      await incomeApi.overrideSource(source.id, {
        monthly_amount: parseFloat(newAmount),
        reason: 'Manual override via Smart Docs UI',
      });
      toast.success('Source overridden');
      handleSearch();
    } catch (err) {
      toast.error(`Override failed: ${err.message}`);
    }
  };

  return (
    <div className="sd-income">
      <div className="sd-income__header">
        <div>
          <h1 className="sd-income__title">Income Calculation</h1>
          <p className="sd-income__subtitle">
            AI-powered income calculation with maker-checker approval
          </p>
        </div>
      </div>

      {summary && (
        <div className="sd-income__summary-grid">
          <AnalyticsCard title="Total Calculated" value={summary.total_calculated || 0} subtitle="Last 30 days" />
          <AnalyticsCard title="Pending Approval" value={summary.pending_approval || 0} status={summary.pending_approval > 0 ? 'warning' : 'success'} />
          <AnalyticsCard title="Approved" value={summary.approved || 0} status="success" />
          <AnalyticsCard title="Avg Confidence" value={summary.avg_confidence ? `${Math.round(summary.avg_confidence)}%` : 'N/A'} />
        </div>
      )}

      <div className="sd-income__search">
        <input
          type="text"
          placeholder="Enter Loan ID..."
          value={loanSearch}
          onChange={(e) => setLoanSearch(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
        />
        <button onClick={handleSearch} className="btn-secondary" disabled={loading}>
          Load
        </button>
        <button onClick={handleCalculate} className="btn-primary" disabled={loading}>
          {loading ? 'Calculating...' : 'Calculate Income'}
        </button>
      </div>

      {incomeData && (
        <IncomeWorksheet
          income={incomeData}
          onApprove={handleApprove}
          onReject={handleReject}
          onOverrideSource={handleOverrideSource}
        />
      )}
    </div>
  );
}
```

- [ ] **Step 4: Write SmartDocsIncome CSS**

```css
/* frontend/src/pages/SmartDocsIncome.css */
.sd-income {
  padding: var(--space-lg);
  max-width: 1200px;
  margin: 0 auto;
}

.sd-income__header {
  margin-bottom: var(--space-lg);
}

.sd-income__title {
  font-size: var(--font-2xl);
  font-weight: var(--weight-bold);
  margin-bottom: var(--space-xs);
}

.sd-income__subtitle {
  font-size: var(--font-sm);
  color: var(--color-text-secondary);
}

.sd-income__summary-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: var(--space-md);
  margin-bottom: var(--space-lg);
}

.sd-income__search {
  display: flex;
  gap: var(--space-sm);
  margin-bottom: var(--space-lg);
}

.sd-income__search input {
  flex: 1;
  max-width: 400px;
}

@media (max-width: 768px) {
  .sd-income__summary-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 480px) {
  .sd-income {
    padding: var(--space-md);
  }

  .sd-income__summary-grid {
    grid-template-columns: 1fr;
  }

  .sd-income__search {
    flex-direction: column;
  }

  .sd-income__search input {
    max-width: none;
  }
}
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/SmartDocsIncome.js frontend/src/pages/SmartDocsIncome.css frontend/src/components/smart-docs/IncomeWorksheet.jsx frontend/src/components/smart-docs/IncomeWorksheet.css
git commit -m "feat(smart-docs): add income calculation page with maker-checker approval"
```

---

## Task 12: Admin Configuration Page

**Files:**
- Create: `frontend/src/pages/SmartDocsAdmin.js`
- Create: `frontend/src/pages/SmartDocsAdmin.css`

- [ ] **Step 1: Write the page component**

```jsx
// frontend/src/pages/SmartDocsAdmin.js
import React, { useState, useEffect } from 'react';
import { toast } from 'react-hot-toast';
import * as reviewApi from '../services/docReviewApi';
import * as securityApi from '../services/docSecurityApi';
import './SmartDocsAdmin.css';

export default function SmartDocsAdmin() {
  const [activeTab, setActiveTab] = useState('auto-review');
  const [autoReview, setAutoReview] = useState(null);
  const [retentionPolicies, setRetentionPolicies] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      setLoading(true);
      try {
        const [arSettings, policies] = await Promise.all([
          reviewApi.getAutoReviewSettings(),
          securityApi.getRetentionPolicies(),
        ]);
        setAutoReview(arSettings);
        setRetentionPolicies(policies.policies || []);
      } catch (err) {
        toast.error(`Failed to load settings: ${err.message}`);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  const handleSaveAutoReview = async () => {
    try {
      await reviewApi.updateAutoReviewSettings(autoReview);
      toast.success('Auto-review settings saved');
    } catch (err) {
      toast.error(`Save failed: ${err.message}`);
    }
  };

  const handleCreatePolicy = async () => {
    const name = window.prompt('Policy name:');
    if (!name) return;
    try {
      await securityApi.createRetentionPolicy({
        name,
        doc_type: null,
        retention_days: 2555,
        action: 'archive',
        active: true,
      });
      toast.success('Policy created');
      const policies = await securityApi.getRetentionPolicies();
      setRetentionPolicies(policies.policies || []);
    } catch (err) {
      toast.error(`Create failed: ${err.message}`);
    }
  };

  const tabs = [
    { id: 'auto-review', label: 'Auto-Review Settings' },
    { id: 'retention', label: 'Retention Policies' },
  ];

  if (loading) {
    return <div className="loading">Loading admin settings...</div>;
  }

  return (
    <div className="sd-admin">
      <div className="sd-admin__header">
        <h1 className="sd-admin__title">Smart Docs Administration</h1>
        <p className="sd-admin__subtitle">Configure document review, retention, and compliance settings</p>
      </div>

      <div className="sd-admin__tabs">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            className={`sd-admin__tab${activeTab === tab.id ? ' sd-admin__tab--active' : ''}`}
            onClick={() => setActiveTab(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {activeTab === 'auto-review' && autoReview && (
        <div className="sd-admin__section">
          <div className="sd-admin__card">
            <h3>AI Auto-Review Configuration</h3>
            <div className="sd-admin__form">
              <label className="sd-admin__field">
                <span>Enable Auto-Review</span>
                <input
                  type="checkbox"
                  checked={autoReview.enabled || false}
                  onChange={(e) => setAutoReview({ ...autoReview, enabled: e.target.checked })}
                />
              </label>
              <label className="sd-admin__field">
                <span>Confidence Threshold (%)</span>
                <input
                  type="number"
                  min="50"
                  max="100"
                  value={autoReview.confidence_threshold || 85}
                  onChange={(e) => setAutoReview({ ...autoReview, confidence_threshold: Number(e.target.value) })}
                />
              </label>
              <label className="sd-admin__field">
                <span>Quality Threshold (%)</span>
                <input
                  type="number"
                  min="50"
                  max="100"
                  value={autoReview.quality_threshold || 80}
                  onChange={(e) => setAutoReview({ ...autoReview, quality_threshold: Number(e.target.value) })}
                />
              </label>
              <label className="sd-admin__field">
                <span>Max Auto-Approvals per Day</span>
                <input
                  type="number"
                  min="0"
                  max="1000"
                  value={autoReview.max_daily_auto_approvals || 100}
                  onChange={(e) => setAutoReview({ ...autoReview, max_daily_auto_approvals: Number(e.target.value) })}
                />
              </label>
              <div className="sd-admin__form-actions">
                <button onClick={handleSaveAutoReview} className="btn-primary">
                  Save Settings
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {activeTab === 'retention' && (
        <div className="sd-admin__section">
          <div className="sd-admin__section-header">
            <h3>Document Retention Policies</h3>
            <button onClick={handleCreatePolicy} className="btn-primary">
              Add Policy
            </button>
          </div>
          <div className="sd-admin__table-container">
            <table className="sd-admin__table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Document Type</th>
                  <th>Retention (days)</th>
                  <th>Action</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {retentionPolicies.length === 0 ? (
                  <tr><td colSpan="5" style={{ textAlign: 'center', color: 'var(--color-text-tertiary)' }}>No policies configured</td></tr>
                ) : retentionPolicies.map((policy) => (
                  <tr key={policy.id}>
                    <td>{policy.name}</td>
                    <td>{policy.doc_type || 'All'}</td>
                    <td>{policy.retention_days}</td>
                    <td>{policy.action}</td>
                    <td>
                      <span className={`badge badge-${policy.active ? 'success' : 'warning'}`}>
                        {policy.active ? 'Active' : 'Inactive'}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Write the CSS**

```css
/* frontend/src/pages/SmartDocsAdmin.css */
.sd-admin {
  padding: var(--space-lg);
  max-width: 900px;
  margin: 0 auto;
}

.sd-admin__header {
  margin-bottom: var(--space-lg);
}

.sd-admin__title {
  font-size: var(--font-2xl);
  font-weight: var(--weight-bold);
  margin-bottom: var(--space-xs);
}

.sd-admin__subtitle {
  font-size: var(--font-sm);
  color: var(--color-text-secondary);
}

.sd-admin__tabs {
  display: flex;
  gap: var(--space-xs);
  border-bottom: 1px solid var(--color-border-light);
  margin-bottom: var(--space-lg);
}

.sd-admin__tab {
  padding: var(--space-sm) var(--space-md);
  background: none;
  border: none;
  border-bottom: 2px solid transparent;
  color: var(--color-text-secondary);
  font-size: var(--font-sm);
  cursor: pointer;
}

.sd-admin__tab--active {
  color: var(--color-primary);
  border-bottom-color: var(--color-primary);
}

.sd-admin__section {
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
}

.sd-admin__section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.sd-admin__card {
  background: var(--color-bg-surface);
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-md);
  padding: var(--space-lg);
}

.sd-admin__card h3 {
  font-size: var(--font-md);
  font-weight: var(--weight-semibold);
  margin-bottom: var(--space-md);
}

.sd-admin__form {
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
}

.sd-admin__field {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--space-sm) 0;
  border-bottom: 1px solid var(--color-border-light);
}

.sd-admin__field span {
  font-size: var(--font-sm);
  font-weight: var(--weight-medium);
}

.sd-admin__field input[type="number"] {
  width: 100px;
  text-align: right;
}

.sd-admin__field input[type="checkbox"] {
  width: 20px;
  height: 20px;
}

.sd-admin__form-actions {
  display: flex;
  justify-content: flex-end;
  padding-top: var(--space-sm);
}

.sd-admin__table-container {
  overflow-x: auto;
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-md);
}

.sd-admin__table {
  width: 100%;
  border-collapse: collapse;
}

.sd-admin__table th,
.sd-admin__table td {
  padding: var(--space-sm) var(--space-md);
  text-align: left;
  font-size: var(--font-sm);
  border-bottom: 1px solid var(--color-border-light);
}

.sd-admin__table th {
  background: var(--color-bg-secondary);
  font-weight: var(--weight-semibold);
  color: var(--color-text-secondary);
  font-size: var(--font-xs);
  text-transform: uppercase;
}

@media (max-width: 480px) {
  .sd-admin {
    padding: var(--space-md);
  }

  .sd-admin__field {
    flex-direction: column;
    align-items: flex-start;
    gap: var(--space-xs);
  }
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/SmartDocsAdmin.js frontend/src/pages/SmartDocsAdmin.css
git commit -m "feat(smart-docs): add admin configuration page for auto-review and retention"
```

---

## Task 13: Document Timeline Component

**Files:**
- Create: `frontend/src/components/smart-docs/DocumentTimeline.jsx`
- Create: `frontend/src/components/smart-docs/DocumentTimeline.css`

- [ ] **Step 1: Write the component**

```jsx
// frontend/src/components/smart-docs/DocumentTimeline.jsx
import React, { useState, useEffect } from 'react';
import { toast } from 'react-hot-toast';
import * as analyticsApi from '../../services/docAnalyticsApi';
import './DocumentTimeline.css';

const EVENT_ICONS = {
  UPLOADED: 'U',
  REVIEWED: 'R',
  APPROVED: 'A',
  REJECTED: 'X',
  REQUESTED: 'Q',
  EXPIRED: 'E',
  RENEWED: 'N',
  ESIGNED: 'S',
};

export default function DocumentTimeline({ loanId }) {
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!loanId) return;
    setLoading(true);
    analyticsApi.getLoanTimeline(loanId)
      .then((data) => setEvents(data.events || data.timeline || []))
      .catch((err) => toast.error(`Timeline load failed: ${err.message}`))
      .finally(() => setLoading(false));
  }, [loanId]);

  if (loading) return <div className="loading" style={{ minHeight: 200 }}>Loading timeline...</div>;
  if (events.length === 0) return <p style={{ color: 'var(--color-text-tertiary)', textAlign: 'center' }}>No events</p>;

  return (
    <div className="dtl">
      {events.map((event, i) => (
        <div key={i} className="dtl__item">
          <div className="dtl__marker">
            <span className={`dtl__icon dtl__icon--${(event.event_type || event.type || '').toLowerCase()}`}>
              {EVENT_ICONS[event.event_type || event.type] || 'E'}
            </span>
            {i < events.length - 1 && <div className="dtl__line" />}
          </div>
          <div className="dtl__content">
            <div className="dtl__event-header">
              <span className="dtl__event-type">{event.event_type || event.type}</span>
              <span className="dtl__date">
                {event.timestamp ? new Date(event.timestamp).toLocaleString() : ''}
              </span>
            </div>
            <p className="dtl__description">
              {event.doc_type && <strong>{event.doc_type}</strong>}
              {event.description && ` — ${event.description}`}
            </p>
            {event.user_name && (
              <span className="dtl__user">by {event.user_name}</span>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 2: Write the CSS**

```css
/* frontend/src/components/smart-docs/DocumentTimeline.css */
.dtl {
  display: flex;
  flex-direction: column;
}

.dtl__item {
  display: flex;
  gap: var(--space-md);
  min-height: 60px;
}

.dtl__marker {
  display: flex;
  flex-direction: column;
  align-items: center;
  flex-shrink: 0;
  width: 32px;
}

.dtl__icon {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: var(--font-xs);
  font-weight: var(--weight-bold);
  color: white;
  background: var(--color-info);
  flex-shrink: 0;
}

.dtl__icon--uploaded { background: var(--color-primary); }
.dtl__icon--approved { background: var(--color-success); }
.dtl__icon--rejected { background: var(--color-error); }
.dtl__icon--requested { background: var(--color-warning); }
.dtl__icon--expired { background: var(--color-error); }
.dtl__icon--esigned { background: var(--color-primary); }

.dtl__line {
  width: 2px;
  flex: 1;
  background: var(--color-border);
  min-height: 20px;
}

.dtl__content {
  flex: 1;
  padding-bottom: var(--space-md);
}

.dtl__event-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 2px;
}

.dtl__event-type {
  font-size: var(--font-xs);
  font-weight: var(--weight-semibold);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--color-text-secondary);
}

.dtl__date {
  font-size: var(--font-xs);
  color: var(--color-text-tertiary);
}

.dtl__description {
  font-size: var(--font-sm);
  color: var(--color-text-primary);
}

.dtl__user {
  font-size: var(--font-xs);
  color: var(--color-text-tertiary);
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/smart-docs/DocumentTimeline.jsx frontend/src/components/smart-docs/DocumentTimeline.css
git commit -m "feat(smart-docs): add DocumentTimeline component for loan document events"
```

---

## Task 14: Update Component Index and Route Registration

**Files:**
- Modify: `frontend/src/components/smart-docs/index.js`
- Modify: `frontend/src/App.js` (add routes)

- [ ] **Step 1: Update component index**

Open `frontend/src/components/smart-docs/index.js` and add the new exports:

```javascript
// frontend/src/components/smart-docs/index.js
export { default as NeedsListView } from './NeedsListView';
export { default as SmartDocumentUpload } from './SmartDocumentUpload';
export { default as DocumentStatusCard } from './DocumentStatusCard';
export { default as FreshnessIndicator } from './FreshnessIndicator';
export { default as AnalyticsCard } from './AnalyticsCard';
export { default as ReviewQueueItem } from './ReviewQueueItem';
export { default as DocumentTimeline } from './DocumentTimeline';
export { default as BankAnalysisPanel } from './BankAnalysisPanel';
export { default as IncomeWorksheet } from './IncomeWorksheet';
```

- [ ] **Step 2: Add routes to App.js**

Find the route section in `frontend/src/App.js` and add 6 new routes. The exact location depends on the current route structure — add them near the existing Smart Docs routes:

```jsx
import SmartDocsAnalytics from './pages/SmartDocsAnalytics';
import SmartDocsReviewQueue from './pages/SmartDocsReviewQueue';
import SmartDocsSecurity from './pages/SmartDocsSecurity';
import SmartDocsBankAnalysis from './pages/SmartDocsBankAnalysis';
import SmartDocsIncome from './pages/SmartDocsIncome';
import SmartDocsAdmin from './pages/SmartDocsAdmin';
```

Add these `<Route>` elements alongside existing Smart Docs routes:

```jsx
<Route path="/smart-docs/analytics" element={<SmartDocsAnalytics />} />
<Route path="/smart-docs/review-queue" element={<SmartDocsReviewQueue />} />
<Route path="/smart-docs/security" element={<SmartDocsSecurity />} />
<Route path="/smart-docs/bank-analysis" element={<SmartDocsBankAnalysis />} />
<Route path="/smart-docs/income" element={<SmartDocsIncome />} />
<Route path="/smart-docs/admin" element={<SmartDocsAdmin />} />
```

- [ ] **Step 3: Verify the build**

Run: `cd frontend && npx react-scripts build 2>&1 | tail -10`
Expected: Build succeeds without errors

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/smart-docs/index.js frontend/src/App.js
git commit -m "feat(smart-docs): register 6 enterprise pages and update component index"
```

---

## Task 15: Run Full Test Suite

- [ ] **Step 1: Run all Smart Docs tests**

Run: `cd frontend && npx react-scripts test --watchAll=false --testPathPattern="(smart-docs|docAnalytics|docReview|docSecurity)" 2>&1 | tail -30`
Expected: All tests pass

- [ ] **Step 2: Run full frontend test suite**

Run: `cd frontend && npx react-scripts test --watchAll=false 2>&1 | tail -30`
Expected: No regressions — existing tests still pass

- [ ] **Step 3: Verify production build**

Run: `cd frontend && npx react-scripts build 2>&1 | tail -5`
Expected: `Compiled successfully.`

- [ ] **Step 4: Final commit**

If any fixes were needed, commit them:

```bash
git add -A
git commit -m "fix: resolve any test or build issues from smart docs enterprise features"
```
