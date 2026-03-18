import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock('../../pages/PipelineEfficiency.css', () => ({}));

// Mock react-router-dom navigate
const mockNavigate = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

// Mock toast
vi.mock('../../utils/toast', () => ({
  toast: {
    info: vi.fn(),
    error: vi.fn(),
    success: vi.fn(),
  },
}));

// Mock global fetch
const mockFetch = vi.fn();
global.fetch = mockFetch;

import PipelineEfficiency from '../PipelineEfficiency';
import { toast } from '../../utils/toast';

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

function renderPage() {
  return render(
    <MemoryRouter>
      <PipelineEfficiency />
    </MemoryRouter>
  );
}

/** Build a full set of mock API responses for the happy path. */
function mockAllEndpoints(overrides = {}) {
  const defaults = {
    efficiency: {
      hasData: true,
      overallScore: 78,
      trend: 5,
      lastUpdated: '2026-03-18T12:00:00Z',
      keyMetrics: {
        avgTimeToClose: 32,
        pullThroughRate: 71,
        loansFallingBehind: 4,
      },
      summary: {
        totalLeads: 48,
        totalLoans: 25,
      },
    },
    stages: {
      hasData: true,
      stageMetrics: [
        { name: 'Application', type: 'lead', volume: 12, avgTime: '3.2 days', efficiency: 85 },
        { name: 'Processing', type: 'loan', volume: 8, avgTime: '5.1 days', efficiency: 62 },
        { name: 'Underwriting', type: 'loan', volume: 5, avgTime: '4.0 days', efficiency: 45 },
        { name: 'Empty Stage', type: 'loan', volume: 0, avgTime: '0 days', efficiency: 0 },
      ],
    },
    team: {
      hasData: true,
      teamMetrics: [
        { role: 'Processor', efficiency: 88, activeLoans: 15 },
        { role: 'Underwriter', efficiency: 72, activeLoans: 10 },
      ],
    },
    bottlenecks: {
      hasData: true,
      bottlenecks: [
        { id: 'b1', issue: 'Document delays', stage: 'Processing', severity: 'high', affectedCount: 6, avgDelay: '3.2 days' },
        { id: 'b2', issue: 'Appraisal backlog', stage: 'Underwriting', severity: 'medium', affectedCount: 3, avgDelay: '2.1 days' },
      ],
    },
    trends: {
      hasData: true,
      trends: [
        { week: 'Week 1', score: 70, volume: 8 },
        { week: 'Week 2', score: 75, volume: 10 },
        { week: 'Week 3', score: 78, volume: 12 },
      ],
    },
  };

  const merged = { ...defaults, ...overrides };

  mockFetch.mockImplementation((url) => {
    if (url.includes('/pipeline/efficiency')) return mockResponse(merged.efficiency);
    if (url.includes('/pipeline/stages')) return mockResponse(merged.stages);
    if (url.includes('/pipeline/team')) return mockResponse(merged.team);
    if (url.includes('/pipeline/bottlenecks')) return mockResponse(merged.bottlenecks);
    if (url.includes('/pipeline/trends')) return mockResponse(merged.trends);
    return mockResponse({}, false);
  });
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('PipelineEfficiency', () => {
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
    it('shows loading spinner while data is being fetched', () => {
      // Never-resolving promises keep component in loading state
      mockFetch.mockReturnValue(new Promise(() => {}));
      renderPage();

      expect(screen.getByText('Loading pipeline efficiency data...')).toBeInTheDocument();
    });

    it('loading spinner is inside an efficiency-page container', () => {
      mockFetch.mockReturnValue(new Promise(() => {}));
      renderPage();

      const spinner = document.querySelector('.efficiency-page .loading-spinner');
      expect(spinner).toBeInTheDocument();
    });
  });

  // =========================================================================
  // 2. Error State
  // =========================================================================

  describe('Error State', () => {
    it('shows error message when API calls fail', async () => {
      mockFetch.mockRejectedValue(new Error('Network failure'));
      renderPage();

      await waitFor(() => {
        expect(screen.getByText('Failed to load pipeline data. Please try again.')).toBeInTheDocument();
      });
    });

    it('shows Try Again button in error state', async () => {
      mockFetch.mockRejectedValue(new Error('Network failure'));
      renderPage();

      await waitFor(() => {
        expect(screen.getByText('Try Again')).toBeInTheDocument();
      });
    });

    it('retries loading when Try Again is clicked', async () => {
      // First call fails, second succeeds
      mockFetch
        .mockRejectedValueOnce(new Error('Temporary'))
        .mockRejectedValueOnce(new Error('Temporary'))
        .mockRejectedValueOnce(new Error('Temporary'))
        .mockRejectedValueOnce(new Error('Temporary'))
        .mockRejectedValueOnce(new Error('Temporary'));

      renderPage();

      await waitFor(() => {
        expect(screen.getByText('Try Again')).toBeInTheDocument();
      });

      // Now set up success responses
      mockAllEndpoints();

      await userEvent.click(screen.getByText('Try Again'));

      await waitFor(() => {
        expect(screen.getByText('Pipeline Efficiency Report')).toBeInTheDocument();
      });
    });
  });

  // =========================================================================
  // 3. Empty State
  // =========================================================================

  describe('Empty State', () => {
    it('shows empty state when no pipeline data exists', async () => {
      mockAllEndpoints({
        efficiency: { hasData: false },
        stages: { hasData: false, stageMetrics: [] },
        bottlenecks: { hasData: false, bottlenecks: [] },
        trends: { hasData: false, trends: [] },
      });

      renderPage();

      await waitFor(() => {
        expect(screen.getByText('No Pipeline Data Yet')).toBeInTheDocument();
      });
    });

    it('empty state shows navigation buttons to leads and loans', async () => {
      mockAllEndpoints({
        efficiency: { hasData: false },
        stages: { hasData: false, stageMetrics: [] },
        bottlenecks: { hasData: false, bottlenecks: [] },
        trends: { hasData: false, trends: [] },
      });

      renderPage();

      await waitFor(() => {
        expect(screen.getByText('Add Your First Lead')).toBeInTheDocument();
        expect(screen.getByText('Add Your First Loan')).toBeInTheDocument();
      });
    });

    it('empty state explains what the page will show', async () => {
      mockAllEndpoints({
        efficiency: { hasData: false },
        stages: { hasData: false, stageMetrics: [] },
        bottlenecks: { hasData: false, bottlenecks: [] },
        trends: { hasData: false, trends: [] },
      });

      renderPage();

      await waitFor(() => {
        expect(screen.getByText('What you\'ll see here:')).toBeInTheDocument();
        expect(screen.getByText('Overall pipeline efficiency score')).toBeInTheDocument();
      });
    });

    it('navigates to /leads when Add Your First Lead is clicked', async () => {
      mockAllEndpoints({
        efficiency: { hasData: false },
        stages: { hasData: false, stageMetrics: [] },
        bottlenecks: { hasData: false, bottlenecks: [] },
        trends: { hasData: false, trends: [] },
      });

      renderPage();

      await waitFor(() => {
        expect(screen.getByText('Add Your First Lead')).toBeInTheDocument();
      });

      await userEvent.click(screen.getByText('Add Your First Lead'));
      expect(mockNavigate).toHaveBeenCalledWith('/leads');
    });
  });

  // =========================================================================
  // 4. Overall Score and Key Metrics
  // =========================================================================

  describe('Overall Score and Key Metrics', () => {
    it('displays the overall efficiency score', async () => {
      mockAllEndpoints();
      renderPage();

      await waitFor(() => {
        expect(screen.getByText('78')).toBeInTheDocument();
        expect(screen.getByText('Overall Pipeline Efficiency')).toBeInTheDocument();
      });
    });

    it('shows positive trend indicator', async () => {
      mockAllEndpoints();
      renderPage();

      await waitFor(() => {
        const trendEl = document.querySelector('.score-trend-large.up');
        expect(trendEl).toBeInTheDocument();
        expect(trendEl.textContent).toContain('5%');
      });
    });

    it('shows negative trend indicator when trend is negative', async () => {
      mockAllEndpoints({
        efficiency: {
          hasData: true,
          overallScore: 65,
          trend: -3,
          keyMetrics: { avgTimeToClose: 35, pullThroughRate: 60, loansFallingBehind: 7 },
          summary: { totalLeads: 30, totalLoans: 15 },
        },
      });

      renderPage();

      await waitFor(() => {
        const trendEl = document.querySelector('.score-trend-large.down');
        expect(trendEl).toBeInTheDocument();
        expect(trendEl.textContent).toContain('3%');
      });
    });

    it('renders all five key metric cards', async () => {
      mockAllEndpoints();
      renderPage();

      await waitFor(() => {
        expect(screen.getByText('Avg. Time to Close')).toBeInTheDocument();
        expect(screen.getByText('Pull-Through Rate')).toBeInTheDocument();
        expect(screen.getByText('Loans Falling Behind')).toBeInTheDocument();
        expect(screen.getByText('Total Leads')).toBeInTheDocument();
        expect(screen.getByText('Total Loans')).toBeInTheDocument();
      });
    });

    it('displays correct metric values', async () => {
      mockAllEndpoints();
      renderPage();

      await waitFor(() => {
        expect(screen.getByText('32 days')).toBeInTheDocument();
        expect(screen.getByText('71%')).toBeInTheDocument();
        expect(screen.getByText('48')).toBeInTheDocument();
        expect(screen.getByText('25')).toBeInTheDocument();
      });
    });
  });

  // =========================================================================
  // 5. Stage Performance Table
  // =========================================================================

  describe('Stage Performance Table', () => {
    it('renders stage performance table with headers', async () => {
      mockAllEndpoints();
      renderPage();

      await waitFor(() => {
        expect(screen.getByText('Stage Performance Analysis')).toBeInTheDocument();
        expect(screen.getByText('Stage')).toBeInTheDocument();
        expect(screen.getByText('Type')).toBeInTheDocument();
        expect(screen.getByText('Volume')).toBeInTheDocument();
        expect(screen.getByText('Avg. Time')).toBeInTheDocument();
        expect(screen.getByText('Efficiency')).toBeInTheDocument();
      });
    });

    it('filters out stages with zero volume', async () => {
      mockAllEndpoints();
      renderPage();

      await waitFor(() => {
        // 'Application', 'Processing', 'Underwriting' should appear (volume > 0)
        expect(screen.getByText('Application')).toBeInTheDocument();
        expect(screen.getByText('Processing')).toBeInTheDocument();
        expect(screen.getByText('Underwriting')).toBeInTheDocument();
        // 'Empty Stage' has volume 0, should NOT appear
        expect(screen.queryByText('Empty Stage')).not.toBeInTheDocument();
      });
    });

    it('shows efficiency percentage with color coding', async () => {
      mockAllEndpoints();
      renderPage();

      await waitFor(() => {
        // 85% efficiency -> 'high' class
        const highBadge = document.querySelector('.efficiency-badge.high');
        expect(highBadge).toBeInTheDocument();
        expect(highBadge.textContent).toBe('85%');

        // 62% efficiency -> 'medium' class
        const mediumBadge = document.querySelector('.efficiency-badge.medium');
        expect(mediumBadge).toBeInTheDocument();
        expect(mediumBadge.textContent).toBe('62%');

        // 45% efficiency -> 'low' class
        const lowBadge = document.querySelector('.efficiency-badge.low');
        expect(lowBadge).toBeInTheDocument();
        expect(lowBadge.textContent).toBe('45%');
      });
    });

    it('navigates to stage detail on row click', async () => {
      mockAllEndpoints();
      renderPage();

      await waitFor(() => {
        expect(screen.getByText('Application')).toBeInTheDocument();
      });

      await userEvent.click(screen.getByText('Application'));
      expect(mockNavigate).toHaveBeenCalledWith('/efficiency/stage/application');
    });

    it('shows empty message when no stage data is available', async () => {
      mockAllEndpoints({
        stages: { hasData: true, stageMetrics: [] },
      });

      renderPage();

      await waitFor(() => {
        expect(screen.getByText('No stage data available.')).toBeInTheDocument();
      });
    });
  });

  // =========================================================================
  // 6. Team Performance
  // =========================================================================

  describe('Team Performance', () => {
    it('renders team performance cards', async () => {
      mockAllEndpoints();
      renderPage();

      await waitFor(() => {
        expect(screen.getByText('Team Performance Metrics')).toBeInTheDocument();
        expect(screen.getByText('Processor')).toBeInTheDocument();
        expect(screen.getByText('Underwriter')).toBeInTheDocument();
      });
    });

    it('shows active loans count for each team member', async () => {
      mockAllEndpoints();
      renderPage();

      await waitFor(() => {
        expect(screen.getByText('15')).toBeInTheDocument(); // Processor active loans
        expect(screen.getByText('10')).toBeInTheDocument(); // Underwriter active loans
      });
    });

    it('navigates to team detail on card click', async () => {
      mockAllEndpoints();
      renderPage();

      await waitFor(() => {
        expect(screen.getByText('Processor')).toBeInTheDocument();
      });

      const processorCard = screen.getByText('Processor').closest('.team-performance-card');
      await userEvent.click(processorCard);
      expect(mockNavigate).toHaveBeenCalledWith('/efficiency/team/processor');
    });

    it('hides team section when no team metrics exist', async () => {
      mockAllEndpoints({
        team: { hasData: true, teamMetrics: [] },
      });

      renderPage();

      await waitFor(() => {
        expect(screen.getByText('Stage Performance Analysis')).toBeInTheDocument();
      });

      expect(screen.queryByText('Team Performance Metrics')).not.toBeInTheDocument();
    });
  });

  // =========================================================================
  // 7. Bottlenecks
  // =========================================================================

  describe('Bottlenecks', () => {
    it('renders bottleneck cards with severity icons', async () => {
      mockAllEndpoints();
      renderPage();

      await waitFor(() => {
        expect(screen.getByText('Active Bottlenecks & Recommendations')).toBeInTheDocument();
        expect(screen.getByText('Document delays')).toBeInTheDocument();
        expect(screen.getByText('Appraisal backlog')).toBeInTheDocument();
      });
    });

    it('shows affected count and delay for each bottleneck', async () => {
      mockAllEndpoints();
      renderPage();

      await waitFor(() => {
        expect(screen.getByText('6')).toBeInTheDocument();
        expect(screen.getByText('3.2 days')).toBeInTheDocument();
      });
    });

    it('shows success message when no bottlenecks exist', async () => {
      mockAllEndpoints({
        bottlenecks: { hasData: true, bottlenecks: [] },
      });

      renderPage();

      await waitFor(() => {
        expect(screen.getByText('No bottlenecks detected! Your pipeline is flowing smoothly.')).toBeInTheDocument();
      });
    });

    it('navigates to bottleneck detail on card click', async () => {
      mockAllEndpoints();
      renderPage();

      await waitFor(() => {
        expect(screen.getByText('Document delays')).toBeInTheDocument();
      });

      const bottleneckCard = screen.getByText('Document delays').closest('.bottleneck-card');
      await userEvent.click(bottleneckCard);
      expect(mockNavigate).toHaveBeenCalledWith('/efficiency/bottleneck/b1');
    });
  });

  // =========================================================================
  // 8. Trends Chart
  // =========================================================================

  describe('Trends Chart', () => {
    it('renders trend chart bars with correct data', async () => {
      mockAllEndpoints();
      renderPage();

      await waitFor(() => {
        expect(screen.getByText('Efficiency Trends (Last 12 Weeks)')).toBeInTheDocument();
      });

      const scoreBars = document.querySelectorAll('.chart-bar.score-bar');
      expect(scoreBars.length).toBe(3);

      // First bar should have height 70% (score is 70)
      expect(scoreBars[0].style.height).toBe('70%');
    });

    it('renders chart labels with abbreviated week names', async () => {
      mockAllEndpoints();
      renderPage();

      await waitFor(() => {
        expect(screen.getByText('W1')).toBeInTheDocument();
        expect(screen.getByText('W2')).toBeInTheDocument();
        expect(screen.getByText('W3')).toBeInTheDocument();
      });
    });

    it('shows chart legend with Efficiency Score and Loan Volume', async () => {
      mockAllEndpoints();
      renderPage();

      await waitFor(() => {
        expect(screen.getByText('Efficiency Score')).toBeInTheDocument();
        expect(screen.getByText('Loan Volume')).toBeInTheDocument();
      });
    });

    it('shows empty message when all trend volumes are zero', async () => {
      mockAllEndpoints({
        trends: {
          hasData: true,
          trends: [
            { week: 'Week 1', score: 0, volume: 0 },
            { week: 'Week 2', score: 0, volume: 0 },
          ],
        },
      });

      renderPage();

      await waitFor(() => {
        expect(screen.getByText('No historical data available yet. Check back after processing some leads and loans.')).toBeInTheDocument();
      });
    });
  });

  // =========================================================================
  // 9. Time Range Selection
  // =========================================================================

  describe('Time Range Selection', () => {
    it('renders time range selector with default 30 days', async () => {
      mockAllEndpoints();
      renderPage();

      await waitFor(() => {
        const selector = document.querySelector('.time-range-selector');
        expect(selector).toBeInTheDocument();
        expect(selector.value).toBe('30days');
      });
    });

    it('refetches data when time range is changed', async () => {
      mockAllEndpoints();
      renderPage();

      await waitFor(() => {
        expect(screen.getByText('Pipeline Efficiency Report')).toBeInTheDocument();
      });

      const callCountBefore = mockFetch.mock.calls.length;

      const selector = document.querySelector('.time-range-selector');
      fireEvent.change(selector, { target: { value: '90days' } });

      // Changing the time range should trigger new fetch calls
      await waitFor(() => {
        expect(mockFetch.mock.calls.length).toBeGreaterThan(callCountBefore);
      });

      // Verify the new time range is passed in the URL
      const latestCalls = mockFetch.mock.calls.slice(callCountBefore);
      const efficiencyCall = latestCalls.find(c => c[0].includes('/pipeline/efficiency'));
      expect(efficiencyCall[0]).toContain('time_range=90days');
    });

    it('includes all four time range options', async () => {
      mockAllEndpoints();
      renderPage();

      await waitFor(() => {
        expect(screen.getByText('Last 7 Days')).toBeInTheDocument();
        expect(screen.getByText('Last 30 Days')).toBeInTheDocument();
        expect(screen.getByText('Last 90 Days')).toBeInTheDocument();
        expect(screen.getByText('Last Year')).toBeInTheDocument();
      });
    });
  });

  // =========================================================================
  // 10. Header and Navigation
  // =========================================================================

  describe('Header and Navigation', () => {
    it('shows Back to Dashboard button', async () => {
      mockAllEndpoints();
      renderPage();

      await waitFor(() => {
        const backBtn = screen.getAllByText(/Back to Dashboard/);
        expect(backBtn.length).toBeGreaterThanOrEqual(1);
      });
    });

    it('navigates back to /dashboard when back button is clicked', async () => {
      mockAllEndpoints();
      renderPage();

      await waitFor(() => {
        expect(screen.getByText('Pipeline Efficiency Report')).toBeInTheDocument();
      });

      const backBtns = screen.getAllByText(/Back to Dashboard/);
      await userEvent.click(backBtns[0]);
      expect(mockNavigate).toHaveBeenCalledWith('/dashboard');
    });

    it('shows Export Report button that triggers toast', async () => {
      mockAllEndpoints();
      renderPage();

      await waitFor(() => {
        expect(screen.getByText('Export Report')).toBeInTheDocument();
      });

      await userEvent.click(screen.getByText('Export Report'));
      expect(toast.info).toHaveBeenCalledWith('Export feature coming soon');
    });

    it('displays last updated timestamp', async () => {
      mockAllEndpoints();
      renderPage();

      await waitFor(() => {
        const lastUpdated = document.querySelector('.last-updated');
        expect(lastUpdated).toBeInTheDocument();
        expect(lastUpdated.textContent).toContain('Last updated:');
      });
    });
  });

  // =========================================================================
  // 11. API Integration
  // =========================================================================

  describe('API Integration', () => {
    it('sends authorization header with all fetch calls', async () => {
      mockAllEndpoints();
      renderPage();

      await waitFor(() => {
        expect(screen.getByText('Pipeline Efficiency Report')).toBeInTheDocument();
      });

      // All fetch calls should include the Authorization header
      mockFetch.mock.calls.forEach((call) => {
        const options = call[1];
        expect(options.headers.Authorization).toBe('Bearer test-token');
      });
    });

    it('makes 5 parallel API calls on load', async () => {
      mockAllEndpoints();
      renderPage();

      await waitFor(() => {
        expect(screen.getByText('Pipeline Efficiency Report')).toBeInTheDocument();
      });

      // Should call efficiency, stages, team, bottlenecks, trends
      expect(mockFetch).toHaveBeenCalledTimes(5);
    });

    it('gracefully handles partial API failures', async () => {
      // Stages endpoint fails but others succeed
      mockFetch.mockImplementation((url) => {
        if (url.includes('/pipeline/stages')) return mockResponse({}, false);
        if (url.includes('/pipeline/efficiency')) return mockResponse({
          hasData: true, overallScore: 78, trend: 5,
          keyMetrics: { avgTimeToClose: 32, pullThroughRate: 71, loansFallingBehind: 4 },
          summary: { totalLeads: 48, totalLoans: 25 },
        });
        if (url.includes('/pipeline/team')) return mockResponse({ teamMetrics: [] });
        if (url.includes('/pipeline/bottlenecks')) return mockResponse({ bottlenecks: [] });
        if (url.includes('/pipeline/trends')) return mockResponse({ trends: [] });
        return mockResponse({}, false);
      });

      renderPage();

      await waitFor(() => {
        // Should still render the page with available data
        expect(screen.getByText('Pipeline Efficiency Report')).toBeInTheDocument();
        expect(screen.getByText('78')).toBeInTheDocument();
      });
    });
  });
});
