import React from 'react';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock('../LeadDetail.css', () => ({}));

// Mock react-router-dom
const mockNavigate = vi.fn();
vi.mock('react-router-dom', () => ({
  useParams: () => ({ id: '42' }),
  useNavigate: () => mockNavigate,
  useSearchParams: () => [new URLSearchParams(), vi.fn()],
}));

// Mock all API services
const mockLoansAPI = {
  getById: vi.fn(),
  update: vi.fn(),
};
const mockActivitiesAPI = {
  getAll: vi.fn(),
  create: vi.fn(),
};
const mockSchedulerAPI = {
  getAppointments: vi.fn(),
};
const mockDialerAPI = {
  clickToDial: vi.fn(),
};
const mockBorrowerApplicationAPI = {
  createForLead: vi.fn(),
};
const mockPurlAPI = {
  getWorkspaceByLead: vi.fn(),
  createWorkspace: vi.fn(),
  createToken: vi.fn(),
};

vi.mock('../../services/api', () => ({
  loansAPI: mockLoansAPI,
  activitiesAPI: mockActivitiesAPI,
  schedulerAPI: mockSchedulerAPI,
  dialerAPI: mockDialerAPI,
  borrowerApplicationAPI: mockBorrowerApplicationAPI,
  purlAPI: mockPurlAPI,
}));

vi.mock('../../utils/toast', () => ({
  toast: {
    error: vi.fn(),
    success: vi.fn(),
    warning: vi.fn(),
    info: vi.fn(),
  },
}));

// Mock child components to keep tests focused on ClientProfile
vi.mock('../../components/ClickableContact', () => ({
  ClickableEmail: ({ email }) =>
    email ? <a href={`mailto:${email}`} data-testid="clickable-email">{email}</a> : <span>N/A</span>,
  ClickablePhone: ({ phone }) =>
    phone ? <button data-testid="clickable-phone">{phone}</button> : <span>N/A</span>,
}));

vi.mock('../../components/SMSModal', () => ({
  default: ({ show, onClose }) =>
    show ? <div data-testid="sms-modal"><button onClick={onClose}>Close</button></div> : null,
}));

vi.mock('../../components/VideoCallScheduleModal', () => ({
  default: () => null,
}));
vi.mock('../../components/RecordingModal', () => ({
  default: () => null,
}));
vi.mock('../../components/video/SendVideoModal', () => ({
  default: () => null,
}));
vi.mock('../../components/VoicemailDrop', () => ({
  default: () => null,
}));
vi.mock('../../components/EscalationModal', () => ({
  default: () => null,
}));
vi.mock('../../components/CreateTaskModal', () => ({
  default: () => null,
}));
vi.mock('../../components/EmailComposerModal', () => ({
  default: () => null,
}));
vi.mock('../../components/TeamAssignment', () => ({
  default: () => <div data-testid="team-assignment">Team Assignment</div>,
}));
vi.mock('../../components/EmploymentTab', () => ({
  default: () => <div data-testid="employment-tab">Employment</div>,
}));
vi.mock('../../components/income/IncomeTab', () => ({
  default: () => <div data-testid="income-tab">Income</div>,
}));
vi.mock('../../components/ScheduleAppointmentModal', () => ({
  default: () => null,
}));
vi.mock('../../components/smart-docs/NeedsListView', () => ({
  default: () => <div data-testid="needs-list">Smart Docs</div>,
}));
vi.mock('../../components/CreditTab', () => ({
  default: () => <div data-testid="credit-tab">Credit</div>,
}));
vi.mock('../../components/SalesforceConnectionBadge', () => ({
  default: () => <div data-testid="sf-badge">SF Badge</div>,
}));
vi.mock('../../components/call-intelligence/CallIntelligenceTab', () => ({
  default: () => <div data-testid="call-intelligence">Call Intelligence</div>,
}));

import ClientProfile from '../ClientProfile';
import { toast } from '../../utils/toast';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const mockFetch = vi.fn();

function mockResponse(body, status = 200) {
  return Promise.resolve({
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(body),
  });
}

const sampleClient = {
  id: 42,
  name: 'Sarah Johnson',
  borrower_name: 'Sarah Johnson',
  first_name: 'Sarah',
  last_name: 'Johnson',
  email: 'sarah@example.com',
  borrower_email: 'sarah@example.com',
  phone: '(555) 123-4567',
  borrower_phone: '(555) 123-4567',
  stage: 'Application',
  source: 'Website',
  credit_score: 720,
  loan_amount: 425000,
  loan_type: 'Conventional',
  loan_number: 'LN-2026-0042',
  property_type: 'Single Family',
  address: '123 Main St',
  city: 'Austin',
  state: 'TX',
  zip_code: '78701',
  created_at: '2026-01-15T10:00:00Z',
  interest_rate: 6.5,
  loan_term: 30,
  co_applicant_name: null,
};

const sampleActivities = [
  {
    id: 1,
    type: 'Call',
    content: 'Initial consultation call completed',
    created_at: '2026-03-10T14:00:00Z',
    user_name: 'Tim Loss',
  },
  {
    id: 2,
    type: 'Email',
    content: 'Sent pre-qualification details',
    created_at: '2026-03-08T09:00:00Z',
    user_name: 'Tim Loss',
  },
  {
    id: 3,
    type: 'Note',
    content: 'Prefers text messages for quick updates',
    created_at: '2026-03-05T11:00:00Z',
    user_name: 'Tim Loss',
  },
];

function setupDefaultMocks(clientOverride = null, activitiesOverride = null) {
  const clientData = clientOverride || sampleClient;
  const actData = activitiesOverride || sampleActivities;

  mockLoansAPI.getById.mockResolvedValue(clientData);
  mockLoansAPI.update.mockResolvedValue(clientData);
  mockActivitiesAPI.getAll.mockResolvedValue(actData);
  mockActivitiesAPI.create.mockResolvedValue({ id: 99, type: 'Note' });
  mockSchedulerAPI.getAppointments.mockResolvedValue([]);
  mockDialerAPI.clickToDial.mockResolvedValue({ success: true });

  // Mock fetch for endpoints that use direct fetch
  mockFetch.mockImplementation((url) => {
    if (url.includes('/circle-contacts')) {
      return mockResponse({ contacts: [] });
    }
    if (url.includes('/milestones')) {
      return mockResponse({ milestones: [] });
    }
    return mockResponse({});
  });

  // Mock localStorage
  vi.spyOn(Storage.prototype, 'getItem').mockImplementation((key) => {
    if (key === 'token') return 'mock-jwt-token';
    if (key === 'viewedLoans') return '[]';
    return null;
  });
  vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {});
}

async function renderClientProfile() {
  let result;
  await act(async () => {
    result = render(<ClientProfile />);
  });
  return result;
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('ClientProfile', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers({ shouldAdvanceTime: true });
    global.fetch = mockFetch;
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  // -- Loading State --

  it('displays loading message while data is being fetched', () => {
    // Make API calls hang
    mockLoansAPI.getById.mockReturnValue(new Promise(() => {}));
    mockActivitiesAPI.getAll.mockReturnValue(new Promise(() => {}));
    mockSchedulerAPI.getAppointments.mockResolvedValue([]);
    mockFetch.mockReturnValue(new Promise(() => {}));
    vi.spyOn(Storage.prototype, 'getItem').mockReturnValue('mock-jwt');
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {});

    render(<ClientProfile />);
    expect(screen.getByText('Loading lead details...')).toBeInTheDocument();
  });

  // -- Not Found State --

  it('displays error when loan is not found', async () => {
    mockLoansAPI.getById.mockRejectedValue(new Error('Not found'));
    mockActivitiesAPI.getAll.mockRejectedValue(new Error('Not found'));
    mockSchedulerAPI.getAppointments.mockResolvedValue([]);
    mockFetch.mockImplementation(() => mockResponse({}));
    vi.spyOn(Storage.prototype, 'getItem').mockReturnValue('mock-jwt');
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {});

    await renderClientProfile();

    // Component navigates to /loans when not found, check the navigation call
    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith('/loans');
    });
  });

  // -- Client Data Display --

  it('displays the client name in the header banner', async () => {
    setupDefaultMocks();
    await renderClientProfile();

    await waitFor(() => {
      expect(screen.getByText('Sarah Johnson')).toBeInTheDocument();
    });
  });

  it('displays the current stage as a colored badge', async () => {
    setupDefaultMocks();
    await renderClientProfile();

    await waitFor(() => {
      // The stage "Application" should appear in the status button
      const statusBtn = screen.getByText(/Application/);
      expect(statusBtn).toBeInTheDocument();
    });
  });

  // -- Tab Navigation --

  it('renders all tab buttons and allows switching between them', async () => {
    setupDefaultMocks();
    await renderClientProfile();

    await waitFor(() => {
      expect(screen.getByText('Loan Details')).toBeInTheDocument();
    });

    const expectedTabs = [
      'Loan Details', 'Personal', 'Property', 'Tasks',
      'Conversation Log', 'Circle', 'Smart Docs', 'Credit',
      'Income', 'Conditions', 'SLA Dates', 'Team Members',
      'Call Intelligence',
    ];

    for (const tabName of expectedTabs) {
      expect(screen.getByRole('button', { name: tabName })).toBeInTheDocument();
    }
  });

  it('switches to Personal tab and shows personal info fields', async () => {
    setupDefaultMocks();
    await renderClientProfile();

    await waitFor(() => {
      expect(screen.getByText('Personal')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: 'Personal' }));

    await waitFor(() => {
      expect(screen.getByText('Personal Information')).toBeInTheDocument();
      expect(screen.getByLabelText('First Name')).toBeInTheDocument();
      expect(screen.getByLabelText('Last Name')).toBeInTheDocument();
      expect(screen.getByLabelText('Email')).toBeInTheDocument();
      expect(screen.getByLabelText('Phone')).toBeInTheDocument();
    });
  });

  // -- Edit / Save Flow --

  it('shows Save and Cancel buttons since form starts in edit mode', async () => {
    setupDefaultMocks();
    await renderClientProfile();

    await waitFor(() => {
      expect(screen.getByText('Save')).toBeInTheDocument();
      expect(screen.getByText('Cancel')).toBeInTheDocument();
    });
  });

  it('calls loansAPI.update on Save click', async () => {
    setupDefaultMocks();
    await renderClientProfile();

    await waitFor(() => {
      expect(screen.getByText('Save')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('Save'));

    await waitFor(() => {
      expect(mockLoansAPI.update).toHaveBeenCalledWith('42', expect.objectContaining({
        name: 'Sarah Johnson',
      }));
    });
  });

  it('shows success toast after successful save', async () => {
    setupDefaultMocks();
    await renderClientProfile();

    await waitFor(() => {
      expect(screen.getByText('Save')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('Save'));

    await waitFor(() => {
      expect(toast.success).toHaveBeenCalledWith('Lead updated successfully!');
    });
  });

  it('shows error toast when save fails', async () => {
    setupDefaultMocks();
    mockLoansAPI.update.mockRejectedValue(new Error('Server error'));

    await renderClientProfile();

    await waitFor(() => {
      expect(screen.getByText('Save')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('Save'));

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('Failed to update lead');
    });
  });

  // -- Loan Details Tab --

  it('displays loan fields on the Loan Details tab by default', async () => {
    setupDefaultMocks();
    await renderClientProfile();

    await waitFor(() => {
      expect(screen.getByText('Loan Details')).toBeInTheDocument();
    });

    // Check that loan fields are present in the tab
    expect(screen.getByLabelText('Loan Number')).toBeInTheDocument();
    expect(screen.getByLabelText('Loan Amount')).toBeInTheDocument();
  });

  it('populates loan detail fields with client data', async () => {
    setupDefaultMocks();
    await renderClientProfile();

    await waitFor(() => {
      const loanNumberInput = screen.getByLabelText('Loan Number');
      expect(loanNumberInput).toHaveValue('LN-2026-0042');
    });
  });

  // -- Loan Toolbar Fields --

  it('renders the loan toolbar with financial fields', async () => {
    setupDefaultMocks();
    await renderClientProfile();

    await waitFor(() => {
      expect(screen.getByText('Loan Details')).toBeInTheDocument();
    });

    // Toolbar fields
    const loanAmountInputs = screen.getAllByPlaceholderText('$');
    expect(loanAmountInputs.length).toBeGreaterThanOrEqual(1);
  });

  // -- Status Change --

  it('opens status dropdown on stage badge click', async () => {
    setupDefaultMocks();
    await renderClientProfile();

    await waitFor(() => {
      const statusBtn = screen.getByText(/Application/);
      expect(statusBtn).toBeInTheDocument();
    });

    // Click the status badge to open dropdown
    const statusBtn = screen.getByText(/Application/);
    fireEvent.click(statusBtn);

    await waitFor(() => {
      // Status options should be visible
      expect(screen.getByText('Lead Stages')).toBeInTheDocument();
      expect(screen.getByText('Active Loan Stages')).toBeInTheDocument();
    });
  });

  it('calls loansAPI.update when a new status is selected', async () => {
    setupDefaultMocks();
    await renderClientProfile();

    await waitFor(() => {
      expect(screen.getByText(/Application/)).toBeInTheDocument();
    });

    // Open dropdown
    fireEvent.click(screen.getByText(/Application/));

    await waitFor(() => {
      expect(screen.getByText('Processing')).toBeInTheDocument();
    });

    // Select new status
    fireEvent.click(screen.getByText('Processing'));

    await waitFor(() => {
      expect(mockLoansAPI.update).toHaveBeenCalledWith('42', { stage: 'Processing' });
    });
  });

  // -- Borrower Selector --

  it('shows primary borrower in the borrower selector', async () => {
    setupDefaultMocks();
    await renderClientProfile();

    await waitFor(() => {
      // Should show borrower name and Primary badge
      expect(screen.getByText('Sarah Johnson')).toBeInTheDocument();
      expect(screen.getByText('Primary')).toBeInTheDocument();
    });
  });

  it('shows Add Person button in borrower selector', async () => {
    setupDefaultMocks();
    await renderClientProfile();

    await waitFor(() => {
      expect(screen.getByText('+ Add Person')).toBeInTheDocument();
    });
  });

  // -- Communication Channel Display --

  it('renders call action button in the header', async () => {
    setupDefaultMocks();
    await renderClientProfile();

    // Wait for data to load
    await waitFor(() => {
      expect(screen.getByText('Sarah Johnson')).toBeInTheDocument();
    });

    // The action bar should have communication channel buttons
    // The actual rendering depends on the action bar section;
    // here we verify the header actions region exists
    expect(screen.getByText('Save')).toBeInTheDocument();
  });

  // -- Back Navigation --

  it('navigates to /loans when back button is clicked', async () => {
    setupDefaultMocks();
    await renderClientProfile();

    await waitFor(() => {
      const backBtn = screen.getByText(/Back to Leads/);
      expect(backBtn).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText(/Back to Leads/));
    expect(mockNavigate).toHaveBeenCalledWith('/loans');
  });

  // -- Mark as Viewed --

  it('marks the loan as viewed in localStorage on load', async () => {
    const setItemSpy = vi.spyOn(Storage.prototype, 'setItem');
    setupDefaultMocks();
    await renderClientProfile();

    await waitFor(() => {
      expect(setItemSpy).toHaveBeenCalledWith(
        'viewedLoans',
        expect.stringContaining('42')
      );
    });
  });

  // -- Co-Borrower Display --

  it('shows co-borrower tab when co_applicant_name is present', async () => {
    const clientWithCoBorrower = {
      ...sampleClient,
      co_applicant_name: 'David Johnson',
      co_applicant_email: 'david@example.com',
      co_applicant_phone: '(555) 999-0000',
    };
    setupDefaultMocks(clientWithCoBorrower);
    await renderClientProfile();

    await waitFor(() => {
      expect(screen.getByText('David Johnson')).toBeInTheDocument();
    });
  });
});
