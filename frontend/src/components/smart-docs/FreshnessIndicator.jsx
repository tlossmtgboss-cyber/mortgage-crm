/**
 * FreshnessIndicator Component
 *
 * Visual indicator showing document freshness status
 * with expiration countdown and status colors.
 */

import React from 'react';
import './FreshnessIndicator.css';

const FreshnessIndicator = ({
  status,
  daysUntilExpiration,
  expiresAt,
  compact = false,
  showDetails = true,
}) => {
  const statusConfig = {
    fresh: {
      label: 'Fresh',
      color: '#28a745',
      bgColor: '#d4edda',
      icon: '✓',
      description: 'Document is current',
    },
    expiring_soon: {
      label: 'Expiring Soon',
      color: '#fd7e14',
      bgColor: '#fff3cd',
      icon: '⚠️',
      description: 'Document will expire soon',
    },
    expired: {
      label: 'Expired',
      color: '#dc3545',
      bgColor: '#f8d7da',
      icon: '✗',
      description: 'Document has expired',
    },
    unknown: {
      label: 'Unknown',
      color: '#6c757d',
      bgColor: '#e2e3e5',
      icon: '?',
      description: 'Unable to determine freshness',
    },
    not_applicable: {
      label: 'N/A',
      color: '#6c757d',
      bgColor: '#e2e3e5',
      icon: '—',
      description: 'No freshness requirement',
    },
  };

  const config = statusConfig[status] || statusConfig.unknown;

  if (compact) {
    return (
      <div
        className="freshness-indicator compact"
        style={{ backgroundColor: config.bgColor, color: config.color }}
        title={`${config.label}${daysUntilExpiration !== null ? ` - ${formatDaysRemaining(daysUntilExpiration)}` : ''}`}
      >
        <span className="indicator-icon">{config.icon}</span>
        <span className="indicator-label">{config.label}</span>
        {daysUntilExpiration !== null && status !== 'expired' && status !== 'not_applicable' && (
          <span className="days-badge">
            {daysUntilExpiration}d
          </span>
        )}
      </div>
    );
  }

  return (
    <div
      className="freshness-indicator"
      style={{ borderColor: config.color }}
    >
      <div
        className="indicator-header"
        style={{ backgroundColor: config.bgColor }}
      >
        <span className="indicator-icon" style={{ color: config.color }}>
          {config.icon}
        </span>
        <span className="indicator-label" style={{ color: config.color }}>
          {config.label}
        </span>
      </div>

      {showDetails && (
        <div className="indicator-details">
          {status === 'fresh' && daysUntilExpiration !== null && (
            <div className="expiration-countdown">
              <div className="countdown-value">{daysUntilExpiration}</div>
              <div className="countdown-label">days until expiration</div>
              <div className="progress-bar">
                <div
                  className="progress-fill fresh"
                  style={{ width: `${Math.min(100, (daysUntilExpiration / 90) * 100)}%` }}
                />
              </div>
            </div>
          )}

          {status === 'expiring_soon' && daysUntilExpiration !== null && (
            <div className="expiration-countdown warning">
              <div className="countdown-value">{daysUntilExpiration}</div>
              <div className="countdown-label">days remaining</div>
              <div className="countdown-action">
                Consider uploading an updated document
              </div>
            </div>
          )}

          {status === 'expired' && (
            <div className="expired-notice">
              <p>This document has expired and cannot be used.</p>
              <p className="action-required">Please upload an updated version.</p>
            </div>
          )}

          {expiresAt && status !== 'expired' && (
            <div className="expiration-date">
              <span className="date-label">Expires:</span>
              <span className="date-value">{formatDate(expiresAt)}</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

/**
 * Compact inline badge version
 */
export const FreshnessBadge = ({ status, daysUntilExpiration }) => {
  const badges = {
    fresh: { bg: '#d4edda', color: '#155724', icon: '✓' },
    expiring_soon: { bg: '#fff3cd', color: '#856404', icon: '⚠️' },
    expired: { bg: '#f8d7da', color: '#721c24', icon: '✗' },
  };

  const badge = badges[status] || badges.fresh;

  return (
    <span
      className="freshness-badge"
      style={{ backgroundColor: badge.bg, color: badge.color }}
    >
      <span className="badge-icon">{badge.icon}</span>
      {daysUntilExpiration !== null && status !== 'expired' && (
        <span className="badge-days">{daysUntilExpiration}d</span>
      )}
    </span>
  );
};

/**
 * Progress bar showing freshness timeline
 */
export const FreshnessTimeline = ({
  docDate,
  expiresAt,
  freshnessdays = 30,
}) => {
  if (!docDate || !expiresAt) return null;

  const now = new Date();
  const start = new Date(docDate);
  const end = new Date(expiresAt);

  const totalDays = (end - start) / (1000 * 60 * 60 * 24);
  const elapsedDays = (now - start) / (1000 * 60 * 60 * 24);
  const percentElapsed = Math.min(100, Math.max(0, (elapsedDays / totalDays) * 100));

  let fillColor = '#28a745'; // Green
  if (percentElapsed > 75) fillColor = '#fd7e14'; // Orange
  if (percentElapsed >= 100) fillColor = '#dc3545'; // Red

  return (
    <div className="freshness-timeline">
      <div className="timeline-bar">
        <div
          className="timeline-fill"
          style={{ width: `${percentElapsed}%`, backgroundColor: fillColor }}
        />
        <div className="timeline-marker" style={{ left: `${percentElapsed}%` }} />
      </div>
      <div className="timeline-labels">
        <span className="label-start">{formatShortDate(docDate)}</span>
        <span className="label-end">{formatShortDate(expiresAt)}</span>
      </div>
    </div>
  );
};

// Helper functions
function formatDaysRemaining(days) {
  if (days === null || days === undefined) return '';
  if (days < 0) return `${Math.abs(days)} days ago`;
  if (days === 0) return 'Today';
  if (days === 1) return '1 day';
  return `${days} days`;
}

function formatDate(dateStr) {
  if (!dateStr) return '';
  const date = new Date(dateStr);
  return date.toLocaleDateString('en-US', {
    month: 'long',
    day: 'numeric',
    year: 'numeric',
  });
}

function formatShortDate(dateStr) {
  if (!dateStr) return '';
  const date = new Date(dateStr);
  return date.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
  });
}

export default FreshnessIndicator;
