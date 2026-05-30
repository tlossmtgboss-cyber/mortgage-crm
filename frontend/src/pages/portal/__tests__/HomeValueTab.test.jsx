/**
 * HomeValueTab render + data-shape tests (portal borrower-facing additions).
 *
 * HomeValueTab renders the backend home_value payload when present and degrades
 * to the locally-computed MUM estimate (fallbackValue/fallbackBalance) when the
 * backend payload is absent or has no baseline. Currency uses the formatCurrency
 * style (Intl.NumberFormat USD, no decimals by default).
 */
import React from 'react';
import { render, screen } from '@testing-library/react';
import HomeValueTab from '../HomeValueTab';

describe('HomeValueTab', () => {
  it('renders the backend valuation, equity and ownership when home_value is present', () => {
    const homeValue = {
      has_baseline: true,
      baseline: { purchase_price: 400000 },
      current_valuation: { estimated_value: 500000, value_low: 480000, value_high: 520000 },
      equity: { current_balance: 300000, equity: 200000, ltv: 60 },
      insights: ['Your equity grew by $50,000 this year'],
    };
    render(<HomeValueTab homeValue={homeValue} />);

    // $500,000 appears in the hero and the low–high range track midpoint.
    expect(screen.getAllByText('$500,000').length).toBeGreaterThan(0); // hero estimate
    // equity ($200,000) appears in the stat cell and the equity breakdown bar.
    expect(screen.getAllByText(/\$200,000/).length).toBeGreaterThan(0);
    // 100 - 60 ltv = 40% ownership
    expect(screen.getByText(/You own 40% of your home/)).toBeInTheDocument();
    expect(screen.getByText('Your equity grew by $50,000 this year')).toBeInTheDocument();
  });

  it('falls back to the local estimate when home_value is absent', () => {
    render(
      <HomeValueTab
        homeValue={null}
        fallbackValue={450000}
        fallbackBalance={300000}
        purchasePrice={420000}
      />
    );
    expect(screen.getAllByText('$450,000').length).toBeGreaterThan(0); // hero from fallbackValue
    // equity = 450k - 300k = 150k (stat cell + equity breakdown bar)
    expect(screen.getAllByText(/\$150,000/).length).toBeGreaterThan(0);
    // purchase shown
    expect(screen.getByText('$420,000')).toBeInTheDocument();
  });

  it('shows a neutral tracking empty state when there is no baseline and no insights', () => {
    render(
      <HomeValueTab
        homeValue={{ has_baseline: false }}
        fallbackValue={300000}
        fallbackBalance={250000}
        purchasePrice={300000}
      />
    );
    expect(screen.getByText('Tracking your home value')).toBeInTheDocument();
  });

  it('computes appreciation from purchase price and current value', () => {
    render(
      <HomeValueTab
        homeValue={{
          has_baseline: true,
          baseline: { purchase_price: 400000 },
          current_valuation: { estimated_value: 460000 },
          equity: { current_balance: 350000 },
        }}
      />
    );
    // +$60,000 change since purchase
    expect(screen.getByText(/\+\$60,000/)).toBeInTheDocument();
  });
});
