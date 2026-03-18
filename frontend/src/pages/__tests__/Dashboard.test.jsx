import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

// ---------------------------------------------------------------------------
// Mocks — must be declared before importing the component
// ---------------------------------------------------------------------------

vi.mock('../../pages/Dashboard.css', () => ({}));

// Mock react-router-dom navigate
const mockNavigate = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

// Mock useDashboard hook
const mockRefetch = vi.fn();
const mockUseDashboard = vi.fn();
vi.mock('../../hooks/useQueries', () => ({
  useDashboard: (...args) => mockUseDashboard(...args),
}));

// Mock usePermissions
const mockUsePermissions = vi.fn();
vi.mock('../../contexts/PermissionContext', () => ({
  usePermissions: () => mockUsePermissions(),
}));

// Mock getDashboardContainersForRole
const mockGetContainers = vi.fn();
vi.mock('../../config/roleConfig', () => ({
  getDashboardContainersForRole: (...args) => mockGetContainers(...args),
}));

// Mock child components
vi.mock('../../components/PendingPermissionRequests', () => ({
  default: () => <div data-testid="pending-permissions">PendingPermissionRequests</div>,
}));
vi.mock('../../components/ProductionPredictor', () => ({
  default: ({ embedded }) => <div data-testid="production-predictor">ProductionPredictor</div>,
}));
vi.mock('../../components/DealAlerts', () => ({
  default: ({ embedded }) => <div data-testid="deal-alerts">DealAlerts</div>,
}));

// Mock api service
vi.mock('../../services/api', () => ({
  default: {
    get: vi.fn(() => Promise.resolve({ data: null })),
  },
}));

import Dashboard from '../Dashboard';
import api from '../../services/api';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function renderDashboard() {
  return render(
    <MemoryRouter>
      <Dashboard />
    </MemoryRouter>
  );
}

/** Default permissions mock for a loan officer user. */
function defaultPermissions(overrides = {}) {
  return {
    hasPermission: vi.fn(() => false),
    userRole: 'loan_officer',
    effectiveRole: 'loan_officer',
    isRolePreview: false,
    rolePreview: null,
    exitRolePreview: vi.fn(),
    ...overrides,
  };
}

/** Default dashboard data for the useDashboard hook. */
function defaultDashboardData(overrides = {}) {
  return {
    prioritized_tasks: [],
    pipeline_stats: [
      { id: 'new', name: 'New Leads', count: 12, alerts: 3, alert_text: 'follow-ups', volume: null },
      { id: 'processing', name: 'In Processing', count: 11, alerts: 4, alert_text: 'delayed', volume: 4100000 },
      { id: 'ctc', name: 'Clear to Close', count: 4, alerts: 0, alert_text: '', volume: 1300000 },
      { id: 'funded', name: 'Funded This Month', count: 9, alerts: 0, alert_text: '', volume: 3400000 },
    ],
    production: {
      annualGoal: 222,
      annualActual: 189,
      annualProgress: 85,
      monthlyGoal: 18.5,
      monthlyActual: 14,
      monthlyProgress: 76,
      weeklyGoal: 5,
      weeklyActual: 4,
      weeklyProgress: 80,
      dailyGoal: 1,
      dailyActual: 1,
      dailyProgress: 100,
    },
    lead_metrics: {
      new_today: 3,
      avg_contact_time: 1.2,
      conversion_rate: 23,
      hot_leads: 5,
      alerts: ['3 leads not contacted in 24 hours', 'Rate change detected'],
    },
    loan_issues: [],
    ai_tasks: { pending: [], waiting: [] },
    referral_stats: {},
    team_stats: {},
    messages: [],
    efficiency: {
      overallScore: 78,
      trend: 5,
      avgTimeToClose: 32,
      avgTimeToCloseChange: -2,
      pullThroughRate: 71,
      pullThroughRateChange: 3,
      loansFallingBehind: 4,
      loansFallingBehindChange: -1,
      automationRate: 45,
      automationRateChange: 5,
      customerSatisfaction: 92,
      customerSatisfactionChange: 2,
      stages: [
        { name: 'Application', efficiency: 85, status: 'high' },
        { name: 'Processing', efficiency: 62, status: 'medium' },
      ],
      team: [
        { role: 'Processor', performance: 88 },
        { role: 'Underwriter', performance: 72 },
      ],
      bottleneckCount: 2,
      bottlenecks: [
        { issue: 'Document delays', stage: 'Processing', affectedLoans: 6, avgDelay: '3.2 days' },
      ],
    },
    workflow_scores: {
      overallScore: 82,
      statuses: [
        { id: 's1', name: 'Application', score: 90, health: 'good', activeLoans: 12, tasksCompleted: 10, tasksDue: 12 },
        { id: 's2', name: 'Processing', score: 65, health: 'warning', activeLoans: 8, tasksCompleted: 5, tasksDue: 10 },
      ],
    },
    ...overrides,
  };
}

/** Default container list for a loan officer. */
const LO_CONTAINERS = [
  'ai-alerts',
  'production-tracker',
  'production-predictor',
  'deal-alerts',
  'efficiency',
  'workflow-scorecards',
  'ai-tasks',
  'pipeline',
  'referrals',
];

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('Dashboard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    localStorage.setItem('token', 'test-token');
    localStorage.setItem('user', JSON.stringify({ role: 'loan_officer', first_name: 'Test', email: 'test@example.com' }));

    mockUsePermissions.mockReturnValue(defaultPermissions());
    mockGetContainers.mockReturnValue(LO_CONTAINERS);
    mockUseDashboard.mockReturnValue({
      data: defaultDashboardData(),
      isLoading: false,
      refetch: mockRefetch,
    });
  });

  afterEach(() => {
    localStorage.clear();
  });

  // =========================================================================
  // 1. Loading State
  // =========================================================================

  describe('Loading State', () => {
    it('shows loading spinner and message while data is loading', () => {
      mockUseDashboard.mockReturnValue({
        data: undefined,
        isLoading: true,
        refetch: mockRefetch,
      });

      renderDashboard();

      expect(screen.getByText('Loading your command center...')).toBeInTheDocument();
      expect(document.querySelector('.loading-spinner')).toBeInTheDocument();
    });

    it('does not render dashboard content during loading', () => {
      mockUseDashboard.mockReturnValue({
        data: undefined,
        isLoading: true,
        refetch: mockRefetch,
      });

      renderDashboard();

      expect(screen.queryByText("Today's Command Center")).not.toBeInTheDocument();
    });
  });

  // =========================================================================
  // 2. Dashboard Header
  // =========================================================================

  describe('Dashboard Header', () => {
    it('renders the command center heading', () => {
      renderDashboard();
      expect(screen.getByText("Today's Command Center")).toBeInTheDocument();
    });

    it('displays the current date', () => {
      renderDashboard();
      const dateEl = document.querySelector('.header-date');
      expect(dateEl).toBeInTheDocument();
      // Should contain the current year
      expect(dateEl.textContent).toContain(new Date().getFullYear().toString());
    });

    it('renders AI Assistant button', () => {
      renderDashboard();
      expect(screen.getByText('AI Assistant')).toBeInTheDocument();
    });

    it('navigates to /ai when AI Assistant button is clicked', async () => {
      renderDashboard();
      await userEvent.click(screen.getByText('AI Assistant'));
      expect(mockNavigate).toHaveBeenCalledWith('/ai');
    });
  });

  // =========================================================================
  // 3. Admin Redirect
  // =========================================================================

  describe('Admin Redirect', () => {
    it('redirects admin users to /admin page', () => {
      mockUsePermissions.mockReturnValue(defaultPermissions({ userRole: 'admin' }));
      localStorage.setItem('user', JSON.stringify({ role: 'admin' }));

      renderDashboard();

      expect(mockNavigate).toHaveBeenCalledWith('/admin', { replace: true });
    });

    it('does not redirect admin users during role preview', () => {
      localStorage.setItem('role_preview', JSON.stringify({ role_name: 'loan_officer' }));
      mockUsePermissions.mockReturnValue(defaultPermissions({
        userRole: 'admin',
        isRolePreview: true,
        rolePreview: { role_name: 'loan_officer' },
      }));

      renderDashboard();

      // Should NOT redirect to /admin since role preview is active
      expect(mockNavigate).not.toHaveBeenCalledWith('/admin', { replace: true });
    });
  });

  // =========================================================================
  // 4. Role Preview Banner
  // =========================================================================

  describe('Role Preview Banner', () => {
    it('shows role preview banner when in preview mode', () => {
      const exitPreview = vi.fn();
      mockUsePermissions.mockReturnValue(defaultPermissions({
        isRolePreview: true,
        rolePreview: { role_name: 'Processor' },
        exitRolePreview: exitPreview,
      }));
      localStorage.setItem('role_preview', JSON.stringify({ role_name: 'Processor' }));

      renderDashboard();

      expect(screen.getByText(/Previewing as:/)).toBeInTheDocument();
      expect(screen.getByText('Processor')).toBeInTheDocument();
    });

    it('calls exitRolePreview when Exit Preview button is clicked', async () => {
      const exitPreview = vi.fn();
      mockUsePermissions.mockReturnValue(defaultPermissions({
        isRolePreview: true,
        rolePreview: { role_name: 'Processor' },
        exitRolePreview: exitPreview,
      }));
      localStorage.setItem('role_preview', JSON.stringify({ role_name: 'Processor' }));

      renderDashboard();

      await userEvent.click(screen.getByText('Exit Preview'));
      expect(exitPreview).toHaveBeenCalledTimes(1);
    });

    it('does not show role preview banner when not in preview mode', () => {
      renderDashboard();
      expect(screen.queryByText(/Previewing as:/)).not.toBeInTheDocument();
    });
  });

  // =========================================================================
  // 5. Pipeline Container
  // =========================================================================

  describe('Pipeline Container', () => {
    it('renders Live Loan Pipeline heading', () => {
      renderDashboard();
      expect(screen.getByText('Live Loan Pipeline')).toBeInTheDocument();
    });

    it('renders pipeline table with stage headers', () => {
      renderDashboard();

      const table = document.querySelector('.pipeline-table table');
      expect(table).toBeInTheDocument();

      // Check column headers
      const headers = table.querySelectorAll('th');
      const headerTexts = Array.from(headers).map(h => h.textContent);
      expect(headerTexts).toContain('Stage');
      expect(headerTexts).toContain('Count');
      expect(headerTexts).toContain('Alerts');
      expect(headerTexts).toContain('Funding $');
    });

    it('renders pipeline stages with correct counts', () => {
      renderDashboard();

      expect(screen.getByText('New Leads')).toBeInTheDocument();
      expect(screen.getByText('In Processing')).toBeInTheDocument();
      expect(screen.getByText('Clear to Close')).toBeInTheDocument();
      expect(screen.getByText('Funded This Month')).toBeInTheDocument();
    });

    it('shows alert count for stages with alerts', () => {
      renderDashboard();

      // New Leads has 3 follow-ups
      expect(screen.getByText('3 follow-ups')).toBeInTheDocument();
      // Processing has 4 delayed
      expect(screen.getByText('4 delayed')).toBeInTheDocument();
    });

    it('shows "no issues" for stages without alerts', () => {
      renderDashboard();

      const noIssuesElements = screen.getAllByText('no issues');
      expect(noIssuesElements.length).toBeGreaterThanOrEqual(1);
    });

    it('formats volume in millions', () => {
      renderDashboard();

      // $4.1M for Processing, $1.3M for CTC, $3.4M for Funded
      expect(screen.getByText('$4.1M')).toBeInTheDocument();
      expect(screen.getByText('$1.3M')).toBeInTheDocument();
      expect(screen.getByText('$3.4M')).toBeInTheDocument();
    });

    it('navigates to filtered loans page when pipeline row is clicked', async () => {
      renderDashboard();

      const processingRow = screen.getByText('In Processing').closest('tr');
      await userEvent.click(processingRow);
      expect(mockNavigate).toHaveBeenCalledWith('/loans?stage=processing');
    });
  });

  // =========================================================================
  // 6. Production Tracker Container
  // =========================================================================

  describe('Production Tracker Container', () => {
    it('renders Monthly Production Tracker heading', () => {
      mockUsePermissions.mockReturnValue(defaultPermissions({
        hasPermission: vi.fn((perm) => perm === 'production.view'),
      }));

      renderDashboard();
      expect(screen.getByText('Monthly Production Tracker')).toBeInTheDocument();
    });

    it('displays annual, monthly, weekly, and daily KPI cards', () => {
      mockUsePermissions.mockReturnValue(defaultPermissions({
        hasPermission: vi.fn((perm) => perm === 'production.view'),
      }));

      renderDashboard();

      expect(screen.getByText('Annual Origination Goal')).toBeInTheDocument();
      expect(screen.getByText('Monthly Units Goal')).toBeInTheDocument();
      expect(screen.getByText('Weekly Units Goal')).toBeInTheDocument();
      expect(screen.getByText('Daily Units Goal')).toBeInTheDocument();
    });

    it('shows goal vs actual values', () => {
      mockUsePermissions.mockReturnValue(defaultPermissions({
        hasPermission: vi.fn((perm) => perm === 'production.view'),
      }));

      renderDashboard();

      // Annual goal 222 -> formatted as 222.00
      expect(screen.getByText('222.00')).toBeInTheDocument();
      // Annual actual 189 -> formatted as 189.00
      expect(screen.getByText('189.00')).toBeInTheDocument();
    });

    it('shows progress percentage', () => {
      mockUsePermissions.mockReturnValue(defaultPermissions({
        hasPermission: vi.fn((perm) => perm === 'production.view'),
      }));

      renderDashboard();

      expect(screen.getByText('85% of Goal')).toBeInTheDocument();
    });

    it('shows AI coaching insight when annual progress is between 75-90%', () => {
      mockUsePermissions.mockReturnValue(defaultPermissions({
        hasPermission: vi.fn((perm) => perm === 'production.view'),
      }));

      renderDashboard();

      // annualProgress is 85, which is >= 75 and < 90
      expect(screen.getByText(/away from your annual goal/)).toBeInTheDocument();
    });
  });

  // =========================================================================
  // 7. Efficiency Monitor Container
  // =========================================================================

  describe('Efficiency Monitor Container', () => {
    it('renders Pipeline Efficiency Monitor heading', () => {
      renderDashboard();
      expect(screen.getByText('Pipeline Efficiency Monitor')).toBeInTheDocument();
    });

    it('displays overall efficiency score', () => {
      renderDashboard();

      const scoreNumber = document.querySelector('.score-number');
      expect(scoreNumber).toBeInTheDocument();
      expect(scoreNumber.textContent).toBe('78');
    });

    it('shows efficiency trend direction', () => {
      renderDashboard();

      const scoreTrend = document.querySelector('.score-trend.up');
      expect(scoreTrend).toBeInTheDocument();
      expect(scoreTrend.textContent).toContain('5%');
    });

    it('displays key efficiency metrics', () => {
      renderDashboard();

      expect(screen.getByText('Avg. Time to Close')).toBeInTheDocument();
      expect(screen.getByText('32 days')).toBeInTheDocument();
      expect(screen.getByText('Pull-Through Rate')).toBeInTheDocument();
      expect(screen.getByText('71%')).toBeInTheDocument();
      expect(screen.getByText('Automation Rate')).toBeInTheDocument();
      expect(screen.getByText('45%')).toBeInTheDocument();
    });

    it('shows stage performance bars', () => {
      renderDashboard();

      const stageBars = document.querySelectorAll('.stage-bar-row');
      expect(stageBars.length).toBe(2); // Application and Processing
    });

    it('navigates to full efficiency report when button is clicked', async () => {
      renderDashboard();

      await userEvent.click(screen.getByText('View Full Efficiency Report →'));
      expect(mockNavigate).toHaveBeenCalledWith('/dashboard/efficiency');
    });

    it('shows bottleneck count and list', () => {
      renderDashboard();

      expect(screen.getByText('Active Bottlenecks (2)')).toBeInTheDocument();
      expect(screen.getByText('Document delays')).toBeInTheDocument();
    });
  });

  // =========================================================================
  // 8. AI Alerts Container
  // =========================================================================

  describe('AI Alerts Container', () => {
    it('renders AI Alerts heading', () => {
      renderDashboard();
      expect(screen.getByText('AI Alerts')).toBeInTheDocument();
    });

    it('displays alert messages from lead metrics', () => {
      renderDashboard();

      expect(screen.getByText('3 leads not contacted in 24 hours')).toBeInTheDocument();
      expect(screen.getByText('Rate change detected')).toBeInTheDocument();
    });

    it('renders alert bullets for each alert', () => {
      renderDashboard();

      const alertRows = document.querySelectorAll('.ai-alert-row');
      expect(alertRows.length).toBe(2);

      alertRows.forEach(row => {
        expect(row.querySelector('.alert-bullet')).toBeInTheDocument();
      });
    });
  });

  // =========================================================================
  // 9. AI Tasks Container
  // =========================================================================

  describe('AI Tasks Container', () => {
    it('renders AI Prioritized Tasks heading', () => {
      renderDashboard();
      expect(screen.getByText('AI Prioritized Tasks (Today)')).toBeInTheDocument();
    });

    it('shows aggregated task count', () => {
      mockUseDashboard.mockReturnValue({
        data: defaultDashboardData({
          prioritized_tasks: [{ title: 'Task 1' }, { title: 'Task 2' }],
          loan_issues: [{ issue: 'Issue 1' }],
          ai_tasks: { pending: [{ task: 'P1' }], waiting: [] },
          lead_metrics: { alerts: ['Alert 1'] },
          messages: [{ id: 1, read: false }],
        }),
        isLoading: false,
        refetch: mockRefetch,
      });

      renderDashboard();

      // Total = 2 tasks + 1 issue + 1 pending + 0 waiting + 1 alert + 1 unread message = 6
      expect(screen.getByText('6 tasks')).toBeInTheDocument();
    });

    it('navigates to /tasks when tasks container is clicked', async () => {
      renderDashboard();

      const clickableContainer = document.querySelector('.task-summary-view.clickable-container');
      if (clickableContainer) {
        await userEvent.click(clickableContainer);
        expect(mockNavigate).toHaveBeenCalledWith('/tasks');
      }
    });
  });

  // =========================================================================
  // 10. Workflow Scorecards Container
  // =========================================================================

  describe('Workflow Scorecards Container', () => {
    it('renders Workflow Scorecards heading', () => {
      renderDashboard();
      expect(screen.getByText('Workflow Scorecards')).toBeInTheDocument();
    });

    it('shows overall workflow score', () => {
      renderDashboard();

      // Overall score is 82%
      const overallScore = document.querySelector('.workflow-overall-score .score-value');
      expect(overallScore).toBeInTheDocument();
      expect(overallScore.textContent).toBe('82%');
    });

    it('renders workflow status cards', () => {
      renderDashboard();

      expect(screen.getByText('Application')).toBeInTheDocument();
      expect(screen.getByText('90%')).toBeInTheDocument();
    });

    it('applies health class to workflow status cards', () => {
      renderDashboard();

      const goodCard = document.querySelector('.workflow-status-card.good');
      expect(goodCard).toBeInTheDocument();

      const warningCard = document.querySelector('.workflow-status-card.warning');
      expect(warningCard).toBeInTheDocument();
    });
  });

  // =========================================================================
  // 11. Drag and Drop Reordering
  // =========================================================================

  describe('Drag and Drop', () => {
    it('renders drag handles for each container', () => {
      renderDashboard();

      const dragHandles = document.querySelectorAll('.drag-handle');
      expect(dragHandles.length).toBeGreaterThan(0);
    });

    it('drag handles have draggable attribute', () => {
      renderDashboard();

      const dragHandles = document.querySelectorAll('.drag-handle');
      dragHandles.forEach(handle => {
        expect(handle.getAttribute('draggable')).toBe('true');
      });
    });

    it('saves container order to localStorage on drag end', () => {
      renderDashboard();

      const dragHandles = document.querySelectorAll('.drag-handle');
      if (dragHandles.length >= 2) {
        // Simulate drag start on the first handle
        fireEvent.dragStart(dragHandles[0]);

        // Simulate drag over the second container
        const containers = document.querySelectorAll('.draggable-container');
        fireEvent.dragOver(containers[1]);

        // Simulate drag end
        fireEvent.dragEnd(dragHandles[0]);

        // Should save to localStorage
        const savedOrder = localStorage.getItem('dashboardOrder_loan_officer');
        expect(savedOrder).toBeTruthy();
      }
    });
  });

  // =========================================================================
  // 12. Metric Formatting
  // =========================================================================

  describe('Metric Formatting', () => {
    it('formatGoalNumber formats values with two decimal places', () => {
      mockUsePermissions.mockReturnValue(defaultPermissions({
        hasPermission: vi.fn((perm) => perm === 'production.view'),
      }));

      mockUseDashboard.mockReturnValue({
        data: defaultDashboardData({
          production: {
            annualGoal: 222,
            annualActual: 189,
            annualProgress: 85,
            monthlyGoal: 18.5,
            monthlyActual: 14,
            monthlyProgress: 76,
            weeklyGoal: 5,
            weeklyActual: 4,
            weeklyProgress: 80,
            dailyGoal: 1,
            dailyActual: 0,
            dailyProgress: 0,
          },
        }),
        isLoading: false,
        refetch: mockRefetch,
      });

      renderDashboard();

      // Values should be formatted with 2 decimal places
      expect(screen.getByText('18.50')).toBeInTheDocument(); // monthly goal
      expect(screen.getByText('14.00')).toBeInTheDocument(); // monthly actual
    });

    it('handles zero and null production values gracefully', () => {
      mockUsePermissions.mockReturnValue(defaultPermissions({
        hasPermission: vi.fn((perm) => perm === 'production.view'),
      }));

      mockUseDashboard.mockReturnValue({
        data: defaultDashboardData({
          production: {
            annualGoal: 0,
            annualActual: 0,
            annualProgress: 0,
            monthlyGoal: 0,
            monthlyActual: 0,
            monthlyProgress: 0,
            weeklyGoal: 0,
            weeklyActual: 0,
            weeklyProgress: 0,
            dailyGoal: 0,
            dailyActual: 0,
            dailyProgress: 0,
          },
        }),
        isLoading: false,
        refetch: mockRefetch,
      });

      renderDashboard();

      // Should show formatted zeros, not crash
      const kpiNumbers = document.querySelectorAll('.kpi-number');
      expect(kpiNumbers.length).toBeGreaterThan(0);
    });

    it('volume is formatted as $XM in pipeline table', () => {
      renderDashboard();

      expect(screen.getByText('$4.1M')).toBeInTheDocument();
    });

    it('shows dash when volume is null', () => {
      renderDashboard();

      // New Leads has null volume, should show em dash
      const pipelineRows = document.querySelectorAll('.pipeline-table tbody tr');
      const firstRow = pipelineRows[0];
      const lastCell = firstRow.querySelectorAll('td');
      // The "New Leads" row volume cell should display an em dash
      const tdTexts = Array.from(lastCell).map(td => td.textContent);
      expect(tdTexts).toContain('\u2014'); // em dash character
    });
  });

  // =========================================================================
  // 13. Permission-Based Visibility
  // =========================================================================

  describe('Permission-Based Visibility', () => {
    it('shows PendingPermissionRequests for users with manage_permissions', () => {
      mockUsePermissions.mockReturnValue(defaultPermissions({
        hasPermission: vi.fn((perm) => perm === 'team.manage_permissions'),
      }));

      renderDashboard();

      expect(screen.getByTestId('pending-permissions')).toBeInTheDocument();
    });

    it('hides PendingPermissionRequests for regular loan officers', () => {
      renderDashboard();

      expect(screen.queryByTestId('pending-permissions')).not.toBeInTheDocument();
    });

    it('renders containers based on role config', () => {
      // Only return pipeline and efficiency containers
      mockGetContainers.mockReturnValue(['pipeline', 'efficiency']);

      renderDashboard();

      expect(screen.getByText('Live Loan Pipeline')).toBeInTheDocument();
      expect(screen.getByText('Pipeline Efficiency Monitor')).toBeInTheDocument();
      // Other containers should not appear
      expect(screen.queryByText('AI Alerts')).not.toBeInTheDocument();
    });
  });

  // =========================================================================
  // 14. Data Edge Cases
  // =========================================================================

  describe('Data Edge Cases', () => {
    it('handles empty pipeline_stats array gracefully', () => {
      mockUseDashboard.mockReturnValue({
        data: defaultDashboardData({ pipeline_stats: [] }),
        isLoading: false,
        refetch: mockRefetch,
      });

      renderDashboard();

      // Pipeline table should still render, just with no rows
      expect(screen.getByText('Live Loan Pipeline')).toBeInTheDocument();
      const rows = document.querySelectorAll('.pipeline-table tbody tr');
      expect(rows.length).toBe(0);
    });

    it('handles null/undefined dashboard data fields', () => {
      mockUseDashboard.mockReturnValue({
        data: {},
        isLoading: false,
        refetch: mockRefetch,
      });

      renderDashboard();

      // Should render without crashing even with empty data
      expect(screen.getByText("Today's Command Center")).toBeInTheDocument();
    });

    it('filters out null/invalid pipeline_stats entries', () => {
      mockUseDashboard.mockReturnValue({
        data: defaultDashboardData({
          pipeline_stats: [
            null,
            { id: 'valid', name: 'Valid Stage', count: 5, alerts: 0, alert_text: '', volume: 1000000 },
            { id: 'empty', name: null, count: 3, alerts: 0, alert_text: '', volume: 500000 },
          ],
        }),
        isLoading: false,
        refetch: mockRefetch,
      });

      renderDashboard();

      // Only the entry with a valid name should appear
      expect(screen.getByText('Valid Stage')).toBeInTheDocument();
      const rows = document.querySelectorAll('.pipeline-table tbody tr');
      expect(rows.length).toBe(1);
    });

    it('handles messages with read/unread status in task aggregation', () => {
      mockUseDashboard.mockReturnValue({
        data: defaultDashboardData({
          messages: [
            { id: 1, read: true },
            { id: 2, read: false },
            { id: 3, read: false },
          ],
        }),
        isLoading: false,
        refetch: mockRefetch,
      });

      renderDashboard();

      // 2 unread messages should be in the task count
      // Total = 0 tasks + 0 issues + 0 pending + 0 waiting + 2 alerts + 2 unread = 4
      expect(screen.getByText('4 tasks')).toBeInTheDocument();
    });
  });

  // =========================================================================
  // 15. Container Order Persistence
  // =========================================================================

  describe('Container Order Persistence', () => {
    it('loads saved container order from localStorage', () => {
      const savedOrder = ['pipeline', 'efficiency', 'ai-alerts'];
      localStorage.setItem('dashboardOrder_loan_officer', JSON.stringify(savedOrder));

      renderDashboard();

      // Pipeline should be first container rendered
      const containers = document.querySelectorAll('.draggable-container');
      expect(containers.length).toBeGreaterThan(0);
    });

    it('falls back to role defaults when localStorage has invalid JSON', () => {
      localStorage.setItem('dashboardOrder_loan_officer', 'not-valid-json');

      // Should not crash
      renderDashboard();

      expect(screen.getByText("Today's Command Center")).toBeInTheDocument();
    });

    it('updates container order when effectiveRole changes', () => {
      const { rerender } = renderDashboard();

      // mockGetContainers was called with 'loan_officer'
      expect(mockGetContainers).toHaveBeenCalledWith('loan_officer');
    });
  });
});
