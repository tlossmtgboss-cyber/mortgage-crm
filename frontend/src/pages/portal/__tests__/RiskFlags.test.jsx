/**
 * RiskFlags render + data-shape tests (portal borrower-facing additions).
 *
 * RiskFlags renders the `risks` array from the PURL-authed borrower dashboard.
 * It must render nothing when empty (so the Overview stays clean) and map
 * severity to a calm, borrower-friendly chip vocabulary when present.
 */
import React from 'react';
import { render, screen } from '@testing-library/react';
import RiskFlags from '../RiskFlags';

describe('RiskFlags', () => {
  it('renders nothing when there are no risks', () => {
    const { container } = render(<RiskFlags risks={[]} />);
    expect(container.firstChild).toBeNull();
  });

  it('renders nothing when risks is undefined or not an array', () => {
    const { container: c1 } = render(<RiskFlags risks={undefined} />);
    expect(c1.firstChild).toBeNull();
    const { container: c2 } = render(<RiskFlags risks={null} />);
    expect(c2.firstChild).toBeNull();
  });

  it('renders an Attention Needed card with a count badge', () => {
    const risks = [
      { id: 1, severity: 'high', title: 'Your home insurance is expiring soon' },
      { id: 2, severity: 'low', title: 'Annual escrow review available' },
    ];
    render(<RiskFlags risks={risks} />);
    expect(screen.getByText('Attention Needed')).toBeInTheDocument();
    expect(screen.getByText('2 ITEMS')).toBeInTheDocument();
  });

  it('uses the singular ITEM label for a single risk', () => {
    render(<RiskFlags risks={[{ id: 1, severity: 'medium', title: 'One thing' }]} />);
    expect(screen.getByText('1 ITEM')).toBeInTheDocument();
  });

  it('maps severity to borrower-friendly chip labels (no raw codes)', () => {
    const risks = [
      { id: 1, severity: 'critical', title: 'A' },
      { id: 2, severity: 'medium', title: 'B' },
      { id: 3, severity: 'info', title: 'C' },
    ];
    render(<RiskFlags risks={risks} />);
    expect(screen.getByText('Needs your attention')).toBeInTheDocument();
    expect(screen.getByText('Heads up')).toBeInTheDocument();
    expect(screen.getByText('FYI')).toBeInTheDocument();
  });

  it('prefers borrower-safe labels/actions over internal title/description', () => {
    const risks = [
      {
        id: 1,
        severity: 'high',
        title: 'HOI_POLICY_LAPSE_RISK',
        borrower_label: 'Your home insurance is expiring soon',
        borrower_action: 'Send us your renewed policy',
      },
    ];
    render(<RiskFlags risks={risks} />);
    expect(screen.getByText('Your home insurance is expiring soon')).toBeInTheDocument();
    expect(screen.getByText(/Send us your renewed policy/)).toBeInTheDocument();
    expect(screen.queryByText('HOI_POLICY_LAPSE_RISK')).not.toBeInTheDocument();
  });
});
