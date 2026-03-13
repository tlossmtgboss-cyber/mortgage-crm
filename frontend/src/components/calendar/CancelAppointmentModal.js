import React, { useState, useEffect, useCallback, useRef } from 'react';
import useFocusTrap from '../../hooks/useFocusTrap';

const API_BASE = process.env.REACT_APP_API_URL || '';

async function apiFetch(path, options = {}) {
  const token = localStorage.getItem('token');
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(options.headers || {}),
    },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    const detail = err.detail;
    // Handle structured error from policy enforcement
    if (typeof detail === 'object' && detail.message) {
      throw new Error(detail.message);
    }
    throw new Error(detail || `API error ${res.status}`);
  }
  return res.json();
}

/**
 * CancelAppointmentModal -- Policy-aware cancellation flow.
 *
 * On open, performs a pre-flight policy check to display:
 *   - Late cancellation warning (if within notice period)
 *   - Recent cancellation count and limit
 *   - Required reason dropdown
 *
 * Server makes the final enforcement decision; frontend shows advisory info.
 *
 * Props:
 *   appointment  - The appointment object (must have id, title, attendee_name, scheduled_start)
 *   onClose      - Called when modal is dismissed
 *   onCancelled  - Called after successful cancellation with the result
 */
export default function CancelAppointmentModal({ appointment, onClose, onCancelled }) {
  const modalRef = useRef(null);
  const [policyCheck, setPolicyCheck] = useState(null);
  const [loading, setLoading] = useState(true);
  const [cancelling, setCancelling] = useState(false);
  const [error, setError] = useState('');
  const [reason, setReason] = useState('');
  const [notes, setNotes] = useState('');

  // Focus trap
  useFocusTrap(modalRef, {
    active: true,
    onEscape: onClose,
    autoFocus: true,
    restoreFocus: true,
  });

  // Pre-flight policy check
  useEffect(() => {
    if (!appointment?.id) return;

    let cancelled = false;
    (async () => {
      setLoading(true);
      setError('');
      try {
        const emailParam = appointment.attendee_email
          ? `?cancelled_by_email=${encodeURIComponent(appointment.attendee_email)}`
          : '';
        const check = await apiFetch(
          `/api/v1/scheduler/cancellation-policy/check/${appointment.id}${emailParam}`
        );
        if (!cancelled) {
          setPolicyCheck(check);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err.message);
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    })();

    return () => { cancelled = true; };
  }, [appointment?.id, appointment?.attendee_email]);

  const handleCancel = useCallback(async () => {
    if (!appointment?.id) return;
    setCancelling(true);
    setError('');
    try {
      const result = await apiFetch(`/api/v1/scheduler/cancel/${appointment.id}`, {
        method: 'POST',
        body: JSON.stringify({
          reason: reason || null,
          notes: notes || null,
          cancelled_by_email: appointment.attendee_email || null,
        }),
      });
      if (onCancelled) onCancelled(result);
    } catch (err) {
      setError(err.message);
    } finally {
      setCancelling(false);
    }
  }, [appointment, reason, notes, onCancelled]);

  const handleOverlayClick = (e) => {
    if (e.target === e.currentTarget) onClose();
  };

  const formatStart = (isoStr) => {
    if (!isoStr) return '';
    try {
      return new Date(isoStr).toLocaleString(undefined, {
        weekday: 'short', month: 'short', day: 'numeric',
        hour: 'numeric', minute: '2-digit',
      });
    } catch {
      return isoStr;
    }
  };

  const reasons = policyCheck?.cancellation_reasons || [];
  const requireReason = policyCheck?.require_reason ?? false;
  const isLate = policyCheck?.is_late ?? false;
  const cancelCount = policyCheck?.cancel_count ?? 0;
  const maxCancellations = policyCheck?.max_cancellations ?? 0;
  const allowed = policyCheck?.allowed ?? true;
  const lateMessage = policyCheck?.late_cancel_message || '';

  const canSubmit = allowed && (!requireReason || reason) && !cancelling;

  return (
    <div
      style={{
        position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
        background: 'rgba(0,0,0,0.5)', display: 'flex',
        alignItems: 'center', justifyContent: 'center', zIndex: 1000,
      }}
      onClick={handleOverlayClick}
      role="presentation"
    >
      <div
        ref={modalRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="cancel-modal-title"
        style={{
          background: '#fff', borderRadius: 16, padding: 24,
          width: '100%', maxWidth: 480, maxHeight: '90vh',
          overflowY: 'auto', boxShadow: '0 20px 60px rgba(0,0,0,0.3)',
        }}
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 16 }}>
          <div>
            <h3 id="cancel-modal-title" style={{ margin: 0, fontSize: 18, fontWeight: 600, color: '#111827' }}>
              Cancel Appointment
            </h3>
            {appointment && (
              <p style={{ margin: '4px 0 0', fontSize: 13, color: '#6b7280' }}>
                {appointment.title || 'Appointment'}
                {appointment.attendee_name ? ` with ${appointment.attendee_name}` : ''}
              </p>
            )}
            {appointment?.scheduled_start && (
              <p style={{ margin: '2px 0 0', fontSize: 13, color: '#6b7280' }}>
                {formatStart(appointment.scheduled_start)}
              </p>
            )}
          </div>
          <button
            onClick={onClose}
            style={{
              background: 'none', border: 'none', cursor: 'pointer',
              fontSize: 20, color: '#9ca3af', padding: '0 4px', lineHeight: 1,
            }}
            aria-label="Close"
          >
            x
          </button>
        </div>

        {/* Loading */}
        {loading && (
          <div style={{ padding: 20, textAlign: 'center', color: '#6b7280' }}>
            Checking cancellation policy...
          </div>
        )}

        {/* Error */}
        {error && (
          <div style={{
            padding: '10px 14px', background: '#fef2f2', color: '#dc2626',
            borderRadius: 8, marginBottom: 12, fontSize: 13,
          }}>
            {error}
          </div>
        )}

        {!loading && policyCheck && (
          <>
            {/* Late warning */}
            {isLate && (
              <div style={{
                padding: '12px 14px', background: '#fffbeb', border: '1px solid #fbbf24',
                borderRadius: 10, marginBottom: 14,
              }}>
                <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8 }}>
                  <span style={{ fontSize: 18 }} aria-hidden="true">!</span>
                  <div>
                    <strong style={{ fontSize: 14, color: '#92400e' }}>Late Cancellation</strong>
                    <p style={{ margin: '4px 0 0', fontSize: 13, color: '#78350f' }}>
                      {lateMessage || 'This appointment is within the minimum notice period.'}
                    </p>
                  </div>
                </div>
              </div>
            )}

            {/* Cancellation count warning */}
            {maxCancellations > 0 && cancelCount > 0 && (
              <div style={{
                padding: '10px 14px',
                background: cancelCount >= maxCancellations - 1 ? '#fef2f2' : '#f0f9ff',
                border: `1px solid ${cancelCount >= maxCancellations - 1 ? '#fca5a5' : '#bae6fd'}`,
                borderRadius: 10, marginBottom: 14, fontSize: 13,
                color: cancelCount >= maxCancellations - 1 ? '#991b1b' : '#0c4a6e',
              }}>
                {cancelCount} of {maxCancellations} allowed cancellations used in the last 30 days.
                {cancelCount >= maxCancellations - 1 && cancelCount < maxCancellations && (
                  <strong> This will be your last allowed cancellation.</strong>
                )}
              </div>
            )}

            {/* Not allowed message */}
            {!allowed && (
              <div style={{
                padding: '12px 14px', background: '#fef2f2', border: '1px solid #fca5a5',
                borderRadius: 10, marginBottom: 14,
              }}>
                <strong style={{ fontSize: 14, color: '#dc2626' }}>Cancellation Not Allowed</strong>
                <p style={{ margin: '4px 0 0', fontSize: 13, color: '#991b1b' }}>
                  {policyCheck.reason || 'This appointment cannot be cancelled at this time.'}
                </p>
              </div>
            )}

            {/* Reason dropdown */}
            {allowed && reasons.length > 0 && (
              <div style={{ marginBottom: 14 }}>
                <label
                  htmlFor="cancel-reason"
                  style={{ display: 'block', fontSize: 14, fontWeight: 500, marginBottom: 4, color: '#374151' }}
                >
                  Reason for cancellation{requireReason ? ' *' : ''}
                </label>
                <select
                  id="cancel-reason"
                  value={reason}
                  onChange={e => setReason(e.target.value)}
                  style={{
                    width: '100%', padding: '8px 12px', borderRadius: 8,
                    border: '1px solid #d1d5db', fontSize: 14,
                    color: reason ? '#111827' : '#9ca3af',
                  }}
                  required={requireReason}
                >
                  <option value="">Select a reason...</option>
                  {reasons.map(r => (
                    <option key={r} value={r}>{r}</option>
                  ))}
                </select>
              </div>
            )}

            {/* Notes field */}
            {allowed && (
              <div style={{ marginBottom: 16 }}>
                <label
                  htmlFor="cancel-notes"
                  style={{ display: 'block', fontSize: 14, fontWeight: 500, marginBottom: 4, color: '#374151' }}
                >
                  Additional notes (optional)
                </label>
                <textarea
                  id="cancel-notes"
                  value={notes}
                  onChange={e => setNotes(e.target.value)}
                  rows={3}
                  maxLength={2000}
                  style={{
                    width: '100%', padding: '8px 12px', borderRadius: 8,
                    border: '1px solid #d1d5db', fontSize: 14, fontFamily: 'inherit',
                    resize: 'vertical', boxSizing: 'border-box',
                  }}
                  placeholder="Any additional context..."
                />
              </div>
            )}

            {/* Actions */}
            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
              <button
                onClick={onClose}
                style={{
                  padding: '10px 20px', borderRadius: 8,
                  border: '1px solid #d1d5db', background: '#fff',
                  cursor: 'pointer', fontSize: 14, color: '#374151',
                }}
              >
                {allowed ? 'Keep Appointment' : 'Close'}
              </button>
              {allowed && (
                <button
                  onClick={handleCancel}
                  disabled={!canSubmit}
                  style={{
                    padding: '10px 20px', borderRadius: 8, border: 'none',
                    background: canSubmit ? '#dc2626' : '#fca5a5',
                    color: '#fff', cursor: canSubmit ? 'pointer' : 'default',
                    fontSize: 14, fontWeight: 500, opacity: cancelling ? 0.7 : 1,
                  }}
                >
                  {cancelling ? 'Cancelling...' : isLate ? 'Confirm Late Cancellation' : 'Confirm Cancellation'}
                </button>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
