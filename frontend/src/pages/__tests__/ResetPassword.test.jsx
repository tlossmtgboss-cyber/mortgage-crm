import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

const mockNavigate = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return { ...actual, useNavigate: () => mockNavigate };
});

vi.mock('../../services/api', () => ({
  API_BASE_URL: 'http://localhost:8000',
}));

vi.mock('../Login.css', () => ({}));

// Mock global fetch
const mockFetch = vi.fn();

import ResetPassword from '../ResetPassword';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function renderResetPassword(route = '/reset-password?token=valid-reset-token') {
  return render(
    <MemoryRouter initialEntries={[route]}>
      <ResetPassword />
    </MemoryRouter>
  );
}

function mockFetchResponse(body, status = 200) {
  return Promise.resolve({
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(body),
  });
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('ResetPassword', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers({ shouldAdvanceTime: true });
    global.fetch = mockFetch;
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  // --- Missing token ---

  it('shows invalid link message when no token is in the URL', () => {
    renderResetPassword('/reset-password');

    expect(screen.getByRole('heading', { name: /invalid link/i })).toBeInTheDocument();
    expect(
      screen.getByText(/this password reset link is invalid or has expired/i)
    ).toBeInTheDocument();
  });

  it('shows a link to request a new reset when token is missing', () => {
    renderResetPassword('/reset-password');

    const link = screen.getByRole('link', { name: /request new link/i });
    expect(link).toBeInTheDocument();
    expect(link).toHaveAttribute('href', '/forgot-password');
  });

  // --- Rendering (with token) ---

  it('renders the password form when a token is present', () => {
    renderResetPassword();

    expect(screen.getByRole('heading', { name: /set new password/i })).toBeInTheDocument();
    expect(screen.getByLabelText(/new password/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/confirm password/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /reset password/i })).toBeInTheDocument();
  });

  it('renders a back to login link on the form', () => {
    renderResetPassword();

    const backLink = screen.getByRole('link', { name: /back to login/i });
    expect(backLink).toBeInTheDocument();
    expect(backLink).toHaveAttribute('href', '/login');
  });

  // --- Accessibility ---

  it('has properly associated labels for password fields', () => {
    renderResetPassword();

    const newPasswordInput = screen.getByLabelText(/new password/i);
    const confirmPasswordInput = screen.getByLabelText(/confirm password/i);

    expect(newPasswordInput).toHaveAttribute('type', 'password');
    expect(newPasswordInput).toHaveAttribute('id', 'password');
    expect(confirmPasswordInput).toHaveAttribute('type', 'password');
    expect(confirmPasswordInput).toHaveAttribute('id', 'confirmPassword');
  });

  it('marks both password inputs as required', () => {
    renderResetPassword();

    expect(screen.getByLabelText(/new password/i)).toBeRequired();
    expect(screen.getByLabelText(/confirm password/i)).toBeRequired();
  });

  // --- Client-side validation ---

  it('shows error when passwords do not match', async () => {
    renderResetPassword();
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });

    await user.type(screen.getByLabelText(/new password/i), 'password123');
    await user.type(screen.getByLabelText(/confirm password/i), 'different456');
    await user.click(screen.getByRole('button', { name: /reset password/i }));

    await waitFor(() => {
      expect(screen.getByText(/passwords do not match/i)).toBeInTheDocument();
    });

    // Should not have called the API
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it('shows error when password is too short', async () => {
    renderResetPassword();
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });

    await user.type(screen.getByLabelText(/new password/i), 'short');
    await user.type(screen.getByLabelText(/confirm password/i), 'short');
    await user.click(screen.getByRole('button', { name: /reset password/i }));

    await waitFor(() => {
      expect(
        screen.getByText(/password must be at least 6 characters/i)
      ).toBeInTheDocument();
    });

    expect(mockFetch).not.toHaveBeenCalled();
  });

  // --- Loading state ---

  it('shows loading text and disables controls while submitting', async () => {
    mockFetch.mockReturnValue(new Promise(() => {})); // never resolves

    renderResetPassword();
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });

    await user.type(screen.getByLabelText(/new password/i), 'newpassword123');
    await user.type(screen.getByLabelText(/confirm password/i), 'newpassword123');
    await user.click(screen.getByRole('button', { name: /reset password/i }));

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /resetting/i })).toBeDisabled();
      expect(screen.getByLabelText(/new password/i)).toBeDisabled();
      expect(screen.getByLabelText(/confirm password/i)).toBeDisabled();
    });
  });

  // --- Successful reset ---

  it('shows success message and hides the form after successful reset', async () => {
    mockFetch.mockReturnValue(
      mockFetchResponse({ message: 'Password has been reset successfully.' })
    );

    renderResetPassword();
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });

    await user.type(screen.getByLabelText(/new password/i), 'newpassword123');
    await user.type(screen.getByLabelText(/confirm password/i), 'newpassword123');
    await user.click(screen.getByRole('button', { name: /reset password/i }));

    await waitFor(() => {
      expect(
        screen.getByText(/password has been reset successfully/i)
      ).toBeInTheDocument();
      expect(screen.getByText(/redirecting to login/i)).toBeInTheDocument();
    });

    // Form should be gone
    expect(screen.queryByLabelText(/new password/i)).not.toBeInTheDocument();
  });

  it('sends correct payload to the reset-password endpoint', async () => {
    mockFetch.mockReturnValue(
      mockFetchResponse({ message: 'Password has been reset successfully.' })
    );

    renderResetPassword('/reset-password?token=my-secret-token');
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });

    await user.type(screen.getByLabelText(/new password/i), 'newpassword123');
    await user.type(screen.getByLabelText(/confirm password/i), 'newpassword123');
    await user.click(screen.getByRole('button', { name: /reset password/i }));

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith(
        'http://localhost:8000/api/v1/auth/reset-password',
        expect.objectContaining({
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            token: 'my-secret-token',
            new_password: 'newpassword123',
          }),
        })
      );
    });
  });

  it('redirects to login after 3 seconds on success', async () => {
    mockFetch.mockReturnValue(
      mockFetchResponse({ message: 'Password has been reset successfully.' })
    );

    renderResetPassword();
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });

    await user.type(screen.getByLabelText(/new password/i), 'newpassword123');
    await user.type(screen.getByLabelText(/confirm password/i), 'newpassword123');
    await user.click(screen.getByRole('button', { name: /reset password/i }));

    await waitFor(() => {
      expect(screen.getByText(/password has been reset/i)).toBeInTheDocument();
    });

    // Advance timers to trigger the redirect
    vi.advanceTimersByTime(3000);

    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith('/login');
    });
  });

  // --- Error handling ---

  it('displays server error from API response detail', async () => {
    mockFetch.mockReturnValue(
      mockFetchResponse({ detail: 'Token expired' }, 400)
    );

    renderResetPassword();
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });

    await user.type(screen.getByLabelText(/new password/i), 'newpassword123');
    await user.type(screen.getByLabelText(/confirm password/i), 'newpassword123');
    await user.click(screen.getByRole('button', { name: /reset password/i }));

    await waitFor(() => {
      expect(screen.getByText('Token expired')).toBeInTheDocument();
    });

    // Form should still be visible
    expect(screen.getByLabelText(/new password/i)).toBeInTheDocument();
  });

  it('displays fallback error when server provides no detail', async () => {
    mockFetch.mockReturnValue(
      mockFetchResponse({}, 500)
    );

    renderResetPassword();
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });

    await user.type(screen.getByLabelText(/new password/i), 'newpassword123');
    await user.type(screen.getByLabelText(/confirm password/i), 'newpassword123');
    await user.click(screen.getByRole('button', { name: /reset password/i }));

    await waitFor(() => {
      expect(
        screen.getByText(/failed to reset password/i)
      ).toBeInTheDocument();
    });
  });

  it('displays a generic error on network failure', async () => {
    mockFetch.mockRejectedValue(new Error('Network Error'));

    renderResetPassword();
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });

    await user.type(screen.getByLabelText(/new password/i), 'newpassword123');
    await user.type(screen.getByLabelText(/confirm password/i), 'newpassword123');
    await user.click(screen.getByRole('button', { name: /reset password/i }));

    await waitFor(() => {
      expect(
        screen.getByText(/an error occurred.*please try again later/i)
      ).toBeInTheDocument();
    });
  });
});
