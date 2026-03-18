import React from 'react';
import { render, screen, fireEvent, waitFor, act, within } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

// Mock CSS import
vi.mock('../../../pages/PowerDialer.css', () => ({}));

// Mock react-router-dom
const mockNavigate = vi.fn();
vi.mock('react-router-dom', () => ({
  useNavigate: () => mockNavigate,
}));

// Mock auth utils
vi.mock('../../../utils/auth', () => ({
  getAuthHeaders: () => ({
    Authorization: 'Bearer test-token',
    'Content-Type': 'application/json',
  }),
}));

// Mock global fetch
const mockFetch = vi.fn();
global.fetch = mockFetch;

import PowerDialer from '../../../pages/PowerDialer';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function mockResponse(body, status = 200) {
  return Promise.resolve({
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(body),
  });
}

const sampleTasks = [
  {
    id: 'task-1',
    title: 'Follow up call',
    contact_name: 'John Smith',
    contact_phone: '(555) 123-4567',
    lead_phone: '(555) 123-4567',
    lead_name: 'John Smith',
    priority: 'high',
  },
  {
    id: 'task-2',
    title: 'Initial outreach',
    contact_name: 'Jane Doe',
    contact_phone: '(555) 987-6543',
    lead_phone: '(555) 987-6543',
    lead_name: 'Jane Doe',
    priority: 'normal',
  },
  {
    id: 'task-3',
    title: 'Rate quote follow up',
    contact_name: 'Bob Wilson',
    contact_phone: '(555) 555-0100',
    lead_phone: '(555) 555-0100',
    lead_name: 'Bob Wilson',
    priority: 'low',
  },
];

const sampleContacts = [
  {
    id: 'contact-1',
    contact_name: 'Alice Johnson',
    contact_phone: '(555) 111-2222',
    entity_type: 'lead',
    stage: 'New',
  },
  {
    id: 'contact-2',
    contact_name: 'Charlie Brown',
    contact_phone: '(555) 333-4444',
    entity_type: 'loan',
    stage: 'Processing',
  },
];

const sampleSettings = {
  business_caller_id: '(555) 000-0000',
  voicemail_enabled: true,
};

const sampleCallLogs = [
  { id: 'log-1', contact_name: 'John Smith', outcome: 'completed', duration_seconds: 120 },
  { id: 'log-2', contact_name: 'Jane Doe', outcome: 'no-answer', duration_seconds: 0 },
];

/**
 * Sets up fetch mock to return default data for all initial API calls.
 */
function setupDefaultFetchMock(overrides = {}) {
  mockFetch.mockImplementation((url) => {
    if (url.includes('/dialer/settings')) {
      return mockResponse(overrides.settings || sampleSettings);
    }
    if (url.includes('/dialer/call-tasks')) {
      return mockResponse({ tasks: overrides.tasks !== undefined ? overrides.tasks : sampleTasks });
    }
    if (url.includes('/dialer/callable-contacts')) {
      return mockResponse({ contacts: overrides.contacts !== undefined ? overrides.contacts : sampleContacts });
    }
    if (url.includes('/dialer/sessions/active')) {
      return mockResponse(overrides.activeSession || { active_session: null });
    }
    if (url.includes('/dialer/call-logs')) {
      return mockResponse({ call_logs: overrides.callLogs || sampleCallLogs });
    }
    return mockResponse({});
  });
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('PowerDialer', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers({ shouldAdvanceTime: true });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  // --- 1. Loading state ---
  it('shows loading spinner on initial render', async () => {
    // Never resolve the fetch to keep loading state visible
    mockFetch.mockImplementation(() => new Promise(() => {}));

    render(<PowerDialer />);

    expect(screen.getByText('Loading Power Dialer...')).toBeInTheDocument();
  });

  // --- 2. Task list rendering ---
  it('renders the task list after loading', async () => {
    setupDefaultFetchMock();

    await act(async () => {
      render(<PowerDialer />);
    });

    // Wait for tasks to appear
    await waitFor(() => {
      expect(screen.getByText('John Smith')).toBeInTheDocument();
    });

    expect(screen.getByText('Jane Doe')).toBeInTheDocument();
    expect(screen.getByText('Bob Wilson')).toBeInTheDocument();
    expect(screen.getByText(/Call Tasks \(3\)/)).toBeInTheDocument();
  });

  // --- 3. Empty task list ---
  it('shows empty state when no call tasks are available', async () => {
    setupDefaultFetchMock({ tasks: [] });

    await act(async () => {
      render(<PowerDialer />);
    });

    await waitFor(() => {
      expect(screen.getByText('No call tasks available')).toBeInTheDocument();
    });

    expect(screen.getByText(/Switch to "All Contacts"/)).toBeInTheDocument();
  });

  // --- 4. Tab switching between tasks and contacts ---
  it('switches between Call Tasks and All Contacts tabs', async () => {
    setupDefaultFetchMock();

    await act(async () => {
      render(<PowerDialer />);
    });

    await waitFor(() => {
      expect(screen.getByText('John Smith')).toBeInTheDocument();
    });

    // Click the "All Contacts" tab
    fireEvent.click(screen.getByText(/All Contacts/));

    await waitFor(() => {
      expect(screen.getByText('Alice Johnson')).toBeInTheDocument();
    });

    expect(screen.getByText('Charlie Brown')).toBeInTheDocument();
  });

  // --- 5. Task selection and start button ---
  it('enables Start button only when tasks are selected', async () => {
    setupDefaultFetchMock();

    await act(async () => {
      render(<PowerDialer />);
    });

    await waitFor(() => {
      expect(screen.getByText('John Smith')).toBeInTheDocument();
    });

    // Start button should be disabled with 0 selected
    const startBtn = screen.getByText(/Start Power Dialer \(0/);
    expect(startBtn).toBeDisabled();

    // Select first task
    fireEvent.click(screen.getByText('Follow up call'));

    // Button should now show 1 selected
    expect(screen.getByText(/Start Power Dialer \(1/)).not.toBeDisabled();
  });

  // --- 6. Select all / deselect all ---
  it('toggles select all and deselect all', async () => {
    setupDefaultFetchMock();

    await act(async () => {
      render(<PowerDialer />);
    });

    await waitFor(() => {
      expect(screen.getByText('John Smith')).toBeInTheDocument();
    });

    // Click "Select All"
    fireEvent.click(screen.getByText('Select All'));

    // Start button should show all 3 tasks selected
    expect(screen.getByText(/Start Power Dialer \(3/)).toBeInTheDocument();

    // Click "Deselect All"
    fireEvent.click(screen.getByText('Deselect All'));

    expect(screen.getByText(/Start Power Dialer \(0/)).toBeInTheDocument();
  });

  // --- 7. Start session and render active dial interface ---
  it('starts a session and renders the active dial interface', async () => {
    setupDefaultFetchMock();

    await act(async () => {
      render(<PowerDialer />);
    });

    await waitFor(() => {
      expect(screen.getByText('John Smith')).toBeInTheDocument();
    });

    // Select a task
    fireEvent.click(screen.getByText('Follow up call'));

    // Mock the session creation and next-task endpoints
    mockFetch.mockImplementation((url, options) => {
      if (url.includes('/dialer/sessions') && options?.method === 'POST') {
        return mockResponse({ success: true, session_id: 'sess-123' });
      }
      if (url.includes('/next-task')) {
        return mockResponse({
          next_task: {
            id: 'task-1',
            contact_name: 'John Smith',
            contact_phone: '(555) 123-4567',
          },
        });
      }
      if (url.includes('/dialer/sessions/sess-123') && !options?.method) {
        return mockResponse({
          session_id: 'sess-123',
          status: 'active',
          total_tasks: 1,
          completed_tasks: 0,
        });
      }
      return mockResponse({});
    });

    // Start session
    await act(async () => {
      fireEvent.click(screen.getByText(/Start Power Dialer/));
    });

    // The dial session should be visible
    await waitFor(() => {
      expect(screen.getByText('Dial Session')).toBeInTheDocument();
    });

    // Phone inputs should be present
    expect(screen.getByText('Cell Phone')).toBeInTheDocument();
    expect(screen.getByText('Home Phone')).toBeInTheDocument();
    expect(screen.getByText('Work Phone')).toBeInTheDocument();
  });

  // --- 8. Caller ID warning ---
  it('shows caller ID warning when not configured', async () => {
    setupDefaultFetchMock({ settings: { business_caller_id: null } });

    await act(async () => {
      render(<PowerDialer />);
    });

    await waitFor(() => {
      expect(screen.getByText(/No caller ID configured/)).toBeInTheDocument();
    });

    // Configure button
    expect(screen.getByText('Configure')).toBeInTheDocument();
  });

  // --- 9. Error banner display and dismiss ---
  it('shows error when session start fails and allows dismissal', async () => {
    setupDefaultFetchMock();

    await act(async () => {
      render(<PowerDialer />);
    });

    await waitFor(() => {
      expect(screen.getByText('John Smith')).toBeInTheDocument();
    });

    // Select a task
    fireEvent.click(screen.getByText('Follow up call'));

    // Mock a failed session start
    mockFetch.mockImplementation((url, options) => {
      if (url.includes('/dialer/sessions') && options?.method === 'POST') {
        return mockResponse({ detail: 'Caller ID not configured' }, 400);
      }
      return mockResponse({});
    });

    await act(async () => {
      fireEvent.click(screen.getByText(/Start Power Dialer/));
    });

    await waitFor(() => {
      expect(screen.getByText('Caller ID not configured')).toBeInTheDocument();
    });

    // Dismiss the error
    const dismissBtn = screen.getByRole('button', { name: /\u00d7/ });
    fireEvent.click(dismissBtn);

    await waitFor(() => {
      expect(screen.queryByText('Caller ID not configured')).not.toBeInTheDocument();
    });
  });

  // --- 10. Recent call logs display ---
  it('displays recent call logs in the preview panel', async () => {
    setupDefaultFetchMock();

    await act(async () => {
      render(<PowerDialer />);
    });

    await waitFor(() => {
      expect(screen.getByText('Recent Calls')).toBeInTheDocument();
    });

    // Call logs should appear (contact names from sampleCallLogs)
    // The component renders log.contact_name
    const recentPanel = screen.getByText('Recent Calls').closest('.recent-calls-preview');
    expect(recentPanel).toBeInTheDocument();
  });

  // --- 11. Disposition buttons render in active session ---
  it('renders disposition buttons during an active session', async () => {
    // Start with an active session already in progress
    const activeSession = {
      active_session: {
        session_id: 'sess-active',
        status: 'active',
        total_tasks: 3,
        completed_tasks: 0,
        current_task: {
          id: 'task-1',
          contact_name: 'John Smith',
          contact_phone: '(555) 123-4567',
        },
      },
    };

    setupDefaultFetchMock({ activeSession });

    await act(async () => {
      render(<PowerDialer />);
    });

    await waitFor(() => {
      expect(screen.getByText('Dial Session')).toBeInTheDocument();
    });

    // Disposition buttons
    expect(screen.getByText('Live Answer')).toBeInTheDocument();
    expect(screen.getByText('Voice Mail')).toBeInTheDocument();
    expect(screen.getByText('No Answer')).toBeInTheDocument();
    expect(screen.getByText('Busy Signal')).toBeInTheDocument();
    expect(screen.getByText('Bad Number')).toBeInTheDocument();
  });

  // --- 12. Session footer stats display ---
  it('displays session footer stats during an active session', async () => {
    const activeSession = {
      active_session: {
        session_id: 'sess-active',
        status: 'active',
        total_tasks: 5,
        completed_tasks: 2,
        current_task: {
          id: 'task-1',
          contact_name: 'John Smith',
          contact_phone: '(555) 123-4567',
        },
      },
    };

    setupDefaultFetchMock({ activeSession });

    await act(async () => {
      render(<PowerDialer />);
    });

    await waitFor(() => {
      expect(screen.getByText('Dial Session')).toBeInTheDocument();
    });

    // Footer stats labels
    expect(screen.getByText('Caller ID')).toBeInTheDocument();
    expect(screen.getByText('Duration')).toBeInTheDocument();
    expect(screen.getByText('Calls')).toBeInTheDocument();
    expect(screen.getByText('Talks')).toBeInTheDocument();
    expect(screen.getByText('Voicemails')).toBeInTheDocument();

    // The formatted duration starts at 00:00
    expect(screen.getByText('00:00')).toBeInTheDocument();
  });
});
