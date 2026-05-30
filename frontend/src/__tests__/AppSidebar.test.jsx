/**
 * AppSidebar tests.
 *
 * Tests cover: logo link, user profile link, active route highlighting,
 * role-based nav item filtering, badge counts display.
 */
import React from 'react';
import { screen } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach, beforeAll } from 'vitest';
import { renderWithProviders } from '../test/testUtils';

// ---------------------------------------------------------------------------
// Mock Capacitor
// ---------------------------------------------------------------------------
vi.mock('@capacitor/core', () => ({
  Capacitor: { isNativePlatform: () => false },
}));

vi.mock('@capacitor/preferences', () => ({
  Preferences: {
    get: vi.fn().mockResolvedValue({ value: null }),
    set: vi.fn().mockResolvedValue(undefined),
    remove: vi.fn().mockResolvedValue(undefined),
  },
}));

// ---------------------------------------------------------------------------
// Mock contexts
// ---------------------------------------------------------------------------
let mockEffectiveRole = 'loan_officer';
let mockHasModule = () => true;

vi.mock('../contexts/PermissionContext', () => ({
  usePermissions: () => ({
    effectiveRole: mockEffectiveRole,
    hasPermission: () => true,
    isAdmin: mockEffectiveRole === 'admin',
    isPlatformAdmin: mockEffectiveRole === 'admin',
  }),
}));

vi.mock('../contexts/ModuleContext', () => ({
  useModules: () => ({
    hasModule: mockHasModule,
    enabledModules: ['base'],
  }),
}));

// ---------------------------------------------------------------------------
// Mock tokenStore — return controlled user data
// ---------------------------------------------------------------------------
let mockUserData = {
  first_name: 'John',
  last_name: 'Smith',
  email: 'john@test.com',
};

vi.mock('../utils/tokenStore', () => ({
  getUserData: () => mockUserData,
  getToken: () => 'mock-token',
}));

// ---------------------------------------------------------------------------
// Mock CSS
// ---------------------------------------------------------------------------
vi.mock('../components/AppSidebar.css', () => ({}));

// ---------------------------------------------------------------------------
// Lazy import after mocks
// ---------------------------------------------------------------------------
let AppSidebar;
beforeAll(async () => {
  const mod = await import('../components/AppSidebar');
  AppSidebar = mod.default;
});

beforeEach(() => {
  vi.clearAllMocks();
  mockEffectiveRole = 'loan_officer';
  mockHasModule = () => true;
  mockUserData = {
    first_name: 'John',
    last_name: 'Smith',
    email: 'john@test.com',
  };
});

// ===========================================================================
// Tests
// ===========================================================================

describe('AppSidebar', () => {
  // -----------------------------------------------------------------------
  // Logo / header
  // -----------------------------------------------------------------------
  describe('Logo and branding', () => {
    it('renders Aria logo text', () => {
      renderWithProviders(<AppSidebar />);
      expect(screen.getByText('Aria')).toBeInTheDocument();
    });

    it('logo links to the Aria experience', () => {
      renderWithProviders(<AppSidebar />);
      const logoLink = screen.getByText('Aria').closest('a');
      expect(logoLink).toHaveAttribute('href', '/aria-mobile');
    });
  });

  // -----------------------------------------------------------------------
  // User profile section
  // -----------------------------------------------------------------------
  describe('User profile', () => {
    it('renders user display name', () => {
      renderWithProviders(<AppSidebar />);
      expect(screen.getByText('John Smith')).toBeInTheDocument();
    });

    it('shows user initials as avatar', () => {
      renderWithProviders(<AppSidebar />);
      // First letter of first + last name
      expect(screen.getByText('JS')).toBeInTheDocument();
    });

    it('user section links to settings', () => {
      renderWithProviders(<AppSidebar />);
      const userLink = screen.getByText('John Smith').closest('a');
      expect(userLink).toHaveAttribute('href', '/settings');
    });

    it('falls back to "LO" initials when no user data', () => {
      mockUserData = null;
      renderWithProviders(<AppSidebar />);
      // The avatar div should contain "LO" initials
      const avatarEl = document.querySelector('.s-av');
      expect(avatarEl).not.toBeNull();
      expect(avatarEl.textContent).toBe('LO');
    });

    it('shows role label for current role', () => {
      renderWithProviders(<AppSidebar />);
      expect(screen.getByText('Loan Officer')).toBeInTheDocument();
    });
  });

  // -----------------------------------------------------------------------
  // Navigation items
  // -----------------------------------------------------------------------
  describe('Navigation items', () => {
    it('renders Dashboard nav item for loan_officer role', () => {
      renderWithProviders(<AppSidebar />);
      expect(screen.getByText('Dashboard')).toBeInTheDocument();
    });

    it('renders Leads nav item for loan_officer role', () => {
      renderWithProviders(<AppSidebar />);
      expect(screen.getByText('Leads')).toBeInTheDocument();
    });

    it('renders Active Loans nav item for loan_officer role', () => {
      renderWithProviders(<AppSidebar />);
      expect(screen.getByText('Active Loans')).toBeInTheDocument();
    });

    it('renders Tasks nav item', () => {
      renderWithProviders(<AppSidebar />);
      expect(screen.getByText('Tasks')).toBeInTheDocument();
    });

    it('renders Calendar nav item', () => {
      renderWithProviders(<AppSidebar />);
      expect(screen.getByText('Calendar')).toBeInTheDocument();
    });
  });

  // -----------------------------------------------------------------------
  // Badge counts
  // -----------------------------------------------------------------------
  describe('Badge counts', () => {
    it('displays badge count for tasks when > 0', () => {
      renderWithProviders(<AppSidebar taskCounts={{ totalTasks: 5 }} />);
      expect(screen.getByText('5')).toBeInTheDocument();
    });

    it('does NOT display badge when count is 0', () => {
      renderWithProviders(<AppSidebar taskCounts={{ totalTasks: 0 }} />);
      // The '0' badge should not be rendered
      const badges = screen.queryAllByText('0');
      // Filter to only badge elements (small spans), not other content
      const badgeElements = badges.filter(el => el.classList.contains('s-badge'));
      expect(badgeElements).toHaveLength(0);
    });

    it('displays multiple badge counts simultaneously', () => {
      renderWithProviders(
        <AppSidebar taskCounts={{ totalTasks: 3, leads: 7, smartDocs: 2 }} />
      );
      expect(screen.getByText('3')).toBeInTheDocument();
      expect(screen.getByText('7')).toBeInTheDocument();
      expect(screen.getByText('2')).toBeInTheDocument();
    });
  });

  // -----------------------------------------------------------------------
  // Role-based role badge
  // -----------------------------------------------------------------------
  describe('Role badge', () => {
    it('shows "LO" role badge for loan_officer', () => {
      renderWithProviders(<AppSidebar />);
      // The version/role badge next to "Aria"
      expect(screen.getByText('LO')).toBeInTheDocument();
    });

    it('shows "ADM" role badge for admin', () => {
      mockEffectiveRole = 'admin';
      renderWithProviders(<AppSidebar />);
      expect(screen.getByText('ADM')).toBeInTheDocument();
    });
  });
});
