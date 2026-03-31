/**
 * SendReminderModal - Send reminders for outstanding documents
 *
 * Features:
 * - Shows list of overdue/outstanding documents with checkboxes
 * - LO can select which docs to remind about (default: all open)
 * - Channel selection (email, SMS)
 * - Send Reminder button with loading state
 * - Success/error toast feedback
 */

import React, { useState, useEffect, useRef, useCallback } from 'react';
import { sendReminder } from '../../services/docDeliveryApi';
import { toast } from '../../utils/toast';
import './SendReminderModal.css';

// Map doc_type codes to display names
const DOC_TYPE_NAMES = {
  PAYSTUB: 'Pay Stubs',
  BANK_STATEMENT: 'Bank Statements',
  TAX_RETURN: 'Tax Returns',
  BUSINESS_TAX_RETURN: 'Business Tax Returns',
  W2: 'W-2 Forms',
  DRIVERS_LICENSE: "Driver's License",
  PURCHASE_CONTRACT: 'Purchase Contract',
  GIFT_LETTER: 'Gift Letter',
  PROFIT_LOSS: 'Profit & Loss Statement',
  BALANCE_SHEET: 'Balance Sheet',
  INVESTMENT_STATEMENT: 'Investment Statement',
  LOE: 'Letter of Explanation',
  LEASE_AGREEMENT: 'Lease Agreement',
  FHA_CERT: 'FHA Certificate',
  VA_COE: 'VA Certificate of Eligibility',
  DD214: 'DD-214',
  BANKRUPTCY_DISCHARGE: 'Bankruptcy Discharge',
  APPRAISAL: 'Appraisal',
  TITLE_REPORT: 'Title Report',
  HOMEOWNERS_INSURANCE: 'Homeowners Insurance',
  OTHER: 'Other',
};

function getDocDisplayName(doc) {
  if (doc.title) return doc.title;
  const type = (doc.doc_type || '').toUpperCase();
  return DOC_TYPE_NAMES[type] || type.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase()) || 'Document';
}

function SendReminderModal({
  isOpen,
  onClose,
  loanId,
  borrowerName,
  documents,
}) {
  // Filter to open/outstanding documents
  const openDocs = (documents || []).filter((doc) => {
    const status = (doc.status || '').toUpperCase();
    return status === 'OPEN' || status === 'REQUESTED' || status === 'OVERDUE' || status === 'PENDING';
  });

  const [selectedIds, setSelectedIds] = useState(new Set());
  const [channels, setChannels] = useState({ email: true, sms: true });
  const [sending, setSending] = useState(false);
  const overlayRef = useRef(null);
  const modalRef = useRef(null);

  // Reset form when modal opens — select all open docs
  useEffect(() => {
    if (isOpen) {
      setSelectedIds(new Set(openDocs.map((d) => d.id)));
      setChannels({ email: true, sms: true });
      setSending(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen]);

  // Focus trap and escape key
  useEffect(() => {
    if (!isOpen) return;

    const modal = modalRef.current;
    if (!modal) return;

    const focusable = modal.querySelectorAll(
      'button:not([disabled]), input:not([disabled]), [tabindex]:not([tabindex="-1"])'
    );

    // Focus the first focusable element when modal opens
    if (focusable.length > 0) focusable[0].focus();

    const handleKeyDown = (e) => {
      if (e.key === 'Escape') {
        onClose();
        return;
      }

      if (e.key === 'Tab') {
        if (focusable.length === 0) return;

        const first = focusable[0];
        const last = focusable[focusable.length - 1];

        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    };

    modal.addEventListener('keydown', handleKeyDown);
    return () => modal.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  const toggleDoc = useCallback((docId) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(docId)) {
        next.delete(docId);
      } else {
        next.add(docId);
      }
      return next;
    });
  }, []);

  const toggleAll = useCallback(() => {
    if (selectedIds.size === openDocs.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(openDocs.map((d) => d.id)));
    }
  }, [selectedIds.size, openDocs]);

  const toggleChannel = useCallback((channel) => {
    setChannels((prev) => ({ ...prev, [channel]: !prev[channel] }));
  }, []);

  const hasSelectedChannel = channels.email || channels.sms;
  const hasSelectedDocs = selectedIds.size > 0;

  const handleSend = async (e) => {
    e.preventDefault();
    if (!hasSelectedChannel || !hasSelectedDocs || sending) return;

    const selectedChannels = [];
    if (channels.email) selectedChannels.push('email');
    if (channels.sms) selectedChannels.push('sms');

    const documentRequestIds = Array.from(selectedIds);

    setSending(true);
    try {
      const result = await sendReminder(loanId, selectedChannels, documentRequestIds);

      const channelNames = selectedChannels.join(' and ');
      toast.success(
        `Reminder sent for ${selectedIds.size} document${selectedIds.size !== 1 ? 's' : ''} via ${channelNames}`
      );

      if (result.failures && result.failures.length > 0) {
        result.failures.forEach((f) => {
          toast.warning(`${f.channel} delivery failed: ${f.reason}`);
        });
      }

      onClose();
    } catch (err) {
      toast.error(err.message || 'Failed to send reminder');
    } finally {
      setSending(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div
      className="send-reminder-overlay"
      ref={overlayRef}
      onClick={(e) => {
        if (e.target === overlayRef.current) onClose();
      }}
      role="dialog"
      aria-modal="true"
      aria-labelledby="sr-modal-title"
    >
      <div className="send-reminder-modal" ref={modalRef}>
        <div className="sr-header">
          <h2 id="sr-modal-title">Send Reminder</h2>
          <button
            className="sr-close-btn"
            onClick={onClose}
            aria-label="Close dialog"
          >
            &times;
          </button>
        </div>

        <form onSubmit={handleSend} className="sr-form">
          <div className="sr-body">
            {/* Borrower Info */}
            <div className="sr-borrower-bar">
              <span className="sr-borrower-name">
                {borrowerName || 'Borrower'}
              </span>
              <span className="sr-selected-count">
                {selectedIds.size} of {openDocs.length} selected
              </span>
            </div>

            {/* Document List */}
            <div className="sr-section">
              <div className="sr-section-header">
                <label className="sr-section-label">Outstanding Documents</label>
                <button
                  type="button"
                  className="sr-select-all-btn"
                  onClick={toggleAll}
                  aria-label={
                    selectedIds.size === openDocs.length
                      ? 'Deselect all documents'
                      : 'Select all documents'
                  }
                >
                  {selectedIds.size === openDocs.length
                    ? 'Deselect All'
                    : 'Select All'}
                </button>
              </div>

              {openDocs.length === 0 ? (
                <div className="sr-empty-docs">
                  <p>No outstanding documents found.</p>
                </div>
              ) : (
                <div className="sr-doc-list">
                  {openDocs.map((doc) => {
                    const isOverdue =
                      doc.due_date && new Date(doc.due_date) < new Date();
                    return (
                      <label
                        key={doc.id}
                        className={`sr-doc-item ${
                          selectedIds.has(doc.id) ? 'selected' : ''
                        } ${isOverdue ? 'overdue' : ''}`}
                      >
                        <input
                          type="checkbox"
                          checked={selectedIds.has(doc.id)}
                          onChange={() => toggleDoc(doc.id)}
                          aria-label={`Include ${getDocDisplayName(doc)}${isOverdue ? ' (overdue)' : ''}`}
                        />
                        <div className="sr-doc-info">
                          <span className="sr-doc-name">
                            {getDocDisplayName(doc)}
                          </span>
                          {doc.due_date && (
                            <span
                              className={`sr-doc-due ${
                                isOverdue ? 'overdue' : ''
                              }`}
                            >
                              {isOverdue ? 'Overdue - ' : 'Due '}
                              {new Date(doc.due_date).toLocaleDateString(
                                'en-US',
                                {
                                  month: 'short',
                                  day: 'numeric',
                                }
                              )}
                            </span>
                          )}
                        </div>
                        {isOverdue && (
                          <span className="sr-overdue-badge">Overdue</span>
                        )}
                      </label>
                    );
                  })}
                </div>
              )}
            </div>

            {/* Channel Selection */}
            <div className="sr-section">
              <label className="sr-section-label">Delivery Channels</label>
              <div className="sr-channel-options">
                <label className="sr-channel-option">
                  <input
                    type="checkbox"
                    checked={channels.email}
                    onChange={() => toggleChannel('email')}
                    aria-label="Send via email"
                  />
                  <span className="sr-channel-icon">&#9993;</span>
                  <span>Email</span>
                </label>
                <label className="sr-channel-option">
                  <input
                    type="checkbox"
                    checked={channels.sms}
                    onChange={() => toggleChannel('sms')}
                    aria-label="Send via SMS"
                  />
                  <span className="sr-channel-icon">&#128241;</span>
                  <span>SMS</span>
                </label>
              </div>
              {!hasSelectedChannel && (
                <p className="sr-channel-error">
                  Select at least one delivery channel
                </p>
              )}
            </div>
          </div>

          {/* Footer */}
          <div className="sr-footer">
            <button
              type="button"
              className="sr-btn sr-btn-cancel"
              onClick={onClose}
              disabled={sending}
              aria-label="Close dialog"
            >
              Cancel
            </button>
            <button
              type="submit"
              className="sr-btn sr-btn-send"
              disabled={sending || !hasSelectedChannel || !hasSelectedDocs}
              aria-label={`Send reminder for ${selectedIds.size} document${selectedIds.size !== 1 ? 's' : ''} to borrower`}
            >
              {sending
                ? 'Sending...'
                : `Send Reminder${
                    selectedIds.size > 0 ? ` (${selectedIds.size})` : ''
                  }`}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

export default SendReminderModal;
