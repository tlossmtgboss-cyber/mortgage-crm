/**
 * PortalQuickActions tests (portal consolidation Phase 1 harvest).
 *
 * The dead portals' quick-actions bar was decorative (no handlers). This is the
 * working version: Call/Message are real tel:/mailto: links from the LO contact
 * data the live portals already have; Upload/Schedule fire the portal's own
 * tab-switch and modal handlers.
 */
import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import PortalQuickActions from '../PortalQuickActions';

const lo = { name: 'Jane LO', phone: '8435551234', email: 'jane@example.com' };

describe('PortalQuickActions', () => {
  it('renders Call as a tel: link and Message as a mailto: link from LO data', () => {
    render(<PortalQuickActions loanOfficer={lo} onSchedule={() => {}} onUpload={() => {}} />);
    expect(screen.getByRole('link', { name: /call/i })).toHaveAttribute('href', 'tel:8435551234');
    expect(screen.getByRole('link', { name: /message/i })).toHaveAttribute('href', 'mailto:jane@example.com');
  });

  it('omits Call/Message when the LO has no phone/email', () => {
    render(<PortalQuickActions loanOfficer={{ name: 'No Contact' }} onSchedule={() => {}} onUpload={() => {}} />);
    expect(screen.queryByRole('link', { name: /call/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /message/i })).not.toBeInTheDocument();
  });

  it('fires onUpload and onSchedule when those buttons are clicked', () => {
    const onUpload = vi.fn();
    const onSchedule = vi.fn();
    render(<PortalQuickActions loanOfficer={lo} onSchedule={onSchedule} onUpload={onUpload} />);
    fireEvent.click(screen.getByRole('button', { name: /upload/i }));
    fireEvent.click(screen.getByRole('button', { name: /schedule/i }));
    expect(onUpload).toHaveBeenCalledTimes(1);
    expect(onSchedule).toHaveBeenCalledTimes(1);
  });

  it('hides the Upload button when showUpload is false', () => {
    render(<PortalQuickActions loanOfficer={lo} onSchedule={() => {}} showUpload={false} />);
    expect(screen.queryByRole('button', { name: /upload/i })).not.toBeInTheDocument();
  });
});
