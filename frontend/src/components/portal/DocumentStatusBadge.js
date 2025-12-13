/**
 * DocumentStatusBadge Component
 *
 * Displays document status with appropriate styling and icons.
 * Used in borrower portal document lists.
 */

import React from 'react';
import PropTypes from 'prop-types';
import './DocumentStatusBadge.css';

const statusConfig = {
  pending: {
    label: 'Requested',
    className: 'badge-pending',
    icon: 'clock'
  },
  uploaded: {
    label: 'Uploaded',
    className: 'badge-uploaded',
    icon: 'upload'
  },
  in_review: {
    label: 'In Review',
    className: 'badge-review',
    icon: 'search'
  },
  approved: {
    label: 'Approved',
    className: 'badge-approved',
    icon: 'check-circle'
  },
  rejected: {
    label: 'Needs Attention',
    className: 'badge-rejected',
    icon: 'alert-circle'
  },
  expired: {
    label: 'Expired',
    className: 'badge-expired',
    icon: 'alert-triangle'
  },
  quarantined: {
    label: 'Security Issue',
    className: 'badge-quarantined',
    icon: 'shield-off'
  }
};

const icons = {
  clock: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10" />
      <polyline points="12 6 12 12 16 14" />
    </svg>
  ),
  upload: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
      <polyline points="17 8 12 3 7 8" />
      <line x1="12" y1="3" x2="12" y2="15" />
    </svg>
  ),
  search: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="11" cy="11" r="8" />
      <line x1="21" y1="21" x2="16.65" y2="16.65" />
    </svg>
  ),
  'check-circle': (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
      <polyline points="22 4 12 14.01 9 11.01" />
    </svg>
  ),
  'alert-circle': (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10" />
      <line x1="12" y1="8" x2="12" y2="12" />
      <line x1="12" y1="16" x2="12.01" y2="16" />
    </svg>
  ),
  'alert-triangle': (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
      <line x1="12" y1="9" x2="12" y2="13" />
      <line x1="12" y1="17" x2="12.01" y2="17" />
    </svg>
  ),
  'shield-off': (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M19.69 14a6.9 6.9 0 0 0 .31-2V5l-8-3-3.16 1.18" />
      <path d="M4.73 4.73L4 5v7c0 6 8 10 8 10a20.29 20.29 0 0 0 5.62-4.38" />
      <line x1="1" y1="1" x2="23" y2="23" />
    </svg>
  )
};

function DocumentStatusBadge({ status, showIcon = true, size = 'medium' }) {
  const config = statusConfig[status] || statusConfig.pending;

  return (
    <span className={`document-status-badge ${config.className} badge-${size}`}>
      {showIcon && (
        <span className="badge-icon">
          {icons[config.icon]}
        </span>
      )}
      <span className="badge-label">{config.label}</span>
    </span>
  );
}

DocumentStatusBadge.propTypes = {
  status: PropTypes.oneOf([
    'pending',
    'uploaded',
    'in_review',
    'approved',
    'rejected',
    'expired',
    'quarantined'
  ]).isRequired,
  showIcon: PropTypes.bool,
  size: PropTypes.oneOf(['small', 'medium', 'large'])
};

export default DocumentStatusBadge;
