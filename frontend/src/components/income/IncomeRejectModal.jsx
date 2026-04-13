/**
 * IncomeRejectModal - Compliance-critical income rejection dialog
 *
 * Replaces the window.prompt('Enter rejection reason:') pattern in
 * SmartDocsIncome.js with a proper modal that captures structured
 * rejection data for audit trail purposes.
 *
 * Props:
 *   isOpen (boolean)           - controls visibility
 *   onClose (function)         - called on cancel / escape / backdrop click
 *   onConfirm (function)       - called with { reason, category, notes, requestRevision }
 *   loanId (string)            - loan being acted on
 *   totalMonthlyIncome (number)- the income figure being rejected
 */

import React, { useState, useEffect, useRef, useCallback } from 'react';
import './IncomeRejectModal.css';

const REJECTION_CATEGORIES = [
  'Insufficient documentation',
  'Calculation error',
  'Income not qualifying',
  'Declining income concern',
  'Employment verification failed',
  'Document authenticity concern',
  'Guideline non-compliance',
  'Other',
];

const MIN_REASON_LENGTH = 20;

function IncomeRejectModal({ isOpen, onClose, onConfirm, loanId, totalMonthlyIncome }) {
  const [category, setCategory] = useState('');
  const [reason, setReason] = useState('');
  const [notes, setNotes] = useState('');
  const [requestRevision, setRequestRevision] = useState(false);

  const modalRef = useRef(null);
  const firstFocusRef = useRef(null);
  const lastFocusRef = useRef(null);

  // Reset form when modal opens
  useEffect(() => {
    if (isOpen) {
      setCategory('');
      setReason('');
      setNotes('');
      setRequestRevision(false);
    }
  }, [isOpen]);

  // Focus the first interactive element when modal opens
  useEffect(() => {
    if (isOpen && firstFocusRef.current) {
      // Small delay to allow the modal to render
      const timer = setTimeout(() => firstFocusRef.current?.focus(), 50);
      return () => clearTimeout(timer);
    }
  }, [isOpen]);

  // Escape key handler
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

  // Focus trap
  const handleKeyDown = useCallback((e) => {
    if (e.key !== 'Tab') return;
    const focusable = modalRef.current?.querySelectorAll(
      'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
    );
    if (!focusable || focusable.length === 0) return;

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

  const isValid = category !== '' && reason.trim().length >= MIN_REASON_LENGTH;

  function handleConfirm() {
    if (!isValid) return;
    onConfirm({
      reason: reason.trim(),
      category,
      notes: notes.trim(),
      requestRevision,
    });
  }

  function handleBackdropClick(e) {
    if (e.target === e.currentTarget) {
      onClose();
    }
  }

  function formatCurrency(amount) {
    if (amount == null || isNaN(amount)) return '$0.00';
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 2,
    }).format(amount);
  }

  if (!isOpen) return null;

  const actionLabel = requestRevision ? 'Request Revision' : 'Reject Income';
  const reasonLength = reason.trim().length;
  const charsRemaining = MIN_REASON_LENGTH - reasonLength;

  return (
    <div
      className="income-reject-overlay"
      onClick={handleBackdropClick}
      role="presentation"
    >
      <div
        className="income-reject-modal"
        ref={modalRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="income-reject-title"
        onKeyDown={handleKeyDown}
      >
        {/* Header */}
        <div className="income-reject-header">
          <div className="income-reject-header-left">
            <span className="income-reject-warning-icon" aria-hidden="true">
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
                <line x1="12" y1="9" x2="12" y2="13" />
                <line x1="12" y1="17" x2="12.01" y2="17" />
              </svg>
            </span>
            <h2 id="income-reject-title">Reject Income Calculation</h2>
          </div>
          <button
            className="income-reject-close-btn"
            onClick={onClose}
            aria-label="Close"
            type="button"
          >
            &times;
          </button>
        </div>

        {/* Body */}
        <div className="income-reject-body">
          {/* Income summary */}
          <div className="income-reject-summary">
            <div className="income-reject-summary-row">
              <span className="income-reject-summary-label">Loan</span>
              <span className="income-reject-summary-value">{loanId || 'N/A'}</span>
            </div>
            <div className="income-reject-summary-row">
              <span className="income-reject-summary-label">Total Monthly Income</span>
              <span className="income-reject-summary-value income-reject-summary-amount">
                {formatCurrency(totalMonthlyIncome)}
              </span>
            </div>
          </div>

          {/* Category dropdown - REQUIRED */}
          <div className="income-reject-field">
            <label htmlFor="reject-category" className="income-reject-label">
              Rejection Category <span className="income-reject-required">*</span>
            </label>
            <select
              id="reject-category"
              ref={firstFocusRef}
              className="income-reject-select"
              value={category}
              onChange={(e) => setCategory(e.target.value)}
            >
              <option value="" disabled>
                Select a category...
              </option>
              {REJECTION_CATEGORIES.map((cat) => (
                <option key={cat} value={cat}>
                  {cat}
                </option>
              ))}
            </select>
          </div>

          {/* Reason textarea - REQUIRED */}
          <div className="income-reject-field">
            <label htmlFor="reject-reason" className="income-reject-label">
              Rejection Reason <span className="income-reject-required">*</span>
            </label>
            <textarea
              id="reject-reason"
              className="income-reject-textarea"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Describe the specific reason for rejection (minimum 20 characters)..."
              rows={4}
            />
            <div className="income-reject-char-count">
              {charsRemaining > 0 ? (
                <span className="income-reject-char-remaining">
                  {charsRemaining} more character{charsRemaining !== 1 ? 's' : ''} required
                </span>
              ) : (
                <span className="income-reject-char-ok">
                  {reasonLength} character{reasonLength !== 1 ? 's' : ''}
                </span>
              )}
            </div>
          </div>

          {/* Notes textarea - OPTIONAL */}
          <div className="income-reject-field">
            <label htmlFor="reject-notes" className="income-reject-label">
              Additional Notes <span className="income-reject-optional">(optional)</span>
            </label>
            <textarea
              id="reject-notes"
              className="income-reject-textarea income-reject-textarea-sm"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="Any additional context for the underwriter or processor..."
              rows={2}
            />
          </div>

          {/* Revision checkbox */}
          <label className="income-reject-checkbox-row" htmlFor="reject-revision">
            <input
              type="checkbox"
              id="reject-revision"
              checked={requestRevision}
              onChange={(e) => setRequestRevision(e.target.checked)}
            />
            <span className="income-reject-checkbox-label">
              Request revision instead of final rejection
            </span>
          </label>

          {/* Audit warning */}
          <div className="income-reject-audit-warning">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="8" x2="12" y2="12" />
              <line x1="12" y1="16" x2="12.01" y2="16" />
            </svg>
            <span>This action will be logged in the audit trail and cannot be undone.</span>
          </div>
        </div>

        {/* Footer */}
        <div className="income-reject-footer">
          <button
            type="button"
            className="income-reject-btn income-reject-btn-cancel"
            onClick={onClose}
          >
            Cancel
          </button>
          <button
            type="button"
            ref={lastFocusRef}
            className={`income-reject-btn income-reject-btn-confirm ${requestRevision ? 'income-reject-btn-revision' : ''}`}
            disabled={!isValid}
            onClick={handleConfirm}
          >
            {actionLabel}
          </button>
        </div>
      </div>
    </div>
  );
}

export default IncomeRejectModal;
