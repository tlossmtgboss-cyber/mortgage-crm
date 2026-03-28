/**
 * SendNeedsListModal - Send a needs list to a borrower
 *
 * Features:
 * - Shows borrower name and loan number
 * - Checkbox for channels: Email, SMS (both checked by default)
 * - Optional custom message textarea
 * - Shows count of outstanding documents
 * - Send button with loading state
 * - Success/error toast feedback
 */

import React, { useState, useEffect, useRef, useCallback } from 'react';
import { sendNeedsList } from '../../services/docDeliveryApi';
import { toast } from '../../utils/toast';
import './SendNeedsListModal.css';

function SendNeedsListModal({
  isOpen,
  onClose,
  loanId,
  borrowerName,
  loanNumber,
  documentCount,
}) {
  const [channels, setChannels] = useState({ email: true, sms: true });
  const [message, setMessage] = useState('');
  const [sending, setSending] = useState(false);
  const overlayRef = useRef(null);
  const modalRef = useRef(null);

  // Reset form when modal opens
  useEffect(() => {
    if (isOpen) {
      setChannels({ email: true, sms: true });
      setMessage('');
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

      // Focus trap
      if (e.key === 'Tab' && modalRef.current) {
        const focusable = modalRef.current.querySelectorAll(
          'button:not([disabled]), input:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
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
    if (!hasSelectedChannel || sending) return;

    const selectedChannels = [];
    if (channels.email) selectedChannels.push('email');
    if (channels.sms) selectedChannels.push('sms');

    setSending(true);
    try {
      const result = await sendNeedsList(loanId, selectedChannels, message || null);

      const channelNames = selectedChannels.join(' and ');
      toast.success(
        `Needs list sent to ${borrowerName || 'borrower'} via ${channelNames}`
      );

      // Handle partial failures if returned
      if (result.failures && result.failures.length > 0) {
        result.failures.forEach((f) => {
          toast.warning(`${f.channel} delivery failed: ${f.reason}`);
        });
      }

      onClose();
    } catch (err) {
      toast.error(err.message || 'Failed to send needs list');
    } finally {
      setSending(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div
      className="send-needs-list-overlay"
      ref={overlayRef}
      onClick={(e) => {
        if (e.target === overlayRef.current) onClose();
      }}
      role="dialog"
      aria-modal="true"
      aria-label="Send Needs List"
    >
      <div className="send-needs-list-modal" ref={modalRef}>
        <div className="snl-header">
          <h2>Send Needs List</h2>
          <button
            className="snl-close-btn"
            onClick={onClose}
            aria-label="Close modal"
          >
            &times;
          </button>
        </div>

        <form onSubmit={handleSend} className="snl-form">
          <div className="snl-body">
            {/* Borrower Info */}
            <div className="snl-borrower-info">
              <div className="snl-info-row">
                <span className="snl-label">Borrower</span>
                <span className="snl-value">{borrowerName || 'Unknown'}</span>
              </div>
              {loanNumber && (
                <div className="snl-info-row">
                  <span className="snl-label">Loan #</span>
                  <span className="snl-value">{loanNumber}</span>
                </div>
              )}
              <div className="snl-info-row">
                <span className="snl-label">Outstanding Docs</span>
                <span className="snl-value snl-doc-count">
                  {documentCount != null ? documentCount : '--'}
                </span>
              </div>
            </div>

            {/* Channel Selection */}
            <div className="snl-section">
              <label className="snl-section-label">Delivery Channels</label>
              <div className="snl-channel-options">
                <label className="snl-channel-option">
                  <input
                    type="checkbox"
                    checked={channels.email}
                    onChange={() => toggleChannel('email')}
                  />
                  <span className="snl-channel-icon">&#9993;</span>
                  <span>Email</span>
                </label>
                <label className="snl-channel-option">
                  <input
                    type="checkbox"
                    checked={channels.sms}
                    onChange={() => toggleChannel('sms')}
                  />
                  <span className="snl-channel-icon">&#128241;</span>
                  <span>SMS</span>
                </label>
              </div>
              {!hasSelectedChannel && (
                <p className="snl-channel-error">
                  Select at least one delivery channel
                </p>
              )}
            </div>

            {/* Custom Message */}
            <div className="snl-section">
              <label className="snl-section-label" htmlFor="snl-message">
                Custom Message (optional)
              </label>
              <textarea
                id="snl-message"
                className="snl-textarea"
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                placeholder="Add a personal note to include with the needs list..."
                rows={3}
                maxLength={500}
              />
              <span className="snl-char-count">{message.length}/500</span>
            </div>
          </div>

          {/* Footer */}
          <div className="snl-footer">
            <button
              type="button"
              className="snl-btn snl-btn-cancel"
              onClick={onClose}
              disabled={sending}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="snl-btn snl-btn-send"
              disabled={sending || !hasSelectedChannel}
            >
              {sending ? 'Sending...' : 'Send Needs List'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

export default SendNeedsListModal;
