import React from 'react';
import { render, screen, waitFor, within, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

// Mock CSS imports
vi.mock('../Leads.css', () => ({}));

// Mock useQueries (React Query hook)
const mockRefetch = vi.fn();
vi.mock('../../hooks/useQueries', () => ({
  useLeads: vi.fn(() => ({
    data: [],
    isLoading: false,
    refetch: mockRefetch,
  })),
  LIST_PAGE_SIZE: 500,
}));

import { useLeads } from '../../hooks/useQueries';

// Mock API services
vi.mock('../../services/api', () => ({
  leadsAPI: {
    getAll: vi.fn(() => Promise.resolve([])),
    getById: vi.fn(() => Promise.resolve({})),
    create: vi.fn(() => Promise.resolve({ id: 999 })),
    update: vi.fn(() => Promise.resolve({})),
    delete: vi.fn(() => Promise.resolve()),
    bulkDelete: vi.fn(() => Promise.resolve({ deleted_count: 0, message: 'Deleted' })),
    bulkUpdateStatus: vi.fn(() => Promise.resolve({ updated_count: 0 })),
    search: vi.fn(() => Promise.resolve({ leads: [] })),
  },
  loansAPI: {
    getAll: vi.fn(() => Promise.resolve([])),
    create: vi.fn(() => Promise.resolve({ id: 100 })),
    update: vi.fn(() => Promise.resolve({})),
  },
  API_BASE_URL: 'http://localhost:8000',
}));

import { leadsAPI, loansAPI } from '../../services/api';

// Mock PermissionContext
vi.mock('../../contexts/PermissionContext', () => ({
  usePermissions: () => ({
    canPerformAction: vi.fn(() => true),
    isReadOnlyMode: false,
    hasAnyPermission: vi.fn(() => true),
    userRole: 'admin',
    isAdmin: true,
  }),
}));

// Mock toast
vi.mock('../../utils/toast', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
    info: vi.fn(),
  },
}));

// Mock auth
vi.mock('../../utils/auth', () => ({
  getCurrentUser: () => ({ id: 1, email: 'admin@perenniaai.com' }),
}));

// Mock phoneUtils
vi.mock('../../utils/phoneUtils', () => ({
  formatPhoneNumber: (v) => v,
}));

// Mock sub-components that aren't under test
vi.mock('../../components/ClickableContact', () => ({
  ClickableEmail: ({ email }) => <span data-testid="email">{email}</span>,
  ClickablePhone: ({ phone }) => <span data-testid="phone">{phone}</span>,
}));

vi.mock('../../components/SMSModal', () => ({
  default: () => null,
}));

vi.mock('../../components/DispositionNoteModal', () => {
  const comp = () => null;
  comp.REQUIRES_NOTE = ['Withdrawn', 'Does Not Qualify', 'Dead', 'Denied', 'Cancelled'];
  return { default: comp };
});

vi.mock('../../components/CalendarSidebar', () => ({
  default: () => null,
}));

vi.mock('../../components/PermissionGate', () => ({
  default: ({ children }) => <>{children}</>,
}));

vi.mock('../../components/AddressAutocomplete', () => ({
  default: (props) => (
    <input
      data-testid="address-autocomplete"
      value={props.value || ''}
      onChange={(e) => props.onChange(e.target.value)}
      placeholder={props.placeholder}
    />
  ),
}));

import Leads from '../Leads';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function renderLeads() {
  return render(
    <MemoryRouter>
      <Leads />
    </MemoryRouter>
  );
}

const sampleLeads = [
  {
    id: 1,
    name: 'Sarah Johnson',
    first_name: 'Sarah',
    last_name: 'Johnson',
    email: 'sarah@example.com',
    phone: '(555) 123-4567',
    stage: 'New',
    source: 'Website',
    credit_score: 720,
    loan_amount: 425000,
    created_at: new Date().toISOString(),
  },
  {
    id: 2,
    name: 'Michael Chen',
    first_name: 'Michael',
    last_name: 'Chen',
    email: 'mchen@example.com',
    phone: '(555) 234-5678',
    stage: 'Prospect',
    source: 'Referral',
    credit_score: 695,
    loan_amount: 380000,
    created_at: new Date(Date.now() - 5 * 24 * 60 * 60 * 1000).toISOString(),
  },
  {
    id: 3,
    name: 'Emily Rodriguez',
    first_name: 'Emily',
    last_name: 'Rodriguez',
    email: 'emily@example.com',
    phone: '(555) 345-6789',
    stage: 'Pre-Qualified',
    source: 'Zillow',
    credit_score: 750,
    loan_amount: 295000,
    created_at: new Date(Date.now() - 10 * 24 * 60 * 60 * 1000).toISOString(),
  },
  {
    id: 4,
    name: 'David Martinez',
    first_name: 'David',
    last_name: 'Martinez',
    email: 'david@example.com',
    phone: '(555) 456-7890',
    stage: 'Attempted Contact',
    source: 'Facebook',
    credit_score: 680,
    loan_amount: 550000,
    created_at: new Date(Date.now() - 3 * 24 * 60 * 60 * 1000).toISOString(),
  },
];

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('Leads', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    // Default: no leads
    useLeads.mockReturnValue({
      data: [],
      isLoading: false,
      refetch: mockRefetch,
    });
  });

  // =========================================================================
  // 1. Rendering
  // =========================================================================

  describe('Rendering', () => {
    it('renders the page heading', () => {
      renderLeads();
      expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Leads');
    });

    it('renders the Add Lead button', () => {
      renderLeads();
      expect(screen.getByText('+ Add Lead')).toBeInTheDocument();
    });

    it('shows total lead count in header', () => {
      useLeads.mockReturnValue({
        data: sampleLeads,
        isLoading: false,
        refetch: mockRefetch,
      });
      renderLeads();
      expect(screen.getByText('4 total leads')).toBeInTheDocument();
    });

    it('renders filter tabs (All, New, Attempted Contact, etc.)', () => {
      renderLeads();
      expect(screen.getByText(/^All/)).toBeInTheDocument();
      expect(screen.getByText(/^New/)).toBeInTheDocument();
      expect(screen.getByText(/^Attempted Contact/)).toBeInTheDocument();
      expect(screen.getByText(/^Prospect/)).toBeInTheDocument();
      expect(screen.getByText(/^Pre-Qualified/)).toBeInTheDocument();
      expect(screen.getByText(/^Pre-Approved/)).toBeInTheDocument();
    });

    it('renders search bar with placeholder text', () => {
      renderLeads();
      expect(screen.getByPlaceholderText(/Search leads/i)).toBeInTheDocument();
    });

    it('shows loading state when data is loading', () => {
      useLeads.mockReturnValue({
        data: null,
        isLoading: true,
        refetch: mockRefetch,
      });
      renderLeads();
      expect(screen.getByText('Loading leads...')).toBeInTheDocument();
    });
  });

  // =========================================================================
  // 2. Table Display
  // =========================================================================

  describe('Table Display', () => {
    it('renders lead names in the table', () => {
      useLeads.mockReturnValue({
        data: sampleLeads,
        isLoading: false,
        refetch: mockRefetch,
      });
      renderLeads();
      expect(screen.getByText('Sarah Johnson')).toBeInTheDocument();
      expect(screen.getByText('Michael Chen')).toBeInTheDocument();
      expect(screen.getByText('Emily Rodriguez')).toBeInTheDocument();
    });

    it('renders table headers (Name, Phone, Email, Status, etc.)', () => {
      useLeads.mockReturnValue({
        data: sampleLeads,
        isLoading: false,
        refetch: mockRefetch,
      });
      renderLeads();
      const table = screen.getByRole('table');
      expect(within(table).getByText('Name')).toBeInTheDocument();
      expect(within(table).getByText('Phone')).toBeInTheDocument();
      expect(within(table).getByText('Email')).toBeInTheDocument();
      expect(within(table).getByText('Status')).toBeInTheDocument();
      expect(within(table).getByText('Actions')).toBeInTheDocument();
    });

    it('displays status badges for each lead', () => {
      useLeads.mockReturnValue({
        data: sampleLeads,
        isLoading: false,
        refetch: mockRefetch,
      });
      renderLeads();
      // Stage values displayed as badge text
      const newBadges = screen.getAllByText('New');
      expect(newBadges.length).toBeGreaterThanOrEqual(1);
      expect(screen.getByText('Prospect')).toBeInTheDocument();
    });

    it('shows empty state when no leads exist', () => {
      useLeads.mockReturnValue({
        data: [],
        isLoading: false,
        refetch: mockRefetch,
      });
      renderLeads();
      expect(screen.getByText('No leads yet')).toBeInTheDocument();
      expect(screen.getByText('Get started by adding your first lead')).toBeInTheDocument();
    });

    it('shows "No leads found" when filter matches nothing', () => {
      useLeads.mockReturnValue({
        data: sampleLeads,
        isLoading: false,
        refetch: mockRefetch,
      });
      renderLeads();
      // Click on "Pre-Approved" tab which has 0 leads
      const preApprovedTab = screen.getByText(/^Pre-Approved/);
      preApprovedTab.click();
      expect(screen.getByText('No leads found')).toBeInTheDocument();
    });
  });

  // =========================================================================
  // 3. Filtering
  // =========================================================================

  describe('Filtering', () => {
    beforeEach(() => {
      useLeads.mockReturnValue({
        data: sampleLeads,
        isLoading: false,
        refetch: mockRefetch,
      });
    });

    it('defaults to All filter showing all leads', () => {
      renderLeads();
      expect(screen.getByText('Sarah Johnson')).toBeInTheDocument();
      expect(screen.getByText('Michael Chen')).toBeInTheDocument();
      expect(screen.getByText('Emily Rodriguez')).toBeInTheDocument();
      expect(screen.getByText('David Martinez')).toBeInTheDocument();
    });

    it('filters to New leads when New tab is clicked', async () => {
      renderLeads();
      const newTab = screen.getByText(/^New/);
      await userEvent.click(newTab);

      expect(screen.getByText('Sarah Johnson')).toBeInTheDocument();
      expect(screen.queryByText('Michael Chen')).not.toBeInTheDocument();
      expect(screen.queryByText('Emily Rodriguez')).not.toBeInTheDocument();
    });

    it('filters by Prospect stage', async () => {
      renderLeads();
      const prospectTab = screen.getByText(/^Prospect/);
      await userEvent.click(prospectTab);

      expect(screen.getByText('Michael Chen')).toBeInTheDocument();
      expect(screen.queryByText('Sarah Johnson')).not.toBeInTheDocument();
    });

    it('shows filter counts in tabs', () => {
      renderLeads();
      // The "All" tab should show count of 4
      const allTab = screen.getByText(/^All/);
      expect(allTab.closest('button')).toHaveTextContent('All');
      // Check the count span within the button
      const allButton = allTab.closest('button');
      expect(allButton).toHaveTextContent('4');
    });

    it('excludes non-lead-pipeline stages from the list', () => {
      const leadsWithFunded = [
        ...sampleLeads,
        {
          id: 5,
          name: 'Funded Person',
          stage: 'Funded',
          email: 'funded@example.com',
          phone: '555-000-0000',
          created_at: new Date().toISOString(),
        },
        {
          id: 6,
          name: 'Disclosed Person',
          stage: 'Disclosed',
          email: 'disclosed@example.com',
          phone: '555-000-0001',
          created_at: new Date().toISOString(),
        },
      ];
      useLeads.mockReturnValue({
        data: leadsWithFunded,
        isLoading: false,
        refetch: mockRefetch,
      });
      renderLeads();
      expect(screen.queryByText('Funded Person')).not.toBeInTheDocument();
      expect(screen.queryByText('Disclosed Person')).not.toBeInTheDocument();
      // But lead-pipeline stages remain
      expect(screen.getByText('Sarah Johnson')).toBeInTheDocument();
    });
  });

  // =========================================================================
  // 4. Search
  // =========================================================================

  describe('Search', () => {
    beforeEach(() => {
      useLeads.mockReturnValue({
        data: sampleLeads,
        isLoading: false,
        refetch: mockRefetch,
      });
    });

    it('filters leads by name search', async () => {
      renderLeads();
      const searchInput = screen.getByPlaceholderText(/Search leads/i);
      await userEvent.type(searchInput, 'Sarah');

      expect(screen.getByText('Sarah Johnson')).toBeInTheDocument();
      expect(screen.queryByText('Michael Chen')).not.toBeInTheDocument();
    });

    it('filters leads by email search', async () => {
      renderLeads();
      const searchInput = screen.getByPlaceholderText(/Search leads/i);
      await userEvent.type(searchInput, 'mchen');

      expect(screen.getByText('Michael Chen')).toBeInTheDocument();
      expect(screen.queryByText('Sarah Johnson')).not.toBeInTheDocument();
    });

    it('shows clear button when search has text', async () => {
      renderLeads();
      const searchInput = screen.getByPlaceholderText(/Search leads/i);
      await userEvent.type(searchInput, 'test');

      // Clear button renders as "x" character
      const clearBtn = screen.getByText('\u00D7');
      expect(clearBtn).toBeInTheDocument();
    });

    it('clears search when clear button is clicked', async () => {
      renderLeads();
      const searchInput = screen.getByPlaceholderText(/Search leads/i);
      await userEvent.type(searchInput, 'Sarah');

      expect(screen.queryByText('Michael Chen')).not.toBeInTheDocument();

      const clearBtn = screen.getByText('\u00D7');
      await userEvent.click(clearBtn);

      expect(screen.getByText('Michael Chen')).toBeInTheDocument();
      expect(screen.getByText('Sarah Johnson')).toBeInTheDocument();
    });

    it('search is case-insensitive', async () => {
      renderLeads();
      const searchInput = screen.getByPlaceholderText(/Search leads/i);
      await userEvent.type(searchInput, 'sarah');

      expect(screen.getByText('Sarah Johnson')).toBeInTheDocument();
    });
  });

  // =========================================================================
  // 5. New Lead Modal
  // =========================================================================

  describe('New Lead Modal', () => {
    it('opens new lead modal when Add Lead button is clicked', async () => {
      renderLeads();
      await userEvent.click(screen.getByText('+ Add Lead'));
      expect(screen.getByText('New Lead')).toBeInTheDocument();
    });

    it('shows borrower info form fields in the modal', async () => {
      renderLeads();
      await userEvent.click(screen.getByText('+ Add Lead'));

      expect(screen.getByText('First Name *')).toBeInTheDocument();
      expect(screen.getByText('Last Name *')).toBeInTheDocument();
    });

    it('shows form section tabs (Borrower Info, Property, Income, Assets)', async () => {
      renderLeads();
      await userEvent.click(screen.getByText('+ Add Lead'));

      expect(screen.getByText('Borrower Info')).toBeInTheDocument();
      expect(screen.getByText('Property')).toBeInTheDocument();
      expect(screen.getByText('Income')).toBeInTheDocument();
      expect(screen.getByText('Assets')).toBeInTheDocument();
    });

    it('closes the modal when close button is clicked', async () => {
      renderLeads();
      await userEvent.click(screen.getByText('+ Add Lead'));
      expect(screen.getByText('New Lead')).toBeInTheDocument();

      // Close button is the x in the modal header
      const closeBtn = screen.getAllByText('\u00D7').find(
        (el) => el.classList.contains('close-btn')
      );
      if (closeBtn) {
        await userEvent.click(closeBtn);
      }
      // Modal should be gone
      await waitFor(() => {
        expect(screen.queryByText('New Lead')).not.toBeInTheDocument();
      });
    });
  });

  // =========================================================================
  // 6. Duplicate Detection
  // =========================================================================

  describe('Duplicate Detection', () => {
    it('shows duplicate warning banner when leads share the same email', () => {
      const duplicateLeads = [
        {
          id: 1,
          name: 'John Doe',
          email: 'john@example.com',
          stage: 'New',
          created_at: new Date().toISOString(),
        },
        {
          id: 2,
          name: 'John D',
          email: 'john@example.com',
          stage: 'Prospect',
          created_at: new Date().toISOString(),
        },
      ];
      useLeads.mockReturnValue({
        data: duplicateLeads,
        isLoading: false,
        refetch: mockRefetch,
      });
      renderLeads();
      expect(screen.getByText(/potential duplicate/i)).toBeInTheDocument();
    });

    it('does not show duplicate banner when all emails are unique', () => {
      useLeads.mockReturnValue({
        data: sampleLeads,
        isLoading: false,
        refetch: mockRefetch,
      });
      renderLeads();
      expect(screen.queryByText(/potential duplicate/i)).not.toBeInTheDocument();
    });
  });

  // =========================================================================
  // 7. New Lead Indicators
  // =========================================================================

  describe('New Lead Indicators', () => {
    it('shows NEW badge for unviewed leads created within 48 hours', () => {
      const recentLead = [
        {
          id: 99,
          name: 'Fresh Lead',
          email: 'fresh@example.com',
          stage: 'New',
          created_at: new Date().toISOString(), // just now
        },
      ];
      useLeads.mockReturnValue({
        data: recentLead,
        isLoading: false,
        refetch: mockRefetch,
      });
      // Ensure this lead has NOT been viewed
      localStorage.removeItem('viewedLeads');
      renderLeads();
      expect(screen.getByText('NEW')).toBeInTheDocument();
    });

    it('does not show NEW badge for leads already viewed', () => {
      const recentLead = [
        {
          id: 99,
          name: 'Fresh Lead',
          email: 'fresh@example.com',
          stage: 'New',
          created_at: new Date().toISOString(),
        },
      ];
      // Mark as viewed
      localStorage.setItem('viewedLeads', JSON.stringify(['99']));
      useLeads.mockReturnValue({
        data: recentLead,
        isLoading: false,
        refetch: mockRefetch,
      });
      renderLeads();
      expect(screen.queryByText('NEW')).not.toBeInTheDocument();
    });
  });
});
