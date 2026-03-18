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

vi.mock('../BorrowerLogin.css', () => ({}));

// Mock global fetch
const mockFetch = vi.fn();

import BorrowerLogin from '../BorrowerLogin';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function renderBorrowerLogin(route = '/borrower-login') {
  return render(
    <MemoryRouter initialEntries={[route]}>
      <BorrowerLogin />
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

describe('BorrowerLogin', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    global.fetch = mockFetch;
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  // --- Rendering ---

  it('renders the main heading and subtitle', () => {
    renderBorrowerLogin();

    expect(
      screen.getByRole('heading', { name: /start your mortgage application/i })
    ).toBeInTheDocument();
    expect(
      screen.getByText(/sign in to begin or continue your application/i)
    ).toBeInTheDocument();
  });

  it('renders all four social login buttons', () => {
    renderBorrowerLogin();

    expect(screen.getByRole('button', { name: /continue with google/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /continue with apple/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /continue with facebook/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /continue with linkedin/i })).toBeInTheDocument();
  });

  it('renders a "Continue with Email" button initially (form hidden)', () => {
    renderBorrowerLogin();

    expect(
      screen.getByRole('button', { name: /continue with email/i })
    ).toBeInTheDocument();
    // Email form should not be visible yet
    expect(screen.queryByLabelText(/email address/i)).not.toBeInTheDocument();
  });

  it('renders benefit items section', () => {
    renderBorrowerLogin();

    expect(screen.getByText(/save your progress/i)).toBeInTheDocument();
    expect(screen.getByText(/faster completion/i)).toBeInTheDocument();
    expect(screen.getByText(/secure access/i)).toBeInTheDocument();
    expect(screen.getByText(/access anywhere/i)).toBeInTheDocument();
  });

  it('renders consent and privacy notices', () => {
    renderBorrowerLogin();

    expect(
      screen.getByText(/by continuing, you agree to receive communications/i)
    ).toBeInTheDocument();
    expect(
      screen.getByText(/your information is protected/i)
    ).toBeInTheDocument();
  });

  // --- Email form toggle ---

  it('shows email form when "Continue with Email" is clicked', async () => {
    renderBorrowerLogin();
    const user = userEvent.setup();

    await user.click(screen.getByRole('button', { name: /continue with email/i }));

    expect(screen.getByLabelText(/email address/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/first name/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/last name/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /send login link/i })).toBeInTheDocument();
  });

  it('hides email form when "Back to sign-in options" is clicked', async () => {
    renderBorrowerLogin();
    const user = userEvent.setup();

    await user.click(screen.getByRole('button', { name: /continue with email/i }));
    expect(screen.getByLabelText(/email address/i)).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /back to sign-in options/i }));
    expect(screen.queryByLabelText(/email address/i)).not.toBeInTheDocument();
  });

  // --- Email form accessibility ---

  it('marks the email field as required and name fields as optional', async () => {
    renderBorrowerLogin();
    const user = userEvent.setup();

    await user.click(screen.getByRole('button', { name: /continue with email/i }));

    expect(screen.getByLabelText(/email address/i)).toBeRequired();
    // Name fields should not be required (labels say "optional")
    expect(screen.getByLabelText(/first name/i)).not.toBeRequired();
    expect(screen.getByLabelText(/last name/i)).not.toBeRequired();
  });

  // --- Email form submission ---

  it('sends correct payload on email form submission', async () => {
    mockFetch.mockReturnValue(mockFetchResponse({ success: true }));

    renderBorrowerLogin();
    const user = userEvent.setup();

    await user.click(screen.getByRole('button', { name: /continue with email/i }));
    await user.type(screen.getByLabelText(/email address/i), 'borrower@example.com');
    await user.type(screen.getByLabelText(/first name/i), 'Jane');
    await user.type(screen.getByLabelText(/last name/i), 'Smith');
    await user.click(screen.getByRole('button', { name: /send login link/i }));

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/borrower-auth/email/request'),
        expect.objectContaining({
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            email: 'borrower@example.com',
            first_name: 'Jane',
            last_name: 'Smith',
          }),
        })
      );
    });
  });

  it('shows email-sent confirmation after successful submission', async () => {
    mockFetch.mockReturnValue(mockFetchResponse({ success: true }));

    renderBorrowerLogin();
    const user = userEvent.setup();

    await user.click(screen.getByRole('button', { name: /continue with email/i }));
    await user.type(screen.getByLabelText(/email address/i), 'borrower@example.com');
    await user.click(screen.getByRole('button', { name: /send login link/i }));

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /check your email/i })).toBeInTheDocument();
      expect(screen.getByText('borrower@example.com')).toBeInTheDocument();
      expect(screen.getByText(/link will expire in 24 hours/i)).toBeInTheDocument();
    });
  });

  it('allows going back from email-sent screen to try a different email', async () => {
    mockFetch.mockReturnValue(mockFetchResponse({ success: true }));

    renderBorrowerLogin();
    const user = userEvent.setup();

    await user.click(screen.getByRole('button', { name: /continue with email/i }));
    await user.type(screen.getByLabelText(/email address/i), 'borrower@example.com');
    await user.click(screen.getByRole('button', { name: /send login link/i }));

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /check your email/i })).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: /use a different email/i }));

    // Should be back to the main page (not the email form — email form collapsed)
    expect(screen.getByRole('heading', { name: /start your mortgage application/i })).toBeInTheDocument();
  });

  // --- Error handling ---

  it('displays server error on email form submission failure', async () => {
    mockFetch.mockReturnValue(
      mockFetchResponse({ detail: 'Too many requests' }, 429)
    );

    renderBorrowerLogin();
    const user = userEvent.setup();

    await user.click(screen.getByRole('button', { name: /continue with email/i }));
    await user.type(screen.getByLabelText(/email address/i), 'borrower@example.com');
    await user.click(screen.getByRole('button', { name: /send login link/i }));

    await waitFor(() => {
      expect(screen.getByText(/too many requests/i)).toBeInTheDocument();
    });
  });

  it('displays a generic error on network failure during email submission', async () => {
    mockFetch.mockRejectedValue(new Error('Network Error'));

    renderBorrowerLogin();
    const user = userEvent.setup();

    await user.click(screen.getByRole('button', { name: /continue with email/i }));
    await user.type(screen.getByLabelText(/email address/i), 'borrower@example.com');
    await user.click(screen.getByRole('button', { name: /send login link/i }));

    await waitFor(() => {
      expect(
        screen.getByText(/failed to send login link.*please try again/i)
      ).toBeInTheDocument();
    });
  });

  // --- Social login ---

  it('initiates Google OAuth flow and redirects to auth URL', async () => {
    mockFetch.mockReturnValue(
      mockFetchResponse({ auth_url: 'https://accounts.google.com/o/oauth2/auth?...' })
    );

    // Mock window.location.href assignment
    const locationSpy = vi.spyOn(window, 'location', 'get').mockReturnValue({
      ...window.location,
      href: '',
    });
    delete window.location;
    window.location = { href: '' };

    renderBorrowerLogin();
    const user = userEvent.setup();

    await user.click(screen.getByRole('button', { name: /continue with google/i }));

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/borrower-auth/google/connect')
      );
      expect(window.location.href).toBe('https://accounts.google.com/o/oauth2/auth?...');
    });

    // Restore
    window.location = location;
  });

  it('shows error when social provider is not configured', async () => {
    mockFetch.mockReturnValue(
      mockFetchResponse(
        { detail: 'Apple Sign-In client_id not configured' },
        500
      )
    );

    renderBorrowerLogin();
    const user = userEvent.setup();

    await user.click(screen.getByRole('button', { name: /continue with apple/i }));

    await waitFor(() => {
      expect(
        screen.getByText(/apple sign in is not available/i)
      ).toBeInTheDocument();
    });
  });

  // --- URL error params ---

  it('displays error message from URL error parameter', () => {
    renderBorrowerLogin('/borrower-login?error=link_expired');

    expect(
      screen.getByText(/this login link has expired/i)
    ).toBeInTheDocument();
  });

  it('displays generic error for unknown error codes in URL', () => {
    renderBorrowerLogin('/borrower-login?error=unknown_code');

    expect(
      screen.getByText(/an error occurred.*please try again/i)
    ).toBeInTheDocument();
  });

  // --- Demo mode ---

  it('navigates to /apply/start when demo button is clicked', async () => {
    renderBorrowerLogin();
    const user = userEvent.setup();

    await user.click(screen.getByRole('button', { name: /skip login.*demo/i }));

    expect(mockNavigate).toHaveBeenCalledWith('/apply/start');
  });
});
