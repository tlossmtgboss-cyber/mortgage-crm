import { describe, it, expect, vi, beforeEach } from 'vitest';

// ---------------------------------------------------------------------------
// Mock ./api so API_BASE_URL is deterministic
// ---------------------------------------------------------------------------
vi.mock('../api', () => ({
  API_BASE_URL: 'http://test-api.local',
}));

// ---------------------------------------------------------------------------
// Mock global fetch
// ---------------------------------------------------------------------------
const mockFetch = vi.fn();
global.fetch = mockFetch;

// Mock localStorage
const mockLocalStorage = {
  getItem: vi.fn(),
};
Object.defineProperty(global, 'localStorage', {
  value: mockLocalStorage,
  writable: true,
});

// ---------------------------------------------------------------------------
// Import the module under test (after mocks are set up)
// ---------------------------------------------------------------------------
import {
  getDashboard,
  getPipelineCompleteness,
  getSlaCompliance,
  getAiPerformance,
  getFollowupEffectiveness,
  getIncomeSummary,
  getBankAnalysisSummary,
  getEsignMetrics,
  getProcessorProductivity,
  getLoanTimeline,
  getTrends,
  getBottlenecks,
  docAnalyticsAPI,
} from '../docAnalyticsApi';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Build a successful fetch response */
function makeOkResponse(data) {
  return {
    ok: true,
    json: vi.fn().mockResolvedValue(data),
  };
}

/** Build a failing fetch response */
function makeErrorResponse(status, detail) {
  return {
    ok: false,
    status,
    json: vi.fn().mockResolvedValue({ detail }),
  };
}

const BASE = 'http://test-api.local/api/v1/smart-docs';

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('docAnalyticsApi', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockLocalStorage.getItem.mockReturnValue('test-token-abc');
    mockFetch.mockResolvedValue(makeOkResponse({ ok: true }));
  });

  // =========================================================================
  // Named exports exist
  // =========================================================================

  describe('named exports', () => {
    it('exports getDashboard as a function', () => {
      expect(typeof getDashboard).toBe('function');
    });
    it('exports getPipelineCompleteness as a function', () => {
      expect(typeof getPipelineCompleteness).toBe('function');
    });
    it('exports getSlaCompliance as a function', () => {
      expect(typeof getSlaCompliance).toBe('function');
    });
    it('exports getAiPerformance as a function', () => {
      expect(typeof getAiPerformance).toBe('function');
    });
    it('exports getFollowupEffectiveness as a function', () => {
      expect(typeof getFollowupEffectiveness).toBe('function');
    });
    it('exports getIncomeSummary as a function', () => {
      expect(typeof getIncomeSummary).toBe('function');
    });
    it('exports getBankAnalysisSummary as a function', () => {
      expect(typeof getBankAnalysisSummary).toBe('function');
    });
    it('exports getEsignMetrics as a function', () => {
      expect(typeof getEsignMetrics).toBe('function');
    });
    it('exports getProcessorProductivity as a function', () => {
      expect(typeof getProcessorProductivity).toBe('function');
    });
    it('exports getLoanTimeline as a function', () => {
      expect(typeof getLoanTimeline).toBe('function');
    });
    it('exports getTrends as a function', () => {
      expect(typeof getTrends).toBe('function');
    });
    it('exports getBottlenecks as a function', () => {
      expect(typeof getBottlenecks).toBe('function');
    });
  });

  // =========================================================================
  // Default export (docAnalyticsAPI object)
  // =========================================================================

  describe('default export — docAnalyticsAPI object', () => {
    it('is exported as default', () => {
      expect(docAnalyticsAPI).toBeDefined();
    });

    const expectedMethods = [
      'getDashboard',
      'getPipelineCompleteness',
      'getSlaCompliance',
      'getAiPerformance',
      'getFollowupEffectiveness',
      'getIncomeSummary',
      'getBankAnalysisSummary',
      'getEsignMetrics',
      'getProcessorProductivity',
      'getLoanTimeline',
      'getTrends',
      'getBottlenecks',
    ];

    expectedMethods.forEach((name) => {
      it(`docAnalyticsAPI.${name} is a function`, () => {
        expect(typeof docAnalyticsAPI[name]).toBe('function');
      });
    });
  });

  // =========================================================================
  // Auth headers
  // =========================================================================

  describe('auth headers', () => {
    it('sends Bearer token from localStorage', async () => {
      await getDashboard();
      const [, options] = mockFetch.mock.calls[0];
      expect(options.headers['Authorization']).toBe('Bearer test-token-abc');
    });

    it('sends Content-Type: application/json', async () => {
      await getDashboard();
      const [, options] = mockFetch.mock.calls[0];
      expect(options.headers['Content-Type']).toBe('application/json');
    });

    it('sends empty Authorization when no token', async () => {
      mockLocalStorage.getItem.mockReturnValue(null);
      await getDashboard();
      const [, options] = mockFetch.mock.calls[0];
      expect(options.headers['Authorization']).toBe('');
    });
  });

  // =========================================================================
  // Error handling
  // =========================================================================

  describe('error handling', () => {
    it('throws with detail message from JSON body on non-ok response', async () => {
      mockFetch.mockResolvedValue(makeErrorResponse(422, 'Validation failed'));
      await expect(getDashboard()).rejects.toThrow('Validation failed');
    });

    it('throws HTTP status message when detail field is missing', async () => {
      mockFetch.mockResolvedValue({
        ok: false,
        status: 500,
        json: vi.fn().mockResolvedValue({}),
      });
      await expect(getDashboard()).rejects.toThrow('HTTP 500');
    });

    it('falls back gracefully when response body is not JSON', async () => {
      mockFetch.mockResolvedValue({
        ok: false,
        status: 503,
        json: vi.fn().mockRejectedValue(new SyntaxError('bad json')),
      });
      await expect(getDashboard()).rejects.toThrow('Request failed');
    });
  });

  // =========================================================================
  // getDashboard
  // =========================================================================

  describe('getDashboard', () => {
    it('calls /doc-analytics/dashboard with default days=30', async () => {
      await getDashboard();
      const [url] = mockFetch.mock.calls[0];
      expect(url).toBe(`${BASE}/doc-analytics/dashboard?days=30`);
    });

    it('calls /doc-analytics/dashboard with custom days', async () => {
      await getDashboard(90);
      const [url] = mockFetch.mock.calls[0];
      expect(url).toBe(`${BASE}/doc-analytics/dashboard?days=90`);
    });

    it('uses GET method', async () => {
      await getDashboard();
      const [, options] = mockFetch.mock.calls[0];
      expect((options.method || 'GET').toUpperCase()).toBe('GET');
    });

    it('returns parsed JSON response', async () => {
      const payload = { total_loans: 42 };
      mockFetch.mockResolvedValue(makeOkResponse(payload));
      const result = await getDashboard();
      expect(result).toEqual(payload);
    });
  });

  // =========================================================================
  // getPipelineCompleteness
  // =========================================================================

  describe('getPipelineCompleteness', () => {
    it('calls /doc-analytics/pipeline-completeness with no params by default', async () => {
      await getPipelineCompleteness();
      const [url] = mockFetch.mock.calls[0];
      expect(url).toBe(`${BASE}/doc-analytics/pipeline-completeness`);
    });

    it('appends min_pct when provided', async () => {
      await getPipelineCompleteness(50);
      const [url] = mockFetch.mock.calls[0];
      expect(url).toContain('min_pct=50');
    });

    it('appends max_pct when provided', async () => {
      await getPipelineCompleteness(undefined, 90);
      const [url] = mockFetch.mock.calls[0];
      expect(url).toContain('max_pct=90');
    });

    it('appends both min_pct and max_pct when both provided', async () => {
      await getPipelineCompleteness(20, 80);
      const [url] = mockFetch.mock.calls[0];
      expect(url).toContain('min_pct=20');
      expect(url).toContain('max_pct=80');
    });
  });

  // =========================================================================
  // getSlaCompliance
  // =========================================================================

  describe('getSlaCompliance', () => {
    it('calls /doc-analytics/sla-compliance with default days=30', async () => {
      await getSlaCompliance();
      const [url] = mockFetch.mock.calls[0];
      expect(url).toBe(`${BASE}/doc-analytics/sla-compliance?days=30`);
    });

    it('calls /doc-analytics/sla-compliance with custom days', async () => {
      await getSlaCompliance(60);
      const [url] = mockFetch.mock.calls[0];
      expect(url).toBe(`${BASE}/doc-analytics/sla-compliance?days=60`);
    });
  });

  // =========================================================================
  // getAiPerformance
  // =========================================================================

  describe('getAiPerformance', () => {
    it('calls /doc-analytics/ai-performance with default days=30', async () => {
      await getAiPerformance();
      const [url] = mockFetch.mock.calls[0];
      expect(url).toBe(`${BASE}/doc-analytics/ai-performance?days=30`);
    });

    it('calls /doc-analytics/ai-performance with custom days', async () => {
      await getAiPerformance(14);
      const [url] = mockFetch.mock.calls[0];
      expect(url).toBe(`${BASE}/doc-analytics/ai-performance?days=14`);
    });
  });

  // =========================================================================
  // getFollowupEffectiveness
  // =========================================================================

  describe('getFollowupEffectiveness', () => {
    it('calls /doc-analytics/followup-effectiveness with default days=30', async () => {
      await getFollowupEffectiveness();
      const [url] = mockFetch.mock.calls[0];
      expect(url).toBe(`${BASE}/doc-analytics/followup-effectiveness?days=30`);
    });

    it('supports custom days', async () => {
      await getFollowupEffectiveness(45);
      const [url] = mockFetch.mock.calls[0];
      expect(url).toBe(`${BASE}/doc-analytics/followup-effectiveness?days=45`);
    });
  });

  // =========================================================================
  // getIncomeSummary
  // =========================================================================

  describe('getIncomeSummary', () => {
    it('calls /doc-analytics/income-summary with default days=30', async () => {
      await getIncomeSummary();
      const [url] = mockFetch.mock.calls[0];
      expect(url).toBe(`${BASE}/doc-analytics/income-summary?days=30`);
    });

    it('supports custom days', async () => {
      await getIncomeSummary(7);
      const [url] = mockFetch.mock.calls[0];
      expect(url).toBe(`${BASE}/doc-analytics/income-summary?days=7`);
    });
  });

  // =========================================================================
  // getBankAnalysisSummary
  // =========================================================================

  describe('getBankAnalysisSummary', () => {
    it('calls /doc-analytics/bank-analysis-summary with default days=30', async () => {
      await getBankAnalysisSummary();
      const [url] = mockFetch.mock.calls[0];
      expect(url).toBe(`${BASE}/doc-analytics/bank-analysis-summary?days=30`);
    });

    it('supports custom days', async () => {
      await getBankAnalysisSummary(120);
      const [url] = mockFetch.mock.calls[0];
      expect(url).toBe(`${BASE}/doc-analytics/bank-analysis-summary?days=120`);
    });
  });

  // =========================================================================
  // getEsignMetrics
  // =========================================================================

  describe('getEsignMetrics', () => {
    it('calls /doc-analytics/esign-metrics with default days=30', async () => {
      await getEsignMetrics();
      const [url] = mockFetch.mock.calls[0];
      expect(url).toBe(`${BASE}/doc-analytics/esign-metrics?days=30`);
    });

    it('supports custom days', async () => {
      await getEsignMetrics(180);
      const [url] = mockFetch.mock.calls[0];
      expect(url).toBe(`${BASE}/doc-analytics/esign-metrics?days=180`);
    });
  });

  // =========================================================================
  // getProcessorProductivity
  // =========================================================================

  describe('getProcessorProductivity', () => {
    it('calls /doc-analytics/processor-productivity with default days=30', async () => {
      await getProcessorProductivity();
      const [url] = mockFetch.mock.calls[0];
      expect(url).toBe(`${BASE}/doc-analytics/processor-productivity?days=30`);
    });

    it('supports custom days', async () => {
      await getProcessorProductivity(365);
      const [url] = mockFetch.mock.calls[0];
      expect(url).toBe(`${BASE}/doc-analytics/processor-productivity?days=365`);
    });
  });

  // =========================================================================
  // getLoanTimeline
  // =========================================================================

  describe('getLoanTimeline', () => {
    it('calls /doc-analytics/loan/{loanId}/timeline', async () => {
      await getLoanTimeline('loan-123');
      const [url] = mockFetch.mock.calls[0];
      expect(url).toBe(`${BASE}/doc-analytics/loan/loan-123/timeline`);
    });

    it('works with numeric-string loan IDs', async () => {
      await getLoanTimeline('99');
      const [url] = mockFetch.mock.calls[0];
      expect(url).toBe(`${BASE}/doc-analytics/loan/99/timeline`);
    });

    it('returns parsed JSON response', async () => {
      const payload = { loan_id: 'loan-123', events: [] };
      mockFetch.mockResolvedValue(makeOkResponse(payload));
      const result = await getLoanTimeline('loan-123');
      expect(result).toEqual(payload);
    });
  });

  // =========================================================================
  // getTrends
  // =========================================================================

  describe('getTrends', () => {
    it('calls /doc-analytics/trends with defaults period=weekly&days=90', async () => {
      await getTrends();
      const [url] = mockFetch.mock.calls[0];
      expect(url).toBe(`${BASE}/doc-analytics/trends?period=weekly&days=90`);
    });

    it('supports custom period', async () => {
      await getTrends('monthly');
      const [url] = mockFetch.mock.calls[0];
      expect(url).toContain('period=monthly');
    });

    it('supports custom days', async () => {
      await getTrends('weekly', 30);
      const [url] = mockFetch.mock.calls[0];
      expect(url).toContain('days=30');
    });

    it('supports both custom period and days', async () => {
      await getTrends('daily', 14);
      const [url] = mockFetch.mock.calls[0];
      expect(url).toBe(`${BASE}/doc-analytics/trends?period=daily&days=14`);
    });
  });

  // =========================================================================
  // getBottlenecks
  // =========================================================================

  describe('getBottlenecks', () => {
    it('calls /doc-analytics/bottlenecks with default days=30', async () => {
      await getBottlenecks();
      const [url] = mockFetch.mock.calls[0];
      expect(url).toBe(`${BASE}/doc-analytics/bottlenecks?days=30`);
    });

    it('supports custom days', async () => {
      await getBottlenecks(60);
      const [url] = mockFetch.mock.calls[0];
      expect(url).toBe(`${BASE}/doc-analytics/bottlenecks?days=60`);
    });
  });
});
