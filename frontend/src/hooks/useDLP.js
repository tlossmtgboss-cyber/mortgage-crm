/**
 * useDLP Hook + ProtectedField Component
 *
 * React integration for the Data Loss Prevention service.
 * Provides declarative protection for sensitive mortgage data.
 *
 * Usage:
 *   const { protect, isProtected, dlpLevel } = useDLP('confidential');
 *   <div ref={protect}>Sensitive Content</div>
 *
 *   <ProtectedField level="restricted" fieldName="ssn" context={{ loan_id: '123' }}>
 *     SSN: {borrower.ssn}
 *   </ProtectedField>
 */

import { useRef, useEffect, useCallback, useState, useMemo } from 'react';
import React from 'react';
import {
  DLP_LEVELS,
  initDLP,
  destroyDLP,
  protectElement,
  unprotectElement,
  enableScreenshotProtection,
  disableScreenshotProtection,
  secureCopy,
  logFieldAccess,
  classifyField,
  requiresProtection,
  requiresAuditLog,
  flushAuditLog,
} from '../services/dataLossProtection';

// =============================================================================
// useDLP HOOK
// =============================================================================

/**
 * Hook that provides DLP protection for a container.
 *
 * @param {string} level - DLP classification level (from DLP_LEVELS)
 * @param {Object} options
 * @param {boolean} options.screenshotProtection - Enable screenshot protection when this component mounts
 * @param {string} options.fieldName - Field name for audit logging
 * @param {Object} options.context - Additional context for audit log (loan_id, borrower_id, etc.)
 * @returns {{ protect: React.RefCallback, isProtected: boolean, dlpLevel: string, secureCopy: Function }}
 */
export function useDLP(level = DLP_LEVELS.INTERNAL, options = {}) {
  const {
    screenshotProtection = false,
    fieldName = null,
    context = {},
  } = options;

  const elementRef = useRef(null);
  const [isProtected, setIsProtected] = useState(false);

  // Ref callback that both stores the element and applies protection
  const protect = useCallback((node) => {
    // Cleanup previous element
    if (elementRef.current && elementRef.current !== node) {
      unprotectElement(elementRef.current);
      setIsProtected(false);
    }

    elementRef.current = node;

    if (node && requiresProtection(level)) {
      protectElement(node);
      setIsProtected(true);

      // Log access for auditable levels
      if (requiresAuditLog(level) && fieldName) {
        logFieldAccess(fieldName, level, context);
      }
    }
  }, [level, fieldName, context]);

  // Enable/disable screenshot protection at the view level
  useEffect(() => {
    if (screenshotProtection && (level === DLP_LEVELS.CONFIDENTIAL || level === DLP_LEVELS.RESTRICTED)) {
      enableScreenshotProtection();
      return () => disableScreenshotProtection();
    }
  }, [screenshotProtection, level]);

  // Bounded secureCopy that logs with context
  const boundSecureCopy = useCallback((text, timeout) => {
    return secureCopy(text, timeout);
  }, []);

  return {
    protect,
    isProtected,
    dlpLevel: level,
    secureCopy: boundSecureCopy,
  };
}

// =============================================================================
// useDLPInit HOOK
// =============================================================================

/**
 * Initialize the DLP service at the app level.
 * Call this once in your root App component.
 *
 * @param {Object} options - Options passed to initDLP
 */
export function useDLPInit(options = {}) {
  useEffect(() => {
    initDLP(options);

    // Flush audit log when app goes to background
    const handleVisibility = () => {
      if (document.visibilityState === 'hidden') {
        flushAuditLog();
      }
    };

    document.addEventListener('visibilitychange', handleVisibility);

    // Periodic flush every 5 minutes
    const flushInterval = setInterval(() => {
      flushAuditLog();
    }, 5 * 60 * 1000);

    return () => {
      document.removeEventListener('visibilitychange', handleVisibility);
      clearInterval(flushInterval);
      destroyDLP();
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
}

// =============================================================================
// ProtectedField COMPONENT
// =============================================================================

/**
 * Wrapper component that applies DLP protections to sensitive content.
 *
 * Props:
 * @param {string} level - DLP classification level (default: auto-detect from fieldName)
 * @param {string} fieldName - Name of the field being displayed (used for classification and audit)
 * @param {Object} context - Additional audit context (loan_id, borrower_id, etc.)
 * @param {boolean} masked - If true, shows masked value with reveal-on-click (for RESTRICTED)
 * @param {string} maskChar - Character to use for masking (default: bullet)
 * @param {number} revealDuration - Auto-hide revealed value after this many ms (default: 10000)
 * @param {React.ReactNode} children - The sensitive content to protect
 * @param {string} className - Additional CSS class
 * @param {string} as - HTML element to render (default: 'span')
 */
export function ProtectedField({
  level,
  fieldName,
  context = {},
  masked = false,
  maskChar = '\u2022',
  revealDuration = 10000,
  children,
  className = '',
  as: Component = 'span',
  ...rest
}) {
  const [isRevealed, setIsRevealed] = useState(false);
  const revealTimerRef = useRef(null);

  // Auto-detect level from field name if not provided
  const effectiveLevel = useMemo(() => {
    if (level) return level;
    if (fieldName) return classifyField(fieldName);
    return DLP_LEVELS.INTERNAL;
  }, [level, fieldName]);

  // Auto-mask RESTRICTED fields by default
  const shouldMask = masked || effectiveLevel === DLP_LEVELS.RESTRICTED;

  // Apply protection via hook
  const { protect, isProtected } = useDLP(effectiveLevel, {
    fieldName,
    context,
    screenshotProtection: effectiveLevel === DLP_LEVELS.RESTRICTED,
  });

  // Handle reveal click for masked fields
  const handleRevealClick = useCallback(() => {
    if (!shouldMask) return;
    if (isRevealed) return;

    setIsRevealed(true);

    logFieldAccess(fieldName || 'unknown', effectiveLevel, {
      ...context,
      action: 'reveal',
    });

    // Auto-hide after duration
    revealTimerRef.current = setTimeout(() => {
      setIsRevealed(false);
    }, revealDuration);
  }, [shouldMask, isRevealed, fieldName, effectiveLevel, context, revealDuration]);

  // Cleanup reveal timer
  useEffect(() => {
    return () => {
      if (revealTimerRef.current) {
        clearTimeout(revealTimerRef.current);
      }
    };
  }, []);

  // Build class names
  const classNames = [
    'dlp-protected-field',
    effectiveLevel === DLP_LEVELS.RESTRICTED && 'dlp-restricted-field',
    className,
  ].filter(Boolean).join(' ');

  // Render masked or revealed content
  const renderContent = () => {
    if (!shouldMask || isRevealed) {
      return children;
    }

    // Convert children to string for masking
    const childText = _extractText(children);
    const maskedText = childText ? maskChar.repeat(Math.min(childText.length, 12)) : maskChar.repeat(8);

    return (
      React.createElement('span', {
        onClick: handleRevealClick,
        style: {
          cursor: 'pointer',
          letterSpacing: '2px',
          fontFamily: 'monospace',
        },
        title: 'Click to reveal',
        role: 'button',
        'aria-label': `Reveal ${fieldName || 'sensitive'} value`,
        tabIndex: 0,
        onKeyDown: (e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            handleRevealClick();
          }
        },
      }, maskedText)
    );
  };

  // Prevent caching for RESTRICTED content
  const restrictedAttrs = effectiveLevel === DLP_LEVELS.RESTRICTED
    ? { 'data-dlp-no-cache': 'true', autoComplete: 'off' }
    : {};

  return React.createElement(
    Component,
    {
      ref: protect,
      className: classNames,
      'data-dlp-level': effectiveLevel,
      'data-dlp-field': fieldName || undefined,
      ...restrictedAttrs,
      ...rest,
    },
    renderContent()
  );
}

// =============================================================================
// HELPER
// =============================================================================

/**
 * Extract text content from React children for masking purposes.
 * @param {React.ReactNode} children
 * @returns {string}
 */
function _extractText(children) {
  if (typeof children === 'string') return children;
  if (typeof children === 'number') return String(children);
  if (Array.isArray(children)) {
    return children.map(_extractText).join('');
  }
  if (children && typeof children === 'object' && children.props && children.props.children) {
    return _extractText(children.props.children);
  }
  return '';
}

// =============================================================================
// RE-EXPORTS for convenience
// =============================================================================

export { DLP_LEVELS } from '../services/dataLossProtection';

export default useDLP;
