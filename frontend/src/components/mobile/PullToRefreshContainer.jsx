import React, { useRef } from 'react';
import usePullToRefresh from '../../hooks/usePullToRefresh';
import './PullToRefreshContainer.css';

/**
 * PullToRefreshContainer - Wrapper component that adds pull-to-refresh
 * gesture support to any scrollable content.
 *
 * Renders a pull indicator (arrow that flips to a spinner) above the
 * children content. The container itself is the scroll target.
 *
 * @param {Object} props
 * @param {function}  props.onRefresh  - Async function called on pull-to-refresh
 * @param {React.ReactNode} props.children - Scrollable content
 * @param {boolean}  [props.disabled=false] - Disable the gesture
 * @param {number}   [props.threshold=80]   - Pull distance to trigger (px)
 * @param {number}   [props.maxPull=120]    - Max pull distance (px)
 * @param {string}   [props.className]      - Additional CSS class for the container
 */
const PullToRefreshContainer = ({
  onRefresh,
  children,
  disabled = false,
  threshold = 80,
  maxPull = 120,
  className = '',
}) => {
  const scrollRef = useRef(null);

  const { isRefreshing, pullProgress, pullDistance, isDragging } = usePullToRefresh({
    onRefresh,
    threshold,
    maxPull,
    disabled,
    containerRef: scrollRef,
  });

  const isActive = pullDistance > 0 || isRefreshing;
  const pastThreshold = pullProgress >= 1;

  // Determine the label text
  let statusText = 'Pull to refresh';
  if (isRefreshing) {
    statusText = 'Refreshing...';
  } else if (pastThreshold) {
    statusText = 'Release to refresh';
  }

  // Arrow rotation: 0deg (pointing down) -> 180deg (pointing up) as progress goes 0->1
  const arrowRotation = pullProgress * 180;

  return (
    <div
      ref={scrollRef}
      className={`ptr-container ${className}`}
      data-dragging={isDragging || undefined}
    >
      {/* Pull indicator */}
      <div
        className="ptr-indicator"
        style={{
          height: isActive ? pullDistance : 0,
          opacity: isActive ? 1 : 0,
        }}
        aria-hidden="true"
      >
        <div className="ptr-indicator__content">
          {isRefreshing ? (
            <div className="ptr-spinner" />
          ) : (
            <svg
              className="ptr-arrow"
              style={{ transform: `rotate(${arrowRotation}deg)` }}
              width="24"
              height="24"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <line x1="12" y1="5" x2="12" y2="19" />
              <polyline points="19 12 12 19 5 12" />
            </svg>
          )}
          <span className="ptr-text">{statusText}</span>
        </div>
      </div>

      {/* Scrollable content */}
      {children}
    </div>
  );
};

export default PullToRefreshContainer;
