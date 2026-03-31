import React, { useMemo } from 'react';
import { useReducedMotion } from '../../hooks/useReducedMotion';

/**
 * MotionSafeWrapper
 *
 * A wrapper component that conditionally applies CSS animations and
 * transitions based on the user's prefers-reduced-motion setting.
 *
 * Props:
 *   animation        - CSS animation value applied when motion is allowed
 *                      (e.g. "fadeIn 300ms ease-out")
 *   reducedFallback  - CSS animation value used when reduced motion is
 *                      active (default: "none")
 *   transition       - CSS transition value applied when motion is allowed
 *                      (e.g. "transform 200ms ease")
 *   style            - Additional inline styles merged with the wrapper
 *   className        - CSS class name forwarded to the outer element
 *   as               - HTML element type to render (default: "div")
 *   children         - React children
 *
 * Usage:
 *   <MotionSafeWrapper animation="slideUp 200ms ease-out">
 *     <Card />
 *   </MotionSafeWrapper>
 *
 *   <MotionSafeWrapper
 *     animation="fadeIn 300ms"
 *     reducedFallback="none"
 *     transition="opacity 150ms"
 *     style={{ padding: 16 }}
 *   >
 *     <Panel />
 *   </MotionSafeWrapper>
 */
function MotionSafeWrapper({
  animation,
  reducedFallback = 'none',
  transition: transitionProp,
  style: externalStyle,
  className,
  as: Component = 'div',
  children,
  ...rest
}) {
  const { prefersReducedMotion } = useReducedMotion();

  const motionStyle = useMemo(() => {
    const base = {};

    if (animation) {
      base.animation = prefersReducedMotion ? reducedFallback : animation;
    }

    if (transitionProp) {
      base.transition = prefersReducedMotion ? 'none' : transitionProp;
    }

    return { ...base, ...externalStyle };
  }, [
    animation,
    reducedFallback,
    transitionProp,
    prefersReducedMotion,
    externalStyle,
  ]);

  return (
    <Component
      className={className}
      style={motionStyle}
      data-reduced-motion={prefersReducedMotion ? 'true' : undefined}
      {...rest}
    >
      {children}
    </Component>
  );
}

export default MotionSafeWrapper;
