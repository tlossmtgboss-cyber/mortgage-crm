import React from 'react';
import './IncomeLoadingSkeleton.css';

/**
 * IncomeCardSkeleton
 * Mimics the Qualifying Income Summary card (.income-summary-card in IncomeTab).
 * Header bar, two side-by-side amount boxes, and a status badge placeholder.
 */
export function IncomeCardSkeleton() {
  return (
    <div className="income-card-skeleton">
      <div className="income-card-skeleton__header">
        <div className="income-card-skeleton__title skeleton-bar" />
        <div className="income-card-skeleton__badge skeleton-bar" />
      </div>
      <div className="income-card-skeleton__amounts">
        <div className="income-card-skeleton__amount-group">
          <div className="income-card-skeleton__amount-label skeleton-bar" />
          <div className="income-card-skeleton__amount-value skeleton-bar" />
        </div>
        <div className="income-card-skeleton__divider" />
        <div className="income-card-skeleton__amount-group">
          <div className="income-card-skeleton__amount-label skeleton-bar" />
          <div className="income-card-skeleton__amount-value skeleton-bar" />
        </div>
      </div>
      <div className="income-card-skeleton__status">
        <div className="income-card-skeleton__status-pill skeleton-bar" />
      </div>
    </div>
  );
}

/**
 * IncomeStreamSkeleton
 * Mimics a single income source card (.source-card in IncomeTab).
 * Left color bar, icon circle + name bar + trend badge, amount bar below.
 *
 * @param {{ count?: number }} props — number of stream rows to render (default 3)
 */
export function IncomeStreamSkeleton({ count = 3 }) {
  return (
    <>
      {Array.from({ length: count }, (_, i) => (
        <div className="income-stream-skeleton" key={i}>
          <div className="income-stream-skeleton__color-bar" />
          <div className="income-stream-skeleton__content">
            <div className="income-stream-skeleton__header">
              <div className="income-stream-skeleton__icon skeleton-circle" />
              <div className="income-stream-skeleton__name skeleton-bar" />
              <div className="income-stream-skeleton__trend skeleton-bar" />
            </div>
            <div className="income-stream-skeleton__amount skeleton-bar" />
          </div>
        </div>
      ))}
    </>
  );
}

/**
 * IncomeTableSkeleton
 * Mimics the bank statement worksheet table.
 * Header row with 6 column placeholders, 4 data rows with varying-width shimmer bars.
 */
export function IncomeTableSkeleton() {
  return (
    <div className="income-table-skeleton">
      <div className="income-table-skeleton__header">
        {Array.from({ length: 6 }, (_, i) => (
          <div className="income-table-skeleton__header-cell skeleton-bar" key={i} />
        ))}
      </div>
      {Array.from({ length: 4 }, (_, rowIdx) => (
        <div className="income-table-skeleton__row" key={rowIdx}>
          {Array.from({ length: 6 }, (_, colIdx) => (
            <div className="income-table-skeleton__cell skeleton-bar" key={colIdx} />
          ))}
        </div>
      ))}
    </div>
  );
}

/**
 * IncomeFormSkeleton
 * Mimics the UnifiedIncomeCalculator input form.
 * 5 type buttons as rectangles, 3 form field groups (label + input), and a submit button.
 */
export function IncomeFormSkeleton() {
  return (
    <div className="income-form-skeleton">
      <div className="income-form-skeleton__type-buttons">
        {Array.from({ length: 5 }, (_, i) => (
          <div className="income-form-skeleton__type-btn skeleton-bar" key={i} />
        ))}
      </div>
      <div className="income-form-skeleton__fields">
        {Array.from({ length: 3 }, (_, i) => (
          <div className="income-form-skeleton__field-group" key={i}>
            <div className="income-form-skeleton__label skeleton-bar" />
            <div className="income-form-skeleton__input skeleton-bar" />
          </div>
        ))}
        <div className="income-form-skeleton__submit skeleton-bar" />
      </div>
    </div>
  );
}

/**
 * AnalyticsCardsSkeleton
 * Mimics a grid of 4 summary analytics cards.
 * Each card has a title bar, value bar, and subtitle bar.
 */
export function AnalyticsCardsSkeleton() {
  return (
    <div className="analytics-cards-skeleton">
      {Array.from({ length: 4 }, (_, i) => (
        <div className="analytics-card-skeleton" key={i}>
          <div className="analytics-card-skeleton__title skeleton-bar" />
          <div className="analytics-card-skeleton__value skeleton-bar" />
          <div className="analytics-card-skeleton__subtitle skeleton-bar" />
        </div>
      ))}
    </div>
  );
}
