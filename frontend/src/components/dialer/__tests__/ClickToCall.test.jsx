import React from 'react';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

// Mock axios
const mockAxiosPost = vi.fn();
vi.mock('axios', () => ({
  default: {
    post: (...args) => mockAxiosPost(...args),
    get: vi.fn(),
  },
  post: (...args) => mockAxiosPost(...args),
}));

// Mock the WebSocket hook
const mockSend = vi.fn();
vi.mock('../../../hooks/useDialerWebSocket', () => ({
  useDialerWebSocket: (agentId, options) => {
    // Store the onMessage handler so tests can invoke it
    if (options?.onMessage) {
      ClickToCallTestHelpers._onMessage = options.onMessage;
    }
    return {
      isConnected: ClickToCallTestHelpers._isConnected,
      send: mockSend,
      disconnect: vi.fn(),
      reconnect: vi.fn(),
      reconnectAttempts: 0,
      lastEvent: null,
    };
  },
}));

// Shared test state for the WebSocket mock
const ClickToCallTestHelpers = {
  _onMessage: null,
  _isConnected: true,
};

// Mock localStorage
const mockLocalStorage = {
  getItem: vi.fn((key) => {
    if (key === 'token') return 'test-jwt-token';
    if (key === 'userId') return 'agent-42';
    if (key === 'user') return JSON.stringify({ id: 'agent-42' });
    return null;
  }),
  setItem: vi.fn(),
  removeItem: vi.fn(),
};
Object.defineProperty(window, 'localStorage', { value: mockLocalStorage, writable: true });

import ClickToDialButton from '../ClickToDialButton';
import ClickToDialModal from '../ClickToDialModal';

// ---------------------------------------------------------------------------
// Tests: ClickToDialButton
// ---------------------------------------------------------------------------

describe('ClickToDialButton', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // --- 1. Renders nothing when no phone ---
  it('returns null when phone prop is not provided', () => {
    const { container } = render(
      <ClickToDialButton
        contactId="c-1"
        contactName="John Smith"
        phone=""
      />
    );

    expect(container.firstChild).toBeNull();
  });

  // --- 2. Renders call button with phone ---
  it('renders a call button when phone number is provided', () => {
    render(
      <ClickToDialButton
        contactId="c-1"
        contactName="John Smith"
        phone="(555) 123-4567"
      />
    );

    const btn = screen.getByTitle('Call John Smith');
    expect(btn).toBeInTheDocument();
    expect(screen.getByText('Call')).toBeInTheDocument();
  });

  // --- 3. Icon-only variant ---
  it('renders icon-only button in icon variant', () => {
    render(
      <ClickToDialButton
        contactId="c-1"
        contactName="John Smith"
        phone="(555) 123-4567"
        variant="icon"
      />
    );

    const btn = screen.getByTitle('Call John Smith');
    expect(btn).toBeInTheDocument();
    // Should not have "Call" text
    expect(screen.queryByText('Call')).not.toBeInTheDocument();
  });

  // --- 4. Opens modal on click ---
  it('opens ClickToDialModal when button is clicked', () => {
    render(
      <ClickToDialButton
        contactId="c-1"
        contactName="John Smith"
        phone="(555) 123-4567"
      />
    );

    fireEvent.click(screen.getByTitle('Call John Smith'));

    // Modal should show the contact name and "Call Contact" heading
    expect(screen.getByText('Call Contact')).toBeInTheDocument();
    expect(screen.getByText('John Smith')).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Tests: ClickToDialModal
// ---------------------------------------------------------------------------

describe('ClickToDialModal', () => {
  const defaultProps = {
    contactId: 'c-1',
    contactName: 'Jane Doe',
    phone: '(555) 987-6543',
    leadId: 'lead-10',
    loanId: null,
    taskId: null,
    context: 'Follow up on pre-approval',
    onClose: vi.fn(),
  };

  beforeEach(() => {
    vi.clearAllMocks();
    ClickToCallTestHelpers._isConnected = true;
    ClickToCallTestHelpers._onMessage = null;
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  // --- 5. Renders contact info and phone number ---
  it('displays contact info and editable phone number', () => {
    render(<ClickToDialModal {...defaultProps} />);

    expect(screen.getByText('Jane Doe')).toBeInTheDocument();
    expect(screen.getByText('Follow up on pre-approval')).toBeInTheDocument();

    const phoneInput = screen.getByDisplayValue('(555) 987-6543');
    expect(phoneInput).toBeInTheDocument();
    expect(phoneInput.tagName).toBe('INPUT');
  });

  // --- 6. Call Now button initiates call ---
  it('initiates a call when Call Now is clicked', async () => {
    mockAxiosPost.mockResolvedValueOnce({
      data: { success: true, call_sid: 'call-abc-123' },
    });

    render(<ClickToDialModal {...defaultProps} />);

    const callBtn = screen.getByText('Call Now');
    await act(async () => {
      fireEvent.click(callBtn);
    });

    // Should have called the API
    expect(mockAxiosPost).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/dialer/click-to-dial'),
      expect.objectContaining({
        phone_number: '(555) 987-6543',
        contact_name: 'Jane Doe',
        lead_id: 10,
      }),
      expect.any(Object)
    );

    // Should transition to ringing state
    await waitFor(() => {
      expect(screen.getByText(/Ringing your phone/)).toBeInTheDocument();
    });
  });

  // --- 7. Call Now disabled without phone ---
  it('disables Call Now button when phone number is empty', () => {
    render(<ClickToDialModal {...defaultProps} phone="" />);

    const callBtn = screen.getByText('Call Now');
    expect(callBtn).toBeDisabled();
  });

  // --- 8. Displays connecting state ---
  it('shows Connecting state while initiating', async () => {
    // Make the post hang so we can see the initiating state
    mockAxiosPost.mockImplementation(() => new Promise(() => {}));

    render(<ClickToDialModal {...defaultProps} />);

    await act(async () => {
      fireEvent.click(screen.getByText('Call Now'));
    });

    expect(screen.getByText('Connecting...')).toBeInTheDocument();
  });

  // --- 9. Displays error on API failure ---
  it('displays error state when call initiation fails', async () => {
    mockAxiosPost.mockRejectedValueOnce({
      response: { data: { detail: 'Caller ID not configured' } },
    });

    render(<ClickToDialModal {...defaultProps} />);

    await act(async () => {
      fireEvent.click(screen.getByText('Call Now'));
    });

    await waitFor(() => {
      expect(screen.getByText('Caller ID not configured')).toBeInTheDocument();
    });
  });

  // --- 10. WebSocket status update transitions to connected ---
  it('transitions to connected state via WebSocket event', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });

    mockAxiosPost.mockResolvedValueOnce({
      data: { success: true, call_sid: 'call-xyz' },
    });

    render(<ClickToDialModal {...defaultProps} />);

    await act(async () => {
      fireEvent.click(screen.getByText('Call Now'));
    });

    await waitFor(() => {
      expect(screen.getByText(/Ringing your phone/)).toBeInTheDocument();
    });

    // Simulate WebSocket "connected" event
    act(() => {
      if (ClickToCallTestHelpers._onMessage) {
        ClickToCallTestHelpers._onMessage({
          type: 'click_to_dial_status',
          call_sid: 'call-xyz',
          status: 'in-progress',
          duration_seconds: 0,
        });
      }
    });

    await waitFor(() => {
      expect(screen.getByText(/Connected/)).toBeInTheDocument();
    });
  });

  // --- 11. Call completed state shows Call Again ---
  it('shows Call Again and Close buttons when call completes', async () => {
    mockAxiosPost.mockResolvedValueOnce({
      data: { success: true, call_sid: 'call-done' },
    });

    render(<ClickToDialModal {...defaultProps} />);

    await act(async () => {
      fireEvent.click(screen.getByText('Call Now'));
    });

    // Simulate completed via WebSocket
    act(() => {
      if (ClickToCallTestHelpers._onMessage) {
        ClickToCallTestHelpers._onMessage({
          type: 'click_to_dial_status',
          call_sid: 'call-done',
          status: 'completed',
          duration_seconds: 45,
          call_log_id: 99,
        });
      }
    });

    await waitFor(() => {
      expect(screen.getByText(/Call completed/)).toBeInTheDocument();
    });

    expect(screen.getByText('Call Again')).toBeInTheDocument();
    expect(screen.getByText('Close')).toBeInTheDocument();
    expect(screen.getByText('Add Call Disposition')).toBeInTheDocument();
  });

  // --- 12. WebSocket disconnection warning ---
  it('shows real-time updates unavailable when WebSocket disconnects during call', async () => {
    ClickToCallTestHelpers._isConnected = false;

    mockAxiosPost.mockResolvedValueOnce({
      data: { success: true, call_sid: 'call-ws-down' },
    });

    render(<ClickToDialModal {...defaultProps} />);

    await act(async () => {
      fireEvent.click(screen.getByText('Call Now'));
    });

    await waitFor(() => {
      expect(screen.getByText(/Real-time updates unavailable/)).toBeInTheDocument();
    });
  });

  // --- 13. Cancel button closes modal ---
  it('calls onClose when Cancel button is clicked', () => {
    render(<ClickToDialModal {...defaultProps} />);

    fireEvent.click(screen.getByText('Cancel'));

    expect(defaultProps.onClose).toHaveBeenCalled();
  });

  // --- 14. Helper text about phone ringing ---
  it('displays helper text explaining the call flow', () => {
    render(<ClickToDialModal {...defaultProps} />);

    expect(
      screen.getByText(/Your cell phone will ring first/)
    ).toBeInTheDocument();
  });
});
