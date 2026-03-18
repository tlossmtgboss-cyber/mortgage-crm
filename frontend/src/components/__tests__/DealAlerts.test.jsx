import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

// ---------------------------------------------------------------------------
// Mocks -- must come before component import
// ---------------------------------------------------------------------------

const mockNavigate = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return { ...actual, useNavigate: () => mockNavigate };
});

vi.mock('@/utils/toast', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
    info: vi.fn(),
    warning: vi.fn(),
  },
}));

vi.mock('./DealAlerts.css', () => ({}));
vi.mock('../DealAlerts.css', () => ({}));

import { AlertPriorityBadge, AlertCard, DealAlertsBell, DealAlertsDashboard } from '../DealAlerts';
import { toast } from '@/utils/toast';

// ---------------------------------------------------------------------------
// Test Data
// ---------------------------------------------------------------------------

const complianceAlert = {
  id: 'alert-1',
  type: 'compliance_deadline',
  title: 'TRID Disclosure Deadline',
  message: 'Initial LE must be sent within 3 business days of application',
  priority: 'critical',
  status: 'active',
  loan_id: 'loan-123',
  loan_number: 'LN-2026-001',
  borrower_name: 'John Smith',
  created_at: new Date(Date.now() - 3600000).toISOString(), // 1 hour ago
  due_date: new Date(Date.now() + 86400000).toISOString(), // tomorrow
  recommended_action: 'Send initial LE disclosures immediately',
  tags: ['trid', 'disclosure', 'urgent'],
};

const slaAlert = {
  id: 'alert-2',
  type: 'sla_at_risk',
  title: 'SLA At Risk: Processing',
  message: 'Loan has been in processing for 12 days (target: 7)',
  priority: 'high',
  status: 'acknowledged',
  loan_id: 'loan-456',
  loan_number: 'LN-2026-002',
  borrower_name: 'Jane Doe',
  created_at: new Date(Date.now() - 172800000).toISOString(), // 2 days ago
  due_date: null,
  recommended_action: null,
  tags: ['sla'],
};

const lowPriorityAlert = {
  id: 'alert-3',
  type: 'document_missing',
  title: 'Missing W-2 Documents',
  message: 'W-2 documents not received for 2024 tax year',
  priority: 'low',
  status: 'active',
  loan_id: 'loan-789',
  loan_number: 'LN-2026-003',
  borrower_name: 'Bob Johnson',
  created_at: new Date(Date.now() - 604800000).toISOString(), // 7 days ago
  due_date: null,
  recommended_action: null,
  tags: [],
};

const resolvedAlert = {
  ...complianceAlert,
  id: 'alert-4',
  status: 'resolved',
};

const alertSummary = {
  total_alerts: 15,
  critical_count: 3,
  high_count: 5,
  loans_at_risk: 4,
  alerts_today: 2,
  resolved_today: 1,
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const mockFetch = vi.fn();

function setupFetchMock() {
  global.fetch = mockFetch;
}

function mockFetchResponse(body, ok = true) {
  return Promise.resolve({
    ok,
    status: ok ? 200 : 500,
    json: () => Promise.resolve(body),
  });
}

// ---------------------------------------------------------------------------
// Tests: AlertPriorityBadge
// ---------------------------------------------------------------------------

describe('AlertPriorityBadge', () => {
  it('renders correct label and class for each priority level', () => {
    const priorities = [
      { value: 'critical', label: 'Critical', className: 'priority-critical' },
      { value: 'high', label: 'High', className: 'priority-high' },
      { value: 'medium', label: 'Medium', className: 'priority-medium' },
      { value: 'low', label: 'Low', className: 'priority-low' },
    ];

    priorities.forEach(({ value, label, className }) => {
      const { container, unmount } = render(<AlertPriorityBadge priority={value} />);
      const badge = container.querySelector('.alert-priority-badge');
      expect(badge).toHaveTextContent(label);
      expect(badge).toHaveClass(className);
      unmount();
    });
  });

  it('falls back to Medium styling for unknown priority', () => {
    const { container } = render(<AlertPriorityBadge priority="unknown" />);
    const badge = container.querySelector('.alert-priority-badge');
    expect(badge).toHaveTextContent('Medium');
    expect(badge).toHaveClass('priority-medium');
  });
});

// ---------------------------------------------------------------------------
// Tests: AlertCard
// ---------------------------------------------------------------------------

describe('AlertCard', () => {
  const mockOnAcknowledge = vi.fn().mockResolvedValue(undefined);
  const mockOnResolve = vi.fn().mockResolvedValue(undefined);
  const mockOnSnooze = vi.fn().mockResolvedValue(undefined);
  const mockOnViewLoan = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  // 1. Renders alert title and message
  it('renders alert title, message, and borrower info', () => {
    render(
      <AlertCard
        alert={complianceAlert}
        onAcknowledge={mockOnAcknowledge}
        onResolve={mockOnResolve}
        onSnooze={mockOnSnooze}
        onViewLoan={mockOnViewLoan}
      />
    );

    expect(screen.getByText('TRID Disclosure Deadline')).toBeInTheDocument();
    expect(screen.getByText('Initial LE must be sent within 3 business days of application')).toBeInTheDocument();
    expect(screen.getByText(/John Smith/)).toBeInTheDocument();
    expect(screen.getByText(/LN-2026-001/)).toBeInTheDocument();
  });

  // 2. Shows priority badge with correct severity
  it('shows Critical priority badge for critical compliance alert', () => {
    const { container } = render(
      <AlertCard alert={complianceAlert} />
    );

    const badge = container.querySelector('.alert-priority-badge');
    expect(badge).toHaveTextContent('Critical');
    expect(badge).toHaveClass('priority-critical');
  });

  // 3. Displays recommended action when present
  it('displays recommended action when provided', () => {
    render(<AlertCard alert={complianceAlert} />);

    expect(screen.getByText(/Recommended:/)).toBeInTheDocument();
    expect(screen.getByText(/Send initial LE disclosures immediately/)).toBeInTheDocument();
  });

  // 4. Does not display recommended action when absent
  it('does not show recommended action section when not provided', () => {
    render(<AlertCard alert={slaAlert} />);

    expect(screen.queryByText(/Recommended:/)).not.toBeInTheDocument();
  });

  // 5. Renders tags
  it('renders compliance-related tags on the alert card', () => {
    render(<AlertCard alert={complianceAlert} />);

    expect(screen.getByText('trid')).toBeInTheDocument();
    expect(screen.getByText('disclosure')).toBeInTheDocument();
    expect(screen.getByText('urgent')).toBeInTheDocument();
  });

  // 6. Due date deadline indicator displays
  it('shows due date deadline indicator when due_date is present', () => {
    render(<AlertCard alert={complianceAlert} />);

    const dueText = screen.getByText(/Due:/);
    expect(dueText).toBeInTheDocument();
  });

  // 7. Compact mode shows minimal info
  it('renders compact card with title and priority badge', () => {
    const { container } = render(
      <AlertCard alert={complianceAlert} compact onViewLoan={mockOnViewLoan} />
    );

    expect(screen.getByText('TRID Disclosure Deadline')).toBeInTheDocument();
    expect(screen.getByText('Critical')).toBeInTheDocument();
    expect(screen.getByText('LN-2026-001')).toBeInTheDocument();

    // Compact card should have the compact class
    expect(container.querySelector('.alert-card.compact')).toBeInTheDocument();
  });

  // 8. Compact mode triggers onViewLoan on click
  it('calls onViewLoan when compact alert card is clicked', () => {
    const { container } = render(
      <AlertCard alert={complianceAlert} compact onViewLoan={mockOnViewLoan} />
    );

    const card = container.querySelector('.alert-card.compact');
    fireEvent.click(card);

    expect(mockOnViewLoan).toHaveBeenCalledWith('loan-123');
  });

  // 9. Acknowledge button not shown for already-acknowledged alerts
  it('does not show Acknowledge button for already-acknowledged alerts', () => {
    const { container } = render(
      <AlertCard
        alert={slaAlert}
        onAcknowledge={mockOnAcknowledge}
        onResolve={mockOnResolve}
        onSnooze={mockOnSnooze}
        onViewLoan={mockOnViewLoan}
      />
    );

    // Simulate hover to show actions
    const card = container.querySelector('.alert-card');
    fireEvent.mouseEnter(card);

    // Should show Resolve but not Acknowledge (slaAlert is already acknowledged)
    expect(screen.queryByText('Acknowledge')).not.toBeInTheDocument();
    expect(screen.getByText('Resolve')).toBeInTheDocument();
  });

  // 10. Actions not shown for resolved alerts
  it('does not show action buttons for resolved alerts', () => {
    const { container } = render(
      <AlertCard
        alert={resolvedAlert}
        onAcknowledge={mockOnAcknowledge}
        onResolve={mockOnResolve}
      />
    );

    const card = container.querySelector('.alert-card');
    fireEvent.mouseEnter(card);

    expect(screen.queryByText('Acknowledge')).not.toBeInTheDocument();
    expect(screen.queryByText('Resolve')).not.toBeInTheDocument();
    expect(screen.queryByText('Snooze')).not.toBeInTheDocument();
  });

  // 11. Alert card has correct priority class
  it('applies priority class to the alert card container', () => {
    const { container: c1 } = render(<AlertCard alert={complianceAlert} />);
    expect(c1.querySelector('.alert-card.critical')).toBeInTheDocument();

    const { container: c2 } = render(<AlertCard alert={slaAlert} />);
    expect(c2.querySelector('.alert-card.high')).toBeInTheDocument();

    const { container: c3 } = render(<AlertCard alert={lowPriorityAlert} />);
    expect(c3.querySelector('.alert-card.low')).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Tests: DealAlertsBell
// ---------------------------------------------------------------------------

describe('DealAlertsBell', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setupFetchMock();
    localStorage.setItem('token', 'test-token');
  });

  afterEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
  });

  // 1. Renders bell icon
  it('renders bell icon button', async () => {
    mockFetch.mockResolvedValue(mockFetchResponse(alertSummary, false));

    render(
      <MemoryRouter>
        <DealAlertsBell userId="user-1" />
      </MemoryRouter>
    );

    expect(screen.getByRole('button')).toBeInTheDocument();
  });

  // 2. Shows alert count badge
  it('shows badge with total alert count after fetching summary', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(alertSummary),
    });

    render(
      <MemoryRouter>
        <DealAlertsBell userId="user-1" />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText('15')).toBeInTheDocument();
    });
  });

  // 3. Applies critical class when critical alerts exist
  it('applies has-critical class to bell when critical alerts exist', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(alertSummary),
    });

    render(
      <MemoryRouter>
        <DealAlertsBell userId="user-1" />
      </MemoryRouter>
    );

    await waitFor(() => {
      const button = screen.getByRole('button');
      expect(button).toHaveClass('has-critical');
    });
  });

  // 4. Opens dropdown on click and shows severity counts
  it('opens dropdown with critical and high severity counts', async () => {
    let callCount = 0;
    mockFetch.mockImplementation(() => {
      callCount++;
      if (callCount <= 1) {
        // Summary call
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve(alertSummary),
        });
      }
      // Alerts call when dropdown opens
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve([complianceAlert, slaAlert]),
      });
    });

    render(
      <MemoryRouter>
        <DealAlertsBell userId="user-1" />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText('15')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button'));

    await waitFor(() => {
      expect(screen.getByText('Deal Alerts')).toBeInTheDocument();
    });

    expect(screen.getByText('3 Critical')).toBeInTheDocument();
    expect(screen.getByText('5 High')).toBeInTheDocument();
  });

  // 5. Shows 99+ for large counts
  it('shows 99+ badge when total alerts exceed 99', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ ...alertSummary, total_alerts: 150 }),
    });

    render(
      <MemoryRouter>
        <DealAlertsBell userId="user-1" />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText('99+')).toBeInTheDocument();
    });
  });

  // 6. No badge when zero alerts
  it('does not show badge when there are no alerts', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ ...alertSummary, total_alerts: 0, critical_count: 0 }),
    });

    const { container } = render(
      <MemoryRouter>
        <DealAlertsBell userId="user-1" />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(container.querySelector('.badge')).not.toBeInTheDocument();
    });
  });

  // 7. View All Alerts navigates to deal-alerts page
  it('navigates to /deal-alerts when View All Alerts is clicked', async () => {
    let callCount = 0;
    mockFetch.mockImplementation(() => {
      callCount++;
      if (callCount <= 1) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve(alertSummary),
        });
      }
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve([]),
      });
    });

    render(
      <MemoryRouter>
        <DealAlertsBell userId="user-1" />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByRole('button')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button'));

    await waitFor(() => {
      expect(screen.getByText('View All Alerts')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('View All Alerts'));
    expect(mockNavigate).toHaveBeenCalledWith('/deal-alerts');
  });

  // 8. Empty dropdown shows "No active alerts" message
  it('shows "No active alerts" when dropdown is open but no alerts exist', async () => {
    let callCount = 0;
    mockFetch.mockImplementation(() => {
      callCount++;
      if (callCount <= 1) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ ...alertSummary, total_alerts: 0, critical_count: 0 }),
        });
      }
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve([]),
      });
    });

    render(
      <MemoryRouter>
        <DealAlertsBell userId="user-1" />
      </MemoryRouter>
    );

    // Wait for initial fetch
    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalled();
    });

    fireEvent.click(screen.getByRole('button'));

    await waitFor(() => {
      expect(screen.getByText('No active alerts')).toBeInTheDocument();
    });
  });
});
