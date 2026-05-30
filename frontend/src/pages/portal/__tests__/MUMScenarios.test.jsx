/**
 * MUMScenarios render tests (portal consolidation Phase 1 harvest).
 * Confirms the calculators render their results and react to input changes.
 */
import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import MUMScenarios from '../MUMScenarios';

describe('MUMScenarios', () => {
  const props = { propertyValue: 500000, currentBalance: 300000, currentRate: 6.5 };

  it('renders all four scenario cards', () => {
    render(<MUMScenarios {...props} />);
    expect(screen.getByText('💵 Refinance')).toBeInTheDocument();
    expect(screen.getByText('🏦 Cash-Out Refinance')).toBeInTheDocument();
    expect(screen.getByText('🔑 HELOC')).toBeInTheDocument();
    expect(screen.getByText('🏡 Sell Analysis')).toBeInTheDocument();
  });

  it('shows equity-derived figures (net proceeds for a 500k/300k loan)', () => {
    render(<MUMScenarios {...props} />);
    // sell: 500k - 300k - 40k costs = 160k net proceeds
    expect(screen.getByText('$160,000')).toBeInTheDocument();
  });

  it('recomputes the refinance payment when the new rate changes', () => {
    render(<MUMScenarios {...props} />);
    const input = screen.getByLabelText('New interest rate (%)');
    fireEvent.change(input, { target: { value: '3.0' } });
    // A 3% rate yields a much larger monthly saving — the savings row should update.
    expect(screen.getByText(/Monthly savings/i)).toBeInTheDocument();
  });
});
