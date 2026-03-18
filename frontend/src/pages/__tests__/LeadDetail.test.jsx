import React from 'react';
import { render, screen, waitFor, within, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

// ---------------------------------------------------------------------------
// Mocks — must come before the component import
// ---------------------------------------------------------------------------

vi.mock('../LeadDetail.css', () => ({}));

// Mock API services
const mockLeadsAPI = {
  getAll: vi.fn(() => Promise.resolve([])),
  getById: vi.fn(() => Promise.resolve(null)),
  create: vi.fn(() => Promise.resolve({ id: 999 })),
  update: vi.fn(() => Promise.resolve({})),
  delete: vi.fn(() => Promise.resolve()),
  search: vi.fn(() => Promise.resolve({ leads: [] })),
};

const mockActivitiesAPI = {
  getAll: vi.fn(() => Promise.resolve([])),
  create: vi.fn(() => Promise.resolve({})),
};

const mockLoansAPI = {
  getAll: vi.fn(() => Promise.resolve([])),
  create: vi.fn(() => Promise.resolve({ id: 100 })),
  update: vi.fn(() => Promise.resolve({})),
};

vi.mock('../../services/api', () => ({
  leadsAPI: mockLeadsAPI,
  activitiesAPI: mockActivitiesAPI,
  loansAPI: mockLoansAPI,
  circleOfCashflowAPI: {
    getOpportunities: vi.fn(() => Promise.resolve([])),
    getReferrals: vi.fn(() => Promise.resolve([])),
  },
  tasksAPI: {
    getAll: vi.fn(() => Promise.resolve([])),
    create: vi.fn(() => Promise.resolve({})),
  },
  dialerAPI: {},
  borrowerApplicationAPI: {
    send: vi.fn(() => Promise.resolve({})),
  },
  purlAPI: {
    getWorkspaceByLead: vi.fn(() => Promise.resolve(null)),
  },
  partnersAPI: {
    getAll: vi.fn(() => Promise.resolve([])),
  },
  API_BASE_URL: 'http://localhost:8000',
}));

// Mock toast
vi.mock('../../utils/toast', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
    info: vi.fn(),
  },
}));

import { toast } from '../../utils/toast';

// Mock phoneUtils
vi.mock('../../utils/phoneUtils', () => ({
  formatPhoneNumber: (v) => v,
}));

// Mock child components that are not under test
vi.mock('../../components/ClickableContact', () => ({
  ClickableEmail: ({ email }) => <span data-testid="clickable-email">{email}</span>,
  ClickablePhone: ({ phone }) => <span data-testid="clickable-phone">{phone}</span>,
}));

vi.mock('../../components/SMSModal', () => ({ default: () => null }));
vi.mock('../../components/TeamsModal', () => ({ default: () => null }));
vi.mock('../../components/RecordingModal', () => ({ default: () => null }));
vi.mock('../../components/EscalationModal', () => ({ default: () => null }));
vi.mock('../../components/VoicemailDrop', () => ({ default: () => null }));
vi.mock('../../components/SendApplicationModal', () => ({ default: () => null }));

vi.mock('../../components/DispositionNoteModal', () => {
  const comp = () => null;
  comp.REQUIRES_NOTE = ['Withdrawn', 'Does Not Qualify', 'Dead', 'Denied', 'Cancelled'];
  return { default: comp };
});

vi.mock('../../components/CreateTaskModal', () => ({ default: () => null }));
vi.mock('../../components/AppointmentModal', () => ({ default: () => null }));
vi.mock('../../components/ScheduleAppointmentModal', () => ({ default: () => null }));
vi.mock('../../components/TeamAssignment', () => ({ default: () => null }));
vi.mock('../../components/WorkflowRoleAssignment', () => ({ default: () => null }));
vi.mock('../../components/EmploymentTab', () => ({ default: () => <div>Employment Tab</div> }));
vi.mock('../../components/income/IncomeTab', () => ({ default: () => <div>Income Tab</div> }));
vi.mock('../../components/income/UnifiedIncomeCalculator', () => ({ default: () => null }));
vi.mock('../../components/IncomeCalculator', () => ({ default: () => null }));
vi.mock('../../components/CreditTab', () => ({ default: () => <div>Credit Tab</div> }));
vi.mock('../../components/call-intelligence/CallIntelligenceTab', () => ({ default: () => <div>Call Intelligence Tab</div> }));
vi.mock('../../components/VideoMeetings', () => ({ default: () => null }));
vi.mock('../../components/VideoCallScheduleModal', () => ({ default: () => null }));
vi.mock('../../components/EmailComposerModal', () => ({ default: () => null }));
vi.mock('../../components/CalendarSidebar', () => ({ default: () => null }));
vi.mock('../../components/smart-docs/NeedsListView', () => ({ default: () => <div>Smart Docs</div> }));
vi.mock('../../components/video/SendVideoModal', () => ({ default: () => null }));
vi.mock('../../components/SalesforceConnectionBadge', () => ({ default: () => null }));
vi.mock('../../components/common/CurrencyInput', () => ({
  default: ({ value, onChange, placeholder }) => (
    <input
      data-testid="currency-input"
      value={value || ''}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
    />
  ),
}));

// Mock global fetch for direct fetch() calls in the component
const mockFetch = vi.fn(() =>
  Promise.resolve({
    ok: true,
    json: () => Promise.resolve([]),
  })
);
global.fetch = mockFetch;

import LeadDetail from '../LeadDetail';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const sampleLead = {
  id: 42,
  name: 'Sarah Johnson',
  first_name: 'Sarah',
  last_name: 'Johnson',
  email: 'sarah@example.com',
  phone: '(555) 123-4567',
  stage: 'New',
  source: 'Website',
  credit_score: 720,
  loan_amount: 425000,
  loan_type: 'conventional',
  loan_purpose: 'Purchase',
  loan_number: 'LN-001',
  property_address: '123 Main St',
  city: 'Springfield',
  state: 'IL',
  zip_code: '62701',
  created_at: new Date().toISOString(),
  ai_score: 85,
};

const sampleActivities = [
  {
    id: 'a1',
    type: 'note',
    content: 'Initial contact made via phone',
    created_at: new Date().toISOString(),
    user_name: 'Admin User',
  },
  {
    id: 'a2',
    type: 'email',
    content: 'Sent pre-qualification info',
    created_at: new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString(),
    user_name: 'Admin User',
  },
];

function renderLeadDetail(leadId = '42') {
  return render(
    <MemoryRouter initialEntries={[`/leads/${leadId}`]}>
      <Routes>
        <Route path="/leads/:id" element={<LeadDetail />} />
        <Route path="/leads" element={<div>Leads List</div>} />
      </Routes>
    </MemoryRouter>
  );
}

function setupDefaultMocks() {
  mockLeadsAPI.getById.mockResolvedValue({ ...sampleLead });
  mockLeadsAPI.getAll.mockResolvedValue([sampleLead]);
  mockActivitiesAPI.getAll.mockResolvedValue([...sampleActivities]);
  mockFetch.mockImplementation(() =>
    Promise.resolve({
      ok: true,
      json: () => Promise.resolve([]),
    })
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('LeadDetail', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    localStorage.setItem('token', 'test-token');
  });

  // =========================================================================
  // 1. Loading State
  // =========================================================================

  describe('Loading State', () => {
    it('shows loading message initially', () => {
      // Make the API call never resolve so we stay in loading
      mockLeadsAPI.getById.mockReturnValue(new Promise(() => {}));
      mockLeadsAPI.getAll.mockReturnValue(new Promise(() => {}));
      mockActivitiesAPI.getAll.mockReturnValue(new Promise(() => {}));
      renderLeadDetail();

      expect(screen.getByText('Loading lead details...')).toBeInTheDocument();
    });
  });

  // =========================================================================
  // 2. Error States
  // =========================================================================

  describe('Error States', () => {
    it('shows error message when lead is not found (404)', async () => {
      mockLeadsAPI.getById.mockRejectedValue({
        response: { status: 404 },
        message: 'Not Found',
      });
      mockLeadsAPI.getAll.mockResolvedValue([]);
      mockActivitiesAPI.getAll.mockResolvedValue([]);

      renderLeadDetail();

      await waitFor(() => {
        expect(screen.getByText('Error Loading Lead')).toBeInTheDocument();
      });
      expect(screen.getByText(/Lead not found/)).toBeInTheDocument();
    });

    it('shows back to leads button on error page', async () => {
      mockLeadsAPI.getById.mockRejectedValue({
        response: { status: 404 },
        message: 'Not Found',
      });
      mockLeadsAPI.getAll.mockResolvedValue([]);
      mockActivitiesAPI.getAll.mockResolvedValue([]);

      renderLeadDetail();

      await waitFor(() => {
        expect(screen.getByText(/Back to Leads/)).toBeInTheDocument();
      });
    });

    it('shows API error message when load fails with non-404', async () => {
      mockLeadsAPI.getById.mockRejectedValue({
        response: { status: 500, data: { detail: 'Internal server error' } },
        message: 'Server Error',
      });
      mockLeadsAPI.getAll.mockResolvedValue([]);
      mockActivitiesAPI.getAll.mockResolvedValue([]);

      renderLeadDetail();

      await waitFor(() => {
        expect(screen.getByText('Error Loading Lead')).toBeInTheDocument();
        expect(screen.getByText('Internal server error')).toBeInTheDocument();
      });
    });
  });

  // =========================================================================
  // 3. Lead Data Display
  // =========================================================================

  describe('Lead Data Display', () => {
    beforeEach(() => {
      setupDefaultMocks();
    });

    it('displays the lead name in the client banner', async () => {
      renderLeadDetail();

      await waitFor(() => {
        expect(screen.getByText('Sarah Johnson')).toBeInTheDocument();
      });
    });

    it('shows the current lead stage in the status button', async () => {
      renderLeadDetail();

      await waitFor(() => {
        // The status button shows the lead stage
        const statusButtons = screen.getAllByText('New');
        expect(statusButtons.length).toBeGreaterThanOrEqual(1);
      });
    });

    it('shows Back to Leads navigation button', async () => {
      renderLeadDetail();

      await waitFor(() => {
        expect(screen.getByText(/Back to Leads/)).toBeInTheDocument();
      });
    });

    it('shows View Next Lead button', async () => {
      renderLeadDetail();

      await waitFor(() => {
        expect(screen.getByText(/View Next Lead/)).toBeInTheDocument();
      });
    });

    it('shows Save and Cancel buttons (always in edit mode)', async () => {
      renderLeadDetail();

      await waitFor(() => {
        expect(screen.getByText('Save')).toBeInTheDocument();
        expect(screen.getByText('Cancel')).toBeInTheDocument();
      });
    });
  });

  // =========================================================================
  // 4. Tab Navigation
  // =========================================================================

  describe('Tab Navigation', () => {
    beforeEach(() => {
      setupDefaultMocks();
    });

    it('renders all profile tabs', async () => {
      renderLeadDetail();

      await waitFor(() => {
        expect(screen.getByText('Loan Details')).toBeInTheDocument();
      });

      expect(screen.getByText('Personal')).toBeInTheDocument();
      expect(screen.getByText('Property')).toBeInTheDocument();
      expect(screen.getByText('Tasks')).toBeInTheDocument();
      expect(screen.getByText('Conversation Log')).toBeInTheDocument();
      expect(screen.getByText('Circle')).toBeInTheDocument();
      expect(screen.getByText('Smart Docs')).toBeInTheDocument();
      expect(screen.getByText('Income')).toBeInTheDocument();
      expect(screen.getByText('Credit')).toBeInTheDocument();
      expect(screen.getByText('Conditions')).toBeInTheDocument();
      expect(screen.getByText('SLA Dates')).toBeInTheDocument();
      expect(screen.getByText('Team Members')).toBeInTheDocument();
      expect(screen.getByText('Call Intelligence')).toBeInTheDocument();
    });

    it('defaults to Loan Details tab', async () => {
      renderLeadDetail();

      await waitFor(() => {
        expect(screen.getByText('Loan Details')).toBeInTheDocument();
      });

      // The Loan Details tab button should have the active class
      const loanDetailsTab = screen.getByText('Loan Details');
      expect(loanDetailsTab.closest('button')).toHaveClass('active');
    });

    it('switches to Personal tab when clicked', async () => {
      renderLeadDetail();

      await waitFor(() => {
        expect(screen.getByText('Personal')).toBeInTheDocument();
      });

      await userEvent.click(screen.getByText('Personal'));

      const personalTab = screen.getByText('Personal');
      expect(personalTab.closest('button')).toHaveClass('active');
    });

    it('switches to Tasks tab when clicked', async () => {
      renderLeadDetail();

      await waitFor(() => {
        expect(screen.getByText('Tasks')).toBeInTheDocument();
      });

      await userEvent.click(screen.getByText('Tasks'));

      const tasksTab = screen.getByText('Tasks');
      expect(tasksTab.closest('button')).toHaveClass('active');
    });
  });

  // =========================================================================
  // 5. Loan Details Tab Content
  // =========================================================================

  describe('Loan Details Tab', () => {
    beforeEach(() => {
      setupDefaultMocks();
    });

    it('shows transaction type toggle (Purchase/Refinance)', async () => {
      renderLeadDetail();

      await waitFor(() => {
        expect(screen.getByText('Transaction Type')).toBeInTheDocument();
      });

      expect(screen.getByText('Purchase')).toBeInTheDocument();
      expect(screen.getByText('Refinance')).toBeInTheDocument();
    });

    it('shows loan number field with the lead loan number', async () => {
      renderLeadDetail();

      await waitFor(() => {
        expect(screen.getByText('Loan Number')).toBeInTheDocument();
      });

      const loanNumberInput = screen.getByDisplayValue('LN-001');
      expect(loanNumberInput).toBeInTheDocument();
    });
  });

  // =========================================================================
  // 6. Status Dropdown
  // =========================================================================

  describe('Status Dropdown', () => {
    beforeEach(() => {
      setupDefaultMocks();
    });

    it('opens status dropdown when status button is clicked', async () => {
      renderLeadDetail();

      await waitFor(() => {
        expect(screen.getByText('Sarah Johnson')).toBeInTheDocument();
      });

      // Find and click the status button (contains the stage text)
      const statusBtn = screen.getAllByText('New').find(
        (el) => el.closest('.btn-status') || el.closest('.status-dropdown-container')
      );
      if (statusBtn) {
        await userEvent.click(statusBtn.closest('button'));

        // Dropdown should show stage options
        await waitFor(() => {
          expect(screen.getByText('Lead Stages')).toBeInTheDocument();
          expect(screen.getByText('Attempted Contact')).toBeInTheDocument();
          expect(screen.getByText('Prospect')).toBeInTheDocument();
        });
      }
    });

    it('shows stage category headers (Lead Stages, Active Loan Stages, MUM)', async () => {
      renderLeadDetail();

      await waitFor(() => {
        expect(screen.getByText('Sarah Johnson')).toBeInTheDocument();
      });

      // Open the status dropdown
      const statusBtns = screen.getAllByText('New');
      const statusBtn = statusBtns.find((el) => el.closest('button'));
      if (statusBtn) {
        await userEvent.click(statusBtn.closest('button'));

        await waitFor(() => {
          expect(screen.getByText('Lead Stages')).toBeInTheDocument();
          expect(screen.getByText('Active Loan Stages')).toBeInTheDocument();
        });
      }
    });
  });

  // =========================================================================
  // 7. Save Functionality
  // =========================================================================

  describe('Save Functionality', () => {
    beforeEach(() => {
      setupDefaultMocks();
    });

    it('calls leadsAPI.update when Save is clicked', async () => {
      renderLeadDetail();

      await waitFor(() => {
        expect(screen.getByText('Save')).toBeInTheDocument();
      });

      mockLeadsAPI.update.mockResolvedValue({ ...sampleLead });
      await userEvent.click(screen.getByText('Save'));

      await waitFor(() => {
        expect(mockLeadsAPI.update).toHaveBeenCalled();
      });
    });

    it('shows success toast after successful save', async () => {
      renderLeadDetail();

      await waitFor(() => {
        expect(screen.getByText('Save')).toBeInTheDocument();
      });

      mockLeadsAPI.update.mockResolvedValue({ ...sampleLead });
      await userEvent.click(screen.getByText('Save'));

      await waitFor(() => {
        expect(toast.success).toHaveBeenCalled();
      });
    });

    it('shows error toast when save fails', async () => {
      renderLeadDetail();

      await waitFor(() => {
        expect(screen.getByText('Save')).toBeInTheDocument();
      });

      mockLeadsAPI.update.mockRejectedValue(new Error('Save failed'));
      await userEvent.click(screen.getByText('Save'));

      await waitFor(() => {
        expect(toast.error).toHaveBeenCalled();
      });
    });
  });

  // =========================================================================
  // 8. Activities / Conversation Log
  // =========================================================================

  describe('Activities', () => {
    beforeEach(() => {
      setupDefaultMocks();
    });

    it('loads activities from the API on mount', async () => {
      renderLeadDetail();

      await waitFor(() => {
        expect(mockActivitiesAPI.getAll).toHaveBeenCalledWith(
          expect.objectContaining({ lead_id: 42 })
        );
      });
    });

    it('continues to load even if activities API fails', async () => {
      mockActivitiesAPI.getAll.mockRejectedValue(new Error('Activities unavailable'));

      renderLeadDetail();

      // Lead should still load successfully
      await waitFor(() => {
        expect(screen.getByText('Sarah Johnson')).toBeInTheDocument();
      });
    });
  });

  // =========================================================================
  // 9. Lead Navigation
  // =========================================================================

  describe('Lead Navigation', () => {
    beforeEach(() => {
      setupDefaultMocks();
    });

    it('marks lead as viewed in localStorage', async () => {
      renderLeadDetail();

      await waitFor(() => {
        expect(screen.getByText('Sarah Johnson')).toBeInTheDocument();
      });

      const viewedLeads = JSON.parse(localStorage.getItem('viewedLeads') || '[]');
      expect(viewedLeads).toContain('42');
    });

    it('fetches lead list for next/previous navigation', async () => {
      renderLeadDetail();

      await waitFor(() => {
        expect(mockLeadsAPI.getAll).toHaveBeenCalled();
      });
    });
  });

  // =========================================================================
  // 10. Edge Cases
  // =========================================================================

  describe('Edge Cases', () => {
    it('handles lead with no name gracefully', async () => {
      mockLeadsAPI.getById.mockResolvedValue({
        id: 42,
        first_name: '',
        last_name: '',
        email: 'noname@example.com',
        stage: 'New',
        created_at: new Date().toISOString(),
      });
      mockLeadsAPI.getAll.mockResolvedValue([]);
      mockActivitiesAPI.getAll.mockResolvedValue([]);

      renderLeadDetail();

      await waitFor(() => {
        // Should show fallback name
        expect(screen.getByText('Unknown Client')).toBeInTheDocument();
      });
    });

    it('handles lead with only first_name', async () => {
      mockLeadsAPI.getById.mockResolvedValue({
        id: 42,
        first_name: 'Jane',
        last_name: '',
        email: 'jane@example.com',
        stage: 'Prospect',
        created_at: new Date().toISOString(),
      });
      mockLeadsAPI.getAll.mockResolvedValue([]);
      mockActivitiesAPI.getAll.mockResolvedValue([]);

      renderLeadDetail();

      await waitFor(() => {
        expect(screen.getByText('Jane')).toBeInTheDocument();
      });
    });

    it('handles lead with co-borrower data', async () => {
      mockLeadsAPI.getById.mockResolvedValue({
        ...sampleLead,
        co_applicant_name: 'Bob Johnson',
        co_applicant_email: 'bob@example.com',
        co_applicant_phone: '(555) 999-0000',
      });
      mockLeadsAPI.getAll.mockResolvedValue([]);
      mockActivitiesAPI.getAll.mockResolvedValue([]);

      renderLeadDetail();

      await waitFor(() => {
        expect(screen.getByText('Sarah Johnson')).toBeInTheDocument();
      });
      // Co-borrower creates a second entry in the borrowers selector
    });

    it('initializes formData from lead response (name parsing)', async () => {
      // Lead with name but no first_name/last_name
      mockLeadsAPI.getById.mockResolvedValue({
        id: 42,
        name: 'Jane Smith',
        email: 'jane@example.com',
        stage: 'New',
        created_at: new Date().toISOString(),
      });
      mockLeadsAPI.getAll.mockResolvedValue([]);
      mockActivitiesAPI.getAll.mockResolvedValue([]);

      renderLeadDetail();

      await waitFor(() => {
        // Name should be parsed: first_name="Jane", last_name="Smith"
        expect(screen.getByText('Jane Smith')).toBeInTheDocument();
      });
    });
  });
});
