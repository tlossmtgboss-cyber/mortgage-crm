/**
 * SkeletonLoader -- Reusable skeleton/shimmer loading states for mobile screens.
 *
 * Composes the base Skeleton primitives from components/common/Skeleton.js
 * into mobile-optimized presets: pipeline cards, stats grids, lead cards,
 * list rows, and full-page dashboard skeletons.
 *
 * Props:
 *   variant  - 'card' | 'stats' | 'lead' | 'list' | 'dashboard' (default 'card')
 *   count    - Number of skeleton items to render (default 3)
 *   className - Additional CSS class names
 *
 * Usage:
 *   <SkeletonLoader variant="card" count={4} />
 *   <SkeletonLoader variant="dashboard" />
 */
import React from 'react';
import './SkeletonLoader.css';

// ---------------------------------------------------------------------------
// Bone -- single shimmer bar (self-contained, no dependency on Skeleton.js
// so this component works even if Skeleton.css is not loaded globally)
// ---------------------------------------------------------------------------
const Bone = ({ width, height, borderRadius, className = '', style = {} }) => (
  <div
    className={`skl-bone ${className}`}
    style={{
      width: width || '100%',
      height: height || '16px',
      borderRadius: borderRadius || '6px',
      ...style,
    }}
    aria-hidden="true"
  />
);

// ---------------------------------------------------------------------------
// Variant: Card -- matches MobilePipelineView loan cards
// ---------------------------------------------------------------------------
function CardSkeleton({ count = 3 }) {
  return (
    <div className="skl-card-list" role="status" aria-label="Loading cards">
      {Array.from({ length: count }, (_, i) => (
        <div key={i} className="skl-card" style={{ animationDelay: `${i * 0.1}s` }}>
          <div className="skl-card__top">
            <Bone width="55%" height="16px" />
            <Bone width="32px" height="16px" borderRadius="8px" />
          </div>
          <Bone width="35%" height="22px" />
          <Bone width="75%" height="14px" />
          <div className="skl-card__footer">
            <Bone width="45%" height="14px" />
            <Bone width="16px" height="16px" borderRadius="50%" />
          </div>
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Variant: Stats -- matches MobileHomeDashboard stat grid (2x2 + 1)
// ---------------------------------------------------------------------------
function StatsSkeleton({ count = 5 }) {
  return (
    <div className="skl-stats-grid" role="status" aria-label="Loading stats">
      {Array.from({ length: count }, (_, i) => (
        <div key={i} className="skl-stat" style={{ animationDelay: `${i * 0.08}s` }}>
          <Bone width="40px" height="28px" />
          <Bone width="60%" height="12px" />
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Variant: Lead -- matches MobileLeadCard layout
// ---------------------------------------------------------------------------
function LeadSkeleton({ count = 3 }) {
  return (
    <div className="skl-lead-list" role="status" aria-label="Loading leads">
      {Array.from({ length: count }, (_, i) => (
        <div key={i} className="skl-lead" style={{ animationDelay: `${i * 0.1}s` }}>
          <div className="skl-lead__row">
            <Bone width="20px" height="20px" borderRadius="50%" className="skl-lead__avatar" />
            <div className="skl-lead__info">
              <Bone width="60%" height="16px" />
              <Bone width="40%" height="12px" />
            </div>
            <Bone width="28px" height="16px" borderRadius="8px" />
          </div>
          <Bone width="80%" height="12px" />
          <div className="skl-lead__actions">
            <Bone width="48px" height="28px" borderRadius="14px" />
            <Bone width="48px" height="28px" borderRadius="14px" />
            <Bone width="48px" height="28px" borderRadius="14px" />
          </div>
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Variant: List -- generic row list (schedule, activity, alerts)
// ---------------------------------------------------------------------------
function ListSkeleton({ count = 3 }) {
  return (
    <div className="skl-list" role="status" aria-label="Loading list">
      {Array.from({ length: count }, (_, i) => (
        <div key={i} className="skl-list-row" style={{ animationDelay: `${i * 0.1}s` }}>
          <Bone width="20px" height="20px" borderRadius="50%" />
          <div className="skl-list-row__content">
            <Bone width={`${60 + (i % 3) * 10}%`} height="14px" />
            <Bone width={`${35 + (i % 2) * 15}%`} height="11px" />
          </div>
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Variant: Dashboard -- full MobileHomeDashboard skeleton
// Greeting + Stats + Alerts + Schedule + Activity
// ---------------------------------------------------------------------------
function DashboardSkeleton() {
  return (
    <div className="skl-dashboard" role="status" aria-label="Loading dashboard">
      {/* Greeting */}
      <div className="skl-dashboard__greeting">
        <Bone width="50%" height="24px" />
        <Bone width="35%" height="14px" />
      </div>

      {/* Stats */}
      <StatsSkeleton count={5} />

      {/* Alerts section */}
      <div className="skl-dashboard__section">
        <Bone width="30%" height="14px" className="skl-dashboard__section-title" />
        <ListSkeleton count={2} />
      </div>

      {/* Schedule section */}
      <div className="skl-dashboard__section">
        <Bone width="40%" height="14px" className="skl-dashboard__section-title" />
        <ListSkeleton count={3} />
      </div>

      {/* Activity section */}
      <div className="skl-dashboard__section">
        <Bone width="35%" height="14px" className="skl-dashboard__section-title" />
        <ListSkeleton count={3} />
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main export
// ---------------------------------------------------------------------------
export default function SkeletonLoader({ variant = 'card', count = 3, className = '' }) {
  const inner = (() => {
    switch (variant) {
      case 'stats':
        return <StatsSkeleton count={count} />;
      case 'lead':
        return <LeadSkeleton count={count} />;
      case 'list':
        return <ListSkeleton count={count} />;
      case 'dashboard':
        return <DashboardSkeleton />;
      case 'card':
      default:
        return <CardSkeleton count={count} />;
    }
  })();

  return (
    <div className={`skl-container ${className}`}>
      {inner}
    </div>
  );
}

// Named exports for direct use
export { CardSkeleton, StatsSkeleton, LeadSkeleton, ListSkeleton, DashboardSkeleton };
