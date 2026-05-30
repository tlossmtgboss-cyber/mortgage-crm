import React from 'react';
import { render, screen, fireEvent, within, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock('../TaskWorkflowManager.css', () => ({}));

// Mock react-router-dom
const mockNavigate = vi.fn();
vi.mock('react-router-dom', () => ({
  useNavigate: () => mockNavigate,
}));

// The component talks to the backend through the axios instance that is the
// DEFAULT export of services/api (api.get(...)), not via global fetch.
// Mock both the default export (with a get spy) and the named API_BASE_URL.
const mockApiGet = vi.fn();
vi.mock('../../services/api', () => ({
  default: {
    get: (...args) => mockApiGet(...args),
  },
  API_BASE_URL: 'http://localhost:8000',
}));

// localStorage mock
Object.defineProperty(window, 'localStorage', {
  value: {
    getItem: vi.fn(() => 'test-token'),
    setItem: vi.fn(),
    removeItem: vi.fn(),
  },
});

import TaskWorkflowManager from '../TaskWorkflowManager';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function setupDefaultApiMock() {
  mockApiGet.mockImplementation((url) => {
    if (url.includes('/workflow-stages') && !url.includes('/team-members')) {
      // Returning no `stages` makes the component keep its default stages.
      return Promise.resolve({ data: { stages: null } });
    }
    if (url.includes('/team-members')) {
      return Promise.resolve({ data: { team_members: [] } });
    }
    if (url.includes('/users')) {
      return Promise.resolve({
        data: {
          users: [
            { id: 'user-1', name: 'Alice Manager', email: 'alice@test.com' },
            { id: 'user-2', name: 'Bob Processor', email: 'bob@test.com' },
          ],
        },
      });
    }
    return Promise.resolve({ data: {} });
  });
}

// The stage name (e.g. "Lead") appears both as a stage-card heading and in the
// Client Lifecycle Flow section, so scope queries to the stage-cards grid.
function getStagesGrid() {
  return document.querySelector('.workflow-stages-grid');
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('TaskWorkflowManager', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setupDefaultApiMock();
  });

  // -- 1. Renders the workflow manager header --
  it('renders the workflow management header', async () => {
    await act(async () => {
      render(<TaskWorkflowManager />);
    });

    expect(screen.getByText('Workflow Management')).toBeInTheDocument();
    expect(screen.getByText(/configure automated workflows/i)).toBeInTheDocument();
  });

  // -- 2. Shows all three workflow stage cards --
  it('renders Lead, Active Loan, and Portfolio stage cards', async () => {
    await act(async () => {
      render(<TaskWorkflowManager />);
    });

    const grid = within(getStagesGrid());
    expect(grid.getByText('Lead')).toBeInTheDocument();
    expect(grid.getByText('Active Loan')).toBeInTheDocument();
    expect(grid.getByText('Portfolio')).toBeInTheDocument();
  });

  // -- 3. Shows task counts in each stage card --
  it('displays correct task counts for each stage', async () => {
    await act(async () => {
      render(<TaskWorkflowManager />);
    });

    const grid = within(getStagesGrid());
    // Lead has 8 tasks, Active Loan has 10, Portfolio has 8 — scoped to cards
    expect(grid.getByText('10 tasks')).toBeInTheDocument();
    // Two cards (Lead and Portfolio) show "8 tasks"
    const eightTaskElements = grid.getAllByText('8 tasks');
    expect(eightTaskElements.length).toBe(2);
  });

  // -- 4. Shows preview tasks in collapsed state --
  it('shows first 3 tasks as preview in collapsed stage cards', async () => {
    await act(async () => {
      render(<TaskWorkflowManager />);
    });

    // Lead stage's first 3 tasks
    expect(screen.getByText('Initial Contact')).toBeInTheDocument();
    expect(screen.getByText('Send Introduction Email')).toBeInTheDocument();
    expect(screen.getByText('Schedule Discovery Call')).toBeInTheDocument();

    // Both Lead and Portfolio have 8 tasks, so each shows "+5 more tasks".
    const fiveMore = screen.getAllByText('+5 more tasks');
    expect(fiveMore.length).toBe(2);
  });

  // -- 5. Stage card navigates to workflow detail --
  it('navigates to workflow detail when stage header is clicked', async () => {
    await act(async () => {
      render(<TaskWorkflowManager />);
    });

    // Click on the Lead stage header (scoped to the stage cards grid)
    const grid = within(getStagesGrid());
    const leadHeader = grid.getByText('Lead').closest('.stage-header');
    fireEvent.click(leadHeader);

    expect(mockNavigate).toHaveBeenCalledWith('/workflow/lead');
  });

  // -- 6. Client lifecycle flow visualization --
  it('renders the client lifecycle flow visualization', async () => {
    await act(async () => {
      render(<TaskWorkflowManager />);
    });

    expect(screen.getByText('Client Lifecycle Flow')).toBeInTheDocument();

    // Flow arrows
    const arrows = screen.getAllByText('→');
    expect(arrows.length).toBe(2);
  });

  // -- 7. Quick stats section --
  it('shows quick stats with total tasks, stages, and automated counts', async () => {
    await act(async () => {
      render(<TaskWorkflowManager />);
    });

    const stats = within(document.querySelector('.workflow-stats'));
    // Total Tasks = 8 + 10 + 8 = 26
    expect(stats.getByText('26')).toBeInTheDocument();
    expect(stats.getByText('Total Tasks')).toBeInTheDocument();

    // 3 workflow stages
    expect(stats.getByText('3')).toBeInTheDocument();
    expect(stats.getByText('Workflow Stages')).toBeInTheDocument();

    // Automated Tasks stat is rendered
    expect(stats.getByText('Automated Tasks')).toBeInTheDocument();
  });

  // -- 8. Loads workflow stages from API --
  it('calls the workflow-stages API on mount', async () => {
    await act(async () => {
      render(<TaskWorkflowManager />);
    });

    expect(mockApiGet).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/workflow-stages')
    );
  });

  // -- 9. Loads users from API for owner dropdown --
  it('fetches users from API on mount', async () => {
    await act(async () => {
      render(<TaskWorkflowManager />);
    });

    expect(mockApiGet).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/users')
    );
  });

  // -- 10. Handles API failure gracefully --
  it('renders with default stages when API fails', async () => {
    mockApiGet.mockRejectedValue(new Error('Network error'));

    await act(async () => {
      render(<TaskWorkflowManager />);
    });

    // Should still render with default hardcoded stages
    const grid = within(getStagesGrid());
    expect(grid.getByText('Lead')).toBeInTheDocument();
    expect(grid.getByText('Active Loan')).toBeInTheDocument();
    expect(grid.getByText('Portfolio')).toBeInTheDocument();
  });

  // -- 11. Stage descriptions are displayed --
  it('displays stage descriptions', async () => {
    await act(async () => {
      render(<TaskWorkflowManager />);
    });

    expect(screen.getByText(/initial contact and qualification/i)).toBeInTheDocument();
    expect(screen.getByText(/loan processing and underwriting/i)).toBeInTheDocument();
    expect(screen.getByText(/post-closing servicing and retention/i)).toBeInTheDocument();
  });

  // -- 12. Active Loan preview tasks render correctly --
  it('shows Active Loan preview tasks', async () => {
    await act(async () => {
      render(<TaskWorkflowManager />);
    });

    // Active Loan's first 3 tasks in preview
    expect(screen.getByText('Application Submitted')).toBeInTheDocument();
    expect(screen.getByText('Order Appraisal')).toBeInTheDocument();
    expect(screen.getByText('Title Search')).toBeInTheDocument();
  });
});
