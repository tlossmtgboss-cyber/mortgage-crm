import React from 'react';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock('../ClickableContact.css', () => ({}));

// Mock the dialerAPI used by ClickablePhone
vi.mock('../../services/api', () => ({
  dialerAPI: {
    clickToDial: vi.fn(),
  },
}));

import { ClickableEmail, ClickablePhone, formatPhoneNumber } from '../ClickableContact';
import { dialerAPI } from '../../services/api';

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

  it('initiates a click-to-dial call on click', async () => {
    dialerAPI.clickToDial.mockResolvedValue({ success: true });

    render(
      <ClickablePhone
        phone="(555) 123-4567"
        contactName="Sarah Johnson"
        leadId="42"
      />
    );

    const button = screen.getByRole('button');
    await act(async () => {
      fireEvent.click(button);
    });

    expect(dialerAPI.clickToDial).toHaveBeenCalledWith({
      phone_number: '5551234567',
      contact_name: 'Sarah Johnson',
      lead_id: '42',
      loan_id: null,
    });
  });

  it('shows success state after successful call initiation', async () => {
    dialerAPI.clickToDial.mockResolvedValue({ success: true });

    render(<ClickablePhone phone="(555) 123-4567" />);

    await act(async () => {
      fireEvent.click(screen.getByRole('button'));
    });

    await waitFor(() => {
      const button = screen.getByRole('button');
      expect(button).toHaveClass('success');
    });
  });

  it('displays error message when call fails', async () => {
    dialerAPI.clickToDial.mockResolvedValue({
      success: false,
      error: 'No caller ID configured',
    });

    render(<ClickablePhone phone="(555) 123-4567" />);

    await act(async () => {
      fireEvent.click(screen.getByRole('button'));
    });

    await waitFor(() => {
      expect(screen.getByText(/No caller ID configured/)).toBeInTheDocument();
    });
  });

  it('handles network errors gracefully', async () => {
    dialerAPI.clickToDial.mockRejectedValue(new Error('Network Error'));

    render(<ClickablePhone phone="(555) 123-4567" />);

    await act(async () => {
      fireEvent.click(screen.getByRole('button'));
    });

    await waitFor(() => {
      expect(screen.getByText(/Failed to connect call/)).toBeInTheDocument();
    });
  });

  it('disables button while calling', async () => {
    // Make clickToDial hang so we can check the intermediate state
    let resolveCall;
    dialerAPI.clickToDial.mockReturnValue(
      new Promise((resolve) => {
        resolveCall = resolve;
      })
    );

    render(<ClickablePhone phone="(555) 123-4567" />);
    const button = screen.getByRole('button');

    await act(async () => {
      fireEvent.click(button);
    });

    // Button should be disabled while calling
    expect(button).toBeDisabled();
    expect(button).toHaveClass('calling');

    // Resolve the call
    await act(async () => {
      resolveCall({ success: true });
    });
  });

  it('cleans phone number by removing formatting characters', async () => {
    dialerAPI.clickToDial.mockResolvedValue({ success: true });

    render(<ClickablePhone phone="+1 (555) 123-4567" />);

    await act(async () => {
      fireEvent.click(screen.getByRole('button'));
    });

    expect(dialerAPI.clickToDial).toHaveBeenCalledWith(
      expect.objectContaining({
        phone_number: '+15551234567',
      })
    );
  });
});

// ---------------------------------------------------------------------------
// ClickablePhone Tests (showActions mode — with call and SMS buttons)
// ---------------------------------------------------------------------------

describe('ClickablePhone with showActions', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders phone number with action buttons', () => {
    render(<ClickablePhone phone="(555) 999-8888" showActions />);
    expect(screen.getByText('(555) 999-8888')).toBeInTheDocument();
    // Should have call and SMS buttons
    const buttons = screen.getAllByRole('button');
    expect(buttons.length).toBeGreaterThanOrEqual(1); // call button
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

  it('shows error tooltip on failed call in showActions mode', async () => {
    dialerAPI.clickToDial.mockResolvedValue({
      success: false,
      error: 'Cell phone not configured',
    });

    render(<ClickablePhone phone="(555) 999-8888" showActions />);

    const callButton = screen.getByTitle('Click to call');
    await act(async () => {
      fireEvent.click(callButton);
    });

    await waitFor(() => {
      expect(screen.getByText('Cell phone not configured')).toBeInTheDocument();
    });
  });

  it('stops event propagation from phone-with-actions container', () => {
    const parentHandler = vi.fn();
    render(
      <div onClick={parentHandler}>
        <ClickablePhone phone="(555) 999-8888" showActions />
      </div>
    );
    // Click on the phone number text area
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
