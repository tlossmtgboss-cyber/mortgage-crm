/**
 * Tests for the Document Review Queue API Service (docReviewApi.js)
 *
 * Uses fetch mocking to verify correct URL construction, HTTP methods,
 * headers, request bodies, and error handling for all 13 endpoints.
 */

import docReviewApi, {
  getQueue,
  getQueueStats,
  claimDocument,
  releaseDocument,
  aiReview,
  batchAiReview,
  crossValidate,
  getReviewHistory,
  getAutoReviewSettings,
  updateAutoReviewSettings,
  getReviewStats,
  getLoanCompleteness,
  aiExtractAndReview,
} from '../docReviewApi';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const TOKEN = 'test-token-abc';
const BASE = 'http://localhost:8000/api/v1/smart-docs/doc-review';

function mockFetch(body = {}, ok = true, status = 200) {
  global.fetch = vi.fn().mockResolvedValue({
    ok,
    status,
    json: vi.fn().mockResolvedValue(body),
  });
}

beforeEach(() => {
  localStorage.setItem('token', TOKEN);
  vi.clearAllMocks();
});

afterEach(() => {
  localStorage.clear();
});

// ---------------------------------------------------------------------------
// Default export shape
// ---------------------------------------------------------------------------

describe('default export', () => {
  it('exposes all 13 functions as properties', () => {
    expect(docReviewApi.getQueue).toBe(getQueue);
    expect(docReviewApi.getQueueStats).toBe(getQueueStats);
    expect(docReviewApi.claimDocument).toBe(claimDocument);
    expect(docReviewApi.releaseDocument).toBe(releaseDocument);
    expect(docReviewApi.aiReview).toBe(aiReview);
    expect(docReviewApi.batchAiReview).toBe(batchAiReview);
    expect(docReviewApi.crossValidate).toBe(crossValidate);
    expect(docReviewApi.getReviewHistory).toBe(getReviewHistory);
    expect(docReviewApi.getAutoReviewSettings).toBe(getAutoReviewSettings);
    expect(docReviewApi.updateAutoReviewSettings).toBe(updateAutoReviewSettings);
    expect(docReviewApi.getReviewStats).toBe(getReviewStats);
    expect(docReviewApi.getLoanCompleteness).toBe(getLoanCompleteness);
    expect(docReviewApi.aiExtractAndReview).toBe(aiExtractAndReview);
  });
});

// ---------------------------------------------------------------------------
// Auth header utility
// ---------------------------------------------------------------------------

describe('auth header', () => {
  it('sends Bearer token from localStorage', async () => {
    mockFetch({ total: 0, items: [] });
    await getQueue();
    const [, options] = global.fetch.mock.calls[0];
    expect(options.headers['Authorization']).toBe(`Bearer ${TOKEN}`);
  });

  it('sends empty Authorization when no token', async () => {
    localStorage.removeItem('token');
    mockFetch({ total: 0, items: [] });
    await getQueue();
    const [, options] = global.fetch.mock.calls[0];
    expect(options.headers['Authorization']).toBe('');
  });
});

// ---------------------------------------------------------------------------
// getQueue
// ---------------------------------------------------------------------------

describe('getQueue', () => {
  it('calls GET /queue with default params', async () => {
    mockFetch({ total: 0, items: [] });
    await getQueue();
    const [url] = global.fetch.mock.calls[0];
    expect(url).toContain(`${BASE}/queue`);
    expect(url).toContain('limit=50');
    expect(url).toContain('offset=0');
  });

  it('appends priority and docType when provided', async () => {
    mockFetch({ total: 1, items: [] });
    await getQueue({ priority: 'HIGH', docType: 'W2', limit: 10, offset: 5 });
    const [url] = global.fetch.mock.calls[0];
    expect(url).toContain('priority=HIGH');
    expect(url).toContain('doc_type=W2');
    expect(url).toContain('limit=10');
    expect(url).toContain('offset=5');
  });

  it('omits priority/docType when not provided', async () => {
    mockFetch({ total: 0, items: [] });
    await getQueue({ limit: 20 });
    const [url] = global.fetch.mock.calls[0];
    expect(url).not.toContain('priority');
    expect(url).not.toContain('doc_type');
  });

  it('uses GET method', async () => {
    mockFetch({});
    await getQueue();
    const [, options] = global.fetch.mock.calls[0];
    expect(options.method).toBeUndefined(); // fetch default is GET
  });

  it('returns parsed JSON', async () => {
    const data = { total: 3, items: [{ id: 1 }] };
    mockFetch(data);
    const result = await getQueue();
    expect(result).toEqual(data);
  });
});

// ---------------------------------------------------------------------------
// getQueueStats
// ---------------------------------------------------------------------------

describe('getQueueStats', () => {
  it('calls GET /queue/stats', async () => {
    mockFetch({ total_in_queue: 5 });
    await getQueueStats();
    const [url] = global.fetch.mock.calls[0];
    expect(url).toBe(`${BASE}/queue/stats`);
  });

  it('returns stats data', async () => {
    const data = { total_in_queue: 5, by_priority: { critical: 1 } };
    mockFetch(data);
    const result = await getQueueStats();
    expect(result).toEqual(data);
  });
});

// ---------------------------------------------------------------------------
// claimDocument
// ---------------------------------------------------------------------------

describe('claimDocument', () => {
  it('calls POST /queue/{documentId}/claim', async () => {
    mockFetch({ document_id: 42, claimed_by: 'Alice' });
    await claimDocument(42);
    const [url, options] = global.fetch.mock.calls[0];
    expect(url).toBe(`${BASE}/queue/42/claim`);
    expect(options.method).toBe('POST');
  });

  it('includes reviewer_id in body when provided', async () => {
    mockFetch({});
    await claimDocument(42, 'user-123');
    const [, options] = global.fetch.mock.calls[0];
    const body = JSON.parse(options.body);
    expect(body).toEqual({ reviewer_id: 'user-123' });
  });

  it('sends empty object in body when reviewerId is omitted', async () => {
    mockFetch({});
    await claimDocument(7);
    const [, options] = global.fetch.mock.calls[0];
    const body = JSON.parse(options.body);
    expect(body).toEqual({});
  });

  it('sets Content-Type header', async () => {
    mockFetch({});
    await claimDocument(1);
    const [, options] = global.fetch.mock.calls[0];
    expect(options.headers['Content-Type']).toBe('application/json');
  });
});

// ---------------------------------------------------------------------------
// releaseDocument
// ---------------------------------------------------------------------------

describe('releaseDocument', () => {
  it('calls POST /queue/{documentId}/release', async () => {
    mockFetch({ released: true });
    await releaseDocument(99);
    const [url, options] = global.fetch.mock.calls[0];
    expect(url).toBe(`${BASE}/queue/99/release`);
    expect(options.method).toBe('POST');
  });

  it('returns parsed JSON', async () => {
    const data = { document_id: 99, status: 'UPLOADED' };
    mockFetch(data);
    const result = await releaseDocument(99);
    expect(result).toEqual(data);
  });
});

// ---------------------------------------------------------------------------
// aiReview
// ---------------------------------------------------------------------------

describe('aiReview', () => {
  it('calls POST /ai-review/{documentId}', async () => {
    mockFetch({ decision: 'ACCEPT', confidence: 95 });
    await aiReview(55);
    const [url, options] = global.fetch.mock.calls[0];
    expect(url).toBe(`${BASE}/ai-review/55`);
    expect(options.method).toBe('POST');
  });

  it('returns AI review result', async () => {
    const data = { document_id: 55, decision: 'ACCEPT', confidence: 90 };
    mockFetch(data);
    const result = await aiReview(55);
    expect(result).toEqual(data);
  });
});

// ---------------------------------------------------------------------------
// batchAiReview
// ---------------------------------------------------------------------------

describe('batchAiReview', () => {
  it('calls POST /ai-review/batch/{loanId}', async () => {
    mockFetch({ loan_id: 10, total: 3 });
    await batchAiReview(10);
    const [url, options] = global.fetch.mock.calls[0];
    expect(url).toBe(`${BASE}/ai-review/batch/10`);
    expect(options.method).toBe('POST');
  });

  it('sends options in body', async () => {
    mockFetch({});
    await batchAiReview(10, { force_recheck: true });
    const [, options] = global.fetch.mock.calls[0];
    const body = JSON.parse(options.body);
    expect(body).toEqual({ force_recheck: true });
  });

  it('sends empty object when no options provided', async () => {
    mockFetch({});
    await batchAiReview(10);
    const [, options] = global.fetch.mock.calls[0];
    const body = JSON.parse(options.body);
    expect(body).toEqual({});
  });
});

// ---------------------------------------------------------------------------
// crossValidate
// ---------------------------------------------------------------------------

describe('crossValidate', () => {
  it('calls POST /cross-validate/{loanId}', async () => {
    mockFetch({ loan_id: 20, risk_level: 'LOW' });
    await crossValidate(20);
    const [url, options] = global.fetch.mock.calls[0];
    expect(url).toBe(`${BASE}/cross-validate/20`);
    expect(options.method).toBe('POST');
  });

  it('returns cross-validation result', async () => {
    const data = { loan_id: 20, inconsistencies: [], risk_level: 'LOW' };
    mockFetch(data);
    const result = await crossValidate(20);
    expect(result).toEqual(data);
  });
});

// ---------------------------------------------------------------------------
// getReviewHistory
// ---------------------------------------------------------------------------

describe('getReviewHistory', () => {
  it('calls GET /document/{documentId}/review-history', async () => {
    mockFetch({ history: [] });
    await getReviewHistory(33);
    const [url] = global.fetch.mock.calls[0];
    expect(url).toBe(`${BASE}/document/33/review-history`);
  });

  it('uses GET method (no method property)', async () => {
    mockFetch({});
    await getReviewHistory(33);
    const [, options] = global.fetch.mock.calls[0];
    expect(options.method).toBeUndefined();
  });
});

// ---------------------------------------------------------------------------
// getAutoReviewSettings
// ---------------------------------------------------------------------------

describe('getAutoReviewSettings', () => {
  it('calls GET /auto-review-settings', async () => {
    mockFetch({ auto_approve_threshold: 90 });
    await getAutoReviewSettings();
    const [url] = global.fetch.mock.calls[0];
    expect(url).toBe(`${BASE}/auto-review-settings`);
  });

  it('returns settings data', async () => {
    const data = { auto_approve_threshold: 90, auto_reject_threshold: 30 };
    mockFetch(data);
    const result = await getAutoReviewSettings();
    expect(result).toEqual(data);
  });
});

// ---------------------------------------------------------------------------
// updateAutoReviewSettings
// ---------------------------------------------------------------------------

describe('updateAutoReviewSettings', () => {
  it('calls POST /auto-review-settings', async () => {
    mockFetch({ updated: true });
    await updateAutoReviewSettings({ auto_approve_threshold: 85 });
    const [url, options] = global.fetch.mock.calls[0];
    expect(url).toBe(`${BASE}/auto-review-settings`);
    expect(options.method).toBe('POST');
  });

  it('sends settings in request body', async () => {
    mockFetch({});
    const settings = { auto_approve_threshold: 85, enabled_checks: ['quality', 'freshness'] };
    await updateAutoReviewSettings(settings);
    const [, options] = global.fetch.mock.calls[0];
    expect(JSON.parse(options.body)).toEqual(settings);
  });
});

// ---------------------------------------------------------------------------
// getReviewStats
// ---------------------------------------------------------------------------

describe('getReviewStats', () => {
  it('calls GET /stats with default days=30', async () => {
    mockFetch({ total_reviewed: 50 });
    await getReviewStats();
    const [url] = global.fetch.mock.calls[0];
    expect(url).toBe(`${BASE}/stats?days=30`);
  });

  it('passes custom days value', async () => {
    mockFetch({});
    await getReviewStats(7);
    const [url] = global.fetch.mock.calls[0];
    expect(url).toBe(`${BASE}/stats?days=7`);
  });

  it('returns stats data', async () => {
    const data = { total_reviewed: 50, auto_approved: 30 };
    mockFetch(data);
    const result = await getReviewStats(14);
    expect(result).toEqual(data);
  });
});

// ---------------------------------------------------------------------------
// getLoanCompleteness
// ---------------------------------------------------------------------------

describe('getLoanCompleteness', () => {
  it('calls GET /loan/{loanId}/completeness', async () => {
    mockFetch({ completeness_pct: 75.0 });
    await getLoanCompleteness(101);
    const [url] = global.fetch.mock.calls[0];
    expect(url).toBe(`${BASE}/loan/101/completeness`);
  });

  it('returns completeness data', async () => {
    const data = { loan_id: 101, completeness_pct: 75.0, missing: 2 };
    mockFetch(data);
    const result = await getLoanCompleteness(101);
    expect(result).toEqual(data);
  });
});

// ---------------------------------------------------------------------------
// aiExtractAndReview
// ---------------------------------------------------------------------------

describe('aiExtractAndReview', () => {
  it('calls POST /document/{documentId}/ai-extract-and-review', async () => {
    mockFetch({ decision: 'ACCEPT' });
    await aiExtractAndReview(77);
    const [url, options] = global.fetch.mock.calls[0];
    expect(url).toBe(`${BASE}/document/77/ai-extract-and-review`);
    expect(options.method).toBe('POST');
  });

  it('returns extraction and review result', async () => {
    const data = { document_id: 77, decision: 'ACCEPT', extracted_fields: {} };
    mockFetch(data);
    const result = await aiExtractAndReview(77);
    expect(result).toEqual(data);
  });
});

// ---------------------------------------------------------------------------
// Error handling
// ---------------------------------------------------------------------------

describe('error handling', () => {
  it('throws with detail message from JSON error body', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 404,
      json: vi.fn().mockResolvedValue({ detail: 'Document not found' }),
    });
    await expect(aiReview(999)).rejects.toThrow('Document not found');
  });

  it('throws fallback message when JSON parse fails', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
      json: vi.fn().mockRejectedValue(new SyntaxError('bad json')),
    });
    await expect(getQueueStats()).rejects.toThrow('Request failed');
  });

  it('throws detail when body has detail but no extra fields', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 409,
      json: vi.fn().mockResolvedValue({ detail: 'Already claimed' }),
    });
    await expect(claimDocument(1, 'user-x')).rejects.toThrow('Already claimed');
  });

  it('re-throws network errors', async () => {
    global.fetch = vi.fn().mockRejectedValue(new TypeError('Network request failed'));
    await expect(getQueue()).rejects.toThrow('Network request failed');
  });
});
