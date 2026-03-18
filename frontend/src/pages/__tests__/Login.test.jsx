import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

// ---------------------------------------------------------------------------
// Mocks — must come before component import
// ---------------------------------------------------------------------------

const mockNavigate = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return { ...actual, useNavigate: () => mockNavigate };
});

const mockLogin = vi.fn();
vi.mock('../../services/api', () => ({
  authAPI: {
    login: (...args) => mockLogin(...args),
  },
  API_BASE_URL: 'http://localhost:8000',
}));

const mockSetAuth = vi.fn(() => Promise.resolve());
vi.mock('../../utils/auth', () => ({
  setAuth: (...args) => mockSetAuth(...args),
}));

vi.mock('../../config/roleConfig', () => ({
  getUserEffectiveRole: vi.fn(() => 'sales'),
  getDefaultRouteForRole: vi.fn(() => '/dashboard'),
}));

vi.mock('../../hooks/useBiometricLogin', () => ({
  useBiometricLogin: () => ({
    isAvailable: false,
    biometryDisplayName: 'Face ID',
    hasStoredCredentials: false,
    isNative: false,
    authenticateWithBiometrics: vi.fn(),
    enableBiometricLogin: vi.fn(),
  }),
}));

vi.mock('../../services/nativeServices', () => ({
  haptics: { success: vi.fn(), error: vi.fn() },
}));

vi.mock('../Login.css', () => ({}));

import Login from '../Login';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function renderLogin(route = '/login') {
  return render(
    <MemoryRouter initialEntries={[route]}>
      <Login />
    </MemoryRouter>
  );
}

const VALID_USER = {
  id: 1,
  email: 'test@example.com',
  first_name: 'Test',
  last_name: 'User',
  permission_role: 'sales',
  role: null,
};

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('Login', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // setAuth stores token in localStorage — mock localStorage.getItem for the
    // post-setAuth verification that Login.js performs
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation((key) => {
      if (key === 'token') return 'mock-jwt-token';
      return null;
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  // --- Rendering ---

  it('renders the login form with email and password fields', () => {
    renderLogin();

    expect(screen.getByLabelText(/email/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/password/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /login/i })).toBeInTheDocument();
  });

  it('renders the page heading and subtitle', () => {
    renderLogin();

    expect(screen.getByRole('heading', { name: /mortgage crm/i })).toBeInTheDocument();
    expect(screen.getByText(/agentic ai platform/i)).toBeInTheDocument();
  });

  it('renders a forgot password link', () => {
    renderLogin();

    const forgotLink = screen.getByRole('link', { name: /forgot password/i });
    expect(forgotLink).toBeInTheDocument();
    expect(forgotLink).toHaveAttribute('href', '/forgot-password');
  });

  // --- Accessibility ---

  it('has properly associated labels for form inputs', () => {
    renderLogin();

    const emailInput = screen.getByLabelText(/email/i);
    const passwordInput = screen.getByLabelText(/password/i);

    expect(emailInput).toHaveAttribute('id', 'email');
    expect(emailInput).toHaveAttribute('type', 'email');
    expect(passwordInput).toHaveAttribute('id', 'password');
    expect(passwordInput).toHaveAttribute('type', 'password');
  });

  it('marks both inputs as required', () => {
    renderLogin();

    expect(screen.getByLabelText(/email/i)).toBeRequired();
    expect(screen.getByLabelText(/password/i)).toBeRequired();
  });

  // --- Form interaction ---

  it('updates email and password fields as user types', async () => {
    renderLogin();
    const user = userEvent.setup();

    const emailInput = screen.getByLabelText(/email/i);
    const passwordInput = screen.getByLabelText(/password/i);

    await user.type(emailInput, 'user@test.com');
    await user.type(passwordInput, 'secret123');

    expect(emailInput).toHaveValue('user@test.com');
    expect(passwordInput).toHaveValue('secret123');
  });

  // --- Loading state ---

  it('shows loading text and disables the button while submitting', async () => {
    // Make login hang so we can observe the loading state
    mockLogin.mockReturnValue(new Promise(() => {}));

    renderLogin();
    const user = userEvent.setup();

    await user.type(screen.getByLabelText(/email/i), 'user@test.com');
    await user.type(screen.getByLabelText(/password/i), 'password123');
    await user.click(screen.getByRole('button', { name: /login/i }));

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /logging in/i })).toBeDisabled();
    });
  });

  it('disables form inputs while submitting', async () => {
    mockLogin.mockReturnValue(new Promise(() => {}));

    renderLogin();
    const user = userEvent.setup();

    await user.type(screen.getByLabelText(/email/i), 'user@test.com');
    await user.type(screen.getByLabelText(/password/i), 'password123');
    await user.click(screen.getByRole('button', { name: /login/i }));

    await waitFor(() => {
      expect(screen.getByLabelText(/email/i)).toBeDisabled();
      expect(screen.getByLabelText(/password/i)).toBeDisabled();
    });
  });

  // --- Successful login ---

  it('calls authAPI.login and navigates to dashboard on success', async () => {
    mockLogin.mockResolvedValue({
      access_token: 'jwt-token-123',
      user: VALID_USER,
    });

    renderLogin();
    const user = userEvent.setup();

    await user.type(screen.getByLabelText(/email/i), 'test@example.com');
    await user.type(screen.getByLabelText(/password/i), 'correctpassword');
    await user.click(screen.getByRole('button', { name: /login/i }));

    await waitFor(() => {
      expect(mockLogin).toHaveBeenCalledWith('test@example.com', 'correctpassword');
      expect(mockSetAuth).toHaveBeenCalledWith('jwt-token-123', VALID_USER);
      expect(mockNavigate).toHaveBeenCalledWith('/dashboard');
    });
  });

  it('navigates to redirect URL when redirect param is present', async () => {
    mockLogin.mockResolvedValue({
      access_token: 'jwt-token-123',
      user: VALID_USER,
    });

    renderLogin('/login?redirect=/pipeline');
    const user = userEvent.setup();

    await user.type(screen.getByLabelText(/email/i), 'test@example.com');
    await user.type(screen.getByLabelText(/password/i), 'correctpassword');
    await user.click(screen.getByRole('button', { name: /login/i }));

    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith('/pipeline');
    });
  });

  // --- Error handling ---

  it('displays server error message from response detail', async () => {
    mockLogin.mockRejectedValue({
      response: { data: { detail: 'Invalid credentials' } },
    });

    renderLogin();
    const user = userEvent.setup();

    await user.type(screen.getByLabelText(/email/i), 'user@test.com');
    await user.type(screen.getByLabelText(/password/i), 'wrongpassword');
    await user.click(screen.getByRole('button', { name: /login/i }));

    await waitFor(() => {
      expect(screen.getByText('Invalid credentials')).toBeInTheDocument();
    });
  });

  it('displays server error message from response error field', async () => {
    mockLogin.mockRejectedValue({
      response: { data: { error: 'Account locked' } },
    });

    renderLogin();
    const user = userEvent.setup();

    await user.type(screen.getByLabelText(/email/i), 'user@test.com');
    await user.type(screen.getByLabelText(/password/i), 'wrongpassword');
    await user.click(screen.getByRole('button', { name: /login/i }));

    await waitFor(() => {
      expect(screen.getByText('Account locked')).toBeInTheDocument();
    });
  });

  it('displays a fallback error message for network failures', async () => {
    mockLogin.mockRejectedValue(new Error('Network Error'));

    renderLogin();
    const user = userEvent.setup();

    await user.type(screen.getByLabelText(/email/i), 'user@test.com');
    await user.type(screen.getByLabelText(/password/i), 'password');
    await user.click(screen.getByRole('button', { name: /login/i }));

    await waitFor(() => {
      expect(screen.getByText('Network Error')).toBeInTheDocument();
    });
  });

  it('displays a generic fallback when error has no message', async () => {
    mockLogin.mockRejectedValue({});

    renderLogin();
    const user = userEvent.setup();

    await user.type(screen.getByLabelText(/email/i), 'user@test.com');
    await user.type(screen.getByLabelText(/password/i), 'password');
    await user.click(screen.getByRole('button', { name: /login/i }));

    await waitFor(() => {
      expect(
        screen.getByText(/login failed.*please check your credentials/i)
      ).toBeInTheDocument();
    });
  });

  it('clears previous error when submitting again', async () => {
    mockLogin
      .mockRejectedValueOnce({
        response: { data: { detail: 'First error' } },
      })
      .mockResolvedValueOnce({
        access_token: 'jwt-token-123',
        user: VALID_USER,
      });

    renderLogin();
    const user = userEvent.setup();

    // First attempt — fails
    await user.type(screen.getByLabelText(/email/i), 'user@test.com');
    await user.type(screen.getByLabelText(/password/i), 'wrongpassword');
    await user.click(screen.getByRole('button', { name: /login/i }));

    await waitFor(() => {
      expect(screen.getByText('First error')).toBeInTheDocument();
    });

    // Second attempt — error should clear on submit
    await user.click(screen.getByRole('button', { name: /login/i }));

    await waitFor(() => {
      expect(screen.queryByText('First error')).not.toBeInTheDocument();
    });
  });

  it('re-enables the button after a failed login attempt', async () => {
    mockLogin.mockRejectedValue({
      response: { data: { detail: 'Invalid credentials' } },
    });

    renderLogin();
    const user = userEvent.setup();

    await user.type(screen.getByLabelText(/email/i), 'user@test.com');
    await user.type(screen.getByLabelText(/password/i), 'wrongpassword');
    await user.click(screen.getByRole('button', { name: /login/i }));

    await waitFor(() => {
      const loginBtn = screen.getByRole('button', { name: /login/i });
      expect(loginBtn).not.toBeDisabled();
    });
  });
});
