import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock('../../services/api', () => ({
  API_BASE_URL: 'http://localhost:8000',
}));

vi.mock('../Login.css', () => ({}));

// Mock global fetch
const mockFetch = vi.fn();

import ForgotPassword from '../ForgotPassword';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function renderForgotPassword() {
  return render(
    <MemoryRouter initialEntries={['/forgot-password']}>
      <ForgotPassword />
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

describe('ForgotPassword', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    global.fetch = mockFetch;
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  // --- Rendering ---

  it('renders the heading and description text', () => {
    renderForgotPassword();

    expect(screen.getByRole('heading', { name: /reset password/i })).toBeInTheDocument();
    expect(screen.getByText(/enter your email to receive a reset link/i)).toBeInTheDocument();
  });

  it('renders the email input with proper label', () => {
    renderForgotPassword();

    const emailInput = screen.getByLabelText(/email address/i);
    expect(emailInput).toBeInTheDocument();
    expect(emailInput).toHaveAttribute('type', 'email');
    expect(emailInput).toHaveAttribute('id', 'email');
  });

  it('renders the submit button with correct initial text', () => {
    renderForgotPassword();

    expect(screen.getByRole('button', { name: /send reset link/i })).toBeInTheDocument();
  });

  it('renders a back to login link', () => {
    renderForgotPassword();

    const backLink = screen.getByRole('link', { name: /back to login/i });
    expect(backLink).toBeInTheDocument();
    expect(backLink).toHaveAttribute('href', '/login');
  });

  // --- Accessibility ---

  it('marks the email input as required', () => {
    renderForgotPassword();

    expect(screen.getByLabelText(/email address/i)).toBeRequired();
  });

  it('has a properly associated label for the email field', () => {
    renderForgotPassword();

    const emailInput = screen.getByLabelText(/email address/i);
    expect(emailInput.id).toBe('email');
    // The label's htmlFor should match the input's id
    const label = screen.getByText(/email address/i);
    expect(label.tagName).toBe('LABEL');
  });

  // --- Form interaction ---

  it('updates email field as user types', async () => {
    renderForgotPassword();
    const user = userEvent.setup();

    const emailInput = screen.getByLabelText(/email address/i);
    await user.type(emailInput, 'user@example.com');

    expect(emailInput).toHaveValue('user@example.com');
  });

  // --- Loading state ---

  it('shows loading text and disables controls while submitting', async () => {
    mockFetch.mockReturnValue(new Promise(() => {})); // never resolves

    renderForgotPassword();
    const user = userEvent.setup();

    await user.type(screen.getByLabelText(/email address/i), 'user@example.com');
    await user.click(screen.getByRole('button', { name: /send reset link/i }));

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /sending/i })).toBeDisabled();
      expect(screen.getByLabelText(/email address/i)).toBeDisabled();
    });
  });

  // --- Successful submission ---

  it('displays success message and hides the form after successful submission', async () => {
    mockFetch.mockReturnValue(
      mockFetchResponse({ message: 'Reset link sent' })
    );

    renderForgotPassword();
    const user = userEvent.setup();

    await user.type(screen.getByLabelText(/email address/i), 'user@example.com');
    await user.click(screen.getByRole('button', { name: /send reset link/i }));

    await waitFor(() => {
      expect(
        screen.getByText(/if an account exists with this email/i)
      ).toBeInTheDocument();
    });

    // Form should be replaced by success view
    expect(screen.queryByLabelText(/email address/i)).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /send reset link/i })).not.toBeInTheDocument();
  });

  it('shows a back to login link on the success screen', async () => {
    mockFetch.mockReturnValue(
      mockFetchResponse({ message: 'Reset link sent' })
    );

    renderForgotPassword();
    const user = userEvent.setup();

    await user.type(screen.getByLabelText(/email address/i), 'user@example.com');
    await user.click(screen.getByRole('button', { name: /send reset link/i }));

    await waitFor(() => {
      const backLink = screen.getByRole('link', { name: /back to login/i });
      expect(backLink).toBeInTheDocument();
      expect(backLink).toHaveAttribute('href', '/login');
    });
  });

  it('sends the correct request to the forgot-password endpoint', async () => {
    mockFetch.mockReturnValue(
      mockFetchResponse({ message: 'Reset link sent' })
    );

    renderForgotPassword();
    const user = userEvent.setup();

    await user.type(screen.getByLabelText(/email address/i), 'test@test.com');
    await user.click(screen.getByRole('button', { name: /send reset link/i }));

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith(
        'http://localhost:8000/api/v1/auth/forgot-password',
        expect.objectContaining({
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email: 'test@test.com' }),
        })
      );
    });
  });

  // --- Error handling ---

  it('displays server error message on API failure', async () => {
    mockFetch.mockReturnValue(
      mockFetchResponse({ detail: 'Rate limit exceeded' }, 429)
    );

    renderForgotPassword();
    const user = userEvent.setup();

    await user.type(screen.getByLabelText(/email address/i), 'user@example.com');
    await user.click(screen.getByRole('button', { name: /send reset link/i }));

    await waitFor(() => {
      expect(screen.getByText('Rate limit exceeded')).toBeInTheDocument();
    });

    // Form should still be visible so user can retry
    expect(screen.getByLabelText(/email address/i)).toBeInTheDocument();
  });

  it('displays fallback error message when server provides no detail', async () => {
    mockFetch.mockReturnValue(
      mockFetchResponse({}, 500)
    );

    renderForgotPassword();
    const user = userEvent.setup();

    await user.type(screen.getByLabelText(/email address/i), 'user@example.com');
    await user.click(screen.getByRole('button', { name: /send reset link/i }));

    await waitFor(() => {
      expect(
        screen.getByText(/failed to send reset email/i)
      ).toBeInTheDocument();
    });
  });

  it('displays a generic error on network failure', async () => {
    mockFetch.mockRejectedValue(new Error('Network Error'));

    renderForgotPassword();
    const user = userEvent.setup();

    await user.type(screen.getByLabelText(/email address/i), 'user@example.com');
    await user.click(screen.getByRole('button', { name: /send reset link/i }));

    await waitFor(() => {
      expect(
        screen.getByText(/an error occurred.*please try again later/i)
      ).toBeInTheDocument();
    });
  });

  it('re-enables the submit button after a failed request', async () => {
    mockFetch.mockReturnValue(
      mockFetchResponse({ detail: 'Server error' }, 500)
    );

    renderForgotPassword();
    const user = userEvent.setup();

    await user.type(screen.getByLabelText(/email address/i), 'user@example.com');
    await user.click(screen.getByRole('button', { name: /send reset link/i }));

    await waitFor(() => {
      const submitBtn = screen.getByRole('button', { name: /send reset link/i });
      expect(submitBtn).not.toBeDisabled();
    });
  });
});
