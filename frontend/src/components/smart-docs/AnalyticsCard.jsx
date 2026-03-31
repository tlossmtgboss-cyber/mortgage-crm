import React from 'react';
import './AnalyticsCard.css';

/**
 * AnalyticsCard — reusable metric display card.
 *
 * Props:
 *   title    {string}       — metric label, displayed uppercase
 *   value    {string|number}— the main metric value, displayed large
 *   subtitle {string}       — optional small text below value
 *   trend    {number}       — optional % change; positive = green, negative = red
 *   status   {string}       — "success" | "warning" | "error"; adds left border + modifier class
 *   icon     {node}         — optional icon element before title
 *   children {node}         — optional additional content below footer
 */
function AnalyticsCard({ title, value, subtitle, trend, status, icon, children }) {
  const cardClass = [
    'analytics-card',
    status ? `analytics-card--${status}` : '',
  ]
    .filter(Boolean)
    .join(' ');

  const trendPositive = typeof trend === 'number' && trend > 0;
  const trendNegative = typeof trend === 'number' && trend < 0;
  const trendClass = trendPositive
    ? 'analytics-card__trend analytics-card__trend--positive'
    : trendNegative
    ? 'analytics-card__trend analytics-card__trend--negative'
    : 'analytics-card__trend';

  const trendLabel =
    typeof trend === 'number'
      ? trendPositive
        ? `+${trend}%`
        : `${trend}%`
      : null;

  // Build a descriptive aria-label combining title, value, status, and trend
  const ariaLabelParts = [`${title}: ${value}`];
  if (status) ariaLabelParts.push(`Status: ${status}`);
  if (trendLabel !== null) ariaLabelParts.push(`Trend: ${trendLabel}`);
  const ariaLabel = ariaLabelParts.join(', ');

  return (
    <div
      className={cardClass}
      role="status"
      aria-label={ariaLabel}
    >
      <div className="analytics-card__header">
        {icon && <span className="analytics-card__icon" aria-hidden="true">{icon}</span>}
        <span className="analytics-card__title">{String(title).toUpperCase()}</span>
      </div>

      <div className="analytics-card__body">
        <span className="analytics-card__value">{value}</span>
        {subtitle && (
          <span className="analytics-card__subtitle">{subtitle}</span>
        )}
      </div>

      {trendLabel !== null && (
        <div className="analytics-card__footer">
          <span className={trendClass}>{trendLabel}</span>
        </div>
      )}

      {children && (
        <div className="analytics-card__children">
          {children}
        </div>
      )}
    </div>
  );
}

export default AnalyticsCard;
