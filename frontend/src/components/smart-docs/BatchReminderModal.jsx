/**
 * BatchReminderModal - Confirm and send batch reminders across multiple loans
 *
 * Features:
 * - Shows count of loans that will receive reminders
 * - Channel selection (email, SMS)
 * - Send button with loading state
 * - Success/error toast feedback
 */

import React, { useState, useEffect, useRef, useCallback } from 'react';
import { sendBatch } from '../../services/docDeliveryApi';
import { toast } from '../../utils/toast';
import './BatchReminderModal.css';

function BatchReminderModal({ isOpen, onClose, loanIds, loanCount }) {
  const [channels, setChannels] = useState({ email: true, sms: false });
  const [sending, setSending] = useState(false);
  const overlayRef = useRef(null);
  const modalRef = useRef(null);

  const count = loanCount || (loanIds ? loanIds.length : 0);

  // Reset when modal opens
  useEffect(() => {
    if (isOpen) {
      setChannels({ email: true, sms: false });
      setSending(false);
    }
  }, [isOpen]);

  // Focus trap and escape key
  useEffect(() => {
    if (!isOpen) return;

    const handleKeyDown = (e) => {
      if (e.key === 'Escape') {
        onClose();
        return;
      }

      if (e.key === 'Tab' && modalRef.current) {
        const focusable = modalRef.current.querySelectorAll(
          'button:not([disabled]), input:not([disabled]), [tabindex]:not([tabindex="-1"])'
        );
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

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  const toggleChannel = useCallback((channel) => {
    setChannels((prev) => ({ ...prev, [channel]: !prev[channel] }));
  }, []);

  const hasSelectedChannel = channels.email || channels.sms;

  const handleSend = async (e) => {
    e.preventDefault();
    if (!hasSelectedChannel || sending || !loanIds || loanIds.length === 0) return;

    const selectedChannels = [];
    if (channels.email) selectedChannels.push('email');
    if (channels.sms) selectedChannels.push('sms');

    setSending(true);
    try {
      const result = await sendBatch(loanIds, selectedChannels, 'needs_list');

      const successCount = result.success_count || loanIds.length;
      const failCount = result.failure_count || 0;

      if (failCount === 0) {
        toast.success(
          `Batch reminders sent to ${successCount} borrower${successCount !== 1 ? 's' : ''}`
        );
      } else {
        toast.warning(
          `Sent to ${successCount} borrowers, ${failCount} failed`
        );
      }

      onClose();
    } catch (err) {
      toast.error(err.message || 'Failed to send batch reminders');
    } finally {
      setSending(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div
      className="batch-reminder-overlay"
      ref={overlayRef}
      onClick={(e) => {
        if (e.target === overlayRef.current) onClose();
      }}
      role="dialog"
      aria-modal="true"
      aria-label="Send Batch Reminders"
    >
      <div className="batch-reminder-modal" ref={modalRef}>
        <div className="br-header">
          <h2>Send Batch Reminders</h2>
          <button
            className="br-close-btn"
            onClick={onClose}
            aria-label="Close modal"
          >
            &times;
          </button>
        </div>

        <form onSubmit={handleSend} className="br-form">
          <div className="br-body">
            {/* Summary */}
            <div className="br-summary">
              <div className="br-summary-icon">&#9993;</div>
              <div className="br-summary-text">
                <p className="br-summary-heading">
                  Send reminders to <strong>{count}</strong> borrower{count !== 1 ? 's' : ''}
                </p>
                <p className="br-summary-sub">
                  Each borrower will receive a reminder about their outstanding documents.
                </p>
              </div>
            </div>

            {/* Channel Selection */}
            <div className="br-section">
              <label className="br-section-label">Delivery Channels</label>
              <div className="br-channel-options">
                <label className="br-channel-option">
                  <input
                    type="checkbox"
                    checked={channels.email}
                    onChange={() => toggleChannel('email')}
                  />
                  <span className="br-channel-icon">&#9993;</span>
                  <span>Email</span>
                </label>
                <label className="br-channel-option">
                  <input
                    type="checkbox"
                    checked={channels.sms}
                    onChange={() => toggleChannel('sms')}
                  />
                  <span className="br-channel-icon">&#128241;</span>
                  <span>SMS</span>
                </label>
              </div>
              {!hasSelectedChannel && (
                <p className="br-channel-error">
                  Select at least one delivery channel
                </p>
              )}
            </div>
          </div>

          {/* Footer */}
          <div className="br-footer">
            <button
              type="button"
              className="br-btn br-btn-cancel"
              onClick={onClose}
              disabled={sending}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="br-btn br-btn-send"
              disabled={sending || !hasSelectedChannel || count === 0}
            >
              {sending
                ? 'Sending...'
                : `Send to ${count} Borrower${count !== 1 ? 's' : ''}`}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

export default BatchReminderModal;
