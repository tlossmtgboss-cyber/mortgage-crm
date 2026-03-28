import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';

vi.mock('../AnalyticsCard.css', () => ({}));

import AnalyticsCard from '../AnalyticsCard';

describe('AnalyticsCard', () => {
  // 1. Renders title and value
  it('renders title and value', () => {
    render(<AnalyticsCard title="Total Loans" value={42} />);
    expect(screen.getByText('TOTAL LOANS')).toBeInTheDocument();
    expect(screen.getByText('42')).toBeInTheDocument();
  });

  // 2. Renders subtitle when provided
  it('renders subtitle when provided', () => {
    render(<AnalyticsCard title="Pipeline" value="$1.2M" subtitle="last 30 days" />);
    expect(screen.getByText('last 30 days')).toBeInTheDocument();
  });

  // 3. Renders positive trend as "+N%"
  it('renders positive trend as "+N%"', () => {
    render(<AnalyticsCard title="Volume" value="$500K" trend={12} />);
    expect(screen.getByText('+12%')).toBeInTheDocument();
  });

  // 4. Renders negative trend as "-N%"
  it('renders negative trend as "-N%"', () => {
    render(<AnalyticsCard title="Fallout" value="3" trend={-5} />);
    expect(screen.getByText('-5%')).toBeInTheDocument();
  });

  // 5. Applies status class
  it('applies status modifier class for error', () => {
    const { container } = render(<AnalyticsCard title="Issues" value="2" status="error" />);
    expect(container.firstChild).toHaveClass('analytics-card--error');
  });

  it('applies status modifier class for success', () => {
    const { container } = render(<AnalyticsCard title="Closed" value="10" status="success" />);
    expect(container.firstChild).toHaveClass('analytics-card--success');
  });

  it('applies status modifier class for warning', () => {
    const { container } = render(<AnalyticsCard title="Expiring" value="4" status="warning" />);
    expect(container.firstChild).toHaveClass('analytics-card--warning');
  });

  // 6. Renders children when provided
  it('renders children when provided', () => {
    render(
      <AnalyticsCard title="Metrics" value="100">
        <span>extra content</span>
      </AnalyticsCard>
    );
    expect(screen.getByText('extra content')).toBeInTheDocument();
  });

  // Additional: does not render subtitle when omitted
  it('does not render subtitle when not provided', () => {
    const { container } = render(<AnalyticsCard title="Score" value="88" />);
    expect(container.querySelector('.analytics-card__subtitle')).toBeNull();
  });

  // Additional: does not render trend when not provided
  it('does not render trend when not provided', () => {
    const { container } = render(<AnalyticsCard title="Count" value="5" />);
    expect(container.querySelector('.analytics-card__trend')).toBeNull();
  });

  // Additional: renders icon when provided
  it('renders icon when provided', () => {
    render(<AnalyticsCard title="Docs" value="7" icon={<span data-testid="test-icon" />} />);
    expect(screen.getByTestId('test-icon')).toBeInTheDocument();
  });
});
