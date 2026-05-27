import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock('../ClickableContact.css', () => ({}));

vi.mock('../../utils/auth', () => ({
  getAuthHeaders: () => ({ Authorization: 'Bearer test-token' }),
}));

vi.mock('../../utils/toast', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
    info: vi.fn(),
    warning: vi.fn(),
  },
}));

import { ClickableEmail, ClickablePhone, formatPhoneNumber } from '../ClickableContact';
import { toast } from '../../utils/toast';

// ---------------------------------------------------------------------------
// ClickableEmail Tests
// ---------------------------------------------------------------------------

describe('ClickableEmail', () => {
  it('renders N/A when email is null', () => {
    render(<ClickableEmail email={null} />);
    expect(screen.getByText('N/A')).toBeInTheDocument();
    expect(screen.getByText('N/A')).toHaveClass('no-value');
  });

  it('renders N/A when email is undefined', () => {
    render(<ClickableEmail />);
    expect(screen.getByText('N/A')).toBeInTheDocument();
  });

  it('renders N/A when email is empty string', () => {
    render(<ClickableEmail email="" />);
    expect(screen.getByText('N/A')).toBeInTheDocument();
  });

  it('renders a mailto link with the email address', () => {
    render(<ClickableEmail email="sarah@example.com" />);
    const link = screen.getByText('sarah@example.com');
    expect(link).toBeInTheDocument();
    expect(link.tagName).toBe('A');
    expect(link).toHaveAttribute('href', 'mailto:sarah@example.com');
  });

  it('applies the clickable-email CSS class', () => {
    render(<ClickableEmail email="test@test.com" />);
    const link = screen.getByText('test@test.com');
    expect(link).toHaveClass('clickable-email');
  });

  it('applies a custom className', () => {
    render(<ClickableEmail email="test@test.com" className="custom-class" />);
    const link = screen.getByText('test@test.com');
    expect(link).toHaveClass('clickable-email');
    expect(link).toHaveClass('custom-class');
  });

  it('stops event propagation on click', () => {
    const parentHandler = vi.fn();
    render(
      <div onClick={parentHandler}>
        <ClickableEmail email="test@test.com" />
      </div>
    );
    fireEvent.click(screen.getByText('test@test.com'));
    expect(parentHandler).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
// ClickablePhone Tests (basic mode — no showActions)
// ---------------------------------------------------------------------------

describe('ClickablePhone', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    global.fetch = vi.fn();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders N/A when phone is null', () => {
    render(<ClickablePhone phone={null} />);
    expect(screen.getByText('N/A')).toBeInTheDocument();
    expect(screen.getByText('N/A')).toHaveClass('no-value');
  });

  it('renders N/A when phone is undefined', () => {
    render(<ClickablePhone />);
    expect(screen.getByText('N/A')).toBeInTheDocument();
  });

  it('renders phone number as a clickable button', () => {
    render(<ClickablePhone phone="(555) 123-4567" />);
    const button = screen.getByRole('button');
    expect(button).toBeInTheDocument();
    expect(button).toHaveTextContent('(555) 123-4567');
    expect(button).toHaveClass('clickable-phone');
  });

  it('calls click-to-dial API on click', async () => {
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ success: true }),
    });

    render(<ClickablePhone phone="(555) 123-4567" />);
    fireEvent.click(screen.getByRole('button'));

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/dialer/click-to-dial'),
        expect.objectContaining({
          method: 'POST',
          body: expect.stringContaining('+15551234567'),
        })
      );
    });
  });

  it('shows success toast after successful call', async () => {
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ success: true }),
    });

    render(<ClickablePhone phone="(555) 123-4567" />);
    fireEvent.click(screen.getByRole('button'));

    await waitFor(() => {
      expect(toast.success).toHaveBeenCalledWith('Call initiated');
    });
  });

  it('shows error toast and falls back to tel: on API failure', async () => {
    global.fetch.mockResolvedValueOnce({
      ok: false,
      status: 500,
      json: () => Promise.resolve({ detail: 'Server error' }),
    });

    const locationHrefSpy = vi.spyOn(window, 'location', 'get').mockReturnValue({
      ...window.location,
      href: '',
    });

    render(<ClickablePhone phone="(555) 123-4567" />);
    fireEvent.click(screen.getByRole('button'));

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalled();
    });

    locationHrefSpy.mockRestore();
  });

  it('stops event propagation on click', () => {
    const parentHandler = vi.fn();
    render(
      <div onClick={parentHandler}>
        <ClickablePhone phone="(555) 123-4567" />
      </div>
    );
    fireEvent.click(screen.getByRole('button'));
    expect(parentHandler).not.toHaveBeenCalled();
  });

  it('sends leadId and loanId when provided', async () => {
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ success: true }),
    });

    render(<ClickablePhone phone="(555) 123-4567" leadId={42} loanId={99} />);
    fireEvent.click(screen.getByRole('button'));

    await waitFor(() => {
      const body = JSON.parse(global.fetch.mock.calls[0][1].body);
      expect(body.lead_id).toBe(42);
      expect(body.loan_id).toBe(99);
    });
  });
});

// ---------------------------------------------------------------------------
// ClickablePhone Tests (showActions mode — with call and SMS buttons)
// ---------------------------------------------------------------------------

describe('ClickablePhone with showActions', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ success: true }),
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders phone number with action buttons', () => {
    render(<ClickablePhone phone="(555) 999-8888" showActions />);
    expect(screen.getByText('(555) 999-8888')).toBeInTheDocument();
    const buttons = screen.getAllByRole('button');
    expect(buttons.length).toBeGreaterThanOrEqual(1);
  });

  it('renders SMS as a link when no onSMSClick handler', () => {
    render(<ClickablePhone phone="(555) 999-8888" showActions />);
    const smsLink = screen.getByTitle('Send SMS');
    expect(smsLink.tagName).toBe('A');
    expect(smsLink).toHaveAttribute('href', 'sms:5559998888');
  });

  it('renders SMS as a button when onSMSClick handler is provided', () => {
    const handleSMS = vi.fn();
    render(
      <ClickablePhone phone="(555) 999-8888" showActions onSMSClick={handleSMS} />
    );
    const smsButton = screen.getByTitle('Send SMS in CRM');
    expect(smsButton.tagName).toBe('BUTTON');

    fireEvent.click(smsButton);
    expect(handleSMS).toHaveBeenCalledTimes(1);
  });

  it('calls click-to-dial API on call button click', async () => {
    render(<ClickablePhone phone="(555) 999-8888" showActions />);

    const callButton = screen.getByTitle('Call');
    fireEvent.click(callButton);

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/dialer/click-to-dial'),
        expect.objectContaining({ method: 'POST' })
      );
    });
  });

  it('stops event propagation from phone-with-actions container', () => {
    const parentHandler = vi.fn();
    render(
      <div onClick={parentHandler}>
        <ClickablePhone phone="(555) 999-8888" showActions />
      </div>
    );
    fireEvent.click(screen.getByText('(555) 999-8888').closest('.phone-with-actions'));
    expect(parentHandler).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
// formatPhoneNumber Utility Tests
// ---------------------------------------------------------------------------

describe('formatPhoneNumber', () => {
  it('returns empty string for null input', () => {
    expect(formatPhoneNumber(null)).toBe('');
  });

  it('returns empty string for undefined input', () => {
    expect(formatPhoneNumber(undefined)).toBe('');
  });

  it('returns empty string for empty string input', () => {
    expect(formatPhoneNumber('')).toBe('');
  });

  it('formats a 10-digit number as (XXX) XXX-XXXX', () => {
    expect(formatPhoneNumber('5551234567')).toBe('(555) 123-4567');
  });

  it('strips non-numeric characters before formatting', () => {
    expect(formatPhoneNumber('(555) 123-4567')).toBe('(555) 123-4567');
  });

  it('returns original string for non-10-digit numbers', () => {
    expect(formatPhoneNumber('+15551234567')).toBe('+15551234567');
  });

  it('returns original string for short numbers', () => {
    expect(formatPhoneNumber('12345')).toBe('12345');
  });

  it('handles number with dots as separators', () => {
    expect(formatPhoneNumber('555.123.4567')).toBe('(555) 123-4567');
  });
});
