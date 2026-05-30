/**
 * PortalQuickActions — floating quick-action bar for the borrower stage portals.
 *
 * Portal consolidation Phase 1 harvest. The deleted portals had a quick-actions
 * bar that was pure decoration (no click handlers). This is the working version:
 * Call/Message are real tel:/mailto: links built from the LO contact data the
 * PURL portal already has; Upload/Schedule delegate to the host portal's own
 * tab-switch and ScheduleAppointmentModal. Inline-styled so it carries no
 * dependency on the deleted components' CSS.
 */
import React from 'react';

const bar = {
  position: 'sticky',
  bottom: 0,
  display: 'flex',
  gap: 8,
  justifyContent: 'center',
  flexWrap: 'wrap',
  padding: '12px 16px',
  background: 'rgba(255,255,255,0.96)',
  borderTop: '1px solid #e2e8f0',
  boxShadow: '0 -2px 8px rgba(0,0,0,0.06)',
  zIndex: 10,
};
const btn = {
  display: 'inline-flex',
  alignItems: 'center',
  gap: 6,
  padding: '10px 16px',
  borderRadius: 10,
  border: '1px solid #cbd5e1',
  background: '#fff',
  color: '#1a202c',
  fontSize: 14,
  fontWeight: 500,
  cursor: 'pointer',
  textDecoration: 'none',
};
const primary = { ...btn, background: '#1F3D2E', color: '#fff', border: '1px solid #1F3D2E' };

export default function PortalQuickActions({ loanOfficer, onSchedule, onUpload, showUpload = true }) {
  const phone = loanOfficer?.phone;
  const email = loanOfficer?.email;

  return (
    <div className="portal-quick-actions" style={bar}>
      {phone && (
        <a href={`tel:${phone}`} style={primary} title="Call your loan officer">
          <span aria-hidden="true">📞</span> Call LO
        </a>
      )}
      {email && (
        <a href={`mailto:${email}`} style={btn} title="Email your loan officer">
          <span aria-hidden="true">💬</span> Message
        </a>
      )}
      {showUpload && onUpload && (
        <button type="button" style={btn} onClick={onUpload} title="Upload a document">
          <span aria-hidden="true">📄</span> Upload
        </button>
      )}
      {onSchedule && (
        <button type="button" style={btn} onClick={onSchedule} title="Schedule a call">
          <span aria-hidden="true">📅</span> Schedule
        </button>
      )}
    </div>
  );
}
