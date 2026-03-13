import React from 'react';

/**
 * ScreenReaderOnly - Visually hidden component that remains accessible to screen readers.
 *
 * Uses the CSS clip-rect technique to hide content visually while keeping it
 * in the accessibility tree. This is preferred over display:none or visibility:hidden
 * which remove the element from the accessibility tree entirely.
 *
 * Props:
 *   as      - The HTML element to render (default: 'span')
 *   children - Content to be read by screen readers
 *   focusable - If true, the element becomes visible when focused (useful for skip links)
 *   ...rest - Additional props passed to the underlying element
 */

const srOnlyStyle = {
  position: 'absolute',
  width: '1px',
  height: '1px',
  padding: 0,
  margin: '-1px',
  overflow: 'hidden',
  clip: 'rect(0, 0, 0, 0)',
  whiteSpace: 'nowrap',
  border: 0,
};

const srOnlyFocusableStyle = {
  ...srOnlyStyle,
};

// When focused, make the element visible
const focusedStyle = {
  position: 'static',
  width: 'auto',
  height: 'auto',
  padding: '0.5rem 1rem',
  margin: 0,
  overflow: 'visible',
  clip: 'auto',
  whiteSpace: 'normal',
};

const ScreenReaderOnly = React.forwardRef(function ScreenReaderOnly(
  { as: Component = 'span', children, focusable = false, style: customStyle, ...rest },
  ref
) {
  const [isFocused, setIsFocused] = React.useState(false);

  const baseStyle = focusable ? srOnlyFocusableStyle : srOnlyStyle;
  const computedStyle = focusable && isFocused
    ? { ...focusedStyle, ...customStyle }
    : { ...baseStyle, ...customStyle };

  const focusHandlers = focusable
    ? {
        onFocus: () => setIsFocused(true),
        onBlur: () => setIsFocused(false),
      }
    : {};

  return (
    <Component
      ref={ref}
      style={computedStyle}
      {...focusHandlers}
      {...rest}
    >
      {children}
    </Component>
  );
});

ScreenReaderOnly.displayName = 'ScreenReaderOnly';

export default ScreenReaderOnly;
