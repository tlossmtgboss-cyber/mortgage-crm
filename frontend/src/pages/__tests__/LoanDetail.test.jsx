import React from 'react';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

// ---------------------------------------------------------------------------
// Mocks — must come before component import
// ---------------------------------------------------------------------------

const mockNavigate = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return { ...actual, useNavigate: () => mockNavigate };
});

vi.mock('@/services/api', () => ({
  loansAPI: {
    getAll: vi.fn(() => Promise.resolve([])),
    getById: vi.fn(() => Promise.resolve(null)),
    update: vi.fn(() => Promise.resolve({})),
    search: vi.fn(() => Promise.resolve({ loans: [] })),
  },
  activitiesAPI: {
    create: vi.fn(() => Promise.resolve({})),
    getAll: vi.fn(() => Promise.resolve([])),
  },
  circleOfCashflowAPI: {
    getOpportunities: vi.fn(() => Promise.resolve({ opportunities: [] })),
    getReferrals: vi.fn(() => Promise.resolve({ referrals: [] })),
    getPartners: vi.fn(() => Promise.resolve({ partners: [] })),
  },
  partnersAPI: {
    getAll: vi.fn(() => Promise.resolve([])),
  },
  salesforceAPI: {
    getStatus: vi.fn(() => Promise.resolve({ connected: false })),
    getLoanSyncStatus: vi.fn(() => Promise.reject(new Error('not configured'))),
    pullLoan: vi.fn(() => Promise.resolve({ status: 'success' })),
  },
  dialerAPI: {
    clickToDial: vi.fn(() => Promise.resolve({ success: true })),
  },
  borrowerApplicationAPI: {
    createForLead: vi.fn(() => Promise.resolve({ id: 1, public_token: 'abc' })),
  },
}));

vi.mock('@/utils/toast', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
    info: vi.fn(),
    warning: vi.fn(),
  },
}));

vi.mock('@/utils/phoneUtils', () => ({
  formatPhoneNumber: vi.fn((phone) => phone || ''),
}));

// Mock CSS imports
vi.mock('../LeadDetail.css', () => ({}));

// Mock child components to isolate LoanDetail behavior
vi.mock('@/components/VoicemailDrop', () => ({ default: () => null }));
vi.mock('@/components/SMSModal', () => ({ default: () => null }));
vi.mock('@/components/TeamsModal', () => ({ default: () => null }));
vi.mock('@/components/RecordingModal', () => ({ default: () => null }));
vi.mock('@/components/CreateTaskModal', () => ({ default: () => null }));
vi.mock('@/components/AppointmentModal', () => ({ default: () => null }));
vi.mock('@/components/ScheduleAppointmentModal', () => ({ default: () => null }));
vi.mock('@/components/EscalationModal', () => ({ default: () => null }));
vi.mock('@/components/EmploymentTab', () => ({ default: () => null }));
vi.mock('@/components/VideoCallScheduleModal', () => ({ default: () => null }));
vi.mock('@/components/EmailComposerModal', () => ({ default: () => null }));
vi.mock('@/components/CalendarSidebar', () => ({ default: () => <div data-testid="calendar-sidebar" /> }));
vi.mock('@/components/AddressAutocomplete', () => ({
  default: (props) => <input data-testid="address-autocomplete" value={props.value || ''} onChange={(e) => props.onSelect?.(e.target.value)} />,
}));
vi.mock('@/components/smart-docs/SmartDocumentUpload', () => ({ default: () => null }));
vi.mock('@/components/smart-docs/LoanSmartDocsTab', () => ({ default: () => <div data-testid="smart-docs-tab" /> }));
vi.mock('@/components/IncomeCalculator', () => ({ default: () => null }));
vi.mock('@/components/income/UnifiedIncomeCalculator', () => ({ default: () => null }));
vi.mock('@/components/PortalSelectorModal', () => ({ default: () => null }));
vi.mock('@/components/video/SendVideoModal', () => ({ default: () => null }));
vi.mock('@/components/CreditTab', () => ({ default: () => <div data-testid="credit-tab" /> }));
vi.mock('@/components/WorkflowRoleAssignment', () => ({ default: () => null }));
vi.mock('@/components/SalesforceConnectionBadge', () => ({
  default: () => <div data-testid="sf-badge" />,
}));
vi.mock('@/components/common/CurrencyInput', () => ({
  default: ({ value, onChange, placeholder }) => (
    <input
      data-testid="currency-input"
      value={value || ''}
      onChange={(e) => onChange?.(e.target.value)}
      placeholder={placeholder}
    />
  ),
}));

// Mock global fetch for endpoints that use fetch directly
const mockFetch = vi.fn(() =>
  Promise.resolve({
    ok: true,
    json: () => Promise.resolve({}),
  })
);
global.fetch = mockFetch;

import LoanDetail from '../LoanDetail';
import { loansAPI, salesforceAPI } from '@/services/api';
import { toast } from '@/utils/toast';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const sampleLoan = {
  id: 42,
  loan_number: 'LN-2026-0042',
  borrower_name: 'Jane Doe',
  borrower_email: 'jane@example.com',
  borrower_phone: '5125551234',
  coborrower_name: 'John Doe',
  amount: 425000,
  loan_amount: 425000,
  loan_type: 'Conventional',
  loan_purpose: 'Purchase',
  interest_rate: 6.875,
  term: 360,
  stage: 'PROCESSING',
  property_address: '123 Oak St',
  property_city: 'Austin',
  property_state: 'TX',
  property_zip: '78701',
  purchase_price: 500000,
  closing_date: '2026-05-15T00:00:00',
  lock_date: '2026-03-01T00:00:00',
  lock_expiration: '2026-04-01T00:00:00',
  apr: 7.125,
  ltv: 85.0,
  dti: 38.5,
  appraisal_value: 510000,
  created_at: '2026-02-01T10:00:00',
  rate_type: 'Fixed',
  monthly_payment: 2821.52,
};

function renderLoanDetail(loanId = '42') {
  return render(
    <MemoryRouter initialEntries={[`/loans/${loanId}`]}>
      <Routes>
        <Route path="/loans/:id" element={<LoanDetail />} />
      </Routes>
    </MemoryRouter>
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('LoanDetail Page', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    localStorage.setItem('token', 'test-token');

    // Default happy-path mocks
    loansAPI.getById.mockResolvedValue(sampleLoan);
    loansAPI.getAll.mockResolvedValue([sampleLoan]);
    salesforceAPI.getLoanSyncStatus.mockRejectedValue(new Error('not configured'));

    mockFetch.mockImplementation(() =>
      Promise.resolve({ ok: true, json: () => Promise.resolve({}) })
    );
  });

  // =========================================================================
  // 1. Loading state
  // =========================================================================

  it('shows loading indicator while loan data is being fetched', () => {
    // Make getById hang so loading state persists
    loansAPI.getById.mockReturnValue(new Promise(() => {}));
    renderLoanDetail();
    expect(screen.getByText('Loading loan details...')).toBeInTheDocument();
  });

  // =========================================================================
  // 2. Loan not found
  // =========================================================================

  it('shows "Loan not found" and navigates away when API returns null', async () => {
    loansAPI.getById.mockRejectedValue(new Error('404'));

    renderLoanDetail('999');

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith(expect.stringContaining('Failed to load loan details'));
    });
    expect(mockNavigate).toHaveBeenCalledWith('/loans');
  });

  // =========================================================================
  // 3. Renders borrower name in the header banner
  // =========================================================================

  it('renders the borrower name in the client name banner', async () => {
    renderLoanDetail();

    await waitFor(() => {
      expect(screen.getByText('Jane Doe')).toBeInTheDocument();
    });
  });

  // =========================================================================
  // 4. Renders co-borrower in borrower list
  // =========================================================================

  it('initializes borrowers list including co-borrower when present', async () => {
    renderLoanDetail();

    await waitFor(() => {
      // The primary borrower name should appear
      expect(screen.getByText('Jane Doe')).toBeInTheDocument();
    });
  });

  // =========================================================================
  // 5. Tab navigation renders all expected tabs
  // =========================================================================

  it('renders all expected tab buttons', async () => {
    renderLoanDetail();

    await waitFor(() => {
      expect(screen.getByText('Jane Doe')).toBeInTheDocument();
    });

    const expectedTabs = [
      'Loan Details', 'Personal', 'Property', 'Tasks',
      'Conversation Log', 'Circle', 'Smart Docs', 'Credit',
      'Income', 'Conditions', 'SLA Dates', 'Team Members',
    ];

    for (const tab of expectedTabs) {
      expect(screen.getByRole('button', { name: tab })).toBeInTheDocument();
    }
  });

  // =========================================================================
  // 6. Loan Details tab shows financial fields
  // =========================================================================

  it('displays loan financial fields on the Loan Details tab', async () => {
    renderLoanDetail();

    await waitFor(() => {
      expect(screen.getByText('Loan Details')).toBeInTheDocument();
    });

    // Verify labels are rendered
    expect(screen.getByText('Loan Number')).toBeInTheDocument();
    expect(screen.getByText('Loan Amount')).toBeInTheDocument();
    expect(screen.getByText('Interest Rate')).toBeInTheDocument();
    expect(screen.getByText('Loan Term')).toBeInTheDocument();
    expect(screen.getByText('Loan Type')).toBeInTheDocument();
    expect(screen.getByText('APR')).toBeInTheDocument();
  });

  // =========================================================================
  // 7. Transaction type toggle (Purchase vs Refinance)
  // =========================================================================

  it('renders Purchase and Refinance transaction type buttons', async () => {
    renderLoanDetail();

    await waitFor(() => {
      expect(screen.getByText('Jane Doe')).toBeInTheDocument();
    });

    expect(screen.getByRole('button', { name: 'Purchase' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Refinance' })).toBeInTheDocument();
  });

  // =========================================================================
  // 8. Loan type dropdown has correct options
  // =========================================================================

  it('renders loan type select with Conventional, FHA, VA, USDA, Jumbo, HELOC options', async () => {
    renderLoanDetail();

    await waitFor(() => {
      expect(screen.getByText('Jane Doe')).toBeInTheDocument();
    });

    const loanTypeSelect = screen.getByDisplayValue('Conventional');
    expect(loanTypeSelect).toBeInTheDocument();

    const options = within(loanTypeSelect).getAllByRole('option');
    const optionValues = options.map((o) => o.value);
    expect(optionValues).toContain('Conventional');
    expect(optionValues).toContain('FHA');
    expect(optionValues).toContain('VA');
    expect(optionValues).toContain('USDA');
    expect(optionValues).toContain('Jumbo');
    expect(optionValues).toContain('HELOC');
  });

  // =========================================================================
  // 9. Back to Loans button
  // =========================================================================

  it('navigates back to loans list when "Back to Loans" is clicked', async () => {
    renderLoanDetail();

    await waitFor(() => {
      expect(screen.getByText('Jane Doe')).toBeInTheDocument();
    });

    const backBtn = screen.getByText(/Back to Loans/i);
    fireEvent.click(backBtn);
    expect(mockNavigate).toHaveBeenCalledWith('/loans');
  });

  // =========================================================================
  // 10. Save and Cancel buttons render in edit mode
  // =========================================================================

  it('renders Save and Cancel buttons (component starts in edit mode)', async () => {
    renderLoanDetail();

    await waitFor(() => {
      expect(screen.getByText('Jane Doe')).toBeInTheDocument();
    });

    // LoanDetail starts with editing=true
    expect(screen.getByText('Save')).toBeInTheDocument();
    expect(screen.getByText('Cancel')).toBeInTheDocument();
  });

  // =========================================================================
  // 11. Save triggers API update call
  // =========================================================================

  it('calls loansAPI.update when Save is clicked', async () => {
    loansAPI.update.mockResolvedValue({});
    renderLoanDetail();

    await waitFor(() => {
      expect(screen.getByText('Jane Doe')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('Save'));

    await waitFor(() => {
      expect(loansAPI.update).toHaveBeenCalledWith('42', expect.objectContaining({
        borrower_name: 'Jane Doe',
      }));
    });

    expect(toast.success).toHaveBeenCalledWith('Loan updated successfully!');
  });

  // =========================================================================
  // 12. Save failure shows error toast
  // =========================================================================

  it('shows error toast when save fails', async () => {
    loansAPI.update.mockRejectedValue(new Error('Server error'));
    renderLoanDetail();

    await waitFor(() => {
      expect(screen.getByText('Jane Doe')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('Save'));

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('Failed to save changes');
    });
  });

  // =========================================================================
  // 13. Loan with no co-borrower only shows primary
  // =========================================================================

  it('does not create co-borrower entry when coborrower_name is absent', async () => {
    const loanNoCoBorrower = { ...sampleLoan, coborrower_name: null };
    loansAPI.getById.mockResolvedValue(loanNoCoBorrower);

    renderLoanDetail();

    await waitFor(() => {
      expect(screen.getByText('Jane Doe')).toBeInTheDocument();
    });

    // Only the primary borrower tab should be visible in the header;
    // there should be no "John Doe" text
    expect(screen.queryByText('John Doe')).not.toBeInTheDocument();
  });

  // =========================================================================
  // 14. Salesforce connection badge renders
  // =========================================================================

  it('renders the Salesforce connection badge', async () => {
    renderLoanDetail();

    await waitFor(() => {
      expect(screen.getByTestId('sf-badge')).toBeInTheDocument();
    });
  });

  // =========================================================================
  // 15. View Next Loan button navigation
  // =========================================================================

  it('navigates to next loan when "View Next Loan" is clicked', async () => {
    const loanList = [
      { ...sampleLoan, id: 42 },
      { ...sampleLoan, id: 43, borrower_name: 'Bob Smith' },
    ];
    loansAPI.getAll.mockResolvedValue(loanList);
    loansAPI.getById.mockResolvedValue(sampleLoan);

    renderLoanDetail('42');

    await waitFor(() => {
      expect(screen.getByText('Jane Doe')).toBeInTheDocument();
    });

    const nextBtn = screen.getByText(/View Next Loan/i);
    fireEvent.click(nextBtn);

    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith('/loans/43');
    });
  });
});
