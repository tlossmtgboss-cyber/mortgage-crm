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

// Mock ThemeToggle — simple placeholder (avoids needing a ThemeProvider)
vi.mock('../ThemeToggle', () => ({
  default: () => <div data-testid="theme-toggle">ThemeToggle</div>,
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

// tokenStore mock — Navigation reads the current user via getUserData() (NOT
// localStorage directly) to detect the master admin. Expose a controllable mock
// so master-admin tests can simulate the logged-in user.
const mockGetUserData = vi.fn(() => null);
vi.mock('../../utils/tokenStore', () => ({
  getUserData: () => mockGetUserData(),
  getToken: () => 'test-token',
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

// Branding context mock — Navigation consumes useBranding() for brand name/logo.
// Provide default branding values so the component renders without a provider.
vi.mock('../../contexts/BrandingContext', () => ({
  useBranding: () => ({
    brandName: 'Perennia AI',
    logoUrl: null,
    faviconUrl: null,
    primaryColor: '#000000',
    secondaryColor: '#ffffff',
    loading: false,
  }),
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
  const result = render(
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
  // The current Navigation renders every item twice: once in the desktop
  // `nav.navigation` bar and again in the responsive `.mobile-menu-drawer`
  // (a sibling rendered outside the <nav>). Scope all queries to the desktop
  // nav so text/role lookups remain unambiguous.
  const navEl = result.container.querySelector('nav.navigation');
  const nav = within(navEl);
  return { ...result, navEl, nav };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('Navigation', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    mockGetUserData.mockReturnValue(null);
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
      const { nav } = renderNav();
      expect(nav.getByText('Settings')).toBeInTheDocument();
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
      const { nav } = renderNav();
      expect(nav.getByText('Dashboard')).toBeInTheDocument();
    });

    it('shows Leads for loan officer', () => {
      const { nav } = renderNav();
      expect(nav.getByText('Leads')).toBeInTheDocument();
    });

    it('shows Active Loans for loan officer', () => {
      const { nav } = renderNav();
      expect(nav.getByText('Active Loans')).toBeInTheDocument();
    });

    it('shows Tasks for loan officer', () => {
      const { nav } = renderNav();
      expect(nav.getByText('Tasks')).toBeInTheDocument();
    });

    it('does not show Admin Panel for loan officer', () => {
      const { nav } = renderNav();
      expect(nav.queryByText('Admin Panel')).not.toBeInTheDocument();
    });

    it('does not show Usage Intelligence for loan officer', () => {
      const { nav } = renderNav();
      expect(nav.queryByText('Usage Intelligence')).not.toBeInTheDocument();
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

    it('shows Usage Intelligence for admin role', () => {
      const { nav } = renderNav();
      expect(nav.getByText('Usage Intelligence')).toBeInTheDocument();
    });

    it('shows Ops Manager for admin role', () => {
      const { nav } = renderNav();
      expect(nav.getByText('Ops Manager')).toBeInTheDocument();
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
      const { nav } = renderNav();
      expect(nav.queryByText('Dashboard')).not.toBeInTheDocument();
    });

    it('shows Active Loans for processor', () => {
      const { nav } = renderNav();
      expect(nav.getByText('Active Loans')).toBeInTheDocument();
    });

    it('shows Closed Loans for processor', () => {
      const { nav } = renderNav();
      expect(nav.getByText('Closed Loans')).toBeInTheDocument();
    });

    it('does not show Leads for processor', () => {
      const { nav } = renderNav();
      expect(nav.queryByText('Leads')).not.toBeInTheDocument();
    });

    it('does not show Marketing for processor', () => {
      const { nav } = renderNav();
      expect(nav.queryByText('Marketing')).not.toBeInTheDocument();
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
      const { nav } = renderNav({}, '/dashboard');
      const dashboardLink = nav.getByText('Dashboard').closest('a');
      expect(dashboardLink).toHaveClass('active');
    });

    it('marks the Leads nav item as active when on /leads', () => {
      const { navEl } = renderNav({}, '/leads');
      // The Leads item may render as an <a> or, when active, as a dropdown
      // toggle <button>. Find the active item in the desktop nav and confirm
      // it corresponds to Leads.
      const active = navEl.querySelector('.nav-links .nav-link.active, .nav-links .active.nav-link');
      expect(active).toBeTruthy();
      expect(active.textContent).toMatch(/Leads/);
    });

    it('does not mark Dashboard as active when on /leads', () => {
      const { navEl } = renderNav({}, '/leads');
      // No active item in the desktop nav should correspond to Dashboard.
      const activeItems = Array.from(
        navEl.querySelectorAll('.nav-links .nav-link.active')
      );
      const dashboardActive = activeItems.some((el) => /Dashboard/.test(el.textContent));
      expect(dashboardActive).toBe(false);
    });

    it('marks Settings as active when on /settings', () => {
      const { nav } = renderNav({}, '/settings');
      const settingsLink = nav.getByText('Settings').closest('a');
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

    it('does not show badge when count is 0', () => {
      const { nav } = renderNav({ taskCounts: { urgentTasks: 0 } });
      expect(nav.queryByText('(0)')).not.toBeInTheDocument();
    });

    it('shows badge for Leads when leads count is present', () => {
      const { nav } = renderNav({ taskCounts: { leads: 3 } });
      expect(nav.getByText('(3)')).toBeInTheDocument();
    });
  });

  // =========================================================================
  // Master Admin navigation
  // =========================================================================

  describe('Master Admin navigation', () => {
    beforeEach(() => {
      mockGetUserData.mockReturnValue({ email: 'admin@perenniaai.com' });
      setPermissions({ effectiveRole: 'admin', userRole: 'admin', viewAsRole: null });
      setModules();
    });

    it('shows consolidated dropdown navigation for master admin', () => {
      const { nav } = renderNav();
      // Master admin sees dropdown categories like Sales, Operations, Management, Leadership
      expect(nav.getByText('Sales')).toBeInTheDocument();
      expect(nav.getByText('Operations')).toBeInTheDocument();
      expect(nav.getByText('Management')).toBeInTheDocument();
      expect(nav.getByText('Leadership')).toBeInTheDocument();
    });

    it('shows standalone items for master admin (Tasks, IT Tickets, Calendar)', () => {
      const { nav } = renderNav();
      // Master admin nav exposes standalone quick-access items alongside the
      // grouped dropdowns. Current standalone set: Tasks, IT Tickets, Calendar.
      expect(nav.getByText('Tasks')).toBeInTheDocument();
      expect(nav.getByText('IT Tickets')).toBeInTheDocument();
      expect(nav.getByText('Calendar')).toBeInTheDocument();
    });

    it('opens dropdown menu on click', () => {
      const { nav } = renderNav();
      const salesButton = nav.getByText('Sales');
      fireEvent.click(salesButton);
      // Dropdown children should now be visible
      expect(nav.getByText('Active Loans')).toBeInTheDocument();
      expect(nav.getByText('Portfolio')).toBeInTheDocument();
    });
  });

  // =========================================================================
  // Master Admin viewing as another role
  // =========================================================================

  describe('Master Admin viewing as another role', () => {
    it('shows loan officer navigation when master admin views as loan_officer', () => {
      mockGetUserData.mockReturnValue({ email: 'admin@perenniaai.com' });
      setPermissions({ effectiveRole: 'admin', userRole: 'admin', viewAsRole: 'loan_officer' });
      setModules();
      const { nav } = renderNav();
      // Should see LO navigation, not master admin dropdown
      expect(nav.getByText('Dashboard')).toBeInTheDocument();
      expect(nav.getByText('Leads')).toBeInTheDocument();
      // Should NOT see master admin dropdown categories
      expect(nav.queryByText('Leadership')).not.toBeInTheDocument();
    });
  });

  // =========================================================================
  // Dropdown interaction
  // =========================================================================

  describe('Dropdown menus', () => {
    it('opens a grouped dropdown to reveal its children', () => {
      // Grouped dropdown nav is the master admin layout; a plain admin gets a
      // flat list with no dropdowns. Use the master admin layout to exercise
      // the open/close dropdown mechanism.
      mockGetUserData.mockReturnValue({ email: 'admin@perenniaai.com' });
      setPermissions({ effectiveRole: 'admin', userRole: 'admin', viewAsRole: null });
      setModules();
      const { navEl } = renderNav();
      const toggle = navEl.querySelector('.nav-links .nav-dropdown .dropdown-toggle');
      expect(toggle).toBeTruthy();
      // Click to open — the parent .nav-dropdown should gain the 'open' class
      // and render its .dropdown-menu.
      fireEvent.click(toggle);
      expect(navEl.querySelector('.nav-links .nav-dropdown.open .dropdown-menu')).toBeTruthy();
    });
  });

  // =========================================================================
  // Prefetch on hover
  // =========================================================================

  describe('Prefetch on hover', () => {
    it('does not crash when hovering over nav links', () => {
      setPermissions({ effectiveRole: 'loan_officer', userRole: 'sales' });
      setModules();
      const { nav } = renderNav();
      const leadsLink = nav.getByText('Leads');
      // Should not throw
      fireEvent.mouseEnter(leadsLink);
    });
  });
});
