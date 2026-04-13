import React from 'react';
import './IncomeConfidenceBadge.css';

/**
 * Canonical confidence badge component for income-related scores.
 *
 * Thresholds (match backend):
 *   >= 98  Auto-Approved (teal solid)
 *   >= 90  High          (teal tonal)
 *   >= 70  Medium        (warning tonal)
 *   <  70  Low           (error tonal)
 *
 * @param {Object} props
 * @param {number}  props.score     - Confidence score 0-100
 * @param {'sm'|'md'|'lg'} [props.size='md'] - Badge size
 * @param {boolean} [props.showLabel=false]   - Show threshold label text
 * @param {boolean} [props.showBar=false]     - Render as progress bar instead of pill badge
 * @param {boolean} [props.animated=true]     - Animate on mount
 */

function getThreshold(score) {
  const s = Number(score) || 0;
  if (s >= 98) return { key: 'auto-approved', label: 'Auto-Approved', level: 'High' };
  if (s >= 90) return { key: 'high', label: 'High', level: 'High' };
  if (s >= 70) return { key: 'medium', label: 'Medium', level: 'Medium' };
  return { key: 'low', label: 'Low', level: 'Low' };
}

function IncomeConfidenceBadge({
  score,
  size = 'md',
  showLabel = false,
  showBar = false,
  animated = true,
}) {
  const clamped = Math.max(0, Math.min(100, Math.round(Number(score) || 0)));
  const threshold = getThreshold(clamped);

  const ariaLabel = `Confidence score: ${clamped}%, level: ${threshold.level}`;

  if (showBar) {
    return (
      <div
        className={`icb-bar icb-bar--${size} icb-bar--${threshold.key}`}
        role="meter"
        aria-label={ariaLabel}
        aria-valuenow={clamped}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        <div className="icb-bar__track">
          <div
            className={`icb-bar__fill${animated ? ' icb-bar__fill--animated' : ''}`}
            style={{ width: `${clamped}%` }}
          />
        </div>
        <span className="icb-bar__text">{clamped}%</span>
      </div>
    );
  }

  return (
    <span
      className={`icb-badge icb-badge--${size} icb-badge--${threshold.key}${animated ? ' icb-badge--animated' : ''}`}
      role="meter"
      aria-label={ariaLabel}
      aria-valuenow={clamped}
      aria-valuemin={0}
      aria-valuemax={100}
    >
      {clamped}%{showLabel ? ` ${threshold.label}` : ''}
    </span>
  );
}

export default IncomeConfidenceBadge;
