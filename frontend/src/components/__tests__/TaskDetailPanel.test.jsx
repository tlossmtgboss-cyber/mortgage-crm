import React from 'react';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock('../shared/TaskDetailPanel.css', () => ({}));

// Mock react-router-dom
const mockNavigate = vi.fn();
vi.mock('react-router-dom', () => ({
  useNavigate: () => mockNavigate,
}));

// Mock toast
vi.mock('../../utils/toast', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
    info: vi.fn(),
  },
}));

// Mock sanitize
vi.mock('../../utils/sanitize', () => ({
  sanitizeHTML: (html) => html,
}));

// Mock services/api
vi.mock('../../services/api', () => ({
  aiAPI: {
    submitTrainingInstruction: vi.fn().mockResolvedValue({ acknowledgment: 'Training received!' }),
  },
  API_BASE_URL: 'http://localhost:8000',
}));

// Mock global fetch for SLA completion
const mockFetch = vi.fn();
global.fetch = mockFetch;

// localStorage mock
Object.defineProperty(window, 'localStorage', {
  value: {
    getItem: vi.fn(() => 'test-token'),
    setItem: vi.fn(),
    removeItem: vi.fn(),
  },
});

import TaskDetailPanel from '../shared/TaskDetailPanel';

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const baseTask = {
  id: 'task-1',
  title: 'Follow up with borrower',
  borrower: 'John Smith',
  stage: 'Pre-Qualified',
  urgency: 'high',
  priority: 'high',
  source: 'Workflow',
  sourceIcon: '⚙️',
  owner: 'Jane Agent',
  date_created: '2026-03-15T10:30:00Z',
  due_date: '2026-03-20T10:30:00Z',
  description: 'Follow up after initial contact',
  preferred_contact_method: 'Email',
  ai_message: 'Draft follow-up email for borrower',
  entity_type: 'lead',
  entity_id: 'lead-123',
  lead_id: 'lead-123',
  communication_history: [],
  days_until_due: 2,
};

const defaultHandlers = {
  onComplete: vi.fn(),
  onDelete: vi.fn(),
  onSnooze: vi.fn(),
  onDelegate: vi.fn(),
  onSend: vi.fn(),
  onApproveAi: vi.fn(),
  onChangeStatus: vi.fn(),
  onClose: vi.fn(),
};

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('TaskDetailPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({}),
    });
  });

  // -- 1. Empty state when no task is selected --
  it('shows empty state when no task is provided', () => {
    render(<TaskDetailPanel task={null} {...defaultHandlers} />);

    expect(screen.getByText(/select a task to view details/i)).toBeInTheDocument();
  });

  // -- 2. Renders task information correctly --
  it('displays task title, borrower, stage, and priority', () => {
    render(<TaskDetailPanel task={baseTask} {...defaultHandlers} />);

    expect(screen.getByText('Follow up with borrower')).toBeInTheDocument();
    expect(screen.getByText('John Smith')).toBeInTheDocument();
    expect(screen.getByText('Pre-Qualified')).toBeInTheDocument();
    // Priority/urgency badge
    expect(screen.getByText(/high/i)).toBeInTheDocument();
  });

  // -- 3. Displays source and owner fields --
  it('shows the source and owner information', () => {
    render(<TaskDetailPanel task={baseTask} {...defaultHandlers} />);

    expect(screen.getByText('Workflow')).toBeInTheDocument();
    expect(screen.getByText('Jane Agent')).toBeInTheDocument();
  });

  // -- 4. Shows due date with days-until-due badge --
  it('renders due date with a days-until-due badge', () => {
    const taskWithDue = { ...baseTask, days_until_due: 2 };
    render(<TaskDetailPanel task={taskWithDue} {...defaultHandlers} />);

    expect(screen.getByText(/in 2 days/i)).toBeInTheDocument();
  });

  // -- 5. Due today badge --
  it('shows "Today" badge when task is due today', () => {
    const taskDueToday = { ...baseTask, days_until_due: 0 };
    render(<TaskDetailPanel task={taskDueToday} {...defaultHandlers} />);

    expect(screen.getByText('Today')).toBeInTheDocument();
  });

  // -- 6. Communication method switching --
  it('allows switching between communication methods', () => {
    render(<TaskDetailPanel task={baseTask} {...defaultHandlers} />);

    // Default should be Email (from task.preferred_contact_method)
    const textBtn = screen.getByRole('button', { name: /text/i });
    fireEvent.click(textBtn);

    // After clicking Text, the text button should be active
    expect(textBtn.className).toContain('active');
  });

  // -- 7. Send button calls onSend with correct arguments --
  it('calls onSend with task id and communication method when send button is clicked', () => {
    render(
      <TaskDetailPanel
        task={baseTask}
        {...defaultHandlers}
        showActionBar={true}
      />
    );

    const sendBtn = screen.getByText(/send via email/i);
    fireEvent.click(sendBtn);

    expect(defaultHandlers.onSend).toHaveBeenCalledWith(
      'task-1',
      'Email',
      expect.any(String)
    );
  });

  // -- 8. Complete button calls onComplete --
  it('calls onComplete when the complete button is clicked', () => {
    render(
      <TaskDetailPanel
        task={baseTask}
        {...defaultHandlers}
        showActionBar={true}
      />
    );

    const completeBtn = screen.getByText(/complete/i);
    fireEvent.click(completeBtn);

    expect(defaultHandlers.onComplete).toHaveBeenCalledWith('task-1');
  });

  // -- 9. Close button calls onClose --
  it('calls onClose when the close button is clicked', () => {
    render(<TaskDetailPanel task={baseTask} {...defaultHandlers} />);

    // Close button renders as "x"
    const closeBtn = screen.getByRole('button', { name: /×/i });
    fireEvent.click(closeBtn);

    expect(defaultHandlers.onClose).toHaveBeenCalled();
  });

  // -- 10. Navigate to entity when borrower link is clicked --
  it('navigates to lead page when borrower name is clicked', () => {
    render(<TaskDetailPanel task={baseTask} {...defaultHandlers} />);

    const borrowerLink = screen.getByText('John Smith');
    fireEvent.click(borrowerLink);

    expect(mockNavigate).toHaveBeenCalledWith('/leads/lead-123');
  });

  // -- 11. Navigate to loan when entity_type is loan --
  it('navigates to loan page when entity is a loan', () => {
    const loanTask = {
      ...baseTask,
      entity_type: 'loan',
      entity_id: 'loan-456',
      lead_id: null,
      loan_id: 'loan-456',
      stage: 'processing',
    };

    render(<TaskDetailPanel task={loanTask} {...defaultHandlers} />);

    const borrowerLink = screen.getByText('John Smith');
    fireEvent.click(borrowerLink);

    expect(mockNavigate).toHaveBeenCalledWith('/loans/loan-456');
  });

  // -- 12. Urgency color mapping --
  it('applies correct urgency color for critical tasks', () => {
    const criticalTask = { ...baseTask, urgency: 'critical' };
    render(<TaskDetailPanel task={criticalTask} {...defaultHandlers} />);

    const badge = screen.getByText(/critical/i);
    // Critical color is #dc2626
    expect(badge.style.backgroundColor).toBe('rgb(220, 38, 38)');
  });

  // -- 13. Shows AI confidence badge when present --
  it('renders AI confidence badge when task has ai_confidence', () => {
    const aiTask = { ...baseTask, ai_confidence: 92, source: 'AI Engine' };
    render(<TaskDetailPanel task={aiTask} {...defaultHandlers} />);

    expect(screen.getByText(/ai confidence: 92%/i)).toBeInTheDocument();
  });

  // -- 14. Uses loan status options for active loan stages --
  it('uses loan status options for tasks with loan entity type', () => {
    const loanTask = {
      ...baseTask,
      entity_type: 'loan',
      stage: 'processing',
      loan_id: 'loan-1',
    };

    render(<TaskDetailPanel task={loanTask} {...defaultHandlers} />);

    // The stage displayed should still be 'processing'
    expect(screen.getByText('processing')).toBeInTheDocument();
  });
});
