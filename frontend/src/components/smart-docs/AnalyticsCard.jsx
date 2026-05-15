import React, { useMemo, useCallback } from 'react';
import './AnalyticsCard.css';

/**
 * AnalyticsCard — reusable metric display card.
 *
 * Props:
 *   title         {string}       — metric label, displayed uppercase
 *   value         {string|number}— the main metric value, displayed large
 *   subtitle      {string}       — optional small text below value
 *   trend         {number}       — optional % change; positive = green, negative = red
 *   status        {string}       — "success" | "warning" | "error"; adds left border + modifier class
 *   icon          {node}         — optional icon element before title
 *   children      {node}         — optional additional content below footer
 *   sparklineData {number[]}     — optional array of numbers to render a mini SVG sparkline
 *   previousValue {number}       — optional previous period value; shows comparison text and auto-calculates trend
 *   loading       {boolean}      — optional; shows skeleton shimmer placeholders instead of value/subtitle
 *   onClick       {function}     — optional click handler; makes card clickable with hover elevation
 *   size          {string}       — "sm" | "md" | "lg"; controls padding and font sizes (default "md")
 *   tooltip       {string}       — optional tooltip text; shows info icon next to title
 */
function AnalyticsCard({
  title,
  value,
  subtitle,
  trend,
  status,
  icon,
  children,
  sparklineData,
  previousValue,
  loading = false,
  onClick,
  size = 'md',
  tooltip,
}) {
  // Auto-calculate trend from previousValue if trend prop not explicitly provided
  const computedTrend = useMemo(() => {
    if (typeof trend === 'number') return trend;
    if (typeof previousValue === 'number' && typeof value === 'number' && previousValue !== 0) {
      return Math.round(((value - previousValue) / Math.abs(previousValue)) * 100);
    }
    return null;
  }, [trend, previousValue, value]);

  const trendPositive = typeof computedTrend === 'number' && computedTrend > 0;
  const trendNegative = typeof computedTrend === 'number' && computedTrend < 0;

  const trendClass = trendPositive
    ? 'analytics-card__trend analytics-card__trend--positive'
    : trendNegative
    ? 'analytics-card__trend analytics-card__trend--negative'
    : 'analytics-card__trend';

  const trendLabel =
    typeof computedTrend === 'number'
      ? trendPositive
        ? `+${computedTrend}%`
        : `${computedTrend}%`
      : null;

  // Build card class names
  const cardClass = [
    'analytics-card',
    status ? `analytics-card--${status}` : '',
    size !== 'md' ? `analytics-card--${size}` : '',
    onClick ? 'analytics-card--clickable' : '',
    loading ? 'analytics-card--loading' : '',
  ]
    .filter(Boolean)
    .join(' ');

  // Build a descriptive aria-label combining title, value, trend
  const ariaLabelParts = [`${title}: ${loading ? 'Loading' : value}`];
  if (status) ariaLabelParts.push(`Status: ${status}`);
  if (trendLabel !== null) ariaLabelParts.push(`Trend: ${trendLabel}`);
  const ariaLabel = ariaLabelParts.join(', ');

  // Keyboard support for clickable cards
  const handleKeyDown = useCallback(
    (e) => {
      if (onClick && (e.key === 'Enter' || e.key === ' ')) {
        e.preventDefault();
        onClick(e);
      }
    },
    [onClick]
  );

  // Sparkline color based on status
  const sparklineColor = useMemo(() => {
    if (status === 'success') return 'var(--color-success, #1F3D2E)';
    if (status === 'warning') return 'var(--color-warning, #A84B2F)';
    if (status === 'error') return 'var(--color-error, #C0152F)';
    return 'var(--color-primary, #1F3D2E)';
  }, [status]);

  return (
    <div
      className={cardClass}
      role={onClick ? 'button' : 'status'}
      aria-label={ariaLabel}
      tabIndex={onClick ? 0 : undefined}
      onClick={onClick}
      onKeyDown={onClick ? handleKeyDown : undefined}
    >
      <div className="analytics-card__header">
        {icon && <span className="analytics-card__icon" aria-hidden="true">{icon}</span>}
        <span className="analytics-card__title">{String(title).toUpperCase()}</span>
        {tooltip && (
          <span
            className="analytics-card__tooltip-trigger"
            title={tooltip}
            aria-label={`Info: ${tooltip}`}
          >
            ?
          </span>
        )}
      </div>

      <div className="analytics-card__body">
        {loading ? (
          <>
            <span className="analytics-card__skeleton analytics-card__skeleton--value" aria-hidden="true" />
            <span className="analytics-card__skeleton analytics-card__skeleton--subtitle" aria-hidden="true" />
          </>
        ) : (
          <>
            <span className="analytics-card__value">{value}</span>
            {typeof previousValue === 'number' && (
              <span className="analytics-card__comparison">
                <span
                  className={
                    trendPositive
                      ? 'analytics-card__comparison-arrow analytics-card__comparison-arrow--up'
                      : trendNegative
                      ? 'analytics-card__comparison-arrow analytics-card__comparison-arrow--down'
                      : 'analytics-card__comparison-arrow'
                  }
                  aria-hidden="true"
                >
                  {trendPositive ? '\u2191' : trendNegative ? '\u2193' : ''}
                </span>
                vs. {previousValue} last period
              </span>
            )}
            {subtitle && (
              <span className="analytics-card__subtitle">{subtitle}</span>
            )}
          </>
        )}
      </div>

      {!loading && trendLabel !== null && (
        <div className="analytics-card__footer">
          <span className={trendClass}>{trendLabel}</span>
        </div>
      )}

      {!loading && sparklineData && sparklineData.length > 1 && (
        <Sparkline data={sparklineData} color={sparklineColor} />
      )}

      {children && (
        <div className="analytics-card__children">
          {children}
        </div>
      )}
    </div>
  );
}

/**
 * Sparkline — tiny SVG line chart rendered in the card footer.
 * Animated on mount via CSS stroke-dasharray transition.
 */
function Sparkline({ data, color }) {
  const width = 60;
  const height = 20;
  const padding = 1;

  const points = useMemo(() => {
    if (!data || data.length < 2) return '';
    const min = Math.min(...data);
    const max = Math.max(...data);
    const range = max - min || 1;
    const stepX = (width - padding * 2) / (data.length - 1);

    return data
      .map((val, i) => {
        const x = padding + i * stepX;
        const y = height - padding - ((val - min) / range) * (height - padding * 2);
        return `${x},${y}`;
      })
      .join(' ');
  }, [data]);

  // Approximate total path length for dash animation
  const pathLength = useMemo(() => {
    if (!data || data.length < 2) return 0;
    const min = Math.min(...data);
    const max = Math.max(...data);
    const range = max - min || 1;
    const stepX = (width - padding * 2) / (data.length - 1);
    let len = 0;
    for (let i = 1; i < data.length; i++) {
      const dx = stepX;
      const dy =
        ((data[i] - min) / range) * (height - padding * 2) -
        ((data[i - 1] - min) / range) * (height - padding * 2);
      len += Math.sqrt(dx * dx + dy * dy);
    }
    return Math.ceil(len);
  }, [data]);

  if (!points) return null;

  return (
    <div className="analytics-card__sparkline" aria-hidden="true">
      <svg
        width={width}
        height={height}
        viewBox={`0 0 ${width} ${height}`}
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
      >
        <polyline
          points={points}
          stroke={color}
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeLinejoin="round"
          fill="none"
          className="analytics-card__sparkline-line"
          style={{
            strokeDasharray: pathLength,
            strokeDashoffset: pathLength,
          }}
        />
      </svg>
    </div>
  );
}

export default AnalyticsCard;
