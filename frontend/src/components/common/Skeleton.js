/**
 * Skeleton Loading Components
 *
 * Base skeleton primitives with shimmer animation for loading states.
 * Uses pure CSS animations and the app's CSS custom properties.
 */
import React from 'react';
import './Skeleton.css';

/**
 * Base skeleton element with configurable dimensions and shape.
 *
 * @param {object} props
 * @param {string|number} props.width - CSS width (default '100%')
 * @param {string|number} props.height - CSS height (default '16px')
 * @param {string|number} props.borderRadius - CSS border radius (default 'var(--radius-sm)')
 * @param {string} props.className - Additional CSS class names
 * @param {object} props.style - Additional inline styles
 * @param {string} props.ariaLabel - Accessible label for the skeleton
 */
const Skeleton = React.memo(function Skeleton({
  width = '100%',
  height = '16px',
  borderRadius = 'var(--radius-sm)',
  className = '',
  style = {},
  ariaLabel,
}) {
  const resolvedWidth = typeof width === 'number' ? `${width}px` : width;
  const resolvedHeight = typeof height === 'number' ? `${height}px` : height;
  const resolvedRadius = typeof borderRadius === 'number' ? `${borderRadius}px` : borderRadius;

  return (
    <div
      className={`skeleton ${className}`}
      role="presentation"
      aria-label={ariaLabel || 'Loading...'}
      aria-busy="true"
      style={{
        width: resolvedWidth,
        height: resolvedHeight,
        borderRadius: resolvedRadius,
        ...style,
      }}
    />
  );
});

/**
 * Single text-line skeleton.
 *
 * @param {object} props
 * @param {string|number} props.width - Line width (default '100%')
 * @param {string} props.size - 'sm' | 'md' | 'lg' (default 'md')
 */
const SkeletonText = React.memo(function SkeletonText({
  width = '100%',
  size = 'md',
  className = '',
  style = {},
}) {
  const heightMap = { sm: '12px', md: '16px', lg: '20px' };
  return (
    <Skeleton
      width={width}
      height={heightMap[size] || '16px'}
      borderRadius="var(--radius-sm)"
      className={`skeleton-text skeleton-text--${size} ${className}`}
      style={style}
    />
  );
});

/**
 * Circular skeleton for avatars and icons.
 *
 * @param {object} props
 * @param {number} props.size - Diameter in pixels (default 40)
 */
const SkeletonCircle = React.memo(function SkeletonCircle({
  size = 40,
  className = '',
  style = {},
}) {
  return (
    <Skeleton
      width={size}
      height={size}
      borderRadius="50%"
      className={`skeleton-circle ${className}`}
      style={{ flexShrink: 0, ...style }}
    />
  );
});

/**
 * Rectangular skeleton for cards, images, and content blocks.
 *
 * @param {object} props
 * @param {string|number} props.width - Width (default '100%')
 * @param {string|number} props.height - Height (default '120px')
 */
const SkeletonRect = React.memo(function SkeletonRect({
  width = '100%',
  height = '120px',
  className = '',
  style = {},
}) {
  return (
    <Skeleton
      width={width}
      height={height}
      borderRadius="var(--radius-base)"
      className={`skeleton-rect ${className}`}
      style={style}
    />
  );
});

/**
 * Group container for composing multiple skeleton elements.
 * Provides consistent spacing and optional stagger animation.
 *
 * @param {object} props
 * @param {React.ReactNode} props.children - Skeleton elements
 * @param {string} props.gap - CSS gap (default 'var(--space-sm)')
 * @param {string} props.direction - 'column' | 'row' (default 'column')
 * @param {boolean} props.stagger - Apply staggered animation delays (default false)
 * @param {string} props.className - Additional CSS class names
 */
const SkeletonGroup = React.memo(function SkeletonGroup({
  children,
  gap = 'var(--space-sm)',
  direction = 'column',
  stagger = false,
  className = '',
  style = {},
}) {
  return (
    <div
      className={`skeleton-group ${stagger ? 'skeleton-group--stagger' : ''} ${className}`}
      role="status"
      aria-label="Loading content"
      style={{
        display: 'flex',
        flexDirection: direction,
        gap,
        ...style,
      }}
    >
      {stagger
        ? React.Children.map(children, (child, index) => {
            if (!React.isValidElement(child)) return child;
            return React.cloneElement(child, {
              style: {
                ...child.props.style,
                animationDelay: `${index * 80}ms`,
              },
            });
          })
        : children}
    </div>
  );
});

export { Skeleton, SkeletonText, SkeletonCircle, SkeletonRect, SkeletonGroup };
export default Skeleton;
