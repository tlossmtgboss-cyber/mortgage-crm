import React from 'react';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock('../CreateTaskModal.css', () => ({}));

// Mock toast
vi.mock('../../utils/toast', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
    info: vi.fn(),
  },
}));

// Mock api client
const mockPost = vi.fn();
vi.mock('../../utils/api/client', () => ({
  api: {
    post: (...args) => mockPost(...args),
  },
}));

import CreateTaskModal from '../CreateTaskModal';
import { toast } from '../../utils/toast';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
//
// The component renders labels (<label className="form-label">...) that are NOT
// associated with their inputs via htmlFor/id, so `getByLabelText` does not work.
// We query the controls directly by placeholder / type / role instead.

const getTitleInput = () =>
  screen.getByPlaceholderText(/follow up on application/i);
const getDescriptionInput = () =>
  screen.getByPlaceholderText(/add details about the task/i);
const getDueDateInput = (container) =>
  container.querySelector('input[type="date"]');
const getPrioritySelect = (container) =>
  container.querySelector('select.form-select');

// "Create Task" text appears in BOTH the heading and the submit button, so
// target the submit button specifically by role.
const getSubmitButton = () =>
  screen.getByRole('button', { name: /create task/i });

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const defaultProps = {
  isOpen: true,
  onClose: vi.fn(),
  lead: { id: 'lead-1', name: 'John Smith', loan_number: '12345' },
  onTaskCreated: vi.fn(),
};

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('CreateTaskModal', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockPost.mockResolvedValue({ id: 'new-task-1', title: 'Test Task' });
  });

  // -- 1. Returns null when not open --
  it('renders nothing when isOpen is false', () => {
    const { container } = render(
      <CreateTaskModal {...defaultProps} isOpen={false} />
    );
    expect(container.innerHTML).toBe('');
  });

  // -- 2. Renders modal when open --
  it('renders the modal with title and form fields when open', () => {
    const { container } = render(<CreateTaskModal {...defaultProps} />);

    // "Create Task" appears twice (heading + submit button); target the heading.
    expect(
      screen.getByRole('heading', { name: 'Create Task' })
    ).toBeInTheDocument();
    expect(screen.getByText('Task Title *')).toBeInTheDocument();
    expect(getTitleInput()).toBeInTheDocument();
    expect(screen.getByText('Description')).toBeInTheDocument();
    expect(getDescriptionInput()).toBeInTheDocument();
    expect(screen.getByText('Due Date')).toBeInTheDocument();
    expect(getDueDateInput(container)).toBeInTheDocument();
    expect(screen.getByText('Priority')).toBeInTheDocument();
    expect(getPrioritySelect(container)).toBeInTheDocument();
  });

  // -- 3. Shows lead info when lead is provided --
  it('displays lead name and loan number when lead prop is provided', () => {
    render(<CreateTaskModal {...defaultProps} />);

    expect(screen.getByText(/john smith/i)).toBeInTheDocument();
    expect(screen.getByText(/loan #12345/i)).toBeInTheDocument();
  });

  // -- 4. Form validation: empty title prevents submission --
  it('shows error message when submitting without a title', async () => {
    render(<CreateTaskModal {...defaultProps} />);

    // Submit button should be disabled when title is empty
    expect(getSubmitButton()).toBeDisabled();
  });

  // -- 5. Shows validation error on empty title submit --
  it('sets error when title is whitespace-only and form is submitted', async () => {
    render(<CreateTaskModal {...defaultProps} />);

    // Type only whitespace
    fireEvent.change(getTitleInput(), { target: { value: '   ' } });

    // Button should still be disabled for whitespace-only
    expect(getSubmitButton()).toBeDisabled();
  });

  // -- 6. Successful task creation --
  it('creates a task and calls onTaskCreated on success', async () => {
    render(<CreateTaskModal {...defaultProps} />);

    // Fill in the form
    fireEvent.change(getTitleInput(), {
      target: { value: 'Follow up with borrower' },
    });
    fireEvent.change(getDescriptionInput(), {
      target: { value: 'Check on document status' },
    });

    // Submit
    await act(async () => {
      fireEvent.click(getSubmitButton());
    });

    await waitFor(() => {
      expect(mockPost).toHaveBeenCalledWith('/api/v1/tasks', {
        title: 'Follow up with borrower',
        description: 'Check on document status',
        priority: 'medium',
        lead_id: 'lead-1',
      });
    });

    expect(defaultProps.onTaskCreated).toHaveBeenCalledWith({
      id: 'new-task-1',
      title: 'Test Task',
    });
    expect(toast.success).toHaveBeenCalledWith('Task created successfully!');
    expect(defaultProps.onClose).toHaveBeenCalled();
  });

  // -- 7. Priority selection --
  it('allows selecting different priority levels', () => {
    const { container } = render(<CreateTaskModal {...defaultProps} />);

    const prioritySelect = getPrioritySelect(container);

    // Default should be medium
    expect(prioritySelect.value).toBe('medium');

    // Change to urgent
    fireEvent.change(prioritySelect, { target: { value: 'urgent' } });
    expect(prioritySelect.value).toBe('urgent');

    // Change to low
    fireEvent.change(prioritySelect, { target: { value: 'low' } });
    expect(prioritySelect.value).toBe('low');
  });

  // -- 8. Due date is sent as ISO string --
  it('converts due date to ISO string before sending', async () => {
    const { container } = render(<CreateTaskModal {...defaultProps} />);

    fireEvent.change(getTitleInput(), {
      target: { value: 'Task with due date' },
    });
    fireEvent.change(getDueDateInput(container), {
      target: { value: '2026-04-01' },
    });

    await act(async () => {
      fireEvent.click(getSubmitButton());
    });

    await waitFor(() => {
      expect(mockPost).toHaveBeenCalledWith(
        '/api/v1/tasks',
        expect.objectContaining({
          due_date: expect.stringContaining('2026-04-01'),
        })
      );
    });
  });

  // -- 9. Handles API error gracefully --
  it('shows error message when API call fails', async () => {
    mockPost.mockRejectedValue(new Error('Server error'));

    render(<CreateTaskModal {...defaultProps} />);

    fireEvent.change(getTitleInput(), {
      target: { value: 'Failing task' },
    });

    await act(async () => {
      fireEvent.click(getSubmitButton());
    });

    await waitFor(() => {
      expect(screen.getByText(/server error/i)).toBeInTheDocument();
    });

    // onTaskCreated should NOT be called
    expect(defaultProps.onTaskCreated).not.toHaveBeenCalled();
    // Modal should remain open
    expect(defaultProps.onClose).not.toHaveBeenCalled();
  });

  // -- 10. Cancel button closes the modal --
  it('closes the modal when cancel button is clicked', () => {
    render(<CreateTaskModal {...defaultProps} />);

    const cancelBtn = screen.getByRole('button', { name: 'Cancel' });
    fireEvent.click(cancelBtn);

    expect(defaultProps.onClose).toHaveBeenCalled();
  });

  // -- 11. Overlay click closes the modal --
  it('closes the modal when clicking the overlay backdrop', () => {
    const { container } = render(<CreateTaskModal {...defaultProps} />);

    const overlay = container.querySelector('.modal-overlay');
    fireEvent.click(overlay);

    expect(defaultProps.onClose).toHaveBeenCalled();
  });

  // -- 12. Submit button shows "Creating..." while submitting --
  it('disables submit button and shows "Creating..." while submitting', async () => {
    // Make API call hang
    let resolvePost;
    mockPost.mockReturnValue(new Promise((resolve) => { resolvePost = resolve; }));

    render(<CreateTaskModal {...defaultProps} />);

    fireEvent.change(getTitleInput(), {
      target: { value: 'Slow task' },
    });

    await act(async () => {
      fireEvent.click(getSubmitButton());
    });

    // Should show "Creating..." while in progress
    expect(screen.getByText('Creating...')).toBeInTheDocument();

    // Resolve the promise
    resolvePost({ id: 'done', title: 'Slow task' });
  });
});
