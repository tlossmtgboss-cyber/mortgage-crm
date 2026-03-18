import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

// ---------------------------------------------------------------------------
// Mocks -- must come before component import
// ---------------------------------------------------------------------------

const mockNavigate = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return { ...actual, useNavigate: () => mockNavigate };
});

const mockGetOverview = vi.fn();
const mockGetCertificationsByDepartment = vi.fn();
const mockExportReport = vi.fn();

vi.mock('@/services/api', () => ({
  complianceApi: {
    getOverview: (...args) => mockGetOverview(...args),
    getCertificationsByDepartment: (...args) => mockGetCertificationsByDepartment(...args),
    exportReport: (...args) => mockExportReport(...args),
  },
}));

const mockUsePermissions = vi.fn();
vi.mock('@/contexts/PermissionContext', () => ({
  usePermissions: () => mockUsePermissions(),
}));

vi.mock('@/utils/toast', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
    info: vi.fn(),
    warning: vi.fn(),
  },
}));

vi.mock('./ComplianceDashboard.css', () => ({}));
vi.mock('../ComplianceDashboard.css', () => ({}));

import ComplianceDashboard from '../ComplianceDashboard';
import { toast } from '@/utils/toast';

// ---------------------------------------------------------------------------
// Test Data
// ---------------------------------------------------------------------------

const overviewData = {
  users: { total: 42 },
  certifications: {
    certified_percent: 85,
    certified: 36,
    total: 42,
    overdue: 3,
    pending: 5,
  },
  permissions: {
    high_risk_granted: 7,
    total_granted: 128,
    recent_changes_30d: 14,
  },
};

const departmentData = {
  departments: [
    {
      department: 'Sales',
      total_employees: 20,
      certified: 18,
      overdue: 1,
      certified_percent: 90,
    },
    {
      department: 'Operations',
      total_employees: 12,
      certified: 10,
      overdue: 2,
      certified_percent: 83,
    },
    {
      department: 'Compliance',
      total_employees: 5,
      certified: 5,
      overdue: 0,
      certified_percent: 100,
    },
  ],
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function renderDashboard() {
  return render(
    <MemoryRouter>
      <ComplianceDashboard />
    </MemoryRouter>
  );
}

function setPermissions({ isAdmin = true, hasPermission = () => true, userRole = 'admin' } = {}) {
  mockUsePermissions.mockReturnValue({ isAdmin, hasPermission, userRole });
}

function setApiSuccess() {
  mockGetOverview.mockResolvedValue({ data: overviewData });
  mockGetCertificationsByDepartment.mockResolvedValue({ data: departmentData });
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('ComplianceDashboard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setPermissions();
    setApiSuccess();
  });

  // 1. Loading state
  it('shows loading indicator while data is being fetched', () => {
    // Make the API calls hang so loading state persists
    mockGetOverview.mockReturnValue(new Promise(() => {}));
    mockGetCertificationsByDepartment.mockReturnValue(new Promise(() => {}));

    renderDashboard();

    expect(screen.getByText('Loading compliance data...')).toBeInTheDocument();
  });

  // 2. Access denied for unauthorized users
  it('shows access denied when user lacks compliance permissions', async () => {
    setPermissions({
      isAdmin: false,
      hasPermission: () => false,
      userRole: 'sales',
    });

    renderDashboard();

    expect(screen.getByText('Access Denied')).toBeInTheDocument();
    expect(
      screen.getByText("You don't have permission to view the Compliance Dashboard.")
    ).toBeInTheDocument();
  });

  // 3. Access denied navigation button works
  it('navigates to dashboard when "Return to Dashboard" is clicked on access denied', async () => {
    setPermissions({
      isAdmin: false,
      hasPermission: () => false,
      userRole: 'sales',
    });

    renderDashboard();

    fireEvent.click(screen.getByText('Return to Dashboard'));
    expect(mockNavigate).toHaveBeenCalledWith('/dashboard');
  });

  // 4. Overview metrics render correctly
  it('displays overview metric cards with correct values', async () => {
    renderDashboard();

    await waitFor(() => {
      expect(screen.getByText('42')).toBeInTheDocument();
    });

    // Total Active Users
    expect(screen.getByText('Total Active Users')).toBeInTheDocument();

    // Certifications Complete percentage
    expect(screen.getByText('85%')).toBeInTheDocument();
    expect(screen.getByText('Certifications Complete')).toBeInTheDocument();

    // Certified fraction
    expect(screen.getByText('36 / 42')).toBeInTheDocument();

    // Overdue count
    expect(screen.getByText('3')).toBeInTheDocument();
    expect(screen.getByText('Overdue Certifications')).toBeInTheDocument();

    // High-risk permissions count
    expect(screen.getByText('7')).toBeInTheDocument();
    expect(screen.getByText('High-Risk Permissions')).toBeInTheDocument();
  });

  // 5. Warning class applied when there are overdue certifications
  it('applies warning class to overdue certifications metric card when count > 0', async () => {
    renderDashboard();

    await waitFor(() => {
      expect(screen.getByText('Overdue Certifications')).toBeInTheDocument();
    });

    const overdueCard = screen.getByText('Overdue Certifications').closest('.metric-card');
    expect(overdueCard).toHaveClass('warning');
  });

  // 6. No warning class when overdue count is zero
  it('does not apply warning class when overdue certifications is 0', async () => {
    const noOverdueData = {
      ...overviewData,
      certifications: { ...overviewData.certifications, overdue: 0 },
    };
    mockGetOverview.mockResolvedValue({ data: noOverdueData });

    renderDashboard();

    await waitFor(() => {
      expect(screen.getByText('Overdue Certifications')).toBeInTheDocument();
    });

    const overdueCard = screen.getByText('Overdue Certifications').closest('.metric-card');
    expect(overdueCard).not.toHaveClass('warning');
  });

  // 7. Department table renders rows
  it('renders department breakdown table with correct data', async () => {
    renderDashboard();

    await waitFor(() => {
      expect(screen.getByText('Sales')).toBeInTheDocument();
    });

    expect(screen.getByText('Operations')).toBeInTheDocument();
    expect(screen.getByText('Compliance')).toBeInTheDocument();
    expect(screen.getByText('Certification Status by Department')).toBeInTheDocument();

    // Completion rate percentages in progress bars
    expect(screen.getByText('90%')).toBeInTheDocument();
    expect(screen.getByText('83%')).toBeInTheDocument();
    expect(screen.getByText('100%')).toBeInTheDocument();
  });

  // 8. Empty department table shows empty state
  it('shows empty state when no department data is available', async () => {
    mockGetCertificationsByDepartment.mockResolvedValue({ data: { departments: [] } });

    renderDashboard();

    await waitFor(() => {
      expect(screen.getByText('No department data available')).toBeInTheDocument();
    });
  });

  // 9. System summary section renders
  it('displays system summary section with correct values', async () => {
    renderDashboard();

    await waitFor(() => {
      expect(screen.getByText('System Summary')).toBeInTheDocument();
    });

    expect(screen.getByText('Total Permissions Granted')).toBeInTheDocument();
    expect(screen.getByText('128')).toBeInTheDocument();

    expect(screen.getByText('Recent Changes (30 days)')).toBeInTheDocument();
    expect(screen.getByText('14')).toBeInTheDocument();

    expect(screen.getByText('Pending Certifications')).toBeInTheDocument();
  });

  // 10. Error state when API fails
  it('shows error state and toast when API call fails', async () => {
    mockGetOverview.mockRejectedValue(new Error('Network error'));
    mockGetCertificationsByDepartment.mockRejectedValue(new Error('Network error'));

    renderDashboard();

    await waitFor(() => {
      expect(screen.getByText('Failed to load compliance data')).toBeInTheDocument();
    });

    expect(toast.error).toHaveBeenCalledWith(
      'Failed to load compliance data. Please ensure you have admin/management access.'
    );
  });

  // 11. Export CSV button triggers download
  it('calls exportReport with csv format when Export CSV is clicked', async () => {
    mockExportReport.mockResolvedValue({ data: new Blob(['test'], { type: 'text/csv' }) });

    renderDashboard();

    await waitFor(() => {
      expect(screen.getByText('Export CSV')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('Export CSV'));

    await waitFor(() => {
      expect(mockExportReport).toHaveBeenCalledWith('csv');
    });
  });

  // 12. Refresh button reloads data
  it('reloads data when Refresh button is clicked', async () => {
    renderDashboard();

    await waitFor(() => {
      expect(screen.getByText('Refresh')).toBeInTheDocument();
    });

    // Clear to track the refresh call
    mockGetOverview.mockClear();
    mockGetCertificationsByDepartment.mockClear();
    setApiSuccess();

    fireEvent.click(screen.getByText('Refresh'));

    await waitFor(() => {
      expect(mockGetOverview).toHaveBeenCalledTimes(1);
      expect(mockGetCertificationsByDepartment).toHaveBeenCalledTimes(1);
    });
  });
});
