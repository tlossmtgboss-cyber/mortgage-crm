import React from 'react';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// ---------------------------------------------------------------------------
// Mocks — must be declared before component import
// ---------------------------------------------------------------------------

vi.mock('../SmartDocs.css', () => ({}));
vi.mock('../../components/AdminContracts', () => ({
  default: () => <div data-testid="admin-contracts">Admin Contracts</div>,
}));

// Mock PermissionContext
const mockPermissions = {
  userRole: 'admin',
  hasAnyPermission: vi.fn(() => true),
  isAdmin: true,
  isPlatformAdmin: false,
};
vi.mock('../../contexts/PermissionContext', () => ({
  usePermissions: () => mockPermissions,
}));

// Mock roleConfig
vi.mock('../../config/roleConfig', () => ({
  isMasterAdmin: vi.fn(() => false),
}));

// Mock react-router-dom
const mockNavigate = vi.fn();
vi.mock('react-router-dom', () => ({
  useNavigate: () => mockNavigate,
}));

// Mock smartDocsApi
const mockSmartDocsAPI = {
  getDashboardSummary: vi.fn(),
  getApplicantsPendingReview: vi.fn(),
  getApplicantsOutstandingDocs: vi.fn(),
  getQueue: vi.fn(),
  getQueueSummary: vi.fn(),
  sendReminder: vi.fn(),
};
vi.mock('../../services/smartDocsApi', () => ({
  smartDocsAPI: mockSmartDocsAPI,
}));

// Mock api module
vi.mock('../../services/api', () => ({
  API_BASE_URL: 'http://localhost:8000',
}));

// Mock toast
vi.mock('../../utils/toast', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
    info: vi.fn(),
    warning: vi.fn(),
  },
}));

// Mock global fetch
const mockFetch = vi.fn();
global.fetch = mockFetch;

import SmartDocs from '../SmartDocs';
import { toast } from '../../utils/toast';
import { isMasterAdmin } from '../../config/roleConfig';

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

/**
 * Build sample loan data matching the API shape.
 */
function makeLoan(overrides = {}) {
  return {
    id: 'loan-1',
    loan_number: 'LN-2026-001',
    borrower_name: 'John Smith',
    borrower_email: 'john@example.com',
    borrower_phone: '555-0100',
    loan_purpose: 'Purchase',
    amount: 350000,
    stage: 'PROCESSING',
    property_address: '123 Main St',
    closing_date: '2026-05-15',
    rate: 6.5,
    created_at: new Date(Date.now() - 2 * 86400000).toISOString(), // 2 days ago
    outstanding_docs_count: 3,
    overdue_docs_count: 1,
    pending_docs_count: 2,
    ...overrides,
  };
}

function makeFundedLoan(overrides = {}) {
  return makeLoan({
    id: 'loan-funded-1',
    loan_number: 'LN-2026-F01',
    stage: 'FUNDED',
    funded_at: '2026-02-28',
    ...overrides,
  });
}

/**
 * Set up localStorage with an auth token and user.
 */
function setupAuth() {
  localStorage.setItem('token', 'test-jwt-token');
  localStorage.setItem('user', JSON.stringify({ email: 'lo@company.com', name: 'Test LO' }));
}

/**
 * Default fetch that returns sample loans from the smart-docs endpoint.
 */
function setupDefaultFetch(loans = [makeLoan()]) {
  mockFetch.mockImplementation((url) => {
    if (typeof url === 'string' && url.includes('/api/v1/smart-docs/loans')) {
      return mockFetchResponse({ loans });
    }
    if (typeof url === 'string' && url.includes('/api/v1/loans')) {
      return mockFetchResponse(loans);
    }
    return mockFetchResponse({});
  });
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('SmartDocs Page', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    setupAuth();

    // Reset permissions to admin defaults
    mockPermissions.userRole = 'admin';
    mockPermissions.hasAnyPermission = vi.fn(() => true);
    mockPermissions.isAdmin = true;
    mockPermissions.isPlatformAdmin = false;

    // Default API mocks
    mockSmartDocsAPI.getDashboardSummary.mockResolvedValue({
      outstanding_requests: { applicants: 2, overdue: 1 },
      pending_review: { applicants: 1, documents: 3 },
    });
    mockSmartDocsAPI.getQueueSummary.mockResolvedValue({
      by_sla_status: { breached: 0, at_risk: 1, good: 5 },
    });
    mockSmartDocsAPI.getQueue.mockResolvedValue({
      queue: [],
      total: 0,
      summary: {},
    });
  });

  afterEach(() => {
    localStorage.clear();
  });

  // -------------------------------------------------------------------------
  // 1. Loading state
  // -------------------------------------------------------------------------
  it('shows loading spinner while data is being fetched', () => {
    // Never-resolving fetch to keep loading state
    mockFetch.mockImplementation(() => new Promise(() => {}));
    mockSmartDocsAPI.getQueueSummary.mockReturnValue(new Promise(() => {}));

    render(<SmartDocs />);

    expect(screen.getByText('Loading...')).toBeInTheDocument();
    expect(document.querySelector('.spinner')).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // 2. Empty document list
  // -------------------------------------------------------------------------
  it('shows empty state when no loans are returned', async () => {
    setupDefaultFetch([]);

    render(<SmartDocs />);

    await waitFor(() => {
      expect(screen.getByText('All documents collected!')).toBeInTheDocument();
    });
    expect(screen.getByText('No outstanding document requests')).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // 3. Document list rendering — Documents Owed tab
  // -------------------------------------------------------------------------
  it('renders loan rows in the Documents Owed tab', async () => {
    const loans = [
      makeLoan({ id: 'l1', borrower_name: 'Alice Buyer', loan_number: 'LN-001' }),
      makeLoan({ id: 'l2', borrower_name: 'Bob Seller', loan_number: 'LN-002', stage: 'UNDERWRITING' }),
    ];
    setupDefaultFetch(loans);

    render(<SmartDocs />);

    await waitFor(() => {
      expect(screen.getByText('Alice Buyer')).toBeInTheDocument();
    });
    expect(screen.getByText('Bob Seller')).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // 4. Summary cards reflect data counts
  // -------------------------------------------------------------------------
  it('renders summary cards with correct counts', async () => {
    const activeLoan = makeLoan();
    const funded = makeFundedLoan();
    setupDefaultFetch([activeLoan, funded]);

    render(<SmartDocs />);

    await waitFor(() => {
      // Documents Owed count (active pipeline loans)
      const owedCard = screen.getByText('Documents Owed').closest('.summary-card');
      expect(within(owedCard).getByText('1')).toBeInTheDocument();
    });

    // Completed count
    const completedCard = screen.getByText('Completed').closest('.summary-card');
    expect(within(completedCard).getByText('1')).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // 5. Tab switching
  // -------------------------------------------------------------------------
  it('switches between tabs when clicked', async () => {
    setupDefaultFetch([makeLoan()]);

    render(<SmartDocs />);

    await waitFor(() => {
      expect(screen.queryByText('Loading...')).not.toBeInTheDocument();
    });

    // Click Documents Uploaded tab
    fireEvent.click(screen.getByRole('button', { name: /Documents Uploaded/i }));

    // The empty state for "uploaded" tab should appear (no uploaded docs in test data)
    await waitFor(() => {
      expect(screen.getByText('All caught up!')).toBeInTheDocument();
    });

    // Click Completed tab
    fireEvent.click(screen.getByRole('button', { name: /Completed/i }));
    await waitFor(() => {
      expect(screen.getByText(/No completed loans yet|Funded loans will appear here/)).toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // 6. Search filtering
  // -------------------------------------------------------------------------
  it('filters the list by search query', async () => {
    const loans = [
      makeLoan({ id: 'l1', borrower_name: 'Alice Buyer', loan_number: 'LN-001' }),
      makeLoan({ id: 'l2', borrower_name: 'Bob Seller', loan_number: 'LN-002' }),
    ];
    setupDefaultFetch(loans);

    render(<SmartDocs />);

    await waitFor(() => {
      expect(screen.getByText('Alice Buyer')).toBeInTheDocument();
    });

    // Type search query
    const searchInput = screen.getByPlaceholderText('Search by borrower or loan...');
    fireEvent.change(searchInput, { target: { value: 'Alice' } });

    // Alice should remain, Bob should be filtered out
    expect(screen.getByText('Alice Buyer')).toBeInTheDocument();
    expect(screen.queryByText('Bob Seller')).not.toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // 7. Search clear button
  // -------------------------------------------------------------------------
  it('clears search query when clear button is clicked', async () => {
    const loans = [
      makeLoan({ id: 'l1', borrower_name: 'Alice Buyer' }),
      makeLoan({ id: 'l2', borrower_name: 'Bob Seller' }),
    ];
    setupDefaultFetch(loans);

    render(<SmartDocs />);

    await waitFor(() => {
      expect(screen.getByText('Alice Buyer')).toBeInTheDocument();
    });

    const searchInput = screen.getByPlaceholderText('Search by borrower or loan...');
    fireEvent.change(searchInput, { target: { value: 'Alice' } });
    expect(screen.queryByText('Bob Seller')).not.toBeInTheDocument();

    // Click the clear button
    const clearBtn = screen.getByText('\u00d7', { selector: '.search-clear' });
    fireEvent.click(clearBtn);

    expect(screen.getByText('Bob Seller')).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // 8. Navigation on row click
  // -------------------------------------------------------------------------
  it('navigates to client detail on row click', async () => {
    setupDefaultFetch([makeLoan({ id: 'loan-42' })]);

    render(<SmartDocs />);

    await waitFor(() => {
      expect(screen.getByText('John Smith')).toBeInTheDocument();
    });

    const row = screen.getByText('John Smith').closest('tr');
    fireEvent.click(row);

    expect(mockNavigate).toHaveBeenCalledWith('/smart-docs/client/loan-42');
  });

  // -------------------------------------------------------------------------
  // 9. Duplicate detection banner
  // -------------------------------------------------------------------------
  it('shows duplicate warning banner when duplicate emails found', async () => {
    const loans = [
      makeLoan({ id: 'l1', borrower_name: 'Alice Buyer', borrower_email: 'alice@test.com', loan_number: 'LN-001' }),
      makeLoan({ id: 'l2', borrower_name: 'Alice Buyer', borrower_email: 'alice@test.com', loan_number: 'LN-002' }),
    ];
    setupDefaultFetch(loans);

    render(<SmartDocs />);

    await waitFor(() => {
      expect(screen.getByText(/potential duplicate/i)).toBeInTheDocument();
    });

    expect(screen.getByText('Create Merge Tasks')).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // 10. Access denied for unauthorized users
  // -------------------------------------------------------------------------
  it('shows Access Denied for users without document permissions', async () => {
    mockPermissions.isAdmin = false;
    mockPermissions.userRole = 'viewer';
    mockPermissions.hasAnyPermission = vi.fn(() => false);

    setupDefaultFetch([]);

    render(<SmartDocs />);

    expect(screen.getByText('Access Denied')).toBeInTheDocument();
    expect(screen.getByText("You don't have permission to access Smart Docs.")).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // 11. Platform admin sees Admin Contracts
  // -------------------------------------------------------------------------
  it('renders AdminContracts for platform admins', async () => {
    mockPermissions.isPlatformAdmin = true;

    render(<SmartDocs />);

    expect(screen.getByTestId('admin-contracts')).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // 12. Stage badges display correctly
  // -------------------------------------------------------------------------
  it('renders stage badges on loan rows', async () => {
    setupDefaultFetch([makeLoan({ stage: 'UNDERWRITING' })]);

    render(<SmartDocs />);

    await waitFor(() => {
      expect(screen.getByText('UNDERWRITING')).toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // 13. SLA status indicators
  // -------------------------------------------------------------------------
  it('shows correct SLA status based on age of loan', async () => {
    // Loan created 7 days ago => overdue (> 5 days)
    const oldLoan = makeLoan({
      id: 'old-loan',
      borrower_name: 'Slow Borrower',
      created_at: new Date(Date.now() - 7 * 86400000).toISOString(),
    });
    setupDefaultFetch([oldLoan]);

    render(<SmartDocs />);

    await waitFor(() => {
      expect(screen.getByText('OVERDUE')).toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // 14. Completed tab renders funded loans
  // -------------------------------------------------------------------------
  it('renders funded loans in the Completed tab', async () => {
    const funded = makeFundedLoan({ borrower_name: 'Happy Homeowner', loan_amount: 500000 });
    setupDefaultFetch([funded]);

    render(<SmartDocs />);

    // Wait for loading to finish
    await waitFor(() => {
      expect(screen.queryByText('Loading...')).not.toBeInTheDocument();
    });

    // Switch to completed tab
    fireEvent.click(screen.getByRole('button', { name: /Completed/i }));

    await waitFor(() => {
      expect(screen.getByText('Happy Homeowner')).toBeInTheDocument();
    });
    expect(screen.getByText('Completed', { selector: '.completed-badge' })).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // 15. Fetch error handling — graceful degradation
  // -------------------------------------------------------------------------
  it('shows empty state gracefully when API returns error', async () => {
    mockFetch.mockImplementation(() => mockFetchResponse({ detail: 'Server error' }, 500));

    render(<SmartDocs />);

    await waitFor(() => {
      expect(screen.queryByText('Loading...')).not.toBeInTheDocument();
    });

    // Should show empty state, not crash
    expect(screen.getByText('All documents collected!')).toBeInTheDocument();
  });
});
