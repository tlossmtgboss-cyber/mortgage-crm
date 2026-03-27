/**
 * Tests for docSecurityApi, docBankAnalysisApi, and docIncomeApi service modules.
 *
 * Uses vitest + jsdom. fetch is mocked globally via vi.stubGlobal.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// ---------------------------------------------------------------------------
// Mock the './api' module so API_BASE_URL is a predictable value
// ---------------------------------------------------------------------------
vi.mock('../api', () => ({
  API_BASE_URL: 'http://localhost:8000',
}));

// ---------------------------------------------------------------------------
// Mock localStorage
// ---------------------------------------------------------------------------
const localStorageMock = (() => {
  let store = {};
  return {
    getItem: vi.fn((key) => store[key] ?? null),
    setItem: vi.fn((key, value) => { store[key] = String(value); }),
    removeItem: vi.fn((key) => { delete store[key]; }),
    clear: vi.fn(() => { store = {}; }),
  };
})();

vi.stubGlobal('localStorage', localStorageMock);

// ---------------------------------------------------------------------------
// Import service modules AFTER mocks are in place
// ---------------------------------------------------------------------------
import {
  getAuditLog,
  getDocumentAuditLog,
  logAccess,
  checkIntegrity,
  batchIntegrityCheck,
  getIntegrityHistory,
  getFraudAnalysis,
  getFraudSummary,
  getRetentionPolicies,
  createRetentionPolicy,
  updateRetentionPolicy,
  getExpiringRetentions,
  watermarkDocument,
  getEncryptionStatus,
  encryptDocument,
  getComplianceReport,
  getSuspiciousActivity,
  docSecurityAPI,
} from '../docSecurityApi';

import {
  analyzeBankStatement,
  getLargeDeposits,
  getNsfOverdrafts,
  getRiskScore,
  getBankSummary,
  sourceDeposit,
  docBankAnalysisAPI,
} from '../docBankAnalysisApi';

import {
  calculateIncome,
  getIncomeHistory,
  approveIncome,
  rejectIncome,
  docIncomeAPI,
} from '../docIncomeApi';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Build a successful fetch mock that returns JSON data. */
function mockFetchSuccess(data) {
  return vi.fn().mockResolvedValue({
    ok: true,
    json: vi.fn().mockResolvedValue(data),
  });
}

/** Build a failed fetch mock (non-ok status with detail message). */
function mockFetchError(detail, status = 400) {
  return vi.fn().mockResolvedValue({
    ok: false,
    status,
    json: vi.fn().mockResolvedValue({ detail }),
  });
}

const BASE = 'http://localhost:8000/api/v1/smart-docs';

// ---------------------------------------------------------------------------
// Setup / teardown
// ---------------------------------------------------------------------------

beforeEach(() => {
  localStorageMock.getItem.mockReturnValue('test-token-abc');
});

afterEach(() => {
  vi.restoreAllMocks();
});

// ===========================================================================
// docSecurityApi — Security tests
// ===========================================================================

describe('docSecurityApi', () => {
  // -------------------------------------------------------------------------
  describe('getAuditLog', () => {
    it('calls audit-log endpoint with default params', async () => {
      const fetchMock = mockFetchSuccess({ entries: [] });
      vi.stubGlobal('fetch', fetchMock);

      const result = await getAuditLog();

      expect(fetchMock).toHaveBeenCalledOnce();
      const [url, opts] = fetchMock.mock.calls[0];
      expect(url).toContain(`${BASE}/doc-security/audit-log`);
      expect(url).toContain('days=30');
      expect(url).toContain('limit=100');
      expect(url).toContain('offset=0');
      expect(opts.headers['Authorization']).toBe('Bearer test-token-abc');
      expect(result).toEqual({ entries: [] });
    });

    it('appends optional documentId and action filters', async () => {
      const fetchMock = mockFetchSuccess({ entries: [{ id: '1' }] });
      vi.stubGlobal('fetch', fetchMock);

      await getAuditLog({ documentId: 'doc-123', action: 'view', days: 7 });

      const [url] = fetchMock.mock.calls[0];
      expect(url).toContain('document_id=doc-123');
      expect(url).toContain('action=view');
      expect(url).toContain('days=7');
    });
  });

  // -------------------------------------------------------------------------
  describe('getDocumentAuditLog', () => {
    it('calls audit-log/{documentId} endpoint', async () => {
      const fetchMock = mockFetchSuccess({ events: [] });
      vi.stubGlobal('fetch', fetchMock);

      await getDocumentAuditLog('doc-456');

      const [url] = fetchMock.mock.calls[0];
      expect(url).toBe(`${BASE}/doc-security/audit-log/doc-456`);
    });
  });

  // -------------------------------------------------------------------------
  describe('logAccess', () => {
    it('POSTs to log-access with correct body', async () => {
      const fetchMock = mockFetchSuccess({ logged: true });
      vi.stubGlobal('fetch', fetchMock);

      await logAccess('doc-789', 'download', 'via mobile');

      const [url, opts] = fetchMock.mock.calls[0];
      expect(url).toBe(`${BASE}/doc-security/log-access`);
      expect(opts.method).toBe('POST');
      expect(JSON.parse(opts.body)).toEqual({
        document_id: 'doc-789',
        action: 'download',
        details: 'via mobile',
      });
    });

    it('uses empty string for details when omitted', async () => {
      const fetchMock = mockFetchSuccess({ logged: true });
      vi.stubGlobal('fetch', fetchMock);

      await logAccess('doc-789', 'view');

      const { details } = JSON.parse(fetchMock.mock.calls[0][1].body);
      expect(details).toBe('');
    });
  });

  // -------------------------------------------------------------------------
  describe('checkIntegrity', () => {
    it('calls integrity-check/{documentId} endpoint', async () => {
      const fetchMock = mockFetchSuccess({ status: 'ok' });
      vi.stubGlobal('fetch', fetchMock);

      const result = await checkIntegrity('doc-111');

      const [url, opts] = fetchMock.mock.calls[0];
      expect(url).toBe(`${BASE}/doc-security/integrity-check/doc-111`);
      expect(opts.method).toBeUndefined(); // GET — no method set
      expect(result).toEqual({ status: 'ok' });
    });
  });

  // -------------------------------------------------------------------------
  describe('batchIntegrityCheck', () => {
    it('POSTs document_ids array to batch endpoint', async () => {
      const fetchMock = mockFetchSuccess({ results: [] });
      vi.stubGlobal('fetch', fetchMock);

      await batchIntegrityCheck(['a', 'b', 'c']);

      const [url, opts] = fetchMock.mock.calls[0];
      expect(url).toBe(`${BASE}/doc-security/integrity-check/batch`);
      expect(opts.method).toBe('POST');
      expect(JSON.parse(opts.body)).toEqual({ document_ids: ['a', 'b', 'c'] });
    });
  });

  // -------------------------------------------------------------------------
  describe('getIntegrityHistory', () => {
    it('calls integrity-history/{documentId} endpoint', async () => {
      const fetchMock = mockFetchSuccess({ history: [] });
      vi.stubGlobal('fetch', fetchMock);

      await getIntegrityHistory('doc-222');

      const [url] = fetchMock.mock.calls[0];
      expect(url).toBe(`${BASE}/doc-security/integrity-history/doc-222`);
    });
  });

  // -------------------------------------------------------------------------
  describe('getFraudAnalysis', () => {
    it('calls fraud-analysis/{loanId} endpoint', async () => {
      const fetchMock = mockFetchSuccess({ risk: 'low' });
      vi.stubGlobal('fetch', fetchMock);

      await getFraudAnalysis('loan-999');

      const [url] = fetchMock.mock.calls[0];
      expect(url).toBe(`${BASE}/doc-security/fraud-analysis/loan-999`);
    });
  });

  // -------------------------------------------------------------------------
  describe('getFraudSummary', () => {
    it('uses loan-scoped URL when loanId is provided', async () => {
      const fetchMock = mockFetchSuccess({ summary: {} });
      vi.stubGlobal('fetch', fetchMock);

      await getFraudSummary('loan-abc');

      const [url] = fetchMock.mock.calls[0];
      expect(url).toBe(`${BASE}/doc-security/fraud/loan-abc/summary`);
    });

    it('uses global fraud-summary URL when loanId is omitted', async () => {
      const fetchMock = mockFetchSuccess({ summary: {} });
      vi.stubGlobal('fetch', fetchMock);

      await getFraudSummary();

      const [url] = fetchMock.mock.calls[0];
      expect(url).toBe(`${BASE}/doc-security/fraud-summary`);
    });
  });

  // -------------------------------------------------------------------------
  describe('retention policies', () => {
    it('getRetentionPolicies calls retention-policies endpoint', async () => {
      const fetchMock = mockFetchSuccess({ policies: [] });
      vi.stubGlobal('fetch', fetchMock);

      await getRetentionPolicies();

      const [url] = fetchMock.mock.calls[0];
      expect(url).toBe(`${BASE}/doc-security/retention-policies`);
    });

    it('createRetentionPolicy POSTs policy object', async () => {
      const policy = { name: 'Default', days: 365 };
      const fetchMock = mockFetchSuccess({ id: 'pol-1', ...policy });
      vi.stubGlobal('fetch', fetchMock);

      await createRetentionPolicy(policy);

      const [url, opts] = fetchMock.mock.calls[0];
      expect(url).toBe(`${BASE}/doc-security/retention-policies`);
      expect(opts.method).toBe('POST');
      expect(JSON.parse(opts.body)).toEqual(policy);
    });

    it('updateRetentionPolicy PUTs to retention-policies/{policyId}', async () => {
      const fetchMock = mockFetchSuccess({ updated: true });
      vi.stubGlobal('fetch', fetchMock);

      await updateRetentionPolicy('pol-1', { days: 730 });

      const [url, opts] = fetchMock.mock.calls[0];
      expect(url).toBe(`${BASE}/doc-security/retention-policies/pol-1`);
      expect(opts.method).toBe('PUT');
      expect(JSON.parse(opts.body)).toEqual({ days: 730 });
    });

    it('getExpiringRetentions passes days param', async () => {
      const fetchMock = mockFetchSuccess({ items: [] });
      vi.stubGlobal('fetch', fetchMock);

      await getExpiringRetentions(60);

      const [url] = fetchMock.mock.calls[0];
      expect(url).toContain('days=60');
    });
  });

  // -------------------------------------------------------------------------
  describe('watermarkDocument', () => {
    it('POSTs to watermark/{documentId} with options', async () => {
      const fetchMock = mockFetchSuccess({ watermarked: true });
      vi.stubGlobal('fetch', fetchMock);

      await watermarkDocument('doc-333', { text: 'CONFIDENTIAL' });

      const [url, opts] = fetchMock.mock.calls[0];
      expect(url).toBe(`${BASE}/doc-security/watermark/doc-333`);
      expect(opts.method).toBe('POST');
      expect(JSON.parse(opts.body)).toEqual({ text: 'CONFIDENTIAL' });
    });
  });

  // -------------------------------------------------------------------------
  describe('encryption', () => {
    it('getEncryptionStatus calls encryption-status/{documentId}', async () => {
      const fetchMock = mockFetchSuccess({ encrypted: true });
      vi.stubGlobal('fetch', fetchMock);

      await getEncryptionStatus('doc-444');

      const [url] = fetchMock.mock.calls[0];
      expect(url).toBe(`${BASE}/doc-security/encryption-status/doc-444`);
    });

    it('encryptDocument POSTs to encrypt/{documentId}', async () => {
      const fetchMock = mockFetchSuccess({ encrypted: true });
      vi.stubGlobal('fetch', fetchMock);

      await encryptDocument('doc-555');

      const [url, opts] = fetchMock.mock.calls[0];
      expect(url).toBe(`${BASE}/doc-security/encrypt/doc-555`);
      expect(opts.method).toBe('POST');
    });
  });

  // -------------------------------------------------------------------------
  describe('compliance & suspicious activity', () => {
    it('getComplianceReport passes days param', async () => {
      const fetchMock = mockFetchSuccess({ report: {} });
      vi.stubGlobal('fetch', fetchMock);

      await getComplianceReport(90);

      const [url] = fetchMock.mock.calls[0];
      expect(url).toContain('days=90');
      expect(url).toContain('compliance-report');
    });

    it('getSuspiciousActivity passes days param', async () => {
      const fetchMock = mockFetchSuccess({ events: [] });
      vi.stubGlobal('fetch', fetchMock);

      await getSuspiciousActivity(14);

      const [url] = fetchMock.mock.calls[0];
      expect(url).toContain('days=14');
      expect(url).toContain('suspicious-activity');
    });
  });

  // -------------------------------------------------------------------------
  describe('error handling', () => {
    it('throws with detail message from error response', async () => {
      const fetchMock = mockFetchError('Document not found', 404);
      vi.stubGlobal('fetch', fetchMock);

      await expect(checkIntegrity('bad-id')).rejects.toThrow('Document not found');
    });

    it('throws with fallback message when JSON parse fails on error response', async () => {
      vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
        ok: false,
        status: 500,
        json: vi.fn().mockRejectedValue(new Error('not JSON')),
      }));

      // The handleResponse catch fallback returns { detail: 'Request failed' }
      await expect(getAuditLog()).rejects.toThrow('Request failed');
    });

    it('sends no auth header when token is absent', async () => {
      localStorageMock.getItem.mockReturnValue(null);
      const fetchMock = mockFetchSuccess({});
      vi.stubGlobal('fetch', fetchMock);

      await getRetentionPolicies();

      const [, opts] = fetchMock.mock.calls[0];
      expect(opts.headers['Authorization']).toBe('');
    });
  });

  // -------------------------------------------------------------------------
  describe('default export shape', () => {
    it('docSecurityAPI default export contains all functions', () => {
      expect(typeof docSecurityAPI.getAuditLog).toBe('function');
      expect(typeof docSecurityAPI.logAccess).toBe('function');
      expect(typeof docSecurityAPI.checkIntegrity).toBe('function');
      expect(typeof docSecurityAPI.batchIntegrityCheck).toBe('function');
      expect(typeof docSecurityAPI.getFraudAnalysis).toBe('function');
      expect(typeof docSecurityAPI.getFraudSummary).toBe('function');
      expect(typeof docSecurityAPI.getRetentionPolicies).toBe('function');
      expect(typeof docSecurityAPI.watermarkDocument).toBe('function');
      expect(typeof docSecurityAPI.encryptDocument).toBe('function');
      expect(typeof docSecurityAPI.getComplianceReport).toBe('function');
      expect(typeof docSecurityAPI.getSuspiciousActivity).toBe('function');
    });
  });
});

// ===========================================================================
// docBankAnalysisApi — Bank Analysis tests
// ===========================================================================

describe('docBankAnalysisApi', () => {
  describe('analyzeBankStatement', () => {
    it('POSTs to bank-analysis/analyze/{documentId}', async () => {
      const fetchMock = mockFetchSuccess({ analysis: {} });
      vi.stubGlobal('fetch', fetchMock);

      await analyzeBankStatement('doc-bank-1');

      const [url, opts] = fetchMock.mock.calls[0];
      expect(url).toBe(`${BASE}/bank-analysis/analyze/doc-bank-1`);
      expect(opts.method).toBe('POST');
    });
  });

  describe('getLargeDeposits', () => {
    it('calls large-deposits/{loanId} without threshold', async () => {
      const fetchMock = mockFetchSuccess({ deposits: [] });
      vi.stubGlobal('fetch', fetchMock);

      await getLargeDeposits('loan-bank-1');

      const [url] = fetchMock.mock.calls[0];
      expect(url).toBe(`${BASE}/bank-analysis/large-deposits/loan-bank-1`);
    });

    it('appends threshold query param when provided', async () => {
      const fetchMock = mockFetchSuccess({ deposits: [] });
      vi.stubGlobal('fetch', fetchMock);

      await getLargeDeposits('loan-bank-1', 5000);

      const [url] = fetchMock.mock.calls[0];
      expect(url).toContain('threshold=5000');
    });
  });

  describe('getNsfOverdrafts', () => {
    it('calls nsf-overdrafts/{loanId} endpoint', async () => {
      const fetchMock = mockFetchSuccess({ events: [] });
      vi.stubGlobal('fetch', fetchMock);

      await getNsfOverdrafts('loan-bank-2');

      const [url] = fetchMock.mock.calls[0];
      expect(url).toBe(`${BASE}/bank-analysis/nsf-overdrafts/loan-bank-2`);
    });
  });

  describe('getRiskScore', () => {
    it('calls risk-score/{loanId} endpoint', async () => {
      const fetchMock = mockFetchSuccess({ score: 42 });
      vi.stubGlobal('fetch', fetchMock);

      const result = await getRiskScore('loan-bank-3');

      const [url] = fetchMock.mock.calls[0];
      expect(url).toBe(`${BASE}/bank-analysis/risk-score/loan-bank-3`);
      expect(result).toEqual({ score: 42 });
    });
  });

  describe('getBankSummary', () => {
    it('calls summary/{loanId} endpoint', async () => {
      const fetchMock = mockFetchSuccess({ summary: {} });
      vi.stubGlobal('fetch', fetchMock);

      await getBankSummary('loan-bank-4');

      const [url] = fetchMock.mock.calls[0];
      expect(url).toBe(`${BASE}/bank-analysis/summary/loan-bank-4`);
    });
  });

  describe('sourceDeposit', () => {
    it('POSTs sourcing details to source-deposit/{depositId}', async () => {
      const sourcing = { source: 'payroll', amount: 3000 };
      const fetchMock = mockFetchSuccess({ sourced: true });
      vi.stubGlobal('fetch', fetchMock);

      await sourceDeposit('dep-99', sourcing);

      const [url, opts] = fetchMock.mock.calls[0];
      expect(url).toBe(`${BASE}/bank-analysis/source-deposit/dep-99`);
      expect(opts.method).toBe('POST');
      expect(JSON.parse(opts.body)).toEqual(sourcing);
    });
  });

  describe('default export shape', () => {
    it('docBankAnalysisAPI contains all functions', () => {
      expect(typeof docBankAnalysisAPI.analyzeBankStatement).toBe('function');
      expect(typeof docBankAnalysisAPI.getLargeDeposits).toBe('function');
      expect(typeof docBankAnalysisAPI.getNsfOverdrafts).toBe('function');
      expect(typeof docBankAnalysisAPI.getRiskScore).toBe('function');
      expect(typeof docBankAnalysisAPI.getBankSummary).toBe('function');
      expect(typeof docBankAnalysisAPI.sourceDeposit).toBe('function');
    });
  });
});

// ===========================================================================
// docIncomeApi — Income tests
// ===========================================================================

describe('docIncomeApi', () => {
  describe('calculateIncome', () => {
    it('POSTs to income/calculate/{loanId} with options', async () => {
      const fetchMock = mockFetchSuccess({ income: 8500 });
      vi.stubGlobal('fetch', fetchMock);

      const opts = { include_rental: true };
      const result = await calculateIncome('loan-inc-1', opts);

      const [url, reqOpts] = fetchMock.mock.calls[0];
      expect(url).toBe(`${BASE}/income/calculate/loan-inc-1`);
      expect(reqOpts.method).toBe('POST');
      expect(JSON.parse(reqOpts.body)).toEqual(opts);
      expect(result).toEqual({ income: 8500 });
    });

    it('sends empty object body when options omitted', async () => {
      const fetchMock = mockFetchSuccess({});
      vi.stubGlobal('fetch', fetchMock);

      await calculateIncome('loan-inc-2');

      const body = JSON.parse(fetchMock.mock.calls[0][1].body);
      expect(body).toEqual({});
    });
  });

  describe('getIncomeHistory', () => {
    it('calls income/history/{loanId} endpoint', async () => {
      const fetchMock = mockFetchSuccess({ history: [] });
      vi.stubGlobal('fetch', fetchMock);

      await getIncomeHistory('loan-inc-3');

      const [url] = fetchMock.mock.calls[0];
      expect(url).toBe(`${BASE}/income/history/loan-inc-3`);
    });
  });

  describe('approveIncome', () => {
    it('POSTs to income/approve/{loanId} with notes', async () => {
      const fetchMock = mockFetchSuccess({ approved: true });
      vi.stubGlobal('fetch', fetchMock);

      await approveIncome('loan-inc-4', 'Looks good');

      const [url, opts] = fetchMock.mock.calls[0];
      expect(url).toBe(`${BASE}/income/approve/loan-inc-4`);
      expect(opts.method).toBe('POST');
      expect(JSON.parse(opts.body)).toEqual({ notes: 'Looks good' });
    });
  });

  describe('rejectIncome', () => {
    it('POSTs to income/reject/{loanId} with reason', async () => {
      const fetchMock = mockFetchSuccess({ rejected: true });
      vi.stubGlobal('fetch', fetchMock);

      await rejectIncome('loan-inc-5', 'Insufficient documentation');

      const [url, opts] = fetchMock.mock.calls[0];
      expect(url).toBe(`${BASE}/income/reject/loan-inc-5`);
      expect(opts.method).toBe('POST');
      expect(JSON.parse(opts.body)).toEqual({ reason: 'Insufficient documentation' });
    });
  });

  describe('default export shape', () => {
    it('docIncomeAPI contains all functions', () => {
      expect(typeof docIncomeAPI.calculateIncome).toBe('function');
      expect(typeof docIncomeAPI.getIncomeHistory).toBe('function');
      expect(typeof docIncomeAPI.approveIncome).toBe('function');
      expect(typeof docIncomeAPI.rejectIncome).toBe('function');
      expect(typeof docIncomeAPI.submitForApproval).toBe('function');
      expect(typeof docIncomeAPI.overrideSource).toBe('function');
      expect(typeof docIncomeAPI.getIncomeSources).toBe('function');
    });
  });
});
