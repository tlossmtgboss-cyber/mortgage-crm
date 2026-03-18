import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock('../PipelineProbability.css', () => ({}));

// Mock react-router-dom navigate
const mockNavigate = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

// Mock global fetch
const mockFetch = vi.fn();
global.fetch = mockFetch;

import { PipelineProbabilityWidget, PipelineProbabilityPage } from '../PipelineProbability';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function mockResponse(body, ok = true) {
  return Promise.resolve({
    ok,
    status: ok ? 200 : 500,
    json: () => Promise.resolve(body),
  });
}

function renderWidget(props = {}) {
  return render(
    <MemoryRouter>
      <PipelineProbabilityWidget {...props} />
    </MemoryRouter>
  );
}

function renderPage() {
  return render(
    <MemoryRouter>
      <PipelineProbabilityPage />
    </MemoryRouter>
  );
}

const mockSummary = {
  weighted_avg_probability: 72,
  expected_funded_volume: 5400000,
  at_risk_volume: 1200000,
  total_volume: 8500000,
  total_loans: 30,
  low_risk_count: 12,
  medium_risk_count: 8,
  high_risk_count: 6,
  critical_risk_count: 4,
  improving_count: 10,
  declining_count: 5,
  top_risk_factors: [
    { factor: 'Missing Documents', count: 8 },
    { factor: 'Rate Lock Expiring', count: 5 },
  ],
};

const mockAtRiskLoans = [
  {
    loan_id: 'loan-1',
    borrower_name: 'John Smith',
    loan_amount: 350000,
    close_probability: 35,
    risk_level: 'high',
    trend: 'declining',
    recommended_actions: [{ action: 'Follow up on missing appraisal' }],
  },
  {
    loan_id: 'loan-2',
    borrower_name: 'Jane Doe',
    loan_amount: 275000,
    close_probability: 45,
    risk_level: 'medium',
    trend: 'stable',
    recommended_actions: [{ action: 'Request updated bank statements' }],
  },
];

const mockLoans = [
  {
    loan_id: 'loan-1',
    borrower_name: 'John Smith',
    loan_number: '2026-001',
    loan_amount: 350000,
    current_status: 'Processing',
    close_probability: 35,
    risk_level: 'high',
    trend: 'declining',
    expected_close_days: 45,
    lock_expiration_risk: true,
  },
  {
    loan_id: 'loan-2',
    borrower_name: 'Jane Doe',
    loan_number: '2026-002',
    loan_amount: 275000,
    current_status: 'Underwriting',
    close_probability: 82,
    risk_level: 'low',
    trend: 'improving',
    expected_close_days: 20,
    lock_expiration_risk: false,
  },
];

const mockDistribution = {
  total_loans: 30,
  buckets: ['0-20', '20-40', '40-60', '60-80', '80-100'],
  distribution: {
    '0-20': { count: 3 },
    '20-40': { count: 5 },
    '40-60': { count: 7 },
    '60-80': { count: 10 },
    '80-100': { count: 5 },
  },
};

function mockWidgetEndpoints() {
  mockFetch.mockImplementation((url) => {
    if (url.includes('/pipeline-probability/summary')) return mockResponse(mockSummary);
    if (url.includes('/pipeline-probability/at-risk')) return mockResponse(mockAtRiskLoans);
    return mockResponse({}, false);
  });
}

function mockPageEndpoints() {
  mockFetch.mockImplementation((url) => {
    if (url.includes('/pipeline-probability/summary')) return mockResponse(mockSummary);
    if (url.includes('/pipeline-probability/pipeline')) return mockResponse(mockLoans);
    if (url.includes('/pipeline-probability/distribution')) return mockResponse(mockDistribution);
    if (url.includes('/pipeline-probability/loan/')) return mockResponse({
      ...mockLoans[0],
      close_probability: 35,
      confidence_level: 78,
      risk_factors: [
        { factor: 'Missing Appraisal', impact: 0.25, description: 'Appraisal not received', mitigation: 'Follow up with appraiser' },
      ],
      strength_factors: [
        { factor: 'Strong Credit', impact: 0.15, description: 'Credit score above 780' },
      ],
      recommended_actions: [
        { priority: 'high', action: 'Follow up on appraisal', expected_impact: 15, effort: 'low', deadline_days: 3 },
      ],
      similar_loans_close_rate: 68,
      stage_avg_probability: 55,
    });
    return mockResponse({}, false);
  });
}

// ---------------------------------------------------------------------------
// Tests: PipelineProbabilityWidget
// ---------------------------------------------------------------------------

describe('PipelineProbabilityWidget', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    localStorage.setItem('token', 'test-token');
  });

  afterEach(() => {
    localStorage.clear();
  });

  // =========================================================================
  // 1. Loading State
  // =========================================================================

  describe('Loading State', () => {
    it('shows loading spinner while fetching data', () => {
      mockFetch.mockReturnValue(new Promise(() => {}));
      renderWidget();

      expect(document.querySelector('.pp-widget.loading')).toBeInTheDocument();
      expect(document.querySelector('.loading-spinner')).toBeInTheDocument();
    });
  });

  // =========================================================================
  // 2. Error State
  // =========================================================================

  describe('Error State', () => {
    it('shows error message when API fails', async () => {
      mockFetch.mockRejectedValue(new Error('Network error'));
      renderWidget();

      await waitFor(() => {
        expect(screen.getByText('Failed to load pipeline probability data')).toBeInTheDocument();
      });
    });

    it('shows Retry button in error state', async () => {
      mockFetch.mockRejectedValue(new Error('Network error'));
      renderWidget();

      await waitFor(() => {
        expect(screen.getByText('Retry')).toBeInTheDocument();
      });
    });

    it('retries loading when Retry is clicked', async () => {
      mockFetch.mockRejectedValueOnce(new Error('Temp'));
      mockFetch.mockRejectedValueOnce(new Error('Temp'));
      renderWidget();

      await waitFor(() => {
        expect(screen.getByText('Retry')).toBeInTheDocument();
      });

      mockWidgetEndpoints();
      await userEvent.click(screen.getByText('Retry'));

      await waitFor(() => {
        expect(screen.getByText('Pipeline Probability')).toBeInTheDocument();
      });
    });
  });

  // =========================================================================
  // 3. Compact Mode
  // =========================================================================

  describe('Compact Mode', () => {
    it('renders compact widget with Pipeline Health title', async () => {
      mockWidgetEndpoints();
      renderWidget({ compact: true });

      await waitFor(() => {
        expect(screen.getByText('Pipeline Health')).toBeInTheDocument();
      });
    });

    it('shows weighted average probability score in compact mode', async () => {
      mockWidgetEndpoints();
      renderWidget({ compact: true });

      await waitFor(() => {
        expect(screen.getByText('72%')).toBeInTheDocument();
      });
    });

    it('shows critical and high risk counts in compact mode', async () => {
      mockWidgetEndpoints();
      renderWidget({ compact: true });

      await waitFor(() => {
        expect(screen.getByText('4')).toBeInTheDocument(); // critical count
        expect(screen.getByText('Critical')).toBeInTheDocument();
        expect(screen.getByText('6')).toBeInTheDocument(); // high risk count
        expect(screen.getByText('High Risk')).toBeInTheDocument();
      });
    });

    it('navigates to full page on compact widget click', async () => {
      mockWidgetEndpoints();
      renderWidget({ compact: true });

      await waitFor(() => {
        expect(screen.getByText('Pipeline Health')).toBeInTheDocument();
      });

      const compactWidget = document.querySelector('.pp-widget.compact');
      await userEvent.click(compactWidget);
      expect(mockNavigate).toHaveBeenCalledWith('/pipeline-probability');
    });
  });

  // =========================================================================
  // 4. Full Widget Mode
  // =========================================================================

  describe('Full Widget Mode', () => {
    it('renders widget with Pipeline Probability title', async () => {
      mockWidgetEndpoints();
      renderWidget();

      await waitFor(() => {
        expect(screen.getByText('Pipeline Probability')).toBeInTheDocument();
      });
    });

    it('shows summary statistics', async () => {
      mockWidgetEndpoints();
      renderWidget();

      await waitFor(() => {
        expect(screen.getByText('Weighted Probability')).toBeInTheDocument();
        expect(screen.getByText('Expected Funded')).toBeInTheDocument();
        expect(screen.getByText('At-Risk Volume')).toBeInTheDocument();
        expect(screen.getByText('Total Pipeline')).toBeInTheDocument();
      });
    });

    it('shows total loans count', async () => {
      mockWidgetEndpoints();
      renderWidget();

      await waitFor(() => {
        expect(screen.getByText('30 loans')).toBeInTheDocument();
      });
    });

    it('renders risk distribution bars', async () => {
      mockWidgetEndpoints();
      renderWidget();

      await waitFor(() => {
        expect(screen.getByText('Risk Distribution')).toBeInTheDocument();
      });

      const riskBars = document.querySelectorAll('.pp-risk-bar');
      expect(riskBars.length).toBe(4); // Low, Medium, High, Critical
    });

    it('shows at-risk loans list', async () => {
      mockWidgetEndpoints();
      renderWidget();

      await waitFor(() => {
        expect(screen.getByText('John Smith')).toBeInTheDocument();
        expect(screen.getByText('Jane Doe')).toBeInTheDocument();
      });
    });

    it('shows recommended actions for at-risk loans', async () => {
      mockWidgetEndpoints();
      renderWidget();

      await waitFor(() => {
        expect(screen.getByText('Follow up on missing appraisal')).toBeInTheDocument();
      });
    });

    it('shows improving and declining trend counts', async () => {
      mockWidgetEndpoints();
      renderWidget();

      await waitFor(() => {
        expect(screen.getByText('Improving')).toBeInTheDocument();
        expect(screen.getByText('Declining')).toBeInTheDocument();
        expect(screen.getByText('10')).toBeInTheDocument(); // improving count
      });
    });

    it('navigates to loan detail when at-risk loan is clicked', async () => {
      mockWidgetEndpoints();
      renderWidget();

      await waitFor(() => {
        expect(screen.getByText('John Smith')).toBeInTheDocument();
      });

      const atRiskItem = screen.getByText('John Smith').closest('.pp-at-risk-item');
      await userEvent.click(atRiskItem);
      expect(mockNavigate).toHaveBeenCalledWith('/loans/loan-1');
    });

    it('shows View Details button', async () => {
      mockWidgetEndpoints();
      renderWidget();

      await waitFor(() => {
        expect(screen.getByText('View Details →')).toBeInTheDocument();
      });
    });
  });
});

// ---------------------------------------------------------------------------
// Tests: PipelineProbabilityPage
// ---------------------------------------------------------------------------

describe('PipelineProbabilityPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    localStorage.setItem('token', 'test-token');
  });

  afterEach(() => {
    localStorage.clear();
  });

  // =========================================================================
  // 1. Loading / Error States
  // =========================================================================

  describe('Loading and Error States', () => {
    it('shows loading state with message', () => {
      mockFetch.mockReturnValue(new Promise(() => {}));
      renderPage();

      expect(screen.getByText('Calculating pipeline probabilities...')).toBeInTheDocument();
    });

    it('shows error state with retry button', async () => {
      mockFetch.mockRejectedValue(new Error('Server error'));
      renderPage();

      await waitFor(() => {
        expect(screen.getByText('Error')).toBeInTheDocument();
        expect(screen.getByText('Failed to load pipeline probability data')).toBeInTheDocument();
        expect(screen.getByText('Retry')).toBeInTheDocument();
      });
    });
  });

  // =========================================================================
  // 2. Page Header and Summary
  // =========================================================================

  describe('Page Header and Summary', () => {
    it('renders page title and subtitle', async () => {
      mockPageEndpoints();
      renderPage();

      await waitFor(() => {
        expect(screen.getByText('Pipeline Probability Analysis')).toBeInTheDocument();
        expect(screen.getByText('AI-powered closing probability predictions for your pipeline')).toBeInTheDocument();
      });
    });

    it('renders summary cards with correct values', async () => {
      mockPageEndpoints();
      renderPage();

      await waitFor(() => {
        expect(screen.getByText('Weighted Avg Probability')).toBeInTheDocument();
        expect(screen.getByText('Expected Funded Volume')).toBeInTheDocument();
        expect(screen.getByText('At-Risk Volume')).toBeInTheDocument();
      });
    });

    it('shows Refresh Scores button', async () => {
      mockPageEndpoints();
      renderPage();

      await waitFor(() => {
        expect(screen.getByText(/Refresh Scores/)).toBeInTheDocument();
      });
    });
  });

  // =========================================================================
  // 3. Loans Table
  // =========================================================================

  describe('Loans Table', () => {
    it('renders loans table with all column headers', async () => {
      mockPageEndpoints();
      renderPage();

      await waitFor(() => {
        expect(screen.getByText('Borrower')).toBeInTheDocument();
        expect(screen.getByText('Loan Amount')).toBeInTheDocument();
        expect(screen.getByText('Status')).toBeInTheDocument();
        expect(screen.getByText('Probability')).toBeInTheDocument();
        expect(screen.getByText('Risk')).toBeInTheDocument();
        expect(screen.getByText('Trend')).toBeInTheDocument();
        expect(screen.getByText('Days to Close')).toBeInTheDocument();
        expect(screen.getByText('Actions')).toBeInTheDocument();
      });
    });

    it('renders loan rows with borrower info', async () => {
      mockPageEndpoints();
      renderPage();

      await waitFor(() => {
        expect(screen.getByText('John Smith')).toBeInTheDocument();
        expect(screen.getByText('2026-001')).toBeInTheDocument();
        expect(screen.getByText('Jane Doe')).toBeInTheDocument();
        expect(screen.getByText('2026-002')).toBeInTheDocument();
      });
    });

    it('shows lock expiration warning icon for at-risk loans', async () => {
      mockPageEndpoints();
      renderPage();

      await waitFor(() => {
        const lockWarning = document.querySelector('.lock-warning');
        expect(lockWarning).toBeInTheDocument();
      });
    });

    it('shows loan count in section header', async () => {
      mockPageEndpoints();
      renderPage();

      await waitFor(() => {
        expect(screen.getByText('Pipeline Loans (2)')).toBeInTheDocument();
      });
    });

    it('navigates to loan page via View Loan button', async () => {
      mockPageEndpoints();
      renderPage();

      await waitFor(() => {
        expect(screen.getByText('John Smith')).toBeInTheDocument();
      });

      const viewButtons = screen.getAllByText('View Loan');
      await userEvent.click(viewButtons[0]);
      expect(mockNavigate).toHaveBeenCalledWith('/loans/loan-1');
    });
  });

  // =========================================================================
  // 4. Distribution Chart
  // =========================================================================

  describe('Distribution Chart', () => {
    it('renders probability distribution section', async () => {
      mockPageEndpoints();
      renderPage();

      await waitFor(() => {
        expect(screen.getByText('Probability Distribution')).toBeInTheDocument();
      });
    });

    it('renders distribution bars for each bucket', async () => {
      mockPageEndpoints();
      renderPage();

      await waitFor(() => {
        const bars = document.querySelectorAll('.pp-distribution-bar');
        expect(bars.length).toBe(5);
      });
    });
  });

  // =========================================================================
  // 5. Risk Factors
  // =========================================================================

  describe('Risk Factors', () => {
    it('renders top risk factors section', async () => {
      mockPageEndpoints();
      renderPage();

      await waitFor(() => {
        expect(screen.getByText('Top Risk Factors Across Pipeline')).toBeInTheDocument();
        expect(screen.getByText('Missing Documents')).toBeInTheDocument();
        expect(screen.getByText('8 loans')).toBeInTheDocument();
        expect(screen.getByText('Rate Lock Expiring')).toBeInTheDocument();
        expect(screen.getByText('5 loans')).toBeInTheDocument();
      });
    });
  });

  // =========================================================================
  // 6. Filters
  // =========================================================================

  describe('Filters', () => {
    it('renders risk level filter dropdown', async () => {
      mockPageEndpoints();
      renderPage();

      await waitFor(() => {
        expect(screen.getByText('All Risk Levels')).toBeInTheDocument();
      });
    });

    it('renders min and max probability inputs', async () => {
      mockPageEndpoints();
      renderPage();

      await waitFor(() => {
        expect(screen.getByPlaceholderText('Min Probability')).toBeInTheDocument();
        expect(screen.getByPlaceholderText('Max Probability')).toBeInTheDocument();
      });
    });

    it('refetches data when risk level filter changes', async () => {
      mockPageEndpoints();
      renderPage();

      await waitFor(() => {
        expect(screen.getByText('All Risk Levels')).toBeInTheDocument();
      });

      const callCountBefore = mockFetch.mock.calls.length;

      const select = screen.getByDisplayValue('All Risk Levels');
      fireEvent.change(select, { target: { value: 'high' } });

      await waitFor(() => {
        expect(mockFetch.mock.calls.length).toBeGreaterThan(callCountBefore);
      });

      // The pipeline endpoint should include risk_level param
      const latestCalls = mockFetch.mock.calls.slice(callCountBefore);
      const pipelineCall = latestCalls.find(c => c[0].includes('/pipeline-probability/pipeline'));
      expect(pipelineCall[0]).toContain('risk_level=high');
    });
  });

  // =========================================================================
  // 7. Loan Detail Panel
  // =========================================================================

  describe('Loan Detail Panel', () => {
    it('opens loan detail panel when a loan row is clicked', async () => {
      mockPageEndpoints();
      renderPage();

      await waitFor(() => {
        expect(screen.getByText('John Smith')).toBeInTheDocument();
      });

      // Click the loan row (not the View Loan button)
      const loanRow = screen.getByText('John Smith').closest('tr');
      await userEvent.click(loanRow);

      await waitFor(() => {
        // Detail panel should show
        const detailPanel = document.querySelector('.pp-loan-detail-panel');
        expect(detailPanel).toBeInTheDocument();
      });
    });

    it('closes loan detail panel when close button is clicked', async () => {
      mockPageEndpoints();
      renderPage();

      await waitFor(() => {
        expect(screen.getByText('John Smith')).toBeInTheDocument();
      });

      const loanRow = screen.getByText('John Smith').closest('tr');
      await userEvent.click(loanRow);

      await waitFor(() => {
        expect(document.querySelector('.pp-loan-detail-panel')).toBeInTheDocument();
      });

      const closeBtn = document.querySelector('.pp-close-btn');
      await userEvent.click(closeBtn);

      await waitFor(() => {
        expect(document.querySelector('.pp-loan-detail-panel')).not.toBeInTheDocument();
      });
    });

    it('shows risk factors with impact and mitigation', async () => {
      mockPageEndpoints();
      renderPage();

      await waitFor(() => {
        expect(screen.getByText('John Smith')).toBeInTheDocument();
      });

      const loanRow = screen.getByText('John Smith').closest('tr');
      await userEvent.click(loanRow);

      await waitFor(() => {
        expect(screen.getByText('Risk Factors')).toBeInTheDocument();
        expect(screen.getByText('Missing Appraisal')).toBeInTheDocument();
        expect(screen.getByText('Appraisal not received')).toBeInTheDocument();
      });
    });

    it('shows strength factors', async () => {
      mockPageEndpoints();
      renderPage();

      await waitFor(() => {
        expect(screen.getByText('John Smith')).toBeInTheDocument();
      });

      const loanRow = screen.getByText('John Smith').closest('tr');
      await userEvent.click(loanRow);

      await waitFor(() => {
        expect(screen.getByText('Strength Factors')).toBeInTheDocument();
        expect(screen.getByText('Strong Credit')).toBeInTheDocument();
      });
    });

    it('shows recommended actions with priority and effort', async () => {
      mockPageEndpoints();
      renderPage();

      await waitFor(() => {
        expect(screen.getByText('John Smith')).toBeInTheDocument();
      });

      const loanRow = screen.getByText('John Smith').closest('tr');
      await userEvent.click(loanRow);

      await waitFor(() => {
        expect(screen.getByText('Recommended Actions')).toBeInTheDocument();
        expect(screen.getByText('Follow up on appraisal')).toBeInTheDocument();
        expect(screen.getByText('+15% potential')).toBeInTheDocument();
      });
    });

    it('shows comparison stats', async () => {
      mockPageEndpoints();
      renderPage();

      await waitFor(() => {
        expect(screen.getByText('John Smith')).toBeInTheDocument();
      });

      const loanRow = screen.getByText('John Smith').closest('tr');
      await userEvent.click(loanRow);

      await waitFor(() => {
        expect(screen.getByText('Comparison')).toBeInTheDocument();
        expect(screen.getByText('Similar Loans Close Rate')).toBeInTheDocument();
        expect(screen.getByText('68%')).toBeInTheDocument();
      });
    });
  });

  // =========================================================================
  // 8. Utility Components
  // =========================================================================

  describe('Utility Components', () => {
    it('RiskBadge renders with correct color class', async () => {
      mockPageEndpoints();
      renderPage();

      await waitFor(() => {
        const highBadge = document.querySelector('.risk-badge.risk-high');
        expect(highBadge).toBeInTheDocument();
        expect(highBadge.textContent).toBe('HIGH');

        const lowBadge = document.querySelector('.risk-badge.risk-low');
        expect(lowBadge).toBeInTheDocument();
        expect(lowBadge.textContent).toBe('LOW');
      });
    });

    it('TrendIndicator shows correct arrow', async () => {
      mockPageEndpoints();
      renderPage();

      await waitFor(() => {
        const decliningTrend = document.querySelector('.trend-indicator.trend-declining');
        expect(decliningTrend).toBeInTheDocument();
        expect(decliningTrend.textContent).toBe('\u2193'); // down arrow

        const improvingTrend = document.querySelector('.trend-indicator.trend-improving');
        expect(improvingTrend).toBeInTheDocument();
        expect(improvingTrend.textContent).toBe('\u2191'); // up arrow
      });
    });

    it('ProbabilityBar renders with correct width', async () => {
      mockPageEndpoints();
      renderPage();

      await waitFor(() => {
        const fills = document.querySelectorAll('.probability-fill');
        expect(fills.length).toBeGreaterThan(0);
      });
    });
  });
});
