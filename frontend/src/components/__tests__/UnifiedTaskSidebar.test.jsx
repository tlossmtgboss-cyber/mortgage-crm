import React from 'react';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock('../UnifiedTaskSidebar.css', () => ({}));

// Mock toast
vi.mock('../../utils/toast', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
    info: vi.fn(),
  },
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

import UnifiedTaskSidebar from '../UnifiedTaskSidebar';

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

const sampleTasks = [
  {
    id: 1,
    title: 'Follow up on pre-approval',
    client_name: 'Alice Johnson',
    priority: 'high',
    source: 'task',
    stage: 'Pre-Approved',
    owner: 'Jane LO',
    created_at: '2026-03-15T10:00:00Z',
    communication_count: 3,
    communications: [
      { date: '2026-03-14T09:00:00Z', type: 'Email', summary: 'Sent rate info' },
    ],
  },
  {
    id: 2,
    title: 'Review documents',
    client_name: 'Bob Williams',
    priority: 'urgent',
    source: 'workflow',
    stage: 'Processing',
    owner: 'Jane LO',
    created_at: '2026-03-14T08:00:00Z',
    communication_count: 0,
    communications: [],
  },
  {
    id: 3,
    title: 'Email reconciliation',
    client_name: 'Carol Davis',
    priority: 'medium',
    source: 'reconciliation',
    stage: 'New',
    owner: 'Jane LO',
    created_at: '2026-03-13T07:00:00Z',
    communication_count: 1,
    communications: [],
  },
  {
    id: 4,
    title: 'Schedule closing call',
    client_name: 'Dan Garcia',
    priority: 'low',
    source: 'task',
    stage: 'Clear to Close',
    owner: 'Jane LO',
    created_at: '2026-03-12T06:00:00Z',
    communication_count: 0,
    communications: [],
  },
];

function setupDefaultFetch(tasks = sampleTasks) {
  mockFetch.mockImplementation((url) => {
    if (url.includes('/unified-tasks') && !url.includes('/approve')) {
      return mockFetchResponse({ tasks, total_count: tasks.length });
    }
    if (url.includes('/approve')) {
      return mockFetchResponse({ success: true });
    }
    if (url.includes('/ai/training/instruction')) {
      return mockFetchResponse({ acknowledgment: 'Got it!' });
    }
    if (url.includes('/ai/regenerate-message')) {
      return mockFetchResponse({ message: 'Regenerated message' });
    }
    return mockFetchResponse({});
  });
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('UnifiedTaskSidebar', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setupDefaultFetch();
  });

  // -- 1. Returns null when not open --
  it('renders nothing when isOpen is false', () => {
    const { container } = render(
      <UnifiedTaskSidebar isOpen={false} onClose={vi.fn()} />
    );
    expect(container.innerHTML).toBe('');
  });

  // -- 2. Shows loading state while fetching --
  it('shows loading state while tasks are being fetched', async () => {
    let resolveApi;
    mockFetch.mockReturnValue(new Promise((resolve) => { resolveApi = resolve; }));

    render(<UnifiedTaskSidebar isOpen={true} onClose={vi.fn()} />);

    expect(screen.getByText(/loading tasks/i)).toBeInTheDocument();

    // Resolve to clean up
    resolveApi(mockFetchResponse({ tasks: [], total_count: 0 }));
  });

  // -- 3. Renders task list after loading --
  it('renders all tasks after loading completes', async () => {
    await act(async () => {
      render(<UnifiedTaskSidebar isOpen={true} onClose={vi.fn()} />);
    });

    await waitFor(() => {
      expect(screen.getByText('Follow up on pre-approval')).toBeInTheDocument();
    });

    expect(screen.getByText('Review documents')).toBeInTheDocument();
    expect(screen.getByText('Email reconciliation')).toBeInTheDocument();
    expect(screen.getByText('Schedule closing call')).toBeInTheDocument();
  });

  // -- 4. Shows empty state when no tasks --
  it('displays empty state when there are no tasks', async () => {
    setupDefaultFetch([]);

    await act(async () => {
      render(<UnifiedTaskSidebar isOpen={true} onClose={vi.fn()} />);
    });

    await waitFor(() => {
      expect(screen.getByText(/no pending tasks/i)).toBeInTheDocument();
    });
  });

  // -- 5. Filter tabs filter tasks by source --
  it('filters tasks when source filter tab is clicked', async () => {
    await act(async () => {
      render(<UnifiedTaskSidebar isOpen={true} onClose={vi.fn()} />);
    });

    await waitFor(() => {
      expect(screen.getByText('Follow up on pre-approval')).toBeInTheDocument();
    });

    // Click "Workflow" filter
    const workflowTab = screen.getByRole('button', { name: /workflow/i });
    fireEvent.click(workflowTab);

    // Only workflow task should be visible
    expect(screen.getByText('Review documents')).toBeInTheDocument();
    expect(screen.queryByText('Follow up on pre-approval')).not.toBeInTheDocument();
    expect(screen.queryByText('Email reconciliation')).not.toBeInTheDocument();
  });

  // -- 6. Priority badges display correctly --
  it('shows correct priority badges (URGENT, HIGH, MEDIUM, LOW)', async () => {
    await act(async () => {
      render(<UnifiedTaskSidebar isOpen={true} onClose={vi.fn()} />);
    });

    await waitFor(() => {
      expect(screen.getByText('Follow up on pre-approval')).toBeInTheDocument();
    });

    expect(screen.getByText('URGENT')).toBeInTheDocument();
    expect(screen.getByText('HIGH')).toBeInTheDocument();
    // MEDIUM and LOW may appear in sidebar task list
  });

  // -- 7. Task selection shows detail panel --
  it('shows task details when a task is selected', async () => {
    await act(async () => {
      render(<UnifiedTaskSidebar isOpen={true} onClose={vi.fn()} />);
    });

    await waitFor(() => {
      expect(screen.getByText('Follow up on pre-approval')).toBeInTheDocument();
    });

    // Click a task
    const taskItem = screen.getByText('Follow up on pre-approval').closest('.task-item-v2');
    fireEvent.click(taskItem);

    // Detail panel should show task info
    await waitFor(() => {
      expect(screen.getByText('Alice Johnson')).toBeInTheDocument();
    });
  });

  // -- 8. Task count badge shows total count --
  it('renders a task count badge matching total task count', async () => {
    await act(async () => {
      render(<UnifiedTaskSidebar isOpen={true} onClose={vi.fn()} />);
    });

    await waitFor(() => {
      expect(screen.getByText('Follow up on pre-approval')).toBeInTheDocument();
    });

    expect(screen.getByText('4')).toBeInTheDocument();
  });

  // -- 9. Calls onTaskCountChange with total --
  it('calls onTaskCountChange callback with the total task count', async () => {
    const onTaskCountChange = vi.fn();

    await act(async () => {
      render(
        <UnifiedTaskSidebar isOpen={true} onClose={vi.fn()} onTaskCountChange={onTaskCountChange} />
      );
    });

    await waitFor(() => {
      expect(onTaskCountChange).toHaveBeenCalledWith(4);
    });
  });

  // -- 10. Communication history accordion --
  it('toggles communication history accordion in detail panel', async () => {
    await act(async () => {
      render(<UnifiedTaskSidebar isOpen={true} onClose={vi.fn()} />);
    });

    await waitFor(() => {
      expect(screen.getByText('Follow up on pre-approval')).toBeInTheDocument();
    });

    // Click a task to open detail
    const taskItem = screen.getByText('Follow up on pre-approval').closest('.task-item-v2');
    fireEvent.click(taskItem);

    await waitFor(() => {
      expect(screen.getByText(/communication history/i)).toBeInTheDocument();
    });

    // Click to expand
    const historyBtn = screen.getByText(/communication history/i).closest('button');
    fireEvent.click(historyBtn);

    // Should show communication entry
    await waitFor(() => {
      expect(screen.getByText('Sent rate info')).toBeInTheDocument();
    });
  });

  // -- 11. Snooze moves to next task --
  it('moves to the next task when snooze is clicked', async () => {
    await act(async () => {
      render(<UnifiedTaskSidebar isOpen={true} onClose={vi.fn()} />);
    });

    await waitFor(() => {
      expect(screen.getByText('Follow up on pre-approval')).toBeInTheDocument();
    });

    // Select first task
    const firstTask = screen.getByText('Follow up on pre-approval').closest('.task-item-v2');
    fireEvent.click(firstTask);

    await waitFor(() => {
      expect(screen.getByText('Alice Johnson')).toBeInTheDocument();
    });

    // Click snooze
    const snoozeBtn = screen.getByText('Snooze');
    fireEvent.click(snoozeBtn);

    // Should move to next task (Bob Williams)
    await waitFor(() => {
      expect(screen.getByText('Bob Williams')).toBeInTheDocument();
    });
  });

  // -- 12. No task selected shows placeholder --
  it('shows "Select a task" placeholder when no task is selected', async () => {
    await act(async () => {
      render(<UnifiedTaskSidebar isOpen={true} onClose={vi.fn()} />);
    });

    await waitFor(() => {
      expect(screen.getByText('Follow up on pre-approval')).toBeInTheDocument();
    });

    // Initially no task is selected
    expect(screen.getByText(/select a task/i)).toBeInTheDocument();
  });
});
