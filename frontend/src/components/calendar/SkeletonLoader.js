import React from 'react';
import './SkeletonLoader.css';

/**
 * SkeletonLoader -- Reusable animated loading placeholder for calendar sections.
 *
 * Renders shimmer-animated placeholder shapes matching the layout of the content
 * being loaded. Includes ARIA attributes for screen reader accessibility.
 *
 * Used in: Calendar, CalendarSettings, and anywhere loading states are needed
 *
 * @param {Object} props
 * @param {string} [props.type='card'] - Skeleton layout variant ('appointments'|'tasks'|'card'|'table'|'calendar-grid')
 * @param {number} [props.count=3] - Number of placeholder items (for appointments, tasks, card types)
 * @param {number} [props.rows=5] - Number of table rows (table type only)
 * @param {number} [props.cols=4] - Number of table columns (table type only)
 * @param {string} [props.label='Loading'] - Accessible label describing what is loading
 * @returns {React.ReactElement}
 *
 * @example
 * <SkeletonLoader type="appointments" count={5} />
 * <SkeletonLoader type="table" rows={5} cols={4} label="Loading analytics" />
 * <SkeletonLoader type="calendar-grid" />
 */
function SkeletonLoader({
  type = 'card',
  count = 3,
  rows = 5,
  cols = 4,
  label = 'Loading',
}) {
  return (
    <div
      className="cal-skel-container"
      role="status"
      aria-busy="true"
      aria-label={label}
    >
      {/* Screen reader announcement */}
      <span className="sr-only">{label}</span>

      {type === 'appointments' && <AppointmentsSkeleton count={count} />}
      {type === 'tasks' && <TasksSkeleton count={count} />}
      {type === 'card' && <CardSkeleton count={count} />}
      {type === 'table' && <TableSkeleton rows={rows} cols={cols} />}
      {type === 'calendar-grid' && <CalendarGridSkeleton />}
    </div>
  );
}

/* ---------------------------------------------------------------------------
   Appointment Card Skeleton
   --------------------------------------------------------------------------- */

function AppointmentsSkeleton({ count }) {
  return Array.from({ length: count }, (_, i) => (
    <div key={i} className="cal-skel-appointment" aria-hidden="true">
      <div className="cal-skel-bone cal-skel-appointment-time" />
      <div className="cal-skel-appointment-content">
        <div className="cal-skel-bone cal-skel-appointment-title" style={staggerStyle(i)} />
        <div className="cal-skel-bone cal-skel-appointment-detail" style={staggerStyle(i, 0.08)} />
        <div className="cal-skel-bone cal-skel-appointment-meta" style={staggerStyle(i, 0.16)} />
      </div>
    </div>
  ));
}

/* ---------------------------------------------------------------------------
   Task List Skeleton
   --------------------------------------------------------------------------- */

function TasksSkeleton({ count }) {
  return Array.from({ length: count }, (_, i) => (
    <div key={i} className="cal-skel-task" aria-hidden="true">
      <div className="cal-skel-bone cal-skel-task-checkbox" />
      <div className="cal-skel-task-text">
        <div className="cal-skel-bone cal-skel-task-label" style={staggerStyle(i)} />
        <div className="cal-skel-bone cal-skel-task-sub" style={staggerStyle(i, 0.08)} />
      </div>
    </div>
  ));
}

/* ---------------------------------------------------------------------------
   Card Skeleton
   --------------------------------------------------------------------------- */

function CardSkeleton({ count }) {
  return Array.from({ length: count }, (_, i) => (
    <div key={i} className="cal-skel-card" aria-hidden="true">
      <div className="cal-skel-bone cal-skel-card-header" style={staggerStyle(i)} />
      <div className="cal-skel-bone cal-skel-card-line" style={staggerStyle(i, 0.06)} />
      <div className="cal-skel-bone cal-skel-card-line cal-skel-card-line--short" style={staggerStyle(i, 0.12)} />
      <div className="cal-skel-bone cal-skel-card-line cal-skel-card-line--xs" style={staggerStyle(i, 0.18)} />
    </div>
  ));
}

/* ---------------------------------------------------------------------------
   Table Skeleton
   --------------------------------------------------------------------------- */

function TableSkeleton({ rows, cols }) {
  return (
    <div className="cal-skel-table" aria-hidden="true">
      <div className="cal-skel-table-header">
        {Array.from({ length: cols }, (_, c) => (
          <div key={c} className="cal-skel-bone cal-skel-table-header-cell" style={staggerStyle(c, 0.04)} />
        ))}
      </div>
      {Array.from({ length: rows }, (_, r) => (
        <div key={r} className="cal-skel-table-row">
          {Array.from({ length: cols }, (_, c) => (
            <div
              key={c}
              className="cal-skel-bone cal-skel-table-cell"
              style={{
                ...staggerStyle(r, 0.06),
                width: `${55 + Math.sin((r + c) * 1.3) * 25}%`,
              }}
            />
          ))}
        </div>
      ))}
    </div>
  );
}

/* ---------------------------------------------------------------------------
   Calendar Grid Skeleton
   --------------------------------------------------------------------------- */

function CalendarGridSkeleton() {
  // 7 columns x 5 rows (typical month view)
  const dayCount = 35;

  return (
    <div aria-hidden="true">
      {/* Day-of-week header */}
      <div className="cal-skel-grid-header">
        {Array.from({ length: 7 }, (_, i) => (
          <div key={i} className="cal-skel-grid-header-cell">
            <div className="cal-skel-bone" style={staggerStyle(i, 0.03)} />
          </div>
        ))}
      </div>

      {/* Day cells */}
      <div className="cal-skel-grid">
        {Array.from({ length: dayCount }, (_, i) => {
          // Vary the number of event bars per day for realism
          const eventCount = [0, 1, 2, 1, 0, 2, 1, 0, 1, 3, 0, 1][i % 12];
          return (
            <div key={i} className="cal-skel-grid-day">
              <div className="cal-skel-bone cal-skel-grid-day-number" style={staggerStyle(i, 0.02)} />
              {Array.from({ length: eventCount }, (_, e) => (
                <div
                  key={e}
                  className={`cal-skel-bone cal-skel-grid-day-event ${
                    e % 2 === 0 ? 'cal-skel-grid-day-event--long' : 'cal-skel-grid-day-event--short'
                  }`}
                  style={staggerStyle(i + e, 0.03)}
                />
              ))}
            </div>
          );
        })}
      </div>
    </div>
  );
}

/* ---------------------------------------------------------------------------
   Helpers
   --------------------------------------------------------------------------- */

/**
 * Stagger the shimmer animation so items don't all pulse in sync.
 * Returns an inline style with a negative animation-delay.
 */
function staggerStyle(index, offsetSec = 0.1) {
  return { animationDelay: `${-(index * offsetSec).toFixed(2)}s` };
}

export default SkeletonLoader;
