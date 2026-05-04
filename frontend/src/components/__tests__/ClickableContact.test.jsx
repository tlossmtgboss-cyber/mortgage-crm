import React from 'react';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock('../ClickableContact.css', () => ({}));

import { ClickableEmail, ClickablePhone, formatPhoneNumber } from '../ClickableContact';

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
  let windowOpenSpy;

  beforeEach(() => {
    vi.clearAllMocks();
    windowOpenSpy = vi.spyOn(window, 'open').mockImplementation(() => null);
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

  it('opens Teams deep link on click', () => {
    render(<ClickablePhone phone="(555) 123-4567" />);

    fireEvent.click(screen.getByRole('button'));

    expect(windowOpenSpy).toHaveBeenCalledWith(
      'https://teams.microsoft.com/l/call/0/0?users=4:%2B15551234567',
      '_blank'
    );
  });

  it('shows success state after click', async () => {
    render(<ClickablePhone phone="(555) 123-4567" />);

    fireEvent.click(screen.getByRole('button'));

    const button = screen.getByRole('button');
    expect(button).toHaveClass('success');
  });

  it('preserves + prefix for international numbers', () => {
    render(<ClickablePhone phone="+1 (555) 123-4567" />);

    fireEvent.click(screen.getByRole('button'));

    expect(windowOpenSpy).toHaveBeenCalledWith(
      'https://teams.microsoft.com/l/call/0/0?users=4:%2B15551234567',
      '_blank'
    );
  });

  it('adds +1 prefix for domestic numbers without one', () => {
    render(<ClickablePhone phone="5551234567" />);

    fireEvent.click(screen.getByRole('button'));

    expect(windowOpenSpy).toHaveBeenCalledWith(
      'https://teams.microsoft.com/l/call/0/0?users=4:%2B15551234567',
      '_blank'
    );
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
});

// ---------------------------------------------------------------------------
// ClickablePhone Tests (showActions mode — with call and SMS buttons)
// ---------------------------------------------------------------------------

describe('ClickablePhone with showActions', () => {
  let windowOpenSpy;

  beforeEach(() => {
    vi.clearAllMocks();
    windowOpenSpy = vi.spyOn(window, 'open').mockImplementation(() => null);
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

  it('opens Teams on call button click in showActions mode', () => {
    render(<ClickablePhone phone="(555) 999-8888" showActions />);

    const callButton = screen.getByTitle('Call via Teams');
    fireEvent.click(callButton);

    expect(windowOpenSpy).toHaveBeenCalledWith(
      'https://teams.microsoft.com/l/call/0/0?users=4:%2B15559998888',
      '_blank'
    );
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
