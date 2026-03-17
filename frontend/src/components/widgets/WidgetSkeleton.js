import React from 'react';

/**
 * WidgetSkeleton - Loading skeleton for schedule widgets.
 * Renders animated placeholder rows that mimic the appointment list layout.
 *
 * Props:
 *   rows  - Number of skeleton rows to render (default: 4)
 *   style - Optional inline style overrides
 */
function WidgetSkeleton({ rows = 4, style }) {
  return (
    <div className="widget-skeleton" style={style} aria-busy="true" aria-label="Loading schedule">
      {/* Date group header skeleton */}
      <div className="skeleton-date-header">
        <div className="skeleton-pulse skeleton-date-label" />
      </div>

      {Array.from({ length: rows }).map((_, idx) => (
        <div key={idx} className="skeleton-appointment-row">
          <div className="skeleton-time-col">
            <div className="skeleton-pulse skeleton-time" />
          </div>
          <div className="skeleton-type-stripe skeleton-pulse" />
          <div className="skeleton-details-col">
            <div className="skeleton-pulse skeleton-title" />
            <div className="skeleton-pulse skeleton-subtitle" />
          </div>
          <div className="skeleton-badge-col">
            <div className="skeleton-pulse skeleton-badge" />
          </div>
        </div>
      ))}

      {/* Second date group */}
      <div className="skeleton-date-header" style={{ marginTop: '12px' }}>
        <div className="skeleton-pulse skeleton-date-label" style={{ width: '80px' }} />
      </div>
      {Array.from({ length: Math.max(1, rows - 2) }).map((_, idx) => (
        <div key={`g2-${idx}`} className="skeleton-appointment-row">
          <div className="skeleton-time-col">
            <div className="skeleton-pulse skeleton-time" />
          </div>
          <div className="skeleton-type-stripe skeleton-pulse" />
          <div className="skeleton-details-col">
            <div className="skeleton-pulse skeleton-title" />
            <div className="skeleton-pulse skeleton-subtitle" />
          </div>
          <div className="skeleton-badge-col">
            <div className="skeleton-pulse skeleton-badge" />
          </div>
        </div>
      ))}
    </div>
  );
}

export default WidgetSkeleton;
