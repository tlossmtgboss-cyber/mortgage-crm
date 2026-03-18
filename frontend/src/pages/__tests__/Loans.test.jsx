import React from 'react';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

// ---------------------------------------------------------------------------
// Mocks — must come before component import
// ---------------------------------------------------------------------------

const mockNavigate = vi.fn();
const mockSearchParams = new URLSearchParams();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return {
    ...actual,
    useNavigate: () => mockNavigate,
    useSearchParams: () => [mockSearchParams],
  };
});

vi.mock('@/services/api', () => ({
  loansAPI: {
    getAll: vi.fn(() => Promise.resolve([])),
    create: vi.fn(() => Promise.resolve({})),
    update: vi.fn(() => Promise.resolve({})),
    delete: vi.fn(() => Promise.resolve()),
    bulkDelete: vi.fn(() => Promise.resolve({ deleted_count: 0, errors: [] })),
  },
  salesforceAPI: {
    syncAllLoans: vi.fn(() => Promise.resolve({ linked: 0, created: 0, updated: 0 })),
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

vi.mock('@/contexts/PermissionContext', () => ({
  usePermissions: () => ({
    userRole: 'admin',
    hasAnyPermission: () => true,
    isAdmin: true,
  }),
}));

vi.mock('@/components/CalendarSidebar', () => ({
  default: () => <div data-testid="calendar-sidebar" />,
}));

vi.mock('@/components/PermissionGate', () => ({
  default: ({ children }) => <>{children}</>,
}));

// Mock CSS imports
vi.mock('../Loans.css', () => ({}));

import Loans from '../Loans';
import { loansAPI } from '@/services/api';
import { toast } from '@/utils/toast';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeLoan(overrides = {}) {
  return {
    id: 1,
    loan_number: 'LN-2026-0001',
    borrower_name: 'Jane Doe',
    borrower_email: 'jane@example.com',
    borrower_phone: '5125551234',
    amount: 425000,
    stage: 'PROCESSING',
    property_address: '123 Oak St, Austin TX',
    loan_officer: 'Sarah Johnson',
    production_assistant: 'Mike Wilson',
    days_in_process: 12,
    created_at: '2026-03-01T10:00:00',
    rate_locked: false,
    lock_guidance: null,
    lock_confidence: null,
    ...overrides,
  };
}

// Each loan uses a unique borrower_email to avoid the duplicate-detection banner
// polluting unrelated tests.
const sampleLoans = [
  makeLoan({ id: 1, borrower_name: 'Jane Doe', borrower_email: 'jane@example.com', stage: 'PROCESSING', amount: 425000 }),
  makeLoan({ id: 2, borrower_name: 'Bob Smith', borrower_email: 'bob@example.com', stage: 'APPROVED', amount: 380000, property_address: '456 Pine Ave, Dallas TX', loan_officer: 'Mike Chen' }),
  makeLoan({ id: 3, borrower_name: 'Alice Johnson', borrower_email: 'alice@example.com', stage: 'CLEAR_TO_CLOSE', amount: 520000, property_address: '789 Elm Dr, Houston TX', loan_officer: 'Emily Davis' }),
  makeLoan({ id: 4, borrower_name: 'Carlos Garcia', borrower_email: 'carlos@example.com', stage: 'APPLICATION', amount: 295000 }),
  makeLoan({ id: 5, borrower_name: 'Tom Wilson', borrower_email: 'tom@example.com', stage: 'FUNDED', amount: 615000 }),
  makeLoan({ id: 6, borrower_name: 'Lisa Brown', borrower_email: 'lisa@example.com', stage: 'CANCELLED', amount: 340000 }),
  makeLoan({ id: 7, borrower_name: 'Mark Stevens', borrower_email: 'mark@example.com', stage: 'SUSPENDED', amount: 395000 }),
];

function renderLoans() {
  return render(
    <MemoryRouter>
      <Loans />
    </MemoryRouter>
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('Loans Page', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    loansAPI.getAll.mockResolvedValue(sampleLoans);
  });

  // =========================================================================
  // 1. Loading state
  // =========================================================================

  it('shows loading indicator while loans are being fetched', () => {
    loansAPI.getAll.mockReturnValue(new Promise(() => {})); // hang forever
    renderLoans();
    expect(screen.getByText('Loading loans...')).toBeInTheDocument();
  });

  // =========================================================================
  // 2. Renders Active Loans title and count
  // =========================================================================

  it('renders the "Active Loans" heading and correct active loan count', async () => {
    renderLoans();

    await waitFor(() => {
      expect(screen.getByText('Active Loans')).toBeInTheDocument();
    });

    // Active loans exclude FUNDED, CANCELLED, DENIED, DEAD, etc.
    // sampleLoans: PROCESSING, APPROVED, CLEAR_TO_CLOSE, APPLICATION, FUNDED, CANCELLED, SUSPENDED
    // Active = 5 (PROCESSING, APPROVED, CLEAR_TO_CLOSE, APPLICATION, SUSPENDED)
    expect(screen.getByText('5 active loans')).toBeInTheDocument();
  });

  // =========================================================================
  // 3. Filter tabs render correctly
  // =========================================================================

  it('renders all filter tabs', async () => {
    renderLoans();

    await waitFor(() => {
      expect(screen.getByText('Active Loans')).toBeInTheDocument();
    });

    const expectedFilters = [
      'All', 'Application', 'Disclosed', 'In Processing',
      'In Underwriting', 'Approved', 'Clear to Close', 'Suspended', 'Inactive',
    ];

    for (const filter of expectedFilters) {
      expect(screen.getByRole('button', { name: filter })).toBeInTheDocument();
    }
  });

  // =========================================================================
  // 4. Default "All" filter excludes funded/terminal loans
  // =========================================================================

  it('excludes funded and terminal-stage loans from the active table rows', async () => {
    renderLoans();

    await waitFor(() => {
      expect(screen.getByText('Active Loans')).toBeInTheDocument();
    });

    // The visible table should only contain active-stage rows.
    // Note: there is also a hidden legacy grid that renders ALL loan names,
    // so we check the visible table specifically.
    const table = screen.getByRole('table');
    const tableRows = within(table).getAllByRole('row');
    // Header row + 5 active data rows (PROCESSING, APPROVED, CLEAR_TO_CLOSE, APPLICATION, SUSPENDED)
    expect(tableRows.length).toBe(6); // 1 header + 5 data

    // FUNDED and CANCELLED should not appear in the table
    expect(within(table).queryByText('Tom Wilson')).not.toBeInTheDocument();
    expect(within(table).queryByText('Lisa Brown')).not.toBeInTheDocument();

    // Active loans should appear in the table
    expect(within(table).getByText('Jane Doe')).toBeInTheDocument();
    expect(within(table).getByText('Bob Smith')).toBeInTheDocument();
    expect(within(table).getByText('Alice Johnson')).toBeInTheDocument();
    expect(within(table).getByText('Carlos Garcia')).toBeInTheDocument();
    expect(within(table).getByText('Mark Stevens')).toBeInTheDocument();
  });

  // =========================================================================
  // 5. Filtering by stage tab
  // =========================================================================

  it('filters loans by stage when a filter tab is clicked', async () => {
    renderLoans();

    await waitFor(() => {
      expect(screen.getByText('Jane Doe')).toBeInTheDocument();
    });

    // Click "Approved" filter
    fireEvent.click(screen.getByRole('button', { name: 'Approved' }));

    await waitFor(() => {
      // Bob Smith is APPROVED
      expect(screen.getByText('Bob Smith')).toBeInTheDocument();
    });

    // Jane Doe (PROCESSING) should be hidden under Approved filter
    expect(screen.queryByText('Jane Doe')).not.toBeInTheDocument();
  });

  // =========================================================================
  // 6. Suspended filter
  // =========================================================================

  it('shows only suspended loans when Suspended filter is selected', async () => {
    renderLoans();

    await waitFor(() => {
      expect(screen.getByText('Active Loans')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: 'Suspended' }));

    await waitFor(() => {
      expect(screen.getByText('Mark Stevens')).toBeInTheDocument();
    });

    // Other active loans should not appear
    expect(screen.queryByText('Jane Doe')).not.toBeInTheDocument();
    expect(screen.queryByText('Bob Smith')).not.toBeInTheDocument();
  });

  // =========================================================================
  // 7. Search filters by borrower name
  // =========================================================================

  it('filters loans by search query matching borrower name', async () => {
    renderLoans();

    await waitFor(() => {
      expect(screen.getByText('Jane Doe')).toBeInTheDocument();
    });

    const searchInput = screen.getByPlaceholderText(/Search loans by borrower/i);
    fireEvent.change(searchInput, { target: { value: 'Alice' } });

    // Only Alice Johnson should remain
    expect(screen.getByText('Alice Johnson')).toBeInTheDocument();
    expect(screen.queryByText('Jane Doe')).not.toBeInTheDocument();
    expect(screen.queryByText('Bob Smith')).not.toBeInTheDocument();
  });

  // =========================================================================
  // 8. Search clear button resets results
  // =========================================================================

  it('clears search and shows all loans when clear button is clicked', async () => {
    renderLoans();

    await waitFor(() => {
      expect(screen.getByText('Jane Doe')).toBeInTheDocument();
    });

    const searchInput = screen.getByPlaceholderText(/Search loans by borrower/i);
    fireEvent.change(searchInput, { target: { value: 'Alice' } });

    expect(screen.queryByText('Jane Doe')).not.toBeInTheDocument();

    // Click the clear button
    const clearBtn = screen.getByText('\u00d7'); // multiplication sign ×
    fireEvent.click(clearBtn);

    expect(screen.getByText('Jane Doe')).toBeInTheDocument();
  });

  // =========================================================================
  // 9. Loan amount formatting
  // =========================================================================

  it('formats loan amounts with dollar sign and thousands separators', async () => {
    renderLoans();

    await waitFor(() => {
      expect(screen.getByText('Jane Doe')).toBeInTheDocument();
    });

    // $425,000 for Jane Doe
    expect(screen.getByText('$425,000')).toBeInTheDocument();
    // $380,000 for Bob Smith
    expect(screen.getByText('$380,000')).toBeInTheDocument();
  });

  // =========================================================================
  // 10. Table column headers
  // =========================================================================

  it('renders all expected table column headers', async () => {
    renderLoans();

    await waitFor(() => {
      expect(screen.getByText('Active Loans')).toBeInTheDocument();
    });

    const headers = ['Borrower', 'Loan Amount', 'Rate Lock', 'Property Address', 'Status', 'Days in Process', 'Loan Officer', 'Production Assistant'];
    for (const header of headers) {
      expect(screen.getByText(header)).toBeInTheDocument();
    }
  });

  // =========================================================================
  // 11. Clicking a loan row navigates to loan detail
  // =========================================================================

  it('navigates to loan detail page when a row is clicked', async () => {
    renderLoans();

    await waitFor(() => {
      expect(screen.getByText('Jane Doe')).toBeInTheDocument();
    });

    // Click the row containing Jane Doe
    const janeRow = screen.getByText('Jane Doe').closest('tr');
    fireEvent.click(janeRow);

    expect(mockNavigate).toHaveBeenCalledWith('/loans/1');
  });

  // =========================================================================
  // 12. Empty state when no loans match filter
  // =========================================================================

  it('shows empty state when no loans match the current filter', async () => {
    renderLoans();

    await waitFor(() => {
      expect(screen.getByText('Active Loans')).toBeInTheDocument();
    });

    // Click "Disclosed" filter — no loans have this stage
    fireEvent.click(screen.getByRole('button', { name: 'Disclosed' }));

    expect(screen.getByText('No loans found')).toBeInTheDocument();
    expect(screen.getByText('Try adjusting your filters or add a new loan')).toBeInTheDocument();
  });

  // =========================================================================
  // 13. Empty pipeline (API returns empty array)
  // =========================================================================

  it('renders empty state when API returns an empty array', async () => {
    loansAPI.getAll.mockResolvedValue([]);

    renderLoans();

    await waitFor(() => {
      expect(screen.getByText('0 active loans')).toBeInTheDocument();
    });

    expect(screen.getByText('No loans found')).toBeInTheDocument();
  });

  // =========================================================================
  // 14. API error falls back to empty loans
  // =========================================================================

  it('falls back to empty loans array when API call fails', async () => {
    loansAPI.getAll.mockRejectedValue(new Error('Network error'));

    renderLoans();

    await waitFor(() => {
      expect(screen.getByText('0 active loans')).toBeInTheDocument();
    });
  });

  // =========================================================================
  // 15. Duplicate detection shows warning banner
  // =========================================================================

  it('shows duplicate warning banner when loans share the same borrower email', async () => {
    const duplicateLoans = [
      makeLoan({ id: 1, borrower_name: 'Jane Doe', borrower_email: 'jane@example.com', stage: 'PROCESSING' }),
      makeLoan({ id: 2, borrower_name: 'Jane Doe', borrower_email: 'jane@example.com', stage: 'APPLICATION', loan_number: 'LN-2026-0002' }),
    ];
    loansAPI.getAll.mockResolvedValue(duplicateLoans);

    renderLoans();

    await waitFor(() => {
      expect(screen.getByText(/potential duplicate/i)).toBeInTheDocument();
    });

    // Duplicate badge should appear on the rows
    const badges = screen.getAllByText('DUPLICATE');
    expect(badges.length).toBeGreaterThanOrEqual(1);
  });

  // =========================================================================
  // 16. Stage display mapping (API enum to human-readable)
  // =========================================================================

  it('maps API stage enums to human-readable display names', async () => {
    const stageLoans = [
      makeLoan({ id: 1, borrower_name: 'A', stage: 'PROCESSING' }),
      makeLoan({ id: 2, borrower_name: 'B', stage: 'CLEAR_TO_CLOSE' }),
      makeLoan({ id: 3, borrower_name: 'C', stage: 'CONDITIONAL_APPROVAL' }),
    ];
    loansAPI.getAll.mockResolvedValue(stageLoans);

    renderLoans();

    await waitFor(() => {
      expect(screen.getByText('Processing')).toBeInTheDocument();
    });

    expect(screen.getByText('Clear to Close')).toBeInTheDocument();
    expect(screen.getByText('Conditional Approval')).toBeInTheDocument();
  });

  // =========================================================================
  // 17. Rate lock badge — floating vs locked
  // =========================================================================

  it('shows "Floating" badge for unlocked loans and "Locked" for locked loans', async () => {
    const lockLoans = [
      makeLoan({ id: 1, borrower_name: 'Floating Fred', stage: 'PROCESSING', rate_locked: false, lock_guidance: null }),
      makeLoan({ id: 2, borrower_name: 'Locked Lucy', stage: 'APPROVED', rate_locked: true }),
    ];
    loansAPI.getAll.mockResolvedValue(lockLoans);

    renderLoans();

    await waitFor(() => {
      expect(screen.getByText('Floating Fred')).toBeInTheDocument();
    });

    expect(screen.getByText('Floating')).toBeInTheDocument();
    expect(screen.getByText('Locked')).toBeInTheDocument();
  });

  // =========================================================================
  // 18. Loan officer and production assistant display
  // =========================================================================

  it('shows loan officer name and production assistant or fallbacks', async () => {
    const loans = [
      makeLoan({ id: 1, borrower_name: 'A', stage: 'PROCESSING', loan_officer: 'Sarah J.', production_assistant: 'PA Mike' }),
      makeLoan({ id: 2, borrower_name: 'B', stage: 'APPLICATION', loan_officer: null, production_assistant: null }),
    ];
    loansAPI.getAll.mockResolvedValue(loans);

    renderLoans();

    await waitFor(() => {
      expect(screen.getByText('Sarah J.')).toBeInTheDocument();
    });

    expect(screen.getByText('PA Mike')).toBeInTheDocument();
    // Unassigned fallback for null LO
    expect(screen.getByText('Unassigned')).toBeInTheDocument();
  });

  // =========================================================================
  // 19. Search by property address
  // =========================================================================

  it('filters loans when searching by property address', async () => {
    renderLoans();

    await waitFor(() => {
      expect(screen.getByText('Jane Doe')).toBeInTheDocument();
    });

    const searchInput = screen.getByPlaceholderText(/Search loans by borrower/i);
    fireEvent.change(searchInput, { target: { value: 'Elm Dr' } });

    // Alice Johnson at 789 Elm Dr should remain
    expect(screen.getByText('Alice Johnson')).toBeInTheDocument();
    expect(screen.queryByText('Jane Doe')).not.toBeInTheDocument();
  });

  // =========================================================================
  // 20. Inactive filter shows terminal-stage loans
  // =========================================================================

  it('shows cancelled and denied loans under the Inactive filter', async () => {
    const loansWithInactive = [
      makeLoan({ id: 1, borrower_name: 'Active Annie', stage: 'PROCESSING' }),
      makeLoan({ id: 2, borrower_name: 'Cancelled Carl', stage: 'CANCELLED' }),
      makeLoan({ id: 3, borrower_name: 'Denied Dave', stage: 'DENIED' }),
    ];
    loansAPI.getAll.mockResolvedValue(loansWithInactive);

    renderLoans();

    await waitFor(() => {
      expect(screen.getByText('Active Annie')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: 'Inactive' }));

    await waitFor(() => {
      expect(screen.getByText('Cancelled Carl')).toBeInTheDocument();
    });
    expect(screen.getByText('Denied Dave')).toBeInTheDocument();
    expect(screen.queryByText('Active Annie')).not.toBeInTheDocument();
  });
});
