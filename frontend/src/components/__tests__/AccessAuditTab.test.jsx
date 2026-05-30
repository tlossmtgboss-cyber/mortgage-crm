import React from 'react';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

// ---------------------------------------------------------------------------
// Mocks -- must come before component import
// ---------------------------------------------------------------------------

const mockGetAuditLog = vi.fn();
const mockGetActiveSessions = vi.fn();
const mockGetImpersonationHistory = vi.fn();
const mockRevokeSession = vi.fn();
const mockRevokeAllSessions = vi.fn();
const mockEmergencyRevoke = vi.fn();

vi.mock('@/services/api', () => ({
  auditAPI: {
    getAuditLog: (...args) => mockGetAuditLog(...args),
    getActiveSessions: (...args) => mockGetActiveSessions(...args),
    getImpersonationHistory: (...args) => mockGetImpersonationHistory(...args),
    revokeSession: (...args) => mockRevokeSession(...args),
    revokeAllSessions: (...args) => mockRevokeAllSessions(...args),
    emergencyRevoke: (...args) => mockEmergencyRevoke(...args),
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

vi.mock('./AccessAuditTab.css', () => ({}));
vi.mock('../AccessAuditTab.css', () => ({}));

import AccessAuditTab from '../AccessAuditTab';
import { toast } from '@/utils/toast';

// ---------------------------------------------------------------------------
// Test Data
// ---------------------------------------------------------------------------

const mockUserId = 'user-123';

const auditLogData = {
  logs: [
    {
      id: 'log-1',
      timestamp: '2026-03-10T14:30:00Z',
      change_type: 'permission',
      changed_by_email: 'admin@example.com',
      changed_by_id: 'admin-1',
      entity_type: 'Permission',
      before_state: { role: 'sales' },
      after_state: { role: 'management' },
      reason: 'Promotion to management',
      ip_address: '192.168.1.1',
    },
    {
      id: 'log-2',
      timestamp: '2026-03-08T09:15:00Z',
      change_type: 'role',
      changed_by_email: null,
      changed_by_id: 'system',
      entity_type: 'Role',
      before_state: null,
      after_state: { role: 'admin' },
      reason: null,
      ip_address: null,
    },
    {
      id: 'log-3',
      timestamp: '2026-03-05T16:45:00Z',
      change_type: 'emergency_revocation',
      changed_by_email: 'security@example.com',
      changed_by_id: 'sec-1',
      entity_type: 'Access',
      before_state: { active: true },
      after_state: { active: false },
      reason: 'Security incident',
      ip_address: '10.0.0.1',
    },
  ],
  total: 3,
};

const sessionsData = {
  sessions: [
    {
      id: 'sess-1',
      session_id: 'sid-abc',
      device: 'Chrome on Mac',
      is_current: true,
      logged_in_at: '2026-03-18T08:00:00Z',
      last_activity: '2026-03-18T10:30:00Z',
      ip_address: '192.168.1.10',
      location: 'San Francisco, CA',
    },
    {
      id: 'sess-2',
      session_id: 'sid-def',
      device: 'Safari on iPhone',
      is_current: false,
      logged_in_at: '2026-03-17T12:00:00Z',
      last_activity: '2026-03-17T18:00:00Z',
      ip_address: '10.0.0.5',
      location: 'Los Angeles, CA',
    },
  ],
};

const impersonationData = {
  impersonations: [
    {
      id: 'imp-1',
      impersonated_by_email: 'superadmin@example.com',
      started_at: '2026-03-15T10:00:00Z',
      ended_at: '2026-03-15T10:15:00Z',
      duration: '15 minutes',
      reason: 'Troubleshooting user issue',
    },
  ],
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function renderTab() {
  return render(<AccessAuditTab userId={mockUserId} />);
}

function setApiSuccess() {
  mockGetAuditLog.mockResolvedValue(auditLogData);
  mockGetActiveSessions.mockResolvedValue(sessionsData);
  mockGetImpersonationHistory.mockResolvedValue(impersonationData);
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('AccessAuditTab', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setApiSuccess();
    // Mock window.prompt for session revocation flows
    vi.spyOn(window, 'prompt').mockReturnValue('Test reason');
  });

  // 1. Loading state for audit log
  it('shows loading state while audit log is being fetched', () => {
    mockGetAuditLog.mockReturnValue(new Promise(() => {}));

    renderTab();

    expect(screen.getByText('Loading audit log...')).toBeInTheDocument();
  });

  // 2. Audit log entries render correctly
  it('renders audit log entries with correct data', async () => {
    renderTab();

    await waitFor(() => {
      expect(screen.getByText('admin@example.com')).toBeInTheDocument();
    });

    // Change type badges. These labels also appear in the filter <select>
    // options (and "Permission" additionally as an entity cell), so use the
    // *AllBy* variants and assert at least one match per change type.
    expect(screen.getAllByText('Permission').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('Role').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('Emergency Revocation').length).toBeGreaterThanOrEqual(1);

    // Entity types
    const cells = screen.getAllByText('Permission');
    expect(cells.length).toBeGreaterThanOrEqual(1);

    // IP address
    expect(screen.getByText('192.168.1.1')).toBeInTheDocument();

    // Fallback for null email
    expect(screen.getByText('User system')).toBeInTheDocument();
  });

  // 3. Empty audit log shows empty state
  it('shows empty state when audit log has no entries', async () => {
    mockGetAuditLog.mockResolvedValue({ logs: [], total: 0 });

    renderTab();

    await waitFor(() => {
      expect(screen.getByText('No audit logs found')).toBeInTheDocument();
    });
  });

  // 4. Audit log filter controls render
  it('renders filter controls for date range, change type, and search', async () => {
    renderTab();

    await waitFor(() => {
      expect(screen.getByText('Start Date')).toBeInTheDocument();
    });

    expect(screen.getByText('End Date')).toBeInTheDocument();
    // "Change Type" appears both as a filter <label> and as a table <th>,
    // so assert at least one occurrence rather than a single unique element.
    expect(screen.getAllByText('Change Type').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('Search')).toBeInTheDocument();
    expect(screen.getByText('Apply Filters')).toBeInTheDocument();
  });

  // 5. Apply Filters reloads audit log
  it('reloads audit log when Apply Filters is clicked', async () => {
    renderTab();

    await waitFor(() => {
      expect(screen.getByText('Apply Filters')).toBeInTheDocument();
    });

    mockGetAuditLog.mockClear();
    setApiSuccess();

    fireEvent.click(screen.getByText('Apply Filters'));

    await waitFor(() => {
      expect(mockGetAuditLog).toHaveBeenCalledTimes(1);
      expect(mockGetAuditLog).toHaveBeenCalledWith(mockUserId, expect.any(Object));
    });
  });

  // 6. Section navigation switches views
  it('switches between Audit Log, Active Sessions, and Emergency Revocation sections', async () => {
    renderTab();

    await waitFor(() => {
      // "Audit Log" is both the nav <button> and the section <h3>, so target
      // the nav button specifically.
      expect(screen.getByRole('button', { name: 'Audit Log' })).toBeInTheDocument();
    });

    // Default section is audit log
    expect(screen.getByText('All changes to this user\'s profile and permissions')).toBeInTheDocument();

    // Navigate to Sessions
    const sessionsButton = screen.getByRole('button', { name: /Active Sessions/i });
    fireEvent.click(sessionsButton);

    await waitFor(() => {
      expect(screen.getByText("Manage user's active login sessions")).toBeInTheDocument();
    });

    // Navigate to Emergency
    const emergencyButton = screen.getByRole('button', { name: /Emergency Revocation/i });
    fireEvent.click(emergencyButton);

    await waitFor(() => {
      expect(screen.getByText('Immediately terminate all access and sessions')).toBeInTheDocument();
    });
  });

  // 7. Active sessions render with device info
  it('renders active sessions with device names and current session badge', async () => {
    renderTab();

    // Navigate to sessions section
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Active Sessions/i })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: /Active Sessions/i }));

    await waitFor(() => {
      expect(screen.getByText('Chrome on Mac')).toBeInTheDocument();
    });

    expect(screen.getByText('Safari on iPhone')).toBeInTheDocument();
    expect(screen.getByText('Current Session')).toBeInTheDocument();
    expect(screen.getByText('San Francisco, CA')).toBeInTheDocument();
    expect(screen.getByText('Los Angeles, CA')).toBeInTheDocument();
  });

  // 8. Revoke single session calls API
  it('revokes a single session when Revoke Session is clicked', async () => {
    mockRevokeSession.mockResolvedValue({});

    renderTab();

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Active Sessions/i })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: /Active Sessions/i }));

    await waitFor(() => {
      expect(screen.getAllByText('Revoke Session').length).toBeGreaterThanOrEqual(1);
    });

    // Click first Revoke Session button
    const revokeButtons = screen.getAllByText('Revoke Session');
    fireEvent.click(revokeButtons[0]);

    await waitFor(() => {
      expect(mockRevokeSession).toHaveBeenCalledWith(mockUserId, 'sid-abc', 'Test reason');
    });

    expect(toast.success).toHaveBeenCalledWith('Session revoked successfully');
  });

  // 9. Revoke All Sessions calls API
  it('revokes all sessions when Revoke All Sessions is clicked', async () => {
    mockRevokeAllSessions.mockResolvedValue({});

    renderTab();

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Active Sessions/i })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: /Active Sessions/i }));

    await waitFor(() => {
      expect(screen.getByText('Revoke All Sessions')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('Revoke All Sessions'));

    await waitFor(() => {
      expect(mockRevokeAllSessions).toHaveBeenCalledWith(mockUserId, 'Test reason');
    });

    expect(toast.success).toHaveBeenCalledWith('All sessions revoked successfully');
  });

  // 10. Emergency revocation modal opens and has form fields
  it('opens emergency revocation modal with required form fields', async () => {
    renderTab();

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Emergency Revocation/i })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: /Emergency Revocation/i }));

    await waitFor(() => {
      expect(screen.getByText('Emergency Revoke Access')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('Emergency Revoke Access'));

    await waitFor(() => {
      expect(screen.getByText('This action cannot be undone easily. Proceed with caution.')).toBeInTheDocument();
    });

    // Form fields
    expect(screen.getByText('Reason *')).toBeInTheDocument();
    expect(screen.getByText('Details *')).toBeInTheDocument();
    expect(screen.getByText('Notify')).toBeInTheDocument();
    expect(screen.getByText('Reinstatement')).toBeInTheDocument();
    expect(screen.getByText('Confirm Emergency Revocation')).toBeInTheDocument();
    expect(screen.getByText('Cancel')).toBeInTheDocument();
  });

  // 11. Emergency revocation requires details
  it('shows error toast when emergency revocation is submitted without details', async () => {
    renderTab();

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Emergency Revocation/i })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: /Emergency Revocation/i }));

    await waitFor(() => {
      expect(screen.getByText('Emergency Revoke Access')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('Emergency Revoke Access'));

    await waitFor(() => {
      expect(screen.getByText('Confirm Emergency Revocation')).toBeInTheDocument();
    });

    // Submit without filling details
    fireEvent.click(screen.getByText('Confirm Emergency Revocation'));

    expect(toast.error).toHaveBeenCalledWith('Please provide details for the emergency revocation');
    expect(mockEmergencyRevoke).not.toHaveBeenCalled();
  });

  // 12. API error on audit log shows toast
  it('shows error toast when audit log API call fails', async () => {
    mockGetAuditLog.mockRejectedValue(new Error('Server error'));

    renderTab();

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('Failed to load audit log');
    });
  });
});
