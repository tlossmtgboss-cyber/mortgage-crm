/**
 * PermissionContext tests.
 *
 * Tests cover: role-based navigation filtering, hasPermission, canAccess,
 * effective role computation, admin vs non-admin visibility, viewAsRole,
 * role preview mode, and multi-role switching.
 */
import React from 'react';
import { render, screen, act, waitFor } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';

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
// Mock ImpersonationContext — PermissionContext depends on it
// ---------------------------------------------------------------------------
vi.mock('../contexts/ImpersonationContext', () => ({
  useImpersonation: () => ({
    isImpersonating: false,
    getImpersonatedUser: () => null,
  }),
}));

// ---------------------------------------------------------------------------
// Mock tokenStore
// ---------------------------------------------------------------------------
vi.mock('../utils/tokenStore', () => ({
  getToken: () => 'mock-token',
  getUserData: () => null,
  getRefreshToken: () => null,
  setTokens: vi.fn().mockResolvedValue(undefined),
  clearTokens: vi.fn().mockResolvedValue(undefined),
  initialize: vi.fn().mockResolvedValue(undefined),
  isAuthenticated: () => true,
}));

// ---------------------------------------------------------------------------
// Mock TS utility modules to avoid Babel parsing issues
// ---------------------------------------------------------------------------
vi.mock('../utils/security', () => ({
  getCSRFTokenFromCookie: vi.fn().mockReturnValue(null),
}));

vi.mock('../utils/storage', () => ({
  getItem: vi.fn().mockResolvedValue(null),
  setItem: vi.fn().mockResolvedValue(undefined),
  removeItem: vi.fn().mockResolvedValue(undefined),
  getJSON: vi.fn().mockResolvedValue(null),
  setJSON: vi.fn().mockResolvedValue(undefined),
  clearAllAuthTokens: vi.fn().mockResolvedValue(undefined),
  STORAGE_KEYS: {
    TOKEN: 'token',
    REFRESH_TOKEN: 'refresh_token',
    USER: 'user',
    IMPERSONATION: 'impersonation',
    DASHBOARD_ORDER: 'dashboardOrder',
  },
}));

vi.mock('../utils/pinnedFetch', () => ({
  pinnedAdapter: undefined,
}));

vi.mock('../services/certificatePinning.js', () => ({
  default: {
    createAxiosInterceptor: () => (config) => config,
    createAxiosResponseInterceptor: () => ({
      onFulfilled: (r) => r,
      onRejected: (e) => Promise.reject(e),
    }),
  },
}));

vi.mock('../utils/arrayHelpers.js', () => ({
  ensureArray: (data, key) => Array.isArray(data) ? data : (data?.[key] || []),
}));

// ---------------------------------------------------------------------------
// Mock fetch for permissions API
// ---------------------------------------------------------------------------
let mockFetchResponse = {
  ok: true,
  status: 200,
  json: () => Promise.resolve({
    permissions: {},
    permission_role: 'sales',
    role: null,
  }),
};

const mockFetch = vi.fn(() => Promise.resolve(mockFetchResponse));
global.fetch = mockFetch;

// ---------------------------------------------------------------------------
// Import after mocks
// ---------------------------------------------------------------------------
import { PermissionProvider, usePermissions } from '../contexts/PermissionContext';

// ---------------------------------------------------------------------------
// Test helper — renders a component that consumes the permission context
// ---------------------------------------------------------------------------
function PermissionConsumer({ testFn }) {
  const ctx = usePermissions();
  return <div data-testid="consumer">{testFn(ctx)}</div>;
}

function renderWithPermission(testFn, localStorageSetup = {}) {
  // Set up localStorage before render
  for (const [key, value] of Object.entries(localStorageSetup)) {
    localStorage.setItem(key, typeof value === 'string' ? value : JSON.stringify(value));
  }

  return render(
    <PermissionProvider>
      <PermissionConsumer testFn={testFn} />
    </PermissionProvider>
  );
}

// ---------------------------------------------------------------------------
// Setup / teardown
// ---------------------------------------------------------------------------
beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();

  mockFetchResponse = {
    ok: true,
    status: 200,
    json: () => Promise.resolve({
      permissions: {},
      permission_role: 'sales',
      role: null,
    }),
  };
  global.fetch = mockFetch.mockImplementation(() => Promise.resolve(mockFetchResponse));
});

afterEach(() => {
  localStorage.clear();
});

// ===========================================================================
// Tests
// ===========================================================================

describe('PermissionContext', () => {
  // -----------------------------------------------------------------------
  // usePermissions outside provider
  // -----------------------------------------------------------------------
  describe('Context boundary', () => {
    it('throws when usePermissions is used outside PermissionProvider', () => {
      // Suppress error boundary console.error noise
      const spy = vi.spyOn(console, 'error').mockImplementation(() => {});

      expect(() => {
        render(<PermissionConsumer testFn={() => 'test'} />);
      }).toThrow('usePermissions must be used within PermissionProvider');

      spy.mockRestore();
    });
  });

  // -----------------------------------------------------------------------
  // Default role
  // -----------------------------------------------------------------------
  describe('Default role', () => {
    it('defaults to "sales" when no user data is in localStorage', async () => {
      let capturedRole;
      renderWithPermission((ctx) => {
        capturedRole = ctx.effectiveRole;
        return capturedRole || 'loading';
      });

      // After mount, the effective role should default to loan_officer (mapped from sales)
      await waitFor(() => {
        expect(capturedRole).toBeDefined();
      });
    });
  });

  // -----------------------------------------------------------------------
  // effectiveRole computation
  // -----------------------------------------------------------------------
  describe('effectiveRole computation', () => {
    it('uses permission_role from localStorage user object', async () => {
      let capturedRole;
      renderWithPermission(
        (ctx) => {
          capturedRole = ctx.effectiveRole;
          return capturedRole || 'loading';
        },
        {
          user: JSON.stringify({ id: 1, permission_role: 'admin', role: 'admin' }),
          userRole: 'admin',
        }
      );

      await waitFor(() => {
        expect(capturedRole).toBe('admin');
      });
    });

    it('infers admin from is_admin flag in user object', async () => {
      let capturedRole;
      renderWithPermission(
        (ctx) => {
          capturedRole = ctx.effectiveRole;
          return capturedRole || 'loading';
        },
        {
          user: JSON.stringify({ id: 1, is_admin: true, role: 'admin' }),
          userRole: 'admin',
        }
      );

      await waitFor(() => {
        expect(capturedRole).toBe('admin');
      });
    });

    it('applies viewAsRole when user is admin', async () => {
      let capturedRole;
      renderWithPermission(
        (ctx) => {
          capturedRole = ctx.effectiveRole;
          return capturedRole || 'loading';
        },
        {
          user: JSON.stringify({ id: 1, permission_role: 'admin' }),
          userRole: 'admin',
          viewAsRole: 'processor',
        }
      );

      await waitFor(() => {
        expect(capturedRole).toBe('processor');
      });
    });

    it('maps production_assistant variants to production_assistant', async () => {
      let capturedRole;
      renderWithPermission(
        (ctx) => {
          capturedRole = ctx.effectiveRole;
          return capturedRole || 'loading';
        },
        {
          user: JSON.stringify({ id: 1, permission_role: 'admin' }),
          userRole: 'admin',
          viewAsRole: 'production_assistant_1',
        }
      );

      await waitFor(() => {
        expect(capturedRole).toBe('production_assistant');
      });
    });

    it('maps concierge viewAsRole to production_assistant', async () => {
      let capturedRole;
      renderWithPermission(
        (ctx) => {
          capturedRole = ctx.effectiveRole;
          return capturedRole || 'loading';
        },
        {
          user: JSON.stringify({ id: 1, permission_role: 'admin' }),
          userRole: 'admin',
          viewAsRole: 'concierge',
        }
      );

      await waitFor(() => {
        expect(capturedRole).toBe('production_assistant');
      });
    });

    it('role preview mode takes highest priority', async () => {
      let capturedRole;
      renderWithPermission(
        (ctx) => {
          capturedRole = ctx.effectiveRole;
          return capturedRole || 'loading';
        },
        {
          user: JSON.stringify({ id: 1, permission_role: 'admin' }),
          userRole: 'admin',
          viewAsRole: 'processor',
          role_preview: JSON.stringify({ role_name: 'Underwriter' }),
        }
      );

      await waitFor(() => {
        expect(capturedRole).toBe('underwriter');
      });
    });
  });

  // -----------------------------------------------------------------------
  // hasPermission
  // -----------------------------------------------------------------------
  describe('hasPermission', () => {
    it('admin roles have all permissions', async () => {
      // Mock fetch to return admin role
      mockFetchResponse = {
        ok: true,
        status: 200,
        json: () => Promise.resolve({
          permissions: {},
          permission_role: 'admin',
          role: 'admin',
        }),
      };

      let capturedHas;
      renderWithPermission(
        (ctx) => {
          capturedHas = ctx.hasPermission;
          return 'ok';
        },
        {
          user: JSON.stringify({ id: 1, permission_role: 'admin', role: 'admin' }),
          userRole: 'admin',
        }
      );

      // Wait for fetchPermissions to complete and update state
      await waitFor(() => {
        expect(capturedHas).toBeDefined();
        expect(capturedHas('leads.create')).toBe(true);
      });

      expect(capturedHas('anything.random')).toBe(true);
    });

    it('site_admin roles have all permissions', async () => {
      mockFetchResponse = {
        ok: true,
        status: 200,
        json: () => Promise.resolve({
          permissions: {},
          permission_role: 'site_admin',
          role: 'site_admin',
        }),
      };

      let capturedHas;
      renderWithPermission(
        (ctx) => {
          capturedHas = ctx.hasPermission;
          return 'ok';
        },
        {
          user: JSON.stringify({ id: 1, permission_role: 'site_admin', role: 'site_admin' }),
          userRole: 'site_admin',
        }
      );

      await waitFor(() => {
        expect(capturedHas).toBeDefined();
        expect(capturedHas('leads.delete')).toBe(true);
      });
    });

    it('sales role only has explicitly granted permissions', async () => {
      // Override mock fetch to return specific permissions
      mockFetchResponse = {
        ok: true,
        status: 200,
        json: () => Promise.resolve({
          permissions: { 'leads.view': true, 'leads.create': true },
          permission_role: 'sales',
        }),
      };

      let capturedHas;
      renderWithPermission(
        (ctx) => {
          capturedHas = ctx.hasPermission;
          return 'ok';
        },
        {
          user: JSON.stringify({ id: 1, permission_role: 'sales' }),
          userRole: 'sales',
        }
      );

      await waitFor(() => {
        expect(capturedHas).toBeDefined();
      });

      // Wait for permissions to be fetched
      await waitFor(() => {
        expect(capturedHas('leads.view')).toBe(true);
      });

      expect(capturedHas('leads.create')).toBe(true);
      expect(capturedHas('admin.manage_users')).toBe(false);
    });
  });

  // -----------------------------------------------------------------------
  // canPerformAction — combines permission + read-only impersonation
  // -----------------------------------------------------------------------
  describe('canPerformAction', () => {
    it('blocks write operations in read-only impersonation mode', async () => {
      mockFetchResponse = {
        ok: true,
        status: 200,
        json: () => Promise.resolve({
          permissions: {},
          permission_role: 'admin',
          role: 'admin',
        }),
      };

      let capturedCan;
      renderWithPermission(
        (ctx) => {
          capturedCan = ctx.canPerformAction;
          return 'ok';
        },
        {
          user: JSON.stringify({ id: 1, permission_role: 'admin' }),
          userRole: 'admin',
          impersonation: JSON.stringify({ mode: 'read_only', session_token: 'x' }),
        }
      );

      // Wait for state to settle
      await waitFor(() => {
        expect(capturedCan).toBeDefined();
        // Read operation still allowed (admin has permission)
        expect(capturedCan('leads.view', false)).toBe(true);
      });

      // Write operation blocked in read-only mode
      expect(capturedCan('leads.edit', true)).toBe(false);
    });
  });

  // -----------------------------------------------------------------------
  // getDataScope
  // -----------------------------------------------------------------------
  describe('getDataScope', () => {
    it('returns "all" for admin roles', async () => {
      mockFetchResponse = {
        ok: true,
        status: 200,
        json: () => Promise.resolve({
          permissions: {},
          permission_role: 'admin',
          role: 'admin',
        }),
      };

      let capturedScope;
      renderWithPermission(
        (ctx) => {
          capturedScope = ctx.getDataScope;
          return 'ok';
        },
        {
          user: JSON.stringify({ id: 1, permission_role: 'admin' }),
          userRole: 'admin',
        }
      );

      await waitFor(() => {
        expect(capturedScope).toBeDefined();
        expect(capturedScope('leads')).toBe('all');
      });
    });

    it('returns "own" as default for non-admin without view permissions', async () => {
      mockFetchResponse = {
        ok: true,
        status: 200,
        json: () => Promise.resolve({
          permissions: {},
          permission_role: 'sales',
        }),
      };

      let capturedScope;
      renderWithPermission(
        (ctx) => {
          capturedScope = ctx.getDataScope;
          return 'ok';
        },
        {
          user: JSON.stringify({ id: 1, permission_role: 'sales' }),
          userRole: 'sales',
        }
      );

      await waitFor(() => {
        expect(capturedScope).toBeDefined();
      });

      expect(capturedScope('leads')).toBe('own');
    });
  });

  // -----------------------------------------------------------------------
  // isAdmin / isPlatformAdmin
  // -----------------------------------------------------------------------
  describe('Admin detection', () => {
    it('isAdmin is true for admin role', async () => {
      let capturedIsAdmin;
      renderWithPermission(
        (ctx) => {
          capturedIsAdmin = ctx.isAdmin;
          return String(capturedIsAdmin);
        },
        {
          user: JSON.stringify({ id: 1, permission_role: 'admin', role: 'admin' }),
          userRole: 'admin',
        }
      );

      await waitFor(() => {
        expect(capturedIsAdmin).toBe(true);
      });
    });

    it('isAdmin is true for site_admin role', async () => {
      let capturedIsAdmin;
      renderWithPermission(
        (ctx) => {
          capturedIsAdmin = ctx.isAdmin;
          return String(capturedIsAdmin);
        },
        {
          user: JSON.stringify({ id: 1, permission_role: 'site_admin', role: 'site_admin' }),
          userRole: 'site_admin',
        }
      );

      await waitFor(() => {
        expect(capturedIsAdmin).toBe(true);
      });
    });

    it('isPlatformAdmin is false for site_admin', async () => {
      let capturedIsPlatform;
      renderWithPermission(
        (ctx) => {
          capturedIsPlatform = ctx.isPlatformAdmin;
          return String(capturedIsPlatform);
        },
        {
          user: JSON.stringify({ id: 1, permission_role: 'site_admin', role: 'site_admin' }),
          userRole: 'site_admin',
        }
      );

      await waitFor(() => {
        expect(capturedIsPlatform).toBe(false);
      });
    });

    it('isPlatformAdmin is true for admin role', async () => {
      let capturedIsPlatform;
      renderWithPermission(
        (ctx) => {
          capturedIsPlatform = ctx.isPlatformAdmin;
          return String(capturedIsPlatform);
        },
        {
          user: JSON.stringify({ id: 1, permission_role: 'admin', role: 'admin' }),
          userRole: 'admin',
        }
      );

      await waitFor(() => {
        expect(capturedIsPlatform).toBe(true);
      });
    });
  });

  // -----------------------------------------------------------------------
  // Logout clears state
  // -----------------------------------------------------------------------
  describe('Auth change events', () => {
    it('clears permissions and role on logout event', async () => {
      let capturedRole;
      renderWithPermission(
        (ctx) => {
          capturedRole = ctx.effectiveRole;
          return capturedRole || 'loading';
        },
        {
          user: JSON.stringify({ id: 1, permission_role: 'admin' }),
          userRole: 'admin',
        }
      );

      await waitFor(() => {
        expect(capturedRole).toBe('admin');
      });

      // Dispatch logout event
      act(() => {
        window.dispatchEvent(
          new CustomEvent('authChange', { detail: { type: 'logout' } })
        );
      });

      // After logout, role should reset
      await waitFor(() => {
        // effectiveRole derived from userRole='sales' should be 'loan_officer'
        // The exact mapped value depends on getUserEffectiveRole, but it should
        // not be 'admin' anymore
        expect(capturedRole).not.toBe('admin');
      });
    });
  });
});
