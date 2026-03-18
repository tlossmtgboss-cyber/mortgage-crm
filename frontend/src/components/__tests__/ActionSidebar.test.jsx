import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock('../ActionSidebar.css', () => ({}));

// Mock sub-components
vi.mock('../shared/TaskDetailPanel', () => ({
  default: ({ task, onComplete, onClose }) => (
    <div data-testid="task-detail-panel">
      <span>{task.title}</span>
      <button data-testid="complete-task" onClick={() => onComplete(task.id)}>Complete</button>
      <button data-testid="close-detail" onClick={onClose}>Close</button>
    </div>
  ),
}));

vi.mock('../shared/ReconciliationDetailPanel', () => ({
  default: ({ email, onClose }) => (
    <div data-testid="reconciliation-detail-panel">
      <span>{email.subject}</span>
      <button data-testid="close-detail" onClick={onClose}>Close</button>
    </div>
  ),
}));

vi.mock('../shared/CallDetailPanel', () => ({
  default: ({ task, onClose }) => (
    <div data-testid="call-detail-panel">
      <span>{task.contact_name}</span>
      <button data-testid="close-detail" onClick={onClose}>Close</button>
    </div>
  ),
}));

// Mock toast
vi.mock('../../utils/toast', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
    info: vi.fn(),
  },
}));

// Mock taskEvents
vi.mock('../../utils/taskEvents', () => ({
  TASK_EVENTS: { TASK_COMPLETED: 'task-completed', TASKS_REFRESH: 'tasks-refresh' },
  emitTaskCompleted: vi.fn(),
  subscribeToTaskEvent: vi.fn(() => vi.fn()), // returns unsubscribe function
}));

// Mock API modules
const mockCommandCenterAPI = { getAll: vi.fn() };
const mockTasksAPI = { getUnified: vi.fn(), update: vi.fn() };
const mockReconciliationAPI = {};

vi.mock('../../services/api', () => ({
  commandCenterAPI: { getAll: (...args) => mockCommandCenterAPI.getAll(...args) },
  tasksAPI: {
    getUnified: (...args) => mockTasksAPI.getUnified(...args),
    update: (...args) => mockTasksAPI.update(...args),
  },
  reconciliationAPI: {},
}));

// Mock global fetch for workflow tasks endpoint
const mockFetch = vi.fn();
global.fetch = mockFetch;

import ActionSidebar from '../ActionSidebar';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function renderSidebar(props = {}) {
  return render(
    <MemoryRouter>
      <ActionSidebar
        onTaskSelect={vi.fn()}
        onClose={vi.fn()}
        {...props}
      />
    </MemoryRouter>
  );
}

/**
 * Set up all mock APIs to return empty data (loading resolved, no items).
 */
function resolveEmptyAPIs() {
  mockFetch.mockResolvedValue({
    ok: true,
    json: () => Promise.resolve({ tasks: [] }),
  });
  mockCommandCenterAPI.getAll.mockResolvedValue({
    emails: [],
    calls: [],
    sms: [],
    urgent: [],
    leads: [],
    loans: [],
    portfolio: [],
    reconciliation: [],
  });
  mockTasksAPI.getUnified.mockResolvedValue({ tasks: [] });
}

/**
 * Set up APIs to return data with workflow tasks.
 */
function resolveWithTasks(workflowTasks = [], commandCenterData = {}) {
  mockFetch.mockResolvedValue({
    ok: true,
    json: () => Promise.resolve({ tasks: workflowTasks }),
  });
  mockCommandCenterAPI.getAll.mockResolvedValue({
    emails: [],
    calls: [],
    sms: [],
    urgent: [],
    leads: [],
    loans: [],
    portfolio: [],
    reconciliation: [],
    ...commandCenterData,
  });
  mockTasksAPI.getUnified.mockResolvedValue({ tasks: [] });
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('ActionSidebar', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    localStorage.setItem('token', 'test-token');
  });

  // =========================================================================
  // Structure & Header
  // =========================================================================

  describe('Structure and header', () => {
    it('renders the Action Center heading', async () => {
      resolveEmptyAPIs();
      renderSidebar();
      expect(screen.getByText('Action Center')).toBeInTheDocument();
    });

    it('renders the refresh button', async () => {
      resolveEmptyAPIs();
      renderSidebar();
      expect(screen.getByTitle('Refresh')).toBeInTheDocument();
    });

    it('renders the close button when onClose is provided', async () => {
      resolveEmptyAPIs();
      renderSidebar({ onClose: vi.fn() });
      // The close button uses the x character
      const closeBtn = screen.getByText('\u00D7');
      expect(closeBtn).toBeInTheDocument();
    });

    it('does not render close button when onClose is not provided', async () => {
      resolveEmptyAPIs();
      renderSidebar({ onClose: undefined });
      // The close-btn should not exist
      const { container } = renderSidebar({ onClose: undefined });
      // Only one sidebar rendered in this call
      const closeBtns = container.querySelectorAll('.close-btn');
      expect(closeBtns.length).toBe(0);
    });
  });

  // =========================================================================
  // Tab navigation
  // =========================================================================

  describe('Tab navigation', () => {
    beforeEach(() => {
      resolveEmptyAPIs();
    });

    it('renders Tasks, Emails, and Calls tabs', async () => {
      renderSidebar();
      await waitFor(() => {
        expect(screen.getByText('Tasks')).toBeInTheDocument();
        expect(screen.getByText('Emails')).toBeInTheDocument();
        expect(screen.getByText('Calls')).toBeInTheDocument();
      });
    });

    it('Tasks tab is active by default', async () => {
      const { container } = renderSidebar();
      await waitFor(() => {
        const activeTab = container.querySelector('.action-tab.active');
        expect(activeTab).toBeInTheDocument();
        expect(activeTab.textContent).toContain('Tasks');
      });
    });

    it('switches to Emails tab on click', async () => {
      const { container } = renderSidebar();
      await waitFor(() => {
        expect(screen.queryByText('Loading...')).not.toBeInTheDocument();
      });
      fireEvent.click(screen.getByText('Emails'));
      const activeTab = container.querySelector('.action-tab.active');
      expect(activeTab.textContent).toContain('Emails');
    });

    it('switches to Calls tab on click', async () => {
      const { container } = renderSidebar();
      await waitFor(() => {
        expect(screen.queryByText('Loading...')).not.toBeInTheDocument();
      });
      fireEvent.click(screen.getByText('Calls'));
      const activeTab = container.querySelector('.action-tab.active');
      expect(activeTab.textContent).toContain('Calls');
    });
  });

  // =========================================================================
  // Loading state
  // =========================================================================

  describe('Loading state', () => {
    it('shows loading spinner while data is being fetched', () => {
      // Return promises that never resolve
      mockFetch.mockReturnValue(new Promise(() => {}));
      mockCommandCenterAPI.getAll.mockReturnValue(new Promise(() => {}));
      mockTasksAPI.getUnified.mockReturnValue(new Promise(() => {}));

      renderSidebar();
      expect(screen.getByText('Loading...')).toBeInTheDocument();
    });
  });

  // =========================================================================
  // Empty state
  // =========================================================================

  describe('Empty state', () => {
    it('shows empty state message when no tasks are available', async () => {
      resolveEmptyAPIs();
      renderSidebar();
      await waitFor(() => {
        expect(screen.getByText('No tasks to complete')).toBeInTheDocument();
      });
    });

    it('shows "You\'re all caught up!" in empty state', async () => {
      resolveEmptyAPIs();
      renderSidebar();
      await waitFor(() => {
        expect(screen.getByText("You're all caught up!")).toBeInTheDocument();
      });
    });
  });

  // =========================================================================
  // Task rendering
  // =========================================================================

  describe('Task item rendering', () => {
    it('renders workflow task items in the Tasks tab', async () => {
      resolveWithTasks([
        {
          id: 1,
          title: 'Follow up with John Smith',
          client_name: 'John Smith',
          stage: 'APPLICATION',
          urgency: 'high',
          client_type: 'lead',
          client_id: 'lead-1',
          due_date: '2026-03-20',
          description: 'Call to discuss application',
          workflow_name: 'New Lead',
          communication_methods: ['phone', 'email'],
          days_until_due: 2,
        },
      ]);
      renderSidebar();

      await waitFor(() => {
        expect(screen.getByText('Follow up with John Smith')).toBeInTheDocument();
      });
    });

    it('shows task count badge on Tasks tab', async () => {
      resolveWithTasks([
        { id: 1, title: 'Task 1', client_name: 'A', stage: 'New', urgency: 'medium', client_type: 'lead', client_id: '1', communication_methods: ['email'] },
        { id: 2, title: 'Task 2', client_name: 'B', stage: 'New', urgency: 'high', client_type: 'lead', client_id: '2', communication_methods: ['email'] },
      ]);
      renderSidebar();

      await waitFor(() => {
        // The tab-count badge should show 2
        const tabCount = screen.getByText('2');
        expect(tabCount).toBeInTheDocument();
      });
    });
  });

  // =========================================================================
  // Welcome message
  // =========================================================================

  describe('Welcome message', () => {
    it('shows welcome message when there are action items', async () => {
      resolveWithTasks([
        { id: 1, title: 'Task 1', client_name: 'A', stage: 'New', urgency: 'medium', client_type: 'lead', client_id: '1', communication_methods: ['email'] },
      ]);
      renderSidebar();

      await waitFor(() => {
        expect(screen.getByText(/outstanding things you need to do/)).toBeInTheDocument();
      });
    });

    it('shows correct total count in welcome message', async () => {
      resolveWithTasks([
        { id: 1, title: 'Task 1', client_name: 'A', stage: 'New', urgency: 'medium', client_type: 'lead', client_id: '1', communication_methods: ['email'] },
        { id: 2, title: 'Task 2', client_name: 'B', stage: 'New', urgency: 'high', client_type: 'lead', client_id: '2', communication_methods: ['email'] },
      ]);
      renderSidebar();

      await waitFor(() => {
        expect(screen.getByText(/2 action items need your attention/)).toBeInTheDocument();
      });
    });

    it('does not show welcome message when there are no items', async () => {
      resolveEmptyAPIs();
      renderSidebar();

      await waitFor(() => {
        expect(screen.queryByText(/outstanding things you need to do/)).not.toBeInTheDocument();
      });
    });
  });

  // =========================================================================
  // Footer
  // =========================================================================

  describe('Footer', () => {
    it('shows total item count in footer', async () => {
      resolveWithTasks([
        { id: 1, title: 'Task 1', client_name: 'A', stage: 'New', urgency: 'medium', client_type: 'lead', client_id: '1', communication_methods: ['email'] },
      ]);
      renderSidebar();

      await waitFor(() => {
        expect(screen.getByText(/1 total items/)).toBeInTheDocument();
      });
    });

    it('shows 0 total items when empty', async () => {
      resolveEmptyAPIs();
      renderSidebar();

      await waitFor(() => {
        expect(screen.getByText('0 total items')).toBeInTheDocument();
      });
    });
  });

  // =========================================================================
  // Email tab items
  // =========================================================================

  describe('Email tab', () => {
    it('shows email items in the Emails tab', async () => {
      resolveWithTasks([], {
        emails: [
          { id: 'email-1', title: 'New email from borrower', entity_name: 'Jane Doe', type: 'email', priority: 'medium' },
        ],
      });
      renderSidebar();

      await waitFor(() => {
        expect(screen.queryByText('Loading...')).not.toBeInTheDocument();
      });

      fireEvent.click(screen.getByText('Emails'));

      await waitFor(() => {
        expect(screen.getByText('New email from borrower')).toBeInTheDocument();
      });
    });
  });

  // =========================================================================
  // Calls tab and power dialer
  // =========================================================================

  describe('Calls tab', () => {
    it('shows call items in the Calls tab', async () => {
      resolveWithTasks([], {
        calls: [
          { id: 'call-1', title: 'Return call to borrower', entity_name: 'Bob', type: 'call', priority: 'high', phone: '555-1234' },
        ],
      });
      renderSidebar();

      await waitFor(() => {
        expect(screen.queryByText('Loading...')).not.toBeInTheDocument();
      });

      fireEvent.click(screen.getByText('Calls'));

      await waitFor(() => {
        expect(screen.getByText('Return call to borrower')).toBeInTheDocument();
      });
    });

    it('shows Power Dial button in Calls tab when items exist', async () => {
      resolveWithTasks([], {
        calls: [
          { id: 'call-1', title: 'Call back', entity_name: 'Bob', type: 'call', priority: 'medium', phone: '555-1234' },
        ],
      });
      renderSidebar();

      await waitFor(() => {
        expect(screen.queryByText('Loading...')).not.toBeInTheDocument();
      });

      fireEvent.click(screen.getByText('Calls'));

      await waitFor(() => {
        expect(screen.getByText(/Power Dial/)).toBeInTheDocument();
      });
    });

    it('shows Select All checkbox in Calls tab', async () => {
      resolveWithTasks([], {
        calls: [
          { id: 'call-1', title: 'Call 1', entity_name: 'A', type: 'call', priority: 'medium', phone: '555-0001' },
          { id: 'call-2', title: 'Call 2', entity_name: 'B', type: 'call', priority: 'low', phone: '555-0002' },
        ],
      });
      renderSidebar();

      await waitFor(() => {
        expect(screen.queryByText('Loading...')).not.toBeInTheDocument();
      });

      fireEvent.click(screen.getByText('Calls'));

      await waitFor(() => {
        expect(screen.getByText(/Select All/)).toBeInTheDocument();
      });
    });
  });

  // =========================================================================
  // Error state
  // =========================================================================

  describe('Error state', () => {
    it('shows error message when API fails', async () => {
      mockFetch.mockRejectedValue(new Error('Network error'));
      mockCommandCenterAPI.getAll.mockRejectedValue(new Error('Network error'));
      mockTasksAPI.getUnified.mockRejectedValue(new Error('Network error'));

      renderSidebar();

      await waitFor(() => {
        expect(screen.getByText('Error loading action items')).toBeInTheDocument();
      });
    });

    it('shows Retry button in error state', async () => {
      mockFetch.mockRejectedValue(new Error('fail'));
      mockCommandCenterAPI.getAll.mockRejectedValue(new Error('fail'));
      mockTasksAPI.getUnified.mockRejectedValue(new Error('fail'));

      renderSidebar();

      await waitFor(() => {
        expect(screen.getByText('Retry')).toBeInTheDocument();
      });
    });
  });
});
