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
    render(<CreateTaskModal {...defaultProps} />);

    expect(screen.getByText('Create Task')).toBeInTheDocument();
    expect(screen.getByLabelText(/task title/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/description/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/due date/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/priority/i)).toBeInTheDocument();
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

    const submitBtn = screen.getByText('Create Task');
    // Submit button should be disabled when title is empty
    expect(submitBtn).toBeDisabled();
  });

  // -- 5. Shows validation error on empty title submit --
  it('sets error when title is whitespace-only and form is submitted', async () => {
    render(<CreateTaskModal {...defaultProps} />);

    // Type only whitespace
    const titleInput = screen.getByLabelText(/task title/i);
    fireEvent.change(titleInput, { target: { value: '   ' } });

    const submitBtn = screen.getByText('Create Task');
    // Button should still be disabled for whitespace-only
    expect(submitBtn).toBeDisabled();
  });

  // -- 6. Successful task creation --
  it('creates a task and calls onTaskCreated on success', async () => {
    render(<CreateTaskModal {...defaultProps} />);

    // Fill in the form
    fireEvent.change(screen.getByLabelText(/task title/i), {
      target: { value: 'Follow up with borrower' },
    });
    fireEvent.change(screen.getByLabelText(/description/i), {
      target: { value: 'Check on document status' },
    });

    // Submit
    const submitBtn = screen.getByText('Create Task');
    await act(async () => {
      fireEvent.click(submitBtn);
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
    render(<CreateTaskModal {...defaultProps} />);

    const prioritySelect = screen.getByLabelText(/priority/i);

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
    render(<CreateTaskModal {...defaultProps} />);

    fireEvent.change(screen.getByLabelText(/task title/i), {
      target: { value: 'Task with due date' },
    });
    fireEvent.change(screen.getByLabelText(/due date/i), {
      target: { value: '2026-04-01' },
    });

    const submitBtn = screen.getByText('Create Task');
    await act(async () => {
      fireEvent.click(submitBtn);
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

    fireEvent.change(screen.getByLabelText(/task title/i), {
      target: { value: 'Failing task' },
    });

    const submitBtn = screen.getByText('Create Task');
    await act(async () => {
      fireEvent.click(submitBtn);
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

    const cancelBtn = screen.getByText('Cancel');
    fireEvent.click(cancelBtn);

    expect(defaultProps.onClose).toHaveBeenCalled();
  });

  // -- 11. Overlay click closes the modal --
  it('closes the modal when clicking the overlay backdrop', () => {
    render(<CreateTaskModal {...defaultProps} />);

    const overlay = screen.getByText('Create Task').closest('.modal-overlay');
    fireEvent.click(overlay);

    expect(defaultProps.onClose).toHaveBeenCalled();
  });

  // -- 12. Submit button shows "Creating..." while submitting --
  it('disables submit button and shows "Creating..." while submitting', async () => {
    // Make API call hang
    let resolvePost;
    mockPost.mockReturnValue(new Promise((resolve) => { resolvePost = resolve; }));

    render(<CreateTaskModal {...defaultProps} />);

    fireEvent.change(screen.getByLabelText(/task title/i), {
      target: { value: 'Slow task' },
    });

    const submitBtn = screen.getByText('Create Task');
    await act(async () => {
      fireEvent.click(submitBtn);
    });

    // Should show "Creating..." while in progress
    expect(screen.getByText('Creating...')).toBeInTheDocument();

    // Resolve the promise
    resolvePost({ id: 'done', title: 'Slow task' });
  });
});
