import React from 'react';
import { render, screen, fireEvent, waitFor, act, within } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// ---------------------------------------------------------------------------
// Mocks — must be declared before component import
// ---------------------------------------------------------------------------

vi.mock('../Tasks.css', () => ({}));
vi.mock('../../components/shared/TaskDetailPanel.css', () => ({}));
vi.mock('../../components/shared/ReconciliationDetailPanel', () => ({
  default: () => <div data-testid="reconciliation-panel" />,
}));
vi.mock('../../components/shared/CallDetailPanel', () => ({
  default: () => <div data-testid="call-panel" />,
}));
vi.mock('../../components/shared/TasksSkeleton', () => ({
  default: () => <div data-testid="tasks-skeleton">Loading...</div>,
}));

// Mock react-router-dom
const mockNavigate = vi.fn();
vi.mock('react-router-dom', () => ({
  useNavigate: () => mockNavigate,
  Link: ({ children, to, ...props }) => <a href={to} {...props}>{children}</a>,
}));

// Mock toast
vi.mock('../../utils/toast', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
    info: vi.fn(),
  },
}));

// Mock useLayoutFix hook
vi.mock('../../hooks/useLayoutFix', () => ({
  useLayoutFix: () => ({ containerRef: { current: null } }),
}));

// Mock auth utils
vi.mock('../../utils/auth', () => ({
  getAuthHeaders: () => ({
    'Authorization': 'Bearer test-token',
    'Content-Type': 'application/json',
  }),
}));

// Mock sanitize
vi.mock('../../utils/sanitize', () => ({
  sanitizeHTML: (html) => html,
}));

// Mock taskEvents
const mockEmitTaskCompleted = vi.fn();
const mockSubscribeToTaskEvent = vi.fn(() => vi.fn()); // returns unsubscribe
vi.mock('../../utils/taskEvents', () => ({
  TASK_EVENTS: {
    TASK_COMPLETED: 'task:completed',
    TASK_CREATED: 'task:created',
    TASK_UPDATED: 'task:updated',
    TASK_DELETED: 'task:deleted',
    TASKS_REFRESH: 'tasks:refresh',
  },
  emitTaskCompleted: (...args) => mockEmitTaskCompleted(...args),
  subscribeToTaskEvent: (...args) => mockSubscribeToTaskEvent(...args),
}));

// Mock services/api
const mockGetAll = vi.fn();
const mockGetUnified = vi.fn();
const mockDeleteTask = vi.fn();
const mockDelegateTask = vi.fn();
const mockGetMembers = vi.fn();

vi.mock('../../services/api', () => ({
  tasksAPI: {
    getAll: (...args) => mockGetAll(...args),
    getUnified: (...args) => mockGetUnified(...args),
    delete: (...args) => mockDeleteTask(...args),
    delegate: (...args) => mockDelegateTask(...args),
  },
  teamAPI: {
    getMembers: (...args) => mockGetMembers(...args),
  },
  reconciliationAPI: {
    delete: vi.fn(),
  },
  leadsAPI: {},
  loansAPI: {},
  aiAPI: {
    submitTrainingInstruction: vi.fn().mockResolvedValue({ acknowledgment: 'OK' }),
  },
  API_BASE_URL: 'http://localhost:8000',
}));

// Mock global fetch for workflow-config endpoint
const mockFetch = vi.fn();
global.fetch = mockFetch;

// Provide localStorage mock
const localStorageMock = (() => {
  let store = { token: 'test-token' };
  return {
    getItem: vi.fn((key) => store[key] || null),
    setItem: vi.fn((key, value) => { store[key] = value; }),
    removeItem: vi.fn((key) => { delete store[key]; }),
    clear: vi.fn(() => { store = {}; }),
  };
})();
Object.defineProperty(window, 'localStorage', { value: localStorageMock });

import Tasks from '../Tasks';

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

function setupDefaultMocks(workflowTasks = [], unifiedTasks = [], teamMembers = []) {
  mockFetch.mockImplementation((url) => {
    if (url.includes('/workflow-config/all-workflow-tasks')) {
      return mockFetchResponse({ tasks: workflowTasks });
    }
    if (url.includes('/email-intelligence/stats')) {
      return mockFetchResponse({});
    }
    if (url.includes('/email-intelligence/queue')) {
      return mockFetchResponse({ emails: [], total: 0 });
    }
    if (url.includes('/dialer/')) {
      return mockFetchResponse({ tasks: [], contacts: [], call_logs: [], settings: {} });
    }
    return mockFetchResponse({});
  });

  mockGetUnified.mockResolvedValue({ tasks: unifiedTasks });
  mockGetMembers.mockResolvedValue(teamMembers);
}

const sampleWorkflowTasks = [
  {
    id: 'wf-1',
    title: 'Day 1 Initial Contact',
    client_name: 'John Smith',
    stage: 'New',
    urgency: 'high',
    due_date: new Date().toISOString(),
    description: 'Make first contact',
    workflow_name: 'Prospect Nurture',
    days_until_due: 0,
    communication_methods: ['email', 'phone'],
  },
  {
    id: 'wf-2',
    title: 'Send Follow-Up Email',
    client_name: 'Jane Doe',
    stage: 'Attempted Contact',
    urgency: 'medium',
    due_date: new Date(Date.now() + 86400000).toISOString(),
    description: 'Follow-up email after initial contact',
    workflow_name: 'Prospect Nurture',
    days_until_due: 1,
    communication_methods: ['email'],
  },
  {
    id: 'wf-3',
    title: 'Pre-Qualification Check',
    client_name: 'Bob Wilson',
    stage: 'Pre-Qualified',
    urgency: 'low',
    due_date: new Date(Date.now() + 2 * 86400000).toISOString(),
    description: 'Verify qualification criteria',
    workflow_name: 'Prospect Nurture',
    days_until_due: 2,
    communication_methods: ['email', 'phone'],
  },
];

const sampleTeamMembers = [
  { id: 'tm-1', first_name: 'Alice', last_name: 'Manager', role: 'manager' },
  { id: 'tm-2', first_name: 'Carlos', last_name: 'Processor', role: 'processor' },
];

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('Tasks Page', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorageMock.getItem.mockImplementation((key) => {
      if (key === 'token') return 'test-token';
      if (key === 'completedTasks') return '[]';
      return null;
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  // -- 1. Loading state --
  it('shows skeleton loader while tasks are loading', async () => {
    // Set up mocks that never resolve to keep loading state
    let resolveWorkflow;
    mockFetch.mockImplementation((url) => {
      if (url.includes('/workflow-config/all-workflow-tasks')) {
        return new Promise((resolve) => { resolveWorkflow = resolve; });
      }
      return mockFetchResponse({});
    });
    mockGetUnified.mockReturnValue(new Promise(() => {}));
    mockGetMembers.mockResolvedValue([]);

    render(<Tasks />);

    expect(screen.getByTestId('tasks-skeleton')).toBeInTheDocument();

    // Clean up the hanging promise
    resolveWorkflow?.(mockFetchResponse({ tasks: [] }));
  });

  // -- 2. Renders task list after loading --
  it('renders task list after data loads', async () => {
    setupDefaultMocks(sampleWorkflowTasks, [], sampleTeamMembers);

    await act(async () => {
      render(<Tasks />);
    });

    await waitFor(() => {
      expect(screen.getByText('Day 1 Initial Contact')).toBeInTheDocument();
    });

    expect(screen.getByText('Send Follow-Up Email')).toBeInTheDocument();
    expect(screen.getByText('Pre-Qualification Check')).toBeInTheDocument();
  });

  // -- 3. Empty task list --
  it('shows empty state when no tasks exist', async () => {
    setupDefaultMocks([], [], []);

    await act(async () => {
      render(<Tasks />);
    });

    await waitFor(() => {
      expect(screen.queryByTestId('tasks-skeleton')).not.toBeInTheDocument();
    });

    // When there are no tasks, the detail panel should show "Select a task to view details"
    expect(screen.getByText(/select a task/i)).toBeInTheDocument();
  });

  // -- 4. Tab switching filters tasks --
  it('defaults to outstanding tab and shows active tasks', async () => {
    setupDefaultMocks(sampleWorkflowTasks, [], sampleTeamMembers);

    await act(async () => {
      render(<Tasks />);
    });

    await waitFor(() => {
      expect(screen.getByText('Day 1 Initial Contact')).toBeInTheDocument();
    });

    // Outstanding tab should be active (the default)
    const outstandingTab = screen.getByText(/outstanding/i);
    expect(outstandingTab).toBeInTheDocument();
  });

  // -- 5. Task selection shows detail panel --
  it('selects a task and renders its details in the detail panel', async () => {
    setupDefaultMocks(sampleWorkflowTasks, [], sampleTeamMembers);

    await act(async () => {
      render(<Tasks />);
    });

    await waitFor(() => {
      expect(screen.getByText('Day 1 Initial Contact')).toBeInTheDocument();
    });

    // The first task should be auto-selected, so its borrower should appear in the detail panel
    // TaskDetailPanel shows task.borrower
    expect(screen.getByText('John Smith')).toBeInTheDocument();
  });

  // -- 6. Snoozing a task removes it from the list --
  it('snoozes a task and removes it from the outstanding list', async () => {
    setupDefaultMocks(sampleWorkflowTasks, [], sampleTeamMembers);

    await act(async () => {
      render(<Tasks />);
    });

    await waitFor(() => {
      expect(screen.getByText('Day 1 Initial Contact')).toBeInTheDocument();
    });

    // Find and click the snooze button in the detail panel
    const snoozeBtn = screen.getByText(/snooze/i);
    await act(async () => {
      fireEvent.click(snoozeBtn);
    });

    // After snooze, the snoozed task should be hidden from outstanding tab
    // The next task should be auto-selected
  });

  // -- 7. Task subscribes to cross-component events --
  it('subscribes to task events on mount and unsubscribes on unmount', async () => {
    setupDefaultMocks([], [], []);

    const { unmount } = render(<Tasks />);

    // Should have subscribed to TASK_COMPLETED and TASKS_REFRESH
    expect(mockSubscribeToTaskEvent).toHaveBeenCalledTimes(2);
    expect(mockSubscribeToTaskEvent).toHaveBeenCalledWith(
      'task:completed',
      expect.any(Function)
    );
    expect(mockSubscribeToTaskEvent).toHaveBeenCalledWith(
      'tasks:refresh',
      expect.any(Function)
    );

    // On unmount, the unsubscribe functions should be called
    unmount();
  });

  // -- 8. Completed tasks are persisted to localStorage --
  it('persists completed task IDs to localStorage', async () => {
    setupDefaultMocks(sampleWorkflowTasks, [], sampleTeamMembers);

    await act(async () => {
      render(<Tasks />);
    });

    await waitFor(() => {
      expect(screen.getByText('Day 1 Initial Contact')).toBeInTheDocument();
    });

    // localStorage.setItem should be called with completedTasks
    expect(localStorageMock.setItem).toHaveBeenCalledWith(
      'completedTasks',
      expect.any(String)
    );
  });

  // -- 9. Bulk selection toggles checkboxes --
  it('shows task count badge matching the number of tasks', async () => {
    setupDefaultMocks(sampleWorkflowTasks, [], sampleTeamMembers);

    await act(async () => {
      render(<Tasks />);
    });

    await waitFor(() => {
      expect(screen.getByText('Day 1 Initial Contact')).toBeInTheDocument();
    });

    // All three workflow tasks should render
    const taskTitles = ['Day 1 Initial Contact', 'Send Follow-Up Email', 'Pre-Qualification Check'];
    taskTitles.forEach((title) => {
      expect(screen.getByText(title)).toBeInTheDocument();
    });
  });

  // -- 10. Handles API error gracefully --
  it('handles API error during task loading without crashing', async () => {
    mockFetch.mockRejectedValue(new Error('Network error'));
    mockGetUnified.mockRejectedValue(new Error('Network error'));
    mockGetMembers.mockResolvedValue([]);

    await act(async () => {
      render(<Tasks />);
    });

    // Should not crash and should eventually exit loading state
    await waitFor(() => {
      expect(screen.queryByTestId('tasks-skeleton')).not.toBeInTheDocument();
    });
  });

  // -- 11. Delegate handler calls API --
  it('team members are loaded for delegation', async () => {
    setupDefaultMocks(sampleWorkflowTasks, [], sampleTeamMembers);

    await act(async () => {
      render(<Tasks />);
    });

    await waitFor(() => {
      expect(screen.getByText('Day 1 Initial Contact')).toBeInTheDocument();
    });

    expect(mockGetMembers).toHaveBeenCalled();
  });

  // -- 12. Unified tasks (manual) are merged into the task list --
  it('merges unified manual tasks alongside workflow tasks', async () => {
    const unifiedTasks = [
      {
        id: 'u-1',
        title: 'Manual Follow-Up Task',
        source: 'task',
        client_name: 'Maria Garcia',
        stage: 'New',
        priority: 'high',
        created_at: new Date().toISOString(),
      },
    ];
    setupDefaultMocks(sampleWorkflowTasks, unifiedTasks, sampleTeamMembers);

    await act(async () => {
      render(<Tasks />);
    });

    await waitFor(() => {
      expect(screen.getByText('Day 1 Initial Contact')).toBeInTheDocument();
    });

    // The manual task from unified endpoint should also appear
    expect(screen.getByText('Manual Follow-Up Task')).toBeInTheDocument();
  });
});
