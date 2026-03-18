import React from 'react';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
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

// Mock services/api
vi.mock('../../services/api', () => ({
  API_BASE_URL: 'http://localhost:8000',
}));

// Mock global fetch
const mockFetch = vi.fn();
global.fetch = mockFetch;

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

function mockFetchResponse(body, status = 200) {
  return Promise.resolve({
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(body),
  });
}

function setupDefaultFetchMock() {
  mockFetch.mockImplementation((url) => {
    if (url.includes('/workflow-stages') && !url.includes('/team-members')) {
      return mockFetchResponse({ stages: null }); // use default stages
    }
    if (url.includes('/team-members')) {
      return mockFetchResponse({ team_members: [] });
    }
    if (url.includes('/users')) {
      return mockFetchResponse({
        users: [
          { id: 'user-1', name: 'Alice Manager', email: 'alice@test.com' },
          { id: 'user-2', name: 'Bob Processor', email: 'bob@test.com' },
        ],
      });
    }
    return mockFetchResponse({});
  });
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('TaskWorkflowManager', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setupDefaultFetchMock();
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

    expect(screen.getByText('Lead')).toBeInTheDocument();
    expect(screen.getByText('Active Loan')).toBeInTheDocument();
    expect(screen.getByText('Portfolio')).toBeInTheDocument();
  });

  // -- 3. Shows task counts in each stage card --
  it('displays correct task counts for each stage', async () => {
    await act(async () => {
      render(<TaskWorkflowManager />);
    });

    // Lead has 8 tasks, Active Loan has 10, Portfolio has 8
    expect(screen.getByText('8 tasks')).toBeInTheDocument();
    expect(screen.getByText('10 tasks')).toBeInTheDocument();
    // There should be two elements showing "8 tasks" (Lead and Portfolio)
    const eightTaskElements = screen.getAllByText('8 tasks');
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

    // Should show "+5 more tasks" for Lead (8 total - 3 shown)
    expect(screen.getByText('+5 more tasks')).toBeInTheDocument();
  });

  // -- 5. Stage card navigates to workflow detail --
  it('navigates to workflow detail when stage header is clicked', async () => {
    await act(async () => {
      render(<TaskWorkflowManager />);
    });

    // Click on the Lead stage header
    const leadHeader = screen.getByText('Lead').closest('.stage-header');
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

    // Total Tasks = 8 + 10 + 8 = 26
    expect(screen.getByText('26')).toBeInTheDocument();
    expect(screen.getByText('Total Tasks')).toBeInTheDocument();

    // 3 workflow stages
    expect(screen.getByText('3')).toBeInTheDocument();
    expect(screen.getByText('Workflow Stages')).toBeInTheDocument();

    // Automated Tasks - count tasks where auto_trigger !== 'manual'
    expect(screen.getByText('Automated Tasks')).toBeInTheDocument();
  });

  // -- 8. Loads workflow stages from API --
  it('calls the workflow-stages API on mount', async () => {
    await act(async () => {
      render(<TaskWorkflowManager />);
    });

    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/workflow-stages'),
      expect.objectContaining({
        headers: expect.objectContaining({
          'Authorization': 'Bearer test-token',
        }),
      })
    );
  });

  // -- 9. Loads users from API for owner dropdown --
  it('fetches users from API on mount', async () => {
    await act(async () => {
      render(<TaskWorkflowManager />);
    });

    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/users'),
      expect.any(Object)
    );
  });

  // -- 10. Handles API failure gracefully --
  it('renders with default stages when API fails', async () => {
    mockFetch.mockRejectedValue(new Error('Network error'));

    await act(async () => {
      render(<TaskWorkflowManager />);
    });

    // Should still render with default hardcoded stages
    expect(screen.getByText('Lead')).toBeInTheDocument();
    expect(screen.getByText('Active Loan')).toBeInTheDocument();
    expect(screen.getByText('Portfolio')).toBeInTheDocument();
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
