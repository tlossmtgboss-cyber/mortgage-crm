/**
 * QuickAddLeadModal - Mobile bottom sheet for speed-to-lead capture
 *
 * Designed for sub-10-second lead entry on mobile devices.
 * Slides up from bottom, drag handle to dismiss, minimal required fields.
 *
 * Props:
 *   isOpen       - Boolean controlling visibility
 *   onClose      - Called when the modal should close
 *   onLeadAdded  - Called with the created lead object on success
 */
import React, { useState, useRef, useCallback, useEffect } from 'react';
import { leadsAPI } from '../../services/api';
import { toast } from '../../utils/toast';
import './QuickAddLeadModal.css';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Format a raw numeric string as US currency (no cents). */
function formatCurrencyDisplay(value) {
  if (!value) return '';
  const digits = value.replace(/\D/g, '');
  if (!digits) return '';
  return Number(digits).toLocaleString('en-US');
}

/** Strip formatting and return raw number or null. */
function parseCurrencyValue(display) {
  if (!display) return null;
  const num = Number(display.replace(/\D/g, ''));
  return num > 0 ? num : null;
}

/** Trigger haptic feedback if the browser supports it. */
function haptic() {
  try {
    if (navigator.vibrate) {
      navigator.vibrate(15);
    }
  } catch (_) {
    // Haptics not available - silent fail
  }
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const LOAN_PURPOSES = [
  { value: '', label: 'Select...' },
  { value: 'Purchase', label: 'Purchase' },
  { value: 'Refinance', label: 'Refinance' },
  { value: 'Cash-Out', label: 'Cash-Out Refinance' },
];

const LEAD_SOURCES = [
  { value: '', label: 'Select...' },
  { value: 'Referral', label: 'Referral' },
  { value: 'Website', label: 'Website' },
  { value: 'Call', label: 'Phone Call' },
  { value: 'Walk-in', label: 'Walk-in' },
  { value: 'Other', label: 'Other' },
];

const INITIAL_FORM = {
  firstName: '',
  lastName: '',
  phone: '',
  email: '',
  loanPurpose: '',
  loanAmount: '',
  source: '',
  notes: '',
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function QuickAddLeadModal({ isOpen, onClose, onLeadAdded }) {
  // Form state
  const [form, setForm] = useState(INITIAL_FORM);
  const [errors, setErrors] = useState({});
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [successData, setSuccessData] = useState(null);
  const [expanded, setExpanded] = useState(false);

  // Backdrop animation
  const [backdropVisible, setBackdropVisible] = useState(false);
  const [sheetOpen, setSheetOpen] = useState(false);

  // Drag-to-dismiss state
  const sheetRef = useRef(null);
  const dragStartY = useRef(null);
  const currentDragY = useRef(0);
  const isDragging = useRef(false);

  // Refs for focus management
  const firstInputRef = useRef(null);
  const bodyRef = useRef(null);

  // -----------------------------------------------------------------------
  // Open / close animation sequencing
  // -----------------------------------------------------------------------

  useEffect(() => {
    if (isOpen) {
      // Open: show backdrop first, then slide sheet up
      setBackdropVisible(true);
      // RAF ensures the backdrop transition has started before sheet slides
      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          setSheetOpen(true);
        });
      });
      // Auto-focus first input after animation
      const timer = setTimeout(() => {
        if (firstInputRef.current) {
          firstInputRef.current.focus();
        }
      }, 400);
      return () => clearTimeout(timer);
    } else {
      // Close: slide sheet down first, then hide backdrop
      setSheetOpen(false);
      const timer = setTimeout(() => {
        setBackdropVisible(false);
        // Reset state after close animation completes
        setForm(INITIAL_FORM);
        setErrors({});
        setExpanded(false);
        setSuccessData(null);
      }, 350);
      return () => clearTimeout(timer);
    }
  }, [isOpen]);

  // Lock body scroll when open
  useEffect(() => {
    if (isOpen) {
      const originalOverflow = document.body.style.overflow;
      document.body.style.overflow = 'hidden';
      return () => {
        document.body.style.overflow = originalOverflow;
      };
    }
  }, [isOpen]);

  // -----------------------------------------------------------------------
  // Drag-to-dismiss
  // -----------------------------------------------------------------------

  const handleDragStart = useCallback((e) => {
    // Only allow drag from the handle area (identified by the target check)
    const touch = e.touches ? e.touches[0] : e;
    dragStartY.current = touch.clientY;
    currentDragY.current = 0;
    isDragging.current = true;
    if (sheetRef.current) {
      sheetRef.current.classList.add('quick-add-lead-sheet--dragging');
    }
  }, []);

  const handleDragMove = useCallback((e) => {
    if (!isDragging.current || dragStartY.current === null) return;
    const touch = e.touches ? e.touches[0] : e;
    const dy = touch.clientY - dragStartY.current;
    // Only allow dragging down
    currentDragY.current = Math.max(0, dy);
    if (sheetRef.current) {
      sheetRef.current.style.transform = `translateY(${currentDragY.current}px)`;
    }
  }, []);

  const handleDragEnd = useCallback(() => {
    if (!isDragging.current) return;
    isDragging.current = false;
    if (sheetRef.current) {
      sheetRef.current.classList.remove('quick-add-lead-sheet--dragging');
      sheetRef.current.style.transform = '';
    }
    // Dismiss if dragged more than 120px down
    if (currentDragY.current > 120) {
      onClose();
    }
    dragStartY.current = null;
    currentDragY.current = 0;
  }, [onClose]);

  // -----------------------------------------------------------------------
  // Form handling
  // -----------------------------------------------------------------------

  const handleChange = useCallback((field, value) => {
    setForm((prev) => ({ ...prev, [field]: value }));
    // Clear error for this field on change
    setErrors((prev) => {
      if (!prev[field]) return prev;
      const next = { ...prev };
      delete next[field];
      return next;
    });
  }, []);

  const handleLoanAmountChange = useCallback((e) => {
    const formatted = formatCurrencyDisplay(e.target.value);
    handleChange('loanAmount', formatted);
  }, [handleChange]);

  const validate = useCallback(() => {
    const errs = {};
    const first = form.firstName.trim();
    const last = form.lastName.trim();
    const phone = form.phone.trim();
    const email = form.email.trim();

    if (!first) errs.firstName = 'First name is required';
    if (!last) errs.lastName = 'Last name is required';

    // Need at least phone or email
    if (!phone && !email) {
      errs.phone = 'Phone or email required';
      errs.email = 'Phone or email required';
    }

    // Basic email format check if provided
    if (email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      errs.email = 'Invalid email format';
    }

    // Basic phone check if provided (at least 7 digits)
    if (phone) {
      const phoneDigits = phone.replace(/\D/g, '');
      if (phoneDigits.length < 7) {
        errs.phone = 'Invalid phone number';
      }
    }

    return errs;
  }, [form]);

  // -----------------------------------------------------------------------
  // Submit
  // -----------------------------------------------------------------------

  const handleSubmit = useCallback(async (e) => {
    e.preventDefault();

    const errs = validate();
    if (Object.keys(errs).length > 0) {
      setErrors(errs);
      // Focus the first field with an error
      const firstErrorField = Object.keys(errs)[0];
      const el = document.querySelector(`[data-field="${firstErrorField}"]`);
      if (el) el.focus();
      return;
    }

    setIsSubmitting(true);
    setErrors({});

    try {
      const fullName = `${form.firstName.trim()} ${form.lastName.trim()}`;
      const payload = {
        name: fullName,
        first_name: form.firstName.trim(),
        last_name: form.lastName.trim(),
      };

      if (form.phone.trim()) payload.phone = form.phone.trim();
      if (form.email.trim()) payload.email = form.email.trim();
      if (form.loanPurpose) payload.loan_type = form.loanPurpose;
      if (form.source) payload.source = form.source;
      if (form.notes.trim()) payload.notes = form.notes.trim();

      const amount = parseCurrencyValue(form.loanAmount);
      if (amount) payload.loan_amount = amount;

      const result = await leadsAPI.create(payload);

      // Haptic success feedback
      haptic();

      setSuccessData({
        id: result.id || result.lead_id,
        name: fullName,
      });
    } catch (err) {
      const message = err?.response?.data?.detail || err.message || 'Failed to create lead';
      toast.error(message);
    } finally {
      setIsSubmitting(false);
    }
  }, [form, validate]);

  // -----------------------------------------------------------------------
  // Success actions
  // -----------------------------------------------------------------------

  const handleAddAnother = useCallback(() => {
    setSuccessData(null);
    setForm(INITIAL_FORM);
    setExpanded(false);
    setTimeout(() => {
      if (firstInputRef.current) firstInputRef.current.focus();
    }, 100);
  }, []);

  const handleViewLead = useCallback(() => {
    if (successData && onLeadAdded) {
      onLeadAdded(successData);
    }
    onClose();
  }, [successData, onLeadAdded, onClose]);

  // -----------------------------------------------------------------------
  // Keyboard handling: scroll to keep active field visible
  // -----------------------------------------------------------------------

  useEffect(() => {
    if (!isOpen) return;

    function handleFocusIn(e) {
      const input = e.target;
      if (!input || !bodyRef.current) return;
      if (!input.closest('.quick-add-lead-body')) return;

      // Give the keyboard a moment to open, then scroll field into view
      setTimeout(() => {
        input.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }, 300);
    }

    document.addEventListener('focusin', handleFocusIn);
    return () => document.removeEventListener('focusin', handleFocusIn);
  }, [isOpen]);

  // -----------------------------------------------------------------------
  // Render guard
  // -----------------------------------------------------------------------

  if (!isOpen && !backdropVisible) return null;

  // -----------------------------------------------------------------------
  // Success state
  // -----------------------------------------------------------------------

  if (successData) {
    return (
      <>
        <div
          className={`quick-add-lead-backdrop ${backdropVisible ? 'quick-add-lead-backdrop--visible' : ''}`}
          onClick={onClose}
        />
        <div
          ref={sheetRef}
          className={`quick-add-lead-sheet ${sheetOpen ? 'quick-add-lead-sheet--open' : ''}`}
          role="dialog"
          aria-label="Lead added successfully"
        >
          <div className="quick-add-lead-handle">
            <div className="quick-add-lead-handle-bar" />
          </div>
          <div className="quick-add-lead-success">
            <div className="quick-add-lead-success-check">
              <svg
                width="32"
                height="32"
                viewBox="0 0 24 24"
                fill="none"
                stroke="#2D7A52"
                strokeWidth="2.5"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <polyline
                  points="20 6 9 17 4 12"
                  strokeDasharray="24"
                  strokeDashoffset="0"
                />
              </svg>
            </div>
            <h2 className="quick-add-lead-success-title">Lead added!</h2>
            <p className="quick-add-lead-success-sub">{successData.name}</p>
            <div className="quick-add-lead-success-actions">
              <button
                type="button"
                className="quick-add-lead-btn-secondary"
                onClick={handleAddAnother}
              >
                Add another
              </button>
              <button
                type="button"
                className="quick-add-lead-btn-primary"
                onClick={handleViewLead}
              >
                View lead
              </button>
            </div>
          </div>
        </div>
      </>
    );
  }

  // -----------------------------------------------------------------------
  // Form state
  // -----------------------------------------------------------------------

  return (
    <>
      {/* Backdrop */}
      <div
        className={`quick-add-lead-backdrop ${backdropVisible ? 'quick-add-lead-backdrop--visible' : ''}`}
        onClick={onClose}
      />

      {/* Bottom sheet */}
      <div
        ref={sheetRef}
        className={`quick-add-lead-sheet ${sheetOpen ? 'quick-add-lead-sheet--open' : ''}`}
        role="dialog"
        aria-modal="true"
        aria-label="Quick add lead"
      >
        {/* Drag handle */}
        <div
          className="quick-add-lead-handle"
          onTouchStart={handleDragStart}
          onTouchMove={handleDragMove}
          onTouchEnd={handleDragEnd}
          onMouseDown={handleDragStart}
          onMouseMove={handleDragMove}
          onMouseUp={handleDragEnd}
        >
          <div className="quick-add-lead-handle-bar" />
        </div>

        {/* Header */}
        <div className="quick-add-lead-header">
          <h2 className="quick-add-lead-title">New Lead</h2>
          <button
            type="button"
            className="quick-add-lead-close"
            onClick={onClose}
            aria-label="Close"
          >
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              <line x1="1" y1="1" x2="13" y2="13" />
              <line x1="13" y1="1" x2="1" y2="13" />
            </svg>
          </button>
        </div>

        {/* Scrollable form body */}
        <div className="quick-add-lead-body" ref={bodyRef}>
          <form onSubmit={handleSubmit} noValidate>
            {/* Name row */}
            <div className="quick-add-lead-row">
              <div className="quick-add-lead-field">
                <label className="quick-add-lead-label quick-add-lead-label--required" htmlFor="qal-first">
                  First name
                </label>
                <input
                  ref={firstInputRef}
                  id="qal-first"
                  data-field="firstName"
                  className={`quick-add-lead-input ${errors.firstName ? 'quick-add-lead-input--error' : ''}`}
                  type="text"
                  autoCapitalize="words"
                  autoComplete="given-name"
                  autoCorrect="off"
                  spellCheck="false"
                  enterKeyHint="next"
                  placeholder="First"
                  value={form.firstName}
                  onChange={(e) => handleChange('firstName', e.target.value)}
                />
                {errors.firstName && (
                  <div className="quick-add-lead-error">{errors.firstName}</div>
                )}
              </div>
              <div className="quick-add-lead-field">
                <label className="quick-add-lead-label quick-add-lead-label--required" htmlFor="qal-last">
                  Last name
                </label>
                <input
                  id="qal-last"
                  data-field="lastName"
                  className={`quick-add-lead-input ${errors.lastName ? 'quick-add-lead-input--error' : ''}`}
                  type="text"
                  autoCapitalize="words"
                  autoComplete="family-name"
                  autoCorrect="off"
                  spellCheck="false"
                  enterKeyHint="next"
                  placeholder="Last"
                  value={form.lastName}
                  onChange={(e) => handleChange('lastName', e.target.value)}
                />
                {errors.lastName && (
                  <div className="quick-add-lead-error">{errors.lastName}</div>
                )}
              </div>
            </div>

            {/* Phone */}
            <div className="quick-add-lead-field">
              <label className="quick-add-lead-label quick-add-lead-label--required" htmlFor="qal-phone">
                Phone
              </label>
              <input
                id="qal-phone"
                data-field="phone"
                className={`quick-add-lead-input ${errors.phone ? 'quick-add-lead-input--error' : ''}`}
                type="tel"
                autoComplete="tel"
                enterKeyHint="next"
                inputMode="tel"
                placeholder="(555) 123-4567"
                value={form.phone}
                onChange={(e) => handleChange('phone', e.target.value)}
              />
              {errors.phone && (
                <div className="quick-add-lead-error">{errors.phone}</div>
              )}
            </div>

            {/* Email */}
            <div className="quick-add-lead-field">
              <label className="quick-add-lead-label quick-add-lead-label--required" htmlFor="qal-email">
                Email
              </label>
              <input
                id="qal-email"
                data-field="email"
                className={`quick-add-lead-input ${errors.email ? 'quick-add-lead-input--error' : ''}`}
                type="email"
                autoComplete="email"
                autoCapitalize="none"
                enterKeyHint="done"
                inputMode="email"
                placeholder="name@email.com"
                value={form.email}
                onChange={(e) => handleChange('email', e.target.value)}
              />
              {errors.email && (
                <div className="quick-add-lead-error">{errors.email}</div>
              )}
            </div>

            {/* Expandable "Add more details" */}
            <button
              type="button"
              className="quick-add-lead-expand-btn"
              onClick={() => setExpanded((prev) => !prev)}
              aria-expanded={expanded}
            >
              <span>{expanded ? 'Fewer details' : 'Add more details'}</span>
              <span className={`quick-add-lead-expand-icon ${expanded ? 'quick-add-lead-expand-icon--open' : ''}`}>
                <svg width="12" height="8" viewBox="0 0 12 8" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M1 1.5L6 6.5L11 1.5" />
                </svg>
              </span>
            </button>

            <div className={`quick-add-lead-expandable ${expanded ? 'quick-add-lead-expandable--open' : ''}`}>
              {/* Loan purpose */}
              <div className="quick-add-lead-field">
                <label className="quick-add-lead-label" htmlFor="qal-purpose">
                  Loan purpose
                </label>
                <select
                  id="qal-purpose"
                  className="quick-add-lead-select"
                  value={form.loanPurpose}
                  onChange={(e) => handleChange('loanPurpose', e.target.value)}
                >
                  {LOAN_PURPOSES.map((opt) => (
                    <option key={opt.value} value={opt.value}>{opt.label}</option>
                  ))}
                </select>
              </div>

              {/* Loan amount */}
              <div className="quick-add-lead-field">
                <label className="quick-add-lead-label" htmlFor="qal-amount">
                  Estimated loan amount
                </label>
                <div className="quick-add-lead-currency-wrap">
                  <span className="quick-add-lead-currency-prefix">$</span>
                  <input
                    id="qal-amount"
                    className="quick-add-lead-input"
                    type="text"
                    inputMode="numeric"
                    enterKeyHint="next"
                    placeholder="350,000"
                    value={form.loanAmount}
                    onChange={handleLoanAmountChange}
                  />
                </div>
              </div>

              {/* Source */}
              <div className="quick-add-lead-field">
                <label className="quick-add-lead-label" htmlFor="qal-source">
                  Source
                </label>
                <select
                  id="qal-source"
                  className="quick-add-lead-select"
                  value={form.source}
                  onChange={(e) => handleChange('source', e.target.value)}
                >
                  {LEAD_SOURCES.map((opt) => (
                    <option key={opt.value} value={opt.value}>{opt.label}</option>
                  ))}
                </select>
              </div>

              {/* Notes */}
              <div className="quick-add-lead-field">
                <label className="quick-add-lead-label" htmlFor="qal-notes">
                  Notes
                </label>
                <textarea
                  id="qal-notes"
                  className="quick-add-lead-textarea"
                  rows={2}
                  enterKeyHint="done"
                  placeholder="Quick note about this lead..."
                  value={form.notes}
                  onChange={(e) => handleChange('notes', e.target.value)}
                />
              </div>
            </div>

            {/* Submit */}
            <button
              type="submit"
              className="quick-add-lead-submit"
              disabled={isSubmitting}
            >
              {isSubmitting ? (
                <>
                  <span className="quick-add-lead-spinner" />
                  <span>Adding...</span>
                </>
              ) : (
                'Add Lead'
              )}
            </button>
          </form>
        </div>
      </div>
    </>
  );
}
