import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock('../../shared/CallDetailPanel.css', () => ({}));

// Mock react-router-dom
const mockNavigate = vi.fn();
vi.mock('react-router-dom', () => ({
  useNavigate: () => mockNavigate,
}));

import CallDetailPanel from '../../shared/CallDetailPanel';

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const baseTask = {
  id: 'task-1',
  title: 'Follow up on rate quote',
  contact_name: 'John Smith',
  contact_phone: '(555) 123-4567',
  entity_type: 'lead',
  lead_id: 'lead-42',
  loan_id: null,
  task_type: 'call',
  priority: 'normal',
  description: 'Call to discuss updated rate options.',
  call_script: 'Hi John, this is [Name] calling about your rate quote...',
  workflow_name: null,
  due_date: null,
  stage: 'New',
};

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('CallDetailPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // --- 1. Empty state ---
  it('renders empty state when no task is provided', () => {
    render(<CallDetailPanel />);

    expect(screen.getByText('Select a call task to view details')).toBeInTheDocument();
  });

  // --- 2. Contact info display ---
  it('displays contact name and phone number', () => {
    render(<CallDetailPanel task={baseTask} />);

    expect(screen.getByText('John Smith')).toBeInTheDocument();
    expect(screen.getByText('(555) 123-4567')).toBeInTheDocument();
  });

  // --- 3. Call status: idle ---
  it('shows "Ready to dial" status when idle', () => {
    render(<CallDetailPanel task={baseTask} callStatus="idle" />);

    expect(screen.getByText('Ready to dial')).toBeInTheDocument();
  });

  // --- 4. Call status: dialing ---
  it('shows "Dialing..." status when dialing', () => {
    render(<CallDetailPanel task={baseTask} callStatus="dialing" />);

    expect(screen.getByText('Dialing...')).toBeInTheDocument();
  });

  // --- 5. Call status: in-progress ---
  it('shows "Call in progress" and end call button', () => {
    const mockEndCall = vi.fn();

    render(
      <CallDetailPanel
        task={baseTask}
        callStatus="in-progress"
        onEndCall={mockEndCall}
      />
    );

    expect(screen.getByText('Call in progress')).toBeInTheDocument();

    // End call button should be visible
    const endBtn = screen.getByText(/End Call/);
    expect(endBtn).toBeInTheDocument();

    fireEvent.click(endBtn);
    expect(mockEndCall).toHaveBeenCalledWith(baseTask);
  });

  // --- 6. Call status: completed ---
  it('shows "Call completed" status when call ends', () => {
    render(<CallDetailPanel task={baseTask} callStatus="completed" />);

    expect(screen.getByText('Call completed')).toBeInTheDocument();
  });

  // --- 7. Click to dial button in idle state ---
  it('shows Click to Dial button when idle and not in power dial', () => {
    const mockClickToDial = vi.fn();

    render(
      <CallDetailPanel
        task={baseTask}
        callStatus="idle"
        powerDialActive={false}
        onClickToDial={mockClickToDial}
      />
    );

    const dialBtn = screen.getByText(/Click to Dial/);
    expect(dialBtn).toBeInTheDocument();

    fireEvent.click(dialBtn);
    expect(mockClickToDial).toHaveBeenCalledWith(baseTask);
  });

  // --- 8. Priority badge display ---
  it('displays priority badge for non-normal priorities', () => {
    const highPriorityTask = { ...baseTask, priority: 'high' };

    const { container } = render(<CallDetailPanel task={highPriorityTask} />);

    const badge = container.querySelector('.priority-badge');
    expect(badge).toBeInTheDocument();
    expect(badge).toHaveTextContent('high');
  });

  // --- 9. Priority badge hidden for normal ---
  it('does not display priority badge for normal priority', () => {
    render(<CallDetailPanel task={baseTask} />);

    // Should not have a priority badge element
    const badges = screen.queryAllByText('normal');
    // One instance in the info grid ("Priority: Normal") is fine but no badge
    const badge = document.querySelector('.priority-badge');
    expect(badge).toBeNull();
  });

  // --- 10. Power dial progress display ---
  it('renders power dial progress bar when active', () => {
    render(
      <CallDetailPanel
        task={baseTask}
        callStatus="idle"
        powerDialActive={true}
        powerDialIndex={2}
        powerDialTotal={10}
      />
    );

    expect(screen.getByText('Power Dial Progress')).toBeInTheDocument();
    expect(screen.getByText('Contact 3 of 10')).toBeInTheDocument();
  });

  // --- 11. Power dial controls (skip, stop, next) ---
  it('renders power dial controls and fires callbacks', () => {
    const mockNext = vi.fn();
    const mockSkip = vi.fn();
    const mockStop = vi.fn();

    render(
      <CallDetailPanel
        task={baseTask}
        callStatus="idle"
        powerDialActive={true}
        powerDialIndex={1}
        powerDialTotal={5}
        onNextContact={mockNext}
        onSkipContact={mockSkip}
        onStopPowerDial={mockStop}
      />
    );

    fireEvent.click(screen.getByText(/Next/));
    expect(mockNext).toHaveBeenCalled();

    fireEvent.click(screen.getByText(/Skip/));
    expect(mockSkip).toHaveBeenCalled();

    fireEvent.click(screen.getByText(/Stop/));
    expect(mockStop).toHaveBeenCalled();
  });

  // --- 12. Navigate to lead on View Entity click ---
  it('navigates to lead detail page on View Lead click', () => {
    render(<CallDetailPanel task={baseTask} callStatus="idle" />);

    const viewBtn = screen.getByText(/View Lead/);
    fireEvent.click(viewBtn);

    expect(mockNavigate).toHaveBeenCalledWith('/leads/lead-42');
  });

  // --- 13. Navigate to loan on View Entity click ---
  it('navigates to loan detail page for loan entity type', () => {
    const loanTask = {
      ...baseTask,
      entity_type: 'loan',
      lead_id: null,
      loan_id: 'loan-99',
    };

    render(<CallDetailPanel task={loanTask} callStatus="idle" />);

    const viewBtn = screen.getByText(/View Loan/);
    fireEvent.click(viewBtn);

    expect(mockNavigate).toHaveBeenCalledWith('/loans/loan-99');
  });

  // --- 14. Task description and call script sections ---
  it('renders task description and call script when present', () => {
    render(<CallDetailPanel task={baseTask} />);

    expect(screen.getByText('Task Details')).toBeInTheDocument();
    expect(screen.getByText('Call to discuss updated rate options.')).toBeInTheDocument();

    expect(screen.getByText('Call Script')).toBeInTheDocument();
    expect(screen.getByText(/Hi John, this is/)).toBeInTheDocument();
  });

  // --- 15. Complete task button ---
  it('calls onComplete when Complete Task button is clicked', () => {
    const mockComplete = vi.fn();

    render(
      <CallDetailPanel
        task={baseTask}
        callStatus="idle"
        onComplete={mockComplete}
      />
    );

    const completeBtn = screen.getByText(/Complete Task/);
    fireEvent.click(completeBtn);

    expect(mockComplete).toHaveBeenCalledWith('task-1');
  });

  // --- 16. Compact mode ---
  it('applies compact class when compact prop is true', () => {
    const { container } = render(
      <CallDetailPanel task={baseTask} compact={true} />
    );

    expect(container.querySelector('.call-detail-panel.compact')).toBeInTheDocument();
  });
});
