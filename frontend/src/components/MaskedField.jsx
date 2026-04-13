/**
 * MaskedField Component
 *
 * Reusable component that displays PII data in masked form by default,
 * with a toggle to reveal the actual value. Integrates with the
 * piiMasking utility and the DLP audit system.
 *
 * Usage:
 *   <MaskedField value="123456789" type="ssn" />
 *   <MaskedField value="03/15/1990" type="dob" />
 *   <MaskedField value={85000} type="income" />
 *   <MaskedField value="user@example.com" type="email" revealed={true} />
 */

import React, { useState, useCallback, useEffect, useRef } from 'react';
import { formatMasked } from '../utils/piiMasking';
import { logFieldAccess, classifyField } from '../services/dataLossProtection';

// Inline styles to avoid a separate CSS file for a single component
const styles = {
  container: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: '6px',
    fontFamily: 'inherit',
  },
  value: {
    fontFamily: "'SF Mono', 'Fira Code', 'Consolas', monospace",
    fontSize: 'inherit',
    letterSpacing: '0.5px',
  },
  maskedValue: {
    color: 'var(--text-secondary, #6b7280)',
  },
  revealedValue: {
    color: 'var(--text-primary, #111827)',
  },
  toggleButton: {
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    background: 'none',
    border: '1px solid var(--border-color, #d1d5db)',
    borderRadius: '4px',
    cursor: 'pointer',
    padding: '2px 4px',
    color: 'var(--text-secondary, #6b7280)',
    fontSize: '14px',
    lineHeight: 1,
    transition: 'color 0.15s, border-color 0.15s',
    flexShrink: 0,
  },
  label: {
    fontSize: '0.75rem',
    color: 'var(--text-tertiary, #9ca3af)',
    marginRight: '4px',
  },
};

// SVG eye icons (no external dependency needed)
const EyeIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
    <circle cx="12" cy="12" r="3" />
  </svg>
);

const EyeOffIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94" />
    <path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19" />
    <line x1="1" y1="1" x2="23" y2="23" />
    <path d="M14.12 14.12a3 3 0 1 1-4.24-4.24" />
  </svg>
);

/**
 * @param {Object} props
 * @param {*} props.value - The raw PII value
 * @param {string} props.type - One of: ssn, dob, income, phone, email, account
 * @param {boolean} [props.revealed] - Controlled reveal state (if provided, component is controlled)
 * @param {Function} [props.onToggle] - Callback when reveal/hide is toggled; receives new boolean state
 * @param {string} [props.label] - Optional label displayed before the value
 * @param {number} [props.autoHideMs=15000] - Auto-hide revealed value after this many ms (0 to disable)
 * @param {string} [props.className] - Additional CSS class on the container
 * @param {Object} [props.style] - Additional inline styles on the container
 * @param {Object} [props.auditContext] - Extra context passed to DLP audit log (e.g. { loan_id, borrower_id })
 */
function MaskedField({
  value,
  type,
  revealed: controlledRevealed,
  onToggle,
  label,
  autoHideMs = 15000,
  className = '',
  style = {},
  auditContext = {},
}) {
  // Support both controlled and uncontrolled usage
  const isControlled = controlledRevealed !== undefined;
  const [internalRevealed, setInternalRevealed] = useState(false);
  const revealed = isControlled ? controlledRevealed : internalRevealed;

  const autoHideTimer = useRef(null);

  // Clear auto-hide timer on unmount
  useEffect(() => {
    return () => {
      if (autoHideTimer.current) {
        clearTimeout(autoHideTimer.current);
      }
    };
  }, []);

  // Auto-hide when revealed (uncontrolled mode only)
  useEffect(() => {
    if (!isControlled && revealed && autoHideMs > 0) {
      autoHideTimer.current = setTimeout(() => {
        setInternalRevealed(false);
      }, autoHideMs);

      return () => {
        if (autoHideTimer.current) {
          clearTimeout(autoHideTimer.current);
        }
      };
    }
  }, [revealed, isControlled, autoHideMs]);

  const handleToggle = useCallback(() => {
    const nextState = !revealed;

    if (!isControlled) {
      setInternalRevealed(nextState);
    }

    if (onToggle) {
      onToggle(nextState);
    }

    // Audit log when revealing
    if (nextState) {
      const dlpLevel = classifyField(type);
      logFieldAccess(type || 'unknown', dlpLevel, {
        ...auditContext,
        action: 'pii_reveal',
        component: 'MaskedField',
      });
    }
  }, [revealed, isControlled, onToggle, type, auditContext]);

  // Compute display value
  const maskedValue = formatMasked(value, type);
  const displayValue = revealed ? _formatRevealed(value, type) : maskedValue;

  // Don't show toggle if there's no real value to mask/reveal
  const hasValue = value != null && value !== '';

  return (
    <span
      className={`masked-field ${className}`}
      style={{ ...styles.container, ...style }}
    >
      {label && <span style={styles.label}>{label}</span>}
      <span
        style={{
          ...styles.value,
          ...(revealed ? styles.revealedValue : styles.maskedValue),
        }}
        data-pii-type={type}
        data-pii-masked={!revealed}
      >
        {displayValue}
      </span>
      {hasValue && (
        <button
          type="button"
          style={styles.toggleButton}
          onClick={handleToggle}
          aria-label={revealed ? `Hide ${type || 'value'}` : `Reveal ${type || 'value'}`}
          title={revealed ? 'Hide' : 'Reveal'}
          tabIndex={0}
        >
          {revealed ? <EyeOffIcon /> : <EyeIcon />}
        </button>
      )}
    </span>
  );
}

/**
 * Format the raw value for revealed display.
 * Adds dashes to SSNs, formats phone numbers, etc.
 */
function _formatRevealed(value, type) {
  if (value == null || value === '') return '\u2014';

  switch (type) {
    case 'ssn': {
      const digits = String(value).replace(/\D/g, '');
      if (digits.length === 9) {
        return `${digits.slice(0, 3)}-${digits.slice(3, 5)}-${digits.slice(5)}`;
      }
      return String(value);
    }
    case 'phone': {
      const digits = String(value).replace(/\D/g, '');
      if (digits.length === 10) {
        return `(${digits.slice(0, 3)}) ${digits.slice(3, 6)}-${digits.slice(6)}`;
      }
      if (digits.length === 11 && digits[0] === '1') {
        return `+1 (${digits.slice(1, 4)}) ${digits.slice(4, 7)}-${digits.slice(7)}`;
      }
      return String(value);
    }
    case 'income': {
      const num = typeof value === 'number'
        ? value
        : parseFloat(String(value).replace(/[$,\s]/g, ''));
      if (!isNaN(num)) {
        return '$' + num.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 2 });
      }
      return String(value);
    }
    case 'account': {
      return String(value);
    }
    default:
      return String(value);
  }
}

export default MaskedField;
