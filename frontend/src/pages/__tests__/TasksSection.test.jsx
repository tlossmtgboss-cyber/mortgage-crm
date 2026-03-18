import React from 'react';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

// Mock react-router-dom
vi.mock('react-router-dom', () => ({
  Link: ({ children, to, ...props }) => <a href={to} {...props}>{children}</a>,
}));

// Mock tasksAPI
const mockGetAll = vi.fn();
vi.mock('../../services/api', () => ({
  tasksAPI: {
    getAll: (...args) => mockGetAll(...args),
  },
}));

// Mock helpers
vi.mock('../lo-today/helpers', () => {
  return {
    daysBetween: (dateStr) => {
      if (!dateStr) return null;
      const d = new Date(dateStr);
      const now = new Date();
      const diffMs = now - d;
      return Math.floor(diffMs / (1000 * 60 * 60 * 24));
    },
    LoadingSkeleton: ({ rows }) => (
      <div data-testid="loading-skeleton">Loading {rows} rows...</div>
    ),
  };
});

import { TasksSection } from '../lo-today/TasksSection';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeTask(overrides = {}) {
  return {
    id: `task-${Math.random().toString(36).slice(2, 8)}`,
    title: 'Default Task',
    description: 'Task description',
    status: 'pending',
    due_date: new Date().toISOString(),
    loan_number: null,
    borrower_name: null,
    ...overrides,
  };
}

const today = new Date().toISOString().split('T')[0];
const yesterday = new Date(Date.now() - 86400000).toISOString().split('T')[0];
const tomorrow = new Date(Date.now() + 86400000).toISOString().split('T')[0];

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('TasksSection (Pipeline Tasks)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // -- 1. Loading state --
  it('shows loading skeleton while tasks are being fetched', async () => {
    let resolveApi;
    mockGetAll.mockReturnValue(new Promise((resolve) => { resolveApi = resolve; }));

    render(<TasksSection />);

    expect(screen.getByTestId('loading-skeleton')).toBeInTheDocument();

    resolveApi([]);
  });

  // -- 2. Empty state --
  it('shows "All caught up" when no tasks are due', async () => {
    mockGetAll.mockResolvedValue([]);

    await act(async () => {
      render(<TasksSection />);
    });

    await waitFor(() => {
      expect(screen.getByText(/all caught up/i)).toBeInTheDocument();
    });
  });

  // -- 3. Renders due tasks --
  it('renders tasks that are due today or overdue', async () => {
    const tasks = [
      makeTask({ title: 'Collect W-2 forms', due_date: `${today}T10:00:00Z`, loan_number: 'LN-001', borrower_name: 'John Smith' }),
      makeTask({ title: 'Order appraisal', due_date: `${yesterday}T10:00:00Z`, loan_number: 'LN-002', borrower_name: 'Jane Doe' }),
    ];
    mockGetAll.mockResolvedValue(tasks);

    await act(async () => {
      render(<TasksSection />);
    });

    await waitFor(() => {
      expect(screen.getByText('Collect W-2 forms')).toBeInTheDocument();
    });
    expect(screen.getByText('Order appraisal')).toBeInTheDocument();
  });

  // -- 4. Shows loan number and borrower name --
  it('displays loan number and borrower name in task metadata', async () => {
    const tasks = [
      makeTask({ title: 'Submit to UW', due_date: `${today}T10:00:00Z`, loan_number: 'LN-555', borrower_name: 'Maria Garcia' }),
    ];
    mockGetAll.mockResolvedValue(tasks);

    await act(async () => {
      render(<TasksSection />);
    });

    await waitFor(() => {
      expect(screen.getByText('Loan #LN-555')).toBeInTheDocument();
      expect(screen.getByText('Maria Garcia')).toBeInTheDocument();
    });
  });

  // -- 5. Overdue badge --
  it('shows overdue count badge when tasks are overdue', async () => {
    const tasks = [
      makeTask({ title: 'Past due task', due_date: `${yesterday}T10:00:00Z` }),
      makeTask({ title: 'Today task', due_date: `${today}T10:00:00Z` }),
    ];
    mockGetAll.mockResolvedValue(tasks);

    await act(async () => {
      render(<TasksSection />);
    });

    await waitFor(() => {
      expect(screen.getByText('Past due task')).toBeInTheDocument();
    });

    // Overdue badge should show count of 1
    const badge = screen.getByText('1');
    expect(badge).toBeInTheDocument();
    expect(badge.className).toContain('badge--danger');
  });

  // -- 6. SLA labels: overdue --
  it('shows "overdue" SLA label for past-due tasks', async () => {
    const tasks = [
      makeTask({ title: 'Overdue task', due_date: `${yesterday}T10:00:00Z` }),
    ];
    mockGetAll.mockResolvedValue(tasks);

    await act(async () => {
      render(<TasksSection />);
    });

    await waitFor(() => {
      expect(screen.getByText(/overdue/i)).toBeInTheDocument();
    });
  });

  // -- 7. SLA labels: due today --
  it('shows "Due today" label for tasks due today', async () => {
    const tasks = [
      makeTask({ title: 'Today task', due_date: `${today}T10:00:00Z` }),
    ];
    mockGetAll.mockResolvedValue(tasks);

    await act(async () => {
      render(<TasksSection />);
    });

    await waitFor(() => {
      expect(screen.getByText('Due today')).toBeInTheDocument();
    });
  });

  // -- 8. Filters out completed/cancelled tasks --
  it('excludes completed and cancelled tasks from the display', async () => {
    const tasks = [
      makeTask({ title: 'Active task', status: 'pending', due_date: `${today}T10:00:00Z` }),
      makeTask({ title: 'Done task', status: 'completed', due_date: `${today}T10:00:00Z` }),
      makeTask({ title: 'Cancelled task', status: 'cancelled', due_date: `${today}T10:00:00Z` }),
    ];
    mockGetAll.mockResolvedValue(tasks);

    await act(async () => {
      render(<TasksSection />);
    });

    await waitFor(() => {
      expect(screen.getByText('Active task')).toBeInTheDocument();
    });

    expect(screen.queryByText('Done task')).not.toBeInTheDocument();
    expect(screen.queryByText('Cancelled task')).not.toBeInTheDocument();
  });

  // -- 9. All Tasks link navigates to /tasks --
  it('renders an "All Tasks" link pointing to /tasks', async () => {
    mockGetAll.mockResolvedValue([]);

    await act(async () => {
      render(<TasksSection />);
    });

    await waitFor(() => {
      const link = screen.getByText('All Tasks');
      expect(link).toBeInTheDocument();
      expect(link.closest('a')).toHaveAttribute('href', '/tasks');
    });
  });

  // -- 10. Handles API error with retry button --
  it('shows error message and retry button when API call fails', async () => {
    mockGetAll.mockRejectedValue(new Error('Failed to load tasks'));

    await act(async () => {
      render(<TasksSection />);
    });

    await waitFor(() => {
      expect(screen.getByText(/failed to load tasks/i)).toBeInTheDocument();
    });

    expect(screen.getByText('Retry')).toBeInTheDocument();
  });

  // -- 11. Retry button reloads tasks --
  it('retries loading tasks when retry button is clicked', async () => {
    mockGetAll
      .mockRejectedValueOnce(new Error('Network error'))
      .mockResolvedValueOnce([makeTask({ title: 'Retried Task', due_date: `${today}T10:00:00Z` })]);

    await act(async () => {
      render(<TasksSection />);
    });

    await waitFor(() => {
      expect(screen.getByText('Retry')).toBeInTheDocument();
    });

    await act(async () => {
      fireEvent.click(screen.getByText('Retry'));
    });

    await waitFor(() => {
      expect(screen.getByText('Retried Task')).toBeInTheDocument();
    });
  });

  // -- 12. Sorts tasks by due date (overdue first) --
  it('sorts tasks with overdue first, then today, then upcoming', async () => {
    const tasks = [
      makeTask({ title: 'Tomorrow task', due_date: `${tomorrow}T10:00:00Z` }),
      makeTask({ title: 'Overdue task', due_date: `${yesterday}T10:00:00Z` }),
      makeTask({ title: 'Today task', due_date: `${today}T10:00:00Z` }),
    ];
    mockGetAll.mockResolvedValue(tasks);

    await act(async () => {
      render(<TasksSection />);
    });

    await waitFor(() => {
      expect(screen.getByText('Overdue task')).toBeInTheDocument();
    });

    // Get all task items and verify order
    const taskItems = screen.getAllByText(/task$/i).map(el => el.textContent);
    const overdueIdx = taskItems.indexOf('Overdue task');
    const todayIdx = taskItems.indexOf('Today task');
    const tomorrowIdx = taskItems.indexOf('Tomorrow task');

    // Overdue should come before today, today before tomorrow
    if (overdueIdx !== -1 && todayIdx !== -1) {
      expect(overdueIdx).toBeLessThan(todayIdx);
    }
    if (todayIdx !== -1 && tomorrowIdx !== -1) {
      expect(todayIdx).toBeLessThan(tomorrowIdx);
    }
  });
});
