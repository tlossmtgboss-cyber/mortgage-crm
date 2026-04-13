import React, { useState, useEffect, useRef, useCallback } from 'react';
import './IncomeOverrideModal.css';

const OVERRIDE_REASONS = [
  'Manual calculation',
  'Document discrepancy',
  'Borrower correction',
  'Underwriter adjustment',
  'Guideline change',
  'Other',
];

const LARGE_CHANGE_THRESHOLD = 20; // percent

function formatCurrency(value) {
  if (value == null || isNaN(value)) return '$0.00';
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value);
}

export default function IncomeOverrideModal({
  isOpen,
  onClose,
  onConfirm,
  sourceName,
  currentMonthly,
  currentAnnual,
}) {
  const [monthlyAmount, setMonthlyAmount] = useState('');
  const [reason, setReason] = useState('');
  const [notes, setNotes] = useState('');

  const modalRef = useRef(null);
  const amountInputRef = useRef(null);
  const previousFocusRef = useRef(null);

  // ---- Derived values ----
  const parsedMonthly = parseFloat(monthlyAmount);
  const hasValidAmount = monthlyAmount !== '' && !isNaN(parsedMonthly) && parsedMonthly >= 0;
  const annualAmount = hasValidAmount ? parsedMonthly * 12 : null;

  const notesRequired = reason === 'Other';
  const hasValidReason = reason !== '';
  const hasValidNotes = !notesRequired || (notes.trim().length > 0);
  const canConfirm = hasValidAmount && hasValidReason && hasValidNotes;

  // Delta calculation
  let deltaPercent = null;
  let deltaIsLarge = false;
  if (hasValidAmount && currentMonthly != null && currentMonthly > 0) {
    deltaPercent = ((parsedMonthly - currentMonthly) / currentMonthly) * 100;
    deltaIsLarge = Math.abs(deltaPercent) > LARGE_CHANGE_THRESHOLD;
  }

  // ---- Reset form state when modal opens ----
  useEffect(() => {
    if (isOpen) {
      setMonthlyAmount('');
      setReason('');
      setNotes('');
      previousFocusRef.current = document.activeElement;
    }
  }, [isOpen]);

  // ---- Focus the amount input when modal opens ----
  useEffect(() => {
    if (isOpen && amountInputRef.current) {
      // Small delay to let the DOM render
      const timer = setTimeout(() => {
        amountInputRef.current?.focus();
      }, 50);
      return () => clearTimeout(timer);
    }
  }, [isOpen]);

  // ---- Restore focus on close ----
  useEffect(() => {
    if (!isOpen && previousFocusRef.current) {
      previousFocusRef.current.focus();
      previousFocusRef.current = null;
    }
  }, [isOpen]);

  // ---- Escape key ----
  useEffect(() => {
    if (!isOpen) return;
    function handleKeyDown(e) {
      if (e.key === 'Escape') {
        e.stopPropagation();
        onClose();
      }
    }
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  // ---- Focus trap ----
  const handleKeyDown = useCallback((e) => {
    if (e.key !== 'Tab') return;
    const modal = modalRef.current;
    if (!modal) return;

    const focusable = modal.querySelectorAll(
      'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
    );
    if (focusable.length === 0) return;

    const first = focusable[0];
    const last = focusable[focusable.length - 1];

    if (e.shiftKey) {
      if (document.activeElement === first) {
        e.preventDefault();
        last.focus();
      }
    } else {
      if (document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    }
  }, []);

  // ---- Handlers ----
  function handleOverlayClick(e) {
    if (e.target === e.currentTarget) {
      onClose();
    }
  }

  function handleAmountChange(e) {
    const val = e.target.value;
    // Allow empty string or valid numeric input (with decimals)
    if (val === '' || /^\d*\.?\d{0,2}$/.test(val)) {
      setMonthlyAmount(val);
    }
  }

  function handleConfirm() {
    if (!canConfirm) return;
    onConfirm({
      monthlyAmount: parsedMonthly,
      annualAmount: parsedMonthly * 12,
      reason,
      notes: notes.trim() || null,
    });
  }

  if (!isOpen) return null;

  return (
    <div
      className="income-override-overlay"
      onClick={handleOverlayClick}
      aria-hidden="false"
    >
      <div
        ref={modalRef}
        className="income-override-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="income-override-title"
        onKeyDown={handleKeyDown}
      >
        {/* Header */}
        <div className="income-override-header">
          <div className="income-override-header-left">
            <h2 id="income-override-title">Override Income Amount</h2>
            {sourceName && (
              <span className="income-override-source-name">{sourceName}</span>
            )}
          </div>
          <button
            className="income-override-close-btn"
            onClick={onClose}
            aria-label="Close"
            type="button"
          >
            &times;
          </button>
        </div>

        {/* Body */}
        <div className="income-override-body">
          {/* Current values */}
          <div className="income-override-current">
            <div className="income-override-current-label">Current Values</div>
            <div className="income-override-current-values">
              <div className="income-override-current-item">
                <span>Monthly</span>
                <span>{formatCurrency(currentMonthly)}</span>
              </div>
              <div className="income-override-current-item">
                <span>Annual</span>
                <span>{formatCurrency(currentAnnual)}</span>
              </div>
            </div>
          </div>

          {/* New monthly amount */}
          <div className="income-override-field">
            <label htmlFor="income-override-amount">
              New Monthly Amount<span className="required-star">*</span>
            </label>
            <div className="income-override-amount-input-wrapper">
              <span className="income-override-amount-prefix">$</span>
              <input
                ref={amountInputRef}
                id="income-override-amount"
                className="income-override-amount-input"
                type="number"
                min="0"
                step="0.01"
                placeholder="0.00"
                value={monthlyAmount}
                onChange={handleAmountChange}
                autoComplete="off"
              />
            </div>
            {hasValidAmount && (
              <span className="income-override-annual-calc">
                Annual: <strong>{formatCurrency(annualAmount)}</strong> ({formatCurrency(parsedMonthly)} x 12)
              </span>
            )}
          </div>

          {/* Delta display */}
          {hasValidAmount && currentMonthly != null && currentMonthly > 0 && (
            <div className="income-override-delta">
              This changes monthly income from{' '}
              <span className="income-override-delta-amount">
                {formatCurrency(currentMonthly)}
              </span>{' '}
              to{' '}
              <span className="income-override-delta-amount">
                {formatCurrency(parsedMonthly)}
              </span>{' '}
              (
              <span
                className={`income-override-delta-pct ${
                  deltaPercent >= 0
                    ? 'income-override-delta-pct--increase'
                    : 'income-override-delta-pct--decrease'
                }`}
              >
                {deltaPercent >= 0 ? '+' : ''}
                {deltaPercent.toFixed(1)}%
              </span>
              )
            </div>
          )}

          {/* Large change warning */}
          {deltaIsLarge && (
            <div className="income-override-warning" role="alert">
              <span className="income-override-warning-icon" aria-hidden="true">
                &#9888;
              </span>
              <span>
                This override changes income by more than 20%. Large adjustments
                may require additional documentation for compliance review.
              </span>
            </div>
          )}

          {/* Reason */}
          <div className="income-override-field">
            <label htmlFor="income-override-reason">
              Reason for Override<span className="required-star">*</span>
            </label>
            <select
              id="income-override-reason"
              className="income-override-select"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
            >
              <option value="">Select a reason...</option>
              {OVERRIDE_REASONS.map((r) => (
                <option key={r} value={r}>
                  {r}
                </option>
              ))}
            </select>
          </div>

          {/* Notes */}
          <div className="income-override-field">
            <label htmlFor="income-override-notes">
              Notes
              {notesRequired && <span className="required-star">*</span>}
            </label>
            <textarea
              id="income-override-notes"
              className="income-override-notes"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder={
                notesRequired
                  ? 'Required — explain the reason for this override'
                  : 'Optional additional context for the audit trail'
              }
              rows={3}
            />
            {!notesRequired && (
              <span className="income-override-notes-hint">
                Notes are recorded in the compliance audit trail.
              </span>
            )}
          </div>
        </div>

        {/* Audit notice */}
        <div className="income-override-audit-notice">
          <svg
            width="12"
            height="12"
            viewBox="0 0 16 16"
            fill="currentColor"
            aria-hidden="true"
          >
            <path d="M8 1a7 7 0 100 14A7 7 0 008 1zm0 2a1 1 0 110 2 1 1 0 010-2zm1 4v4a1 1 0 11-2 0V7a1 1 0 112 0z" />
          </svg>
          <span>This action will be recorded in the audit trail with timestamp and user.</span>
        </div>

        {/* Footer */}
        <div className="income-override-footer">
          <button
            className="income-override-btn income-override-btn--cancel"
            onClick={onClose}
            type="button"
          >
            Cancel
          </button>
          <button
            className="income-override-btn income-override-btn--confirm"
            onClick={handleConfirm}
            disabled={!canConfirm}
            type="button"
          >
            Confirm Override
          </button>
        </div>
      </div>
    </div>
  );
}
