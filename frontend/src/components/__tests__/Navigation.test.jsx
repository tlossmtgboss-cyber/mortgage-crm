import React from 'react';
import { render, screen, fireEvent, within } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock('../Navigation.css', () => ({}));
vi.mock('../NotificationBell.css', () => ({}));
vi.mock('../RoleSwitcher.css', () => ({}));
vi.mock('../UpgradeModal.css', () => ({}));

// Mock NotificationBell — renders a simple placeholder
vi.mock('../NotificationBell', () => ({
  default: () => <div data-testid="notification-bell">NotificationBell</div>,
}));

// Mock UpgradeModal — renders only when open
vi.mock('../UpgradeModal', () => ({
  default: ({ isOpen, onClose, module }) =>
    isOpen ? (
      <div data-testid="upgrade-modal">
        <span>{module?.module_name || module?.module_key}</span>
        <button onClick={onClose}>Close</button>
      </div>
    ) : null,
}));

// Mock RoleSwitcher — simple placeholder
vi.mock('../RoleSwitcher', () => ({
  default: () => <div data-testid="role-switcher">RoleSwitcher</div>,
}));

// Mock usePrefetch — return no-op functions
vi.mock('../../hooks/useQueries', () => ({
  usePrefetch: () => ({
    prefetchLeads: vi.fn(),
    prefetchLoans: vi.fn(),
    prefetchDashboard: vi.fn(),
    prefetchTasks: vi.fn(),
    prefetchPortfolio: vi.fn(),
    prefetchPartners: vi.fn(),
  }),
}));

// Permission and Module context mocks — default values, overridable per test
const mockUsePermissions = vi.fn();
const mockUseModules = vi.fn();

vi.mock('../../contexts/PermissionContext', () => ({
  usePermissions: () => mockUsePermissions(),
}));

vi.mock('../../contexts/ModuleContext', () => ({
  useModules: () => mockUseModules(),
}));

import Navigation from '../Navigation';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function setPermissions(overrides = {}) {
  mockUsePermissions.mockReturnValue({
    effectiveRole: 'loan_officer',
    userRole: 'sales',
    viewAsRole: null,
    hasAnyPermission: vi.fn(() => true),
    ...overrides,
  });
}

function setModules(overrides = {}) {
  mockUseModules.mockReturnValue({
    hasModule: vi.fn(() => true),
    getModule: vi.fn(() => null),
    loading: false,
    ...overrides,
  });
}

function renderNav(props = {}, initialRoute = '/dashboard') {
  return render(
    <MemoryRouter initialEntries={[initialRoute]}>
      <Navigation
        onToggleAssistant={vi.fn()}
        onToggleCoach={vi.fn()}
        assistantOpen={false}
        coachOpen={false}
        taskCounts={{}}
        {...props}
      />
    </MemoryRouter>
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('Navigation', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });

  // =========================================================================
  // Basic rendering
  // =========================================================================

  describe('Basic rendering', () => {
    it('renders the nav element', () => {
      setPermissions();
      setModules();
      const { container } = renderNav();
      expect(container.querySelector('nav.navigation')).toBeInTheDocument();
    });

    it('renders the Settings link', () => {
      setPermissions();
      setModules();
      renderNav();
      expect(screen.getByText('Settings')).toBeInTheDocument();
    });

    it('renders NotificationBell component', () => {
      setPermissions();
      setModules();
      renderNav();
      expect(screen.getByTestId('notification-bell')).toBeInTheDocument();
    });

    it('renders RoleSwitcher component', () => {
      setPermissions();
      setModules();
      renderNav();
      expect(screen.getByTestId('role-switcher')).toBeInTheDocument();
    });
  });

  // =========================================================================
  // Role-based navigation items — Loan Officer
  // =========================================================================

  describe('Loan Officer navigation items', () => {
    beforeEach(() => {
      setPermissions({ effectiveRole: 'loan_officer', userRole: 'sales' });
      setModules();
    });

    it('shows Dashboard for loan officer', () => {
      renderNav();
      expect(screen.getByText('Dashboard')).toBeInTheDocument();
    });

    it('shows Leads for loan officer', () => {
      renderNav();
      expect(screen.getByText('Leads')).toBeInTheDocument();
    });

    it('shows Active Loans for loan officer', () => {
      renderNav();
      expect(screen.getByText('Active Loans')).toBeInTheDocument();
    });

    it('shows Tasks for loan officer', () => {
      renderNav();
      expect(screen.getByText('Tasks')).toBeInTheDocument();
    });

    it('does not show Admin Panel for loan officer', () => {
      renderNav();
      expect(screen.queryByText('Admin Panel')).not.toBeInTheDocument();
    });

    it('does not show Usage Intelligence for loan officer', () => {
      renderNav();
      expect(screen.queryByText('Usage Intelligence')).not.toBeInTheDocument();
    });
  });

  // =========================================================================
  // Role-based navigation items — Admin
  // =========================================================================

  describe('Admin navigation items', () => {
    beforeEach(() => {
      setPermissions({ effectiveRole: 'admin', userRole: 'admin' });
      setModules();
    });

    it('shows Admin Panel for admin role', () => {
      renderNav();
      expect(screen.getByText('Admin Panel')).toBeInTheDocument();
    });

    it('shows Usage Intelligence for admin role', () => {
      renderNav();
      expect(screen.getByText('Usage Intelligence')).toBeInTheDocument();
    });

    it('shows Ops Manager for admin role', () => {
      renderNav();
      expect(screen.getByText('Ops Manager')).toBeInTheDocument();
    });
  });

  // =========================================================================
  // Role-based navigation items — Processor
  // =========================================================================

  describe('Processor navigation items', () => {
    beforeEach(() => {
      setPermissions({ effectiveRole: 'processor', userRole: 'processing' });
      setModules();
    });

    it('does not show Dashboard for processor', () => {
      renderNav();
      expect(screen.queryByText('Dashboard')).not.toBeInTheDocument();
    });

    it('shows Active Loans for processor', () => {
      renderNav();
      expect(screen.getByText('Active Loans')).toBeInTheDocument();
    });

    it('shows Closed Loans for processor', () => {
      renderNav();
      expect(screen.getByText('Closed Loans')).toBeInTheDocument();
    });

    it('does not show Leads for processor', () => {
      renderNav();
      expect(screen.queryByText('Leads')).not.toBeInTheDocument();
    });

    it('does not show Marketing for processor', () => {
      renderNav();
      expect(screen.queryByText('Marketing')).not.toBeInTheDocument();
    });
  });

  // =========================================================================
  // Active state highlighting
  // =========================================================================

  describe('Active state highlighting', () => {
    beforeEach(() => {
      setPermissions({ effectiveRole: 'loan_officer', userRole: 'sales' });
      setModules();
    });

    it('marks Dashboard as active when on /dashboard', () => {
      renderNav({}, '/dashboard');
      const dashboardLink = screen.getByText('Dashboard').closest('a');
      expect(dashboardLink).toHaveClass('active');
    });

    it('marks Leads as active when on /leads', () => {
      renderNav({}, '/leads');
      const leadsLink = screen.getByText('Leads').closest('a');
      expect(leadsLink).toHaveClass('active');
    });

    it('does not mark Dashboard as active when on /leads', () => {
      renderNav({}, '/leads');
      const dashboardLink = screen.getByText('Dashboard').closest('a');
      expect(dashboardLink).not.toHaveClass('active');
    });

    it('marks Settings as active when on /settings', () => {
      renderNav({}, '/settings');
      const settingsLink = screen.getByText('Settings').closest('a');
      expect(settingsLink).toHaveClass('active');
    });
  });

  // =========================================================================
  // Badge rendering
  // =========================================================================

  describe('Badge rendering', () => {
    beforeEach(() => {
      setPermissions({ effectiveRole: 'loan_officer', userRole: 'sales' });
      setModules();
    });

    it('shows badge count for Tasks when urgentTasks count is present', () => {
      renderNav({ taskCounts: { urgentTasks: 5 } });
      expect(screen.getByText('(5)')).toBeInTheDocument();
    });

    it('does not show badge when count is 0', () => {
      renderNav({ taskCounts: { urgentTasks: 0 } });
      expect(screen.queryByText('(0)')).not.toBeInTheDocument();
    });

    it('shows badge for Leads when leads count is present', () => {
      renderNav({ taskCounts: { leads: 3 } });
      expect(screen.getByText('(3)')).toBeInTheDocument();
    });

    it('shows multiple badges for different items simultaneously', () => {
      renderNav({ taskCounts: { urgentTasks: 2, leads: 7 } });
      expect(screen.getByText('(2)')).toBeInTheDocument();
      expect(screen.getByText('(7)')).toBeInTheDocument();
    });
  });

  // =========================================================================
  // Master Admin navigation
  // =========================================================================

  describe('Master Admin navigation', () => {
    beforeEach(() => {
      localStorage.setItem('user', JSON.stringify({ email: 'admin@perenniaai.com' }));
      setPermissions({ effectiveRole: 'admin', userRole: 'admin', viewAsRole: null });
      setModules();
    });

    it('shows consolidated dropdown navigation for master admin', () => {
      renderNav();
      // Master admin sees dropdown categories like Sales, Operations, Management, Leadership
      expect(screen.getByText('Sales')).toBeInTheDocument();
      expect(screen.getByText('Operations')).toBeInTheDocument();
      expect(screen.getByText('Management')).toBeInTheDocument();
      expect(screen.getByText('Leadership')).toBeInTheDocument();
    });

    it('shows standalone items for master admin (Tasks, Reconciliation)', () => {
      renderNav();
      expect(screen.getByText('Tasks')).toBeInTheDocument();
      expect(screen.getByText('Reconciliation')).toBeInTheDocument();
    });

    it('opens dropdown menu on click', () => {
      renderNav();
      const salesButton = screen.getByText('Sales');
      fireEvent.click(salesButton);
      // Dropdown children should now be visible
      expect(screen.getByText('Active Loans')).toBeInTheDocument();
      expect(screen.getByText('Portfolio')).toBeInTheDocument();
    });
  });

  // =========================================================================
  // Master Admin viewing as another role
  // =========================================================================

  describe('Master Admin viewing as another role', () => {
    it('shows loan officer navigation when master admin views as loan_officer', () => {
      localStorage.setItem('user', JSON.stringify({ email: 'admin@perenniaai.com' }));
      setPermissions({ effectiveRole: 'admin', userRole: 'admin', viewAsRole: 'loan_officer' });
      setModules();
      renderNav();
      // Should see LO navigation, not master admin dropdown
      expect(screen.getByText('Dashboard')).toBeInTheDocument();
      expect(screen.getByText('Leads')).toBeInTheDocument();
      // Should NOT see master admin dropdown categories
      expect(screen.queryByText('Leadership')).not.toBeInTheDocument();
    });
  });

  // =========================================================================
  // Dropdown interaction
  // =========================================================================

  describe('Dropdown menus', () => {
    it('opens and closes Accounting dropdown for admin', () => {
      setPermissions({ effectiveRole: 'admin', userRole: 'admin' });
      setModules();
      // non-master-admin admin does not get the consolidated nav, gets flat items with Accounting dropdown
      renderNav();
      const accountingBtn = screen.getByText('Accounting');
      expect(accountingBtn).toBeInTheDocument();
      // Click to open
      fireEvent.click(accountingBtn);
      expect(screen.getByText('Chart of Accounts')).toBeInTheDocument();
      // Click again to close
      fireEvent.click(accountingBtn);
    });
  });

  // =========================================================================
  // Prefetch on hover
  // =========================================================================

  describe('Prefetch on hover', () => {
    it('does not crash when hovering over nav links', () => {
      setPermissions({ effectiveRole: 'loan_officer', userRole: 'sales' });
      setModules();
      renderNav();
      const leadsLink = screen.getByText('Leads');
      // Should not throw
      fireEvent.mouseEnter(leadsLink);
    });
  });
});
