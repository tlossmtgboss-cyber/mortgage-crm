import React from 'react';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

// Mock axios
const mockAxiosPost = vi.fn();
vi.mock('axios', () => ({
  default: {
    post: (...args) => mockAxiosPost(...args),
  },
}));

// Mock lucide-react icons
vi.mock('lucide-react', () => ({
  X: (props) => <span data-testid="icon-x" {...props} />,
  Mic: (props) => <span data-testid="icon-mic" {...props} />,
  MicOff: (props) => <span data-testid="icon-mic-off" {...props} />,
  Loader2: (props) => <span data-testid="icon-loader" {...props} />,
}));

// Mock localStorage
const mockLocalStorage = {
  getItem: vi.fn((key) => {
    if (key === 'token') return 'test-jwt-token';
    return null;
  }),
  setItem: vi.fn(),
  removeItem: vi.fn(),
};
Object.defineProperty(window, 'localStorage', { value: mockLocalStorage, writable: true });

// Mock navigator.mediaDevices for voice recording tests
const mockMediaRecorder = {
  start: vi.fn(),
  stop: vi.fn(),
  ondataavailable: null,
  onstop: null,
};

const mockMediaStream = {
  getTracks: () => [{ stop: vi.fn() }],
};

Object.defineProperty(navigator, 'mediaDevices', {
  value: {
    getUserMedia: vi.fn().mockResolvedValue(mockMediaStream),
  },
  writable: true,
});

// Mock MediaRecorder globally
global.MediaRecorder = vi.fn().mockImplementation(() => mockMediaRecorder);

import DispositionModal from '../DispositionModal';

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const defaultProps = {
  taskId: 'task-1',
  sessionId: 'sess-100',
  contactName: 'John Smith',
  callDuration: 125,
  callOutcome: 'COMPLETED',
  onClose: vi.fn(),
  onSaved: vi.fn(),
};

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('DispositionModal', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // --- 1. Renders contact info and call duration ---
  it('displays contact name and formatted call duration', () => {
    render(<DispositionModal {...defaultProps} />);

    expect(screen.getByText('Call Disposition')).toBeInTheDocument();
    expect(screen.getByText('John Smith')).toBeInTheDocument();
    // 125 seconds = 2:05
    expect(screen.getByText('Duration: 2:05')).toBeInTheDocument();
  });

  // --- 2. Disposition dropdown renders all options ---
  it('renders all disposition options in the dropdown', () => {
    render(<DispositionModal {...defaultProps} />);

    const select = screen.getByRole('combobox');
    expect(select).toBeInTheDocument();

    // Check a few key options exist
    const options = select.querySelectorAll('option');
    const optionTexts = Array.from(options).map((o) => o.textContent);

    expect(optionTexts).toContain('Select disposition...');
    expect(optionTexts).toContain('Answered - Conversation completed');
    expect(optionTexts).toContain('Left Voicemail');
    expect(optionTexts).toContain('Do Not Call Again');
    expect(optionTexts).toContain('Busy Signal');
    expect(optionTexts).toContain('Follow-up Required');
  });

  // --- 3. Submit fails without disposition ---
  it('shows error when submitting without selecting a disposition', async () => {
    render(<DispositionModal {...defaultProps} />);

    const submitBtn = screen.getByText('Submit');
    await act(async () => {
      fireEvent.click(submitBtn);
    });

    expect(screen.getByText('Please select a disposition')).toBeInTheDocument();
    expect(mockAxiosPost).not.toHaveBeenCalled();
  });

  // --- 4. Successful submission ---
  it('submits disposition and calls onSaved + onClose on success', async () => {
    mockAxiosPost.mockResolvedValueOnce({
      data: { success: true },
    });

    render(<DispositionModal {...defaultProps} />);

    // Select a disposition
    const select = screen.getByRole('combobox');
    fireEvent.change(select, { target: { value: 'Answered - Conversation completed' } });

    // Add notes
    const notes = screen.getByPlaceholderText(/Add any relevant notes/);
    fireEvent.change(notes, { target: { value: 'Great conversation, interested in refinance.' } });

    // Submit
    await act(async () => {
      fireEvent.click(screen.getByText('Submit'));
    });

    await waitFor(() => {
      expect(mockAxiosPost).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/dialer/task/task-1/disposition'),
        expect.objectContaining({
          disposition: 'Answered - Conversation completed',
          notes: 'Great conversation, interested in refinance.',
        }),
        expect.any(Object)
      );
    });

    expect(defaultProps.onSaved).toHaveBeenCalled();
    expect(defaultProps.onClose).toHaveBeenCalled();
  });

  // --- 5. Follow-up date required for certain dispositions ---
  it('shows follow-up date picker when Follow-up Required is selected', () => {
    render(<DispositionModal {...defaultProps} />);

    const select = screen.getByRole('combobox');
    fireEvent.change(select, { target: { value: 'Follow-up Required' } });

    // The follow-up date input should appear
    expect(screen.getByText(/Follow-up Date/)).toBeInTheDocument();

    // The date input should be of type datetime-local
    const dateInput = screen.getByDisplayValue('');
    expect(dateInput).toBeInTheDocument();
  });

  // --- 6. Follow-up date validation ---
  it('blocks submission when follow-up date is required but not set', async () => {
    render(<DispositionModal {...defaultProps} />);

    const select = screen.getByRole('combobox');
    fireEvent.change(select, { target: { value: 'Callback Scheduled' } });

    await act(async () => {
      fireEvent.click(screen.getByText('Submit'));
    });

    expect(screen.getByText('Please select a follow-up date')).toBeInTheDocument();
    expect(mockAxiosPost).not.toHaveBeenCalled();
  });

  // --- 7. API error handling ---
  it('displays API error message on submission failure', async () => {
    mockAxiosPost.mockRejectedValueOnce({
      response: { data: { detail: 'Session expired' } },
    });

    render(<DispositionModal {...defaultProps} />);

    const select = screen.getByRole('combobox');
    fireEvent.change(select, { target: { value: 'No Answer - Rang but no pickup' } });

    await act(async () => {
      fireEvent.click(screen.getByText('Submit'));
    });

    await waitFor(() => {
      expect(screen.getByText('Session expired')).toBeInTheDocument();
    });
  });

  // --- 8. Cancel button closes modal ---
  it('calls onClose when Cancel is clicked', () => {
    render(<DispositionModal {...defaultProps} />);

    fireEvent.click(screen.getByText('Cancel'));

    expect(defaultProps.onClose).toHaveBeenCalled();
  });

  // --- 9. Close button (X icon) ---
  it('calls onClose when X button is clicked', () => {
    render(<DispositionModal {...defaultProps} />);

    // The X icon is the close button in the header
    const closeBtn = screen.getByTestId('icon-x').closest('button');
    fireEvent.click(closeBtn);

    expect(defaultProps.onClose).toHaveBeenCalled();
  });

  // --- 10. Voice note recording UI ---
  it('shows Record button for voice notes', () => {
    render(<DispositionModal {...defaultProps} />);

    expect(screen.getByText('Voice Note (optional)')).toBeInTheDocument();
    expect(screen.getByText('Record')).toBeInTheDocument();
    expect(screen.getByText(/Voice notes are transcribed/)).toBeInTheDocument();
  });

  // --- 11. DNC disposition flag ---
  it('sends correct flags for Do Not Call disposition', async () => {
    mockAxiosPost.mockResolvedValueOnce({
      data: { success: true },
    });

    render(<DispositionModal {...defaultProps} />);

    const select = screen.getByRole('combobox');
    fireEvent.change(select, { target: { value: 'Do Not Call Again' } });

    await act(async () => {
      fireEvent.click(screen.getByText('Submit'));
    });

    await waitFor(() => {
      expect(mockAxiosPost).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({
          disposition: 'Do Not Call Again',
          follow_up_required: false,
          referral_opportunity: false,
        }),
        expect.any(Object)
      );
    });
  });

  // --- 12. Referral opportunity flag ---
  it('sends referral_opportunity flag for Referral Opportunity disposition', async () => {
    mockAxiosPost.mockResolvedValueOnce({
      data: { success: true },
    });

    render(<DispositionModal {...defaultProps} />);

    const select = screen.getByRole('combobox');
    fireEvent.change(select, { target: { value: 'Referral Opportunity' } });

    await act(async () => {
      fireEvent.click(screen.getByText('Submit'));
    });

    await waitFor(() => {
      expect(mockAxiosPost).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({
          disposition: 'Referral Opportunity',
          referral_opportunity: true,
        }),
        expect.any(Object)
      );
    });
  });

  // --- 13. Helper text about submission requirement ---
  it('shows helper text about submission being required', () => {
    render(<DispositionModal {...defaultProps} />);

    expect(
      screen.getByText('Submission required before next call begins')
    ).toBeInTheDocument();
  });

  // --- 14. Uses call-log endpoint for standalone calls ---
  it('uses call-log disposition endpoint when callLogId is provided without sessionId', async () => {
    mockAxiosPost.mockResolvedValueOnce({
      data: { success: true },
    });

    render(
      <DispositionModal
        taskId={null}
        sessionId={null}
        callLogId="log-55"
        contactName="Bob Wilson"
        callDuration={30}
        onClose={vi.fn()}
        onSaved={vi.fn()}
      />
    );

    const select = screen.getByRole('combobox');
    fireEvent.change(select, { target: { value: 'Busy Signal' } });

    await act(async () => {
      fireEvent.click(screen.getByText('Submit'));
    });

    await waitFor(() => {
      expect(mockAxiosPost).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/dialer/call-log/log-55/disposition'),
        expect.any(Object),
        expect.any(Object)
      );
    });
  });
});
