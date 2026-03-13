import React, { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import useFocusTrap from '../../hooks/useFocusTrap';

const API_BASE = process.env.REACT_APP_API_URL || '';

const RESCHEDULE_REASONS = [
  { value: '', label: 'Select a reason (optional)' },
  { value: 'schedule_conflict', label: 'Schedule conflict' },
  { value: 'client_request', label: 'Client requested change' },
  { value: 'weather', label: 'Weather / emergency' },
  { value: 'lo_unavailable', label: 'Loan officer unavailable' },
  { value: 'other', label: 'Other' },
];

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
    throw new Error(err.detail || `API error ${res.status}`);
  }
  return res.json();
}

function formatSlotTime(isoStr) {
  const d = new Date(isoStr);
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function formatSlotDate(isoStr) {
  const d = new Date(isoStr);
  return d.toLocaleDateString([], { weekday: 'short', month: 'short', day: 'numeric' });
}

function groupSlotsByDate(slots) {
  const groups = {};
  for (const slot of slots) {
    const dateKey = slot.date || slot.start.split('T')[0];
    if (!groups[dateKey]) groups[dateKey] = [];
    groups[dateKey].push(slot);
  }
  return groups;
}

/**
 * RescheduleModal - Accessible reschedule dialog for appointments.
 *
 * Props:
 *   isOpen        - Whether the modal is visible
 *   appointment   - The appointment object to reschedule
 *   onClose       - Callback to close the modal
 *   onRescheduled - Callback after successful reschedule (receives updated data)
 */
const RescheduleModal = React.memo(function RescheduleModal({
  isOpen,
  appointment,
  onClose,
  onRescheduled,
}) {
  const modalRef = useRef(null);

  // Step: "pick" (select date/time) or "confirm" or "send_link" or "done"
  const [step, setStep] = useState('pick');
  const [reason, setReason] = useState('');
  const [customReason, setCustomReason] = useState('');
  const [selectedDate, setSelectedDate] = useState('');
  const [selectedSlot, setSelectedSlot] = useState(null);
  const [slots, setSlots] = useState([]);
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const [successData, setSuccessData] = useState(null);
  const [rescheduleLink, setRescheduleLink] = useState('');
  const [linkCopied, setLinkCopied] = useState(false);

  // Available date range for the date picker
  const dateOptions = useMemo(() => {
    const dates = [];
    const today = new Date();
    for (let i = 1; i <= 14; i++) {
      const d = new Date(today);
      d.setDate(d.getDate() + i);
      // Skip weekends
      if (d.getDay() !== 0 && d.getDay() !== 6) {
        dates.push(d.toISOString().split('T')[0]);
      }
    }
    return dates;
  }, []);

  // Grouped slots for display
  const slotsByDate = useMemo(() => groupSlotsByDate(slots), [slots]);

  // Reset state when modal opens
  useEffect(() => {
    if (isOpen) {
      setStep('pick');
      setReason('');
      setCustomReason('');
      setSelectedDate('');
      setSelectedSlot(null);
      setSlots([]);
      setError('');
      setSuccessData(null);
      setRescheduleLink('');
      setLinkCopied(false);
    }
  }, [isOpen]);

  // Fetch available slots when a date is selected or modal opens with no date selected
  useEffect(() => {
    if (!isOpen || !appointment) return;
    if (step !== 'pick') return;

    let cancelled = false;
    setLoading(true);
    setError('');
    setSelectedSlot(null);

    const params = new URLSearchParams();
    if (selectedDate) params.append('target_date', selectedDate);

    // First initiate the reschedule, then fetch slots
    const fetchSlots = async () => {
      try {
        // Initiate reschedule (creates history record, idempotent-ish)
        await apiFetch(`/api/scheduling/reschedule/${appointment.id}`, {
          method: 'POST',
          body: JSON.stringify({ reason: null }),
        });
      } catch {
        // Ignore initiation errors (may already be initiated, or limit reached)
      }

      try {
        // Use the authenticated initiate endpoint to figure out slot availability
        // We call the LO-side slot-generation via a helper.
        // For the authenticated flow, we need the appointment's slots.
        const data = await apiFetch(
          `/api/scheduling/appointments/${appointment.id}`,
        );
        // Now fetch availability for the LO
        const slotsUrl = `/api/scheduling/available-slots`;
        const slotsData = await apiFetch(slotsUrl, {
          method: 'POST',
          body: JSON.stringify({
            user_id: data.assigned_user_id || appointment.assigned_user_id,
            start_date: selectedDate || dateOptions[0],
            end_date: selectedDate || dateOptions[dateOptions.length - 1],
            duration_minutes: data.duration_minutes || appointment.duration_minutes || 30,
          }),
        });
        if (!cancelled) {
          setSlots(slotsData.slots || slotsData.available_slots || []);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err.message || 'Failed to load available slots');
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    fetchSlots();
    return () => { cancelled = true; };
  }, [isOpen, appointment, selectedDate, step, dateOptions]);

  // Confirm reschedule
  const handleConfirm = useCallback(async () => {
    if (!selectedSlot || !appointment) return;
    setSubmitting(true);
    setError('');

    const finalReason = reason === 'other' ? customReason : (
      RESCHEDULE_REASONS.find(r => r.value === reason)?.label || reason
    );

    try {
      // First initiate with the reason
      await apiFetch(`/api/scheduling/reschedule/${appointment.id}`, {
        method: 'POST',
        body: JSON.stringify({ reason: finalReason || null }),
      });

      // Then update the appointment directly
      await apiFetch(`/api/scheduling/appointments/${appointment.id}`, {
        method: 'PUT',
        body: JSON.stringify({
          scheduled_start: selectedSlot.start || selectedSlot.start_time,
          scheduled_end: selectedSlot.end || selectedSlot.end_time,
        }),
      });

      setSuccessData({
        new_start: selectedSlot.start || selectedSlot.start_time,
        new_end: selectedSlot.end || selectedSlot.end_time,
      });
      setStep('done');

      if (onRescheduled) {
        onRescheduled({
          appointment_id: appointment.id,
          new_start: selectedSlot.start || selectedSlot.start_time,
          new_end: selectedSlot.end || selectedSlot.end_time,
        });
      }
    } catch (err) {
      setError(err.message || 'Failed to reschedule appointment');
    } finally {
      setSubmitting(false);
    }
  }, [selectedSlot, appointment, reason, customReason, onRescheduled]);

  // Send reschedule link to borrower
  const handleSendLink = useCallback(async () => {
    if (!appointment) return;
    setSubmitting(true);
    setError('');
    try {
      const data = await apiFetch(`/api/scheduling/reschedule/${appointment.id}/link`, {
        method: 'POST',
      });
      setRescheduleLink(data.url);
      setStep('send_link');
    } catch (err) {
      setError(err.message || 'Failed to generate reschedule link');
    } finally {
      setSubmitting(false);
    }
  }, [appointment]);

  const handleCopyLink = useCallback(() => {
    if (rescheduleLink) {
      navigator.clipboard.writeText(rescheduleLink).then(() => {
        setLinkCopied(true);
        setTimeout(() => setLinkCopied(false), 2000);
      });
    }
  }, [rescheduleLink]);

  const handleClose = useCallback(() => {
    onClose();
  }, [onClose]);

  const handleOverlayClick = (e) => {
    if (e.target === e.currentTarget) handleClose();
  };

  useFocusTrap(modalRef, {
    active: isOpen,
    onEscape: handleClose,
    autoFocus: true,
    restoreFocus: true,
  });

  if (!isOpen || !appointment) return null;

  return (
    <div
      className="appointment-modal-overlay"
      onClick={handleOverlayClick}
      role="presentation"
    >
      <div
        ref={modalRef}
        className="appointment-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="reschedule-modal-title"
        style={{ maxWidth: '520px' }}
      >
        {/* Header */}
        <div className="appointment-modal-header">
          <h3 id="reschedule-modal-title">
            {step === 'done' ? 'Rescheduled' : 'Reschedule Appointment'}
          </h3>
          <button
            className="close-btn"
            onClick={handleClose}
            aria-label="Close dialog"
            type="button"
          >
            &times;
          </button>
        </div>

        <div style={{ padding: '16px 20px 20px' }}>
          {/* Error banner */}
          {error && (
            <div
              role="alert"
              style={{
                background: '#fef2f2',
                border: '1px solid #fecaca',
                borderRadius: '6px',
                padding: '10px 14px',
                marginBottom: '14px',
                color: '#991b1b',
                fontSize: '13px',
              }}
            >
              {error}
            </div>
          )}

          {/* Current appointment info */}
          {step !== 'done' && (
            <div
              style={{
                background: '#f8fafc',
                borderRadius: '8px',
                padding: '12px 14px',
                marginBottom: '16px',
                border: '1px solid #e2e8f0',
              }}
            >
              <div style={{ fontWeight: 600, fontSize: '14px', marginBottom: '4px' }}>
                {appointment.title}
              </div>
              <div style={{ fontSize: '13px', color: '#64748b' }}>
                {appointment.scheduled_start
                  ? new Date(appointment.scheduled_start).toLocaleString([], {
                      weekday: 'short',
                      month: 'short',
                      day: 'numeric',
                      hour: '2-digit',
                      minute: '2-digit',
                    })
                  : ''}
                {appointment.attendee_name ? ` \u2014 ${appointment.attendee_name}` : ''}
              </div>
            </div>
          )}

          {/* STEP: Pick new time */}
          {step === 'pick' && (
            <>
              {/* Reason */}
              <div style={{ marginBottom: '14px' }}>
                <label
                  htmlFor="reschedule-reason"
                  style={{ display: 'block', fontSize: '13px', fontWeight: 600, marginBottom: '4px' }}
                >
                  Reason for rescheduling
                </label>
                <select
                  id="reschedule-reason"
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  style={{
                    width: '100%',
                    padding: '8px 10px',
                    borderRadius: '6px',
                    border: '1px solid #d1d5db',
                    fontSize: '13px',
                  }}
                >
                  {RESCHEDULE_REASONS.map((r) => (
                    <option key={r.value} value={r.value}>{r.label}</option>
                  ))}
                </select>
                {reason === 'other' && (
                  <input
                    type="text"
                    placeholder="Please specify..."
                    value={customReason}
                    onChange={(e) => setCustomReason(e.target.value)}
                    maxLength={500}
                    style={{
                      width: '100%',
                      padding: '8px 10px',
                      borderRadius: '6px',
                      border: '1px solid #d1d5db',
                      fontSize: '13px',
                      marginTop: '8px',
                    }}
                  />
                )}
              </div>

              {/* Date picker */}
              <div style={{ marginBottom: '14px' }}>
                <label
                  htmlFor="reschedule-date"
                  style={{ display: 'block', fontSize: '13px', fontWeight: 600, marginBottom: '4px' }}
                >
                  Select a new date
                </label>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                  {dateOptions.map((d) => (
                    <button
                      key={d}
                      type="button"
                      onClick={() => setSelectedDate(d)}
                      style={{
                        padding: '6px 12px',
                        borderRadius: '6px',
                        border: selectedDate === d ? '2px solid #3b82f6' : '1px solid #d1d5db',
                        background: selectedDate === d ? '#eff6ff' : '#fff',
                        cursor: 'pointer',
                        fontSize: '12px',
                        fontWeight: selectedDate === d ? 600 : 400,
                      }}
                    >
                      {formatSlotDate(d + 'T12:00:00')}
                    </button>
                  ))}
                </div>
              </div>

              {/* Available slots */}
              <div style={{ marginBottom: '14px' }}>
                <div style={{ fontSize: '13px', fontWeight: 600, marginBottom: '6px' }}>
                  Available times
                </div>
                {loading ? (
                  <div style={{ color: '#94a3b8', fontSize: '13px', padding: '16px 0', textAlign: 'center' }}>
                    Loading available slots...
                  </div>
                ) : slots.length === 0 ? (
                  <div style={{ color: '#94a3b8', fontSize: '13px', padding: '16px 0', textAlign: 'center' }}>
                    No available slots for this date range. Try a different date.
                  </div>
                ) : (
                  <div
                    style={{
                      maxHeight: '200px',
                      overflowY: 'auto',
                      border: '1px solid #e2e8f0',
                      borderRadius: '8px',
                    }}
                  >
                    {Object.entries(slotsByDate).map(([dateKey, daySlots]) => (
                      <div key={dateKey}>
                        <div
                          style={{
                            fontSize: '12px',
                            fontWeight: 600,
                            padding: '8px 12px 4px',
                            color: '#475569',
                            background: '#f8fafc',
                            borderBottom: '1px solid #e2e8f0',
                            position: 'sticky',
                            top: 0,
                          }}
                        >
                          {formatSlotDate(dateKey + 'T12:00:00')}
                        </div>
                        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', padding: '8px 12px' }}>
                          {daySlots.map((slot, idx) => {
                            const slotKey = slot.start || slot.start_time;
                            const isSelected = selectedSlot && (selectedSlot.start || selectedSlot.start_time) === slotKey;
                            return (
                              <button
                                key={`${dateKey}-${idx}`}
                                type="button"
                                onClick={() => setSelectedSlot(slot)}
                                aria-pressed={isSelected}
                                style={{
                                  padding: '5px 10px',
                                  borderRadius: '4px',
                                  border: isSelected ? '2px solid #3b82f6' : '1px solid #d1d5db',
                                  background: isSelected ? '#eff6ff' : '#fff',
                                  cursor: 'pointer',
                                  fontSize: '12px',
                                  fontWeight: isSelected ? 600 : 400,
                                }}
                              >
                                {formatSlotTime(slotKey)}
                              </button>
                            );
                          })}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Actions */}
              <div style={{ display: 'flex', gap: '10px', justifyContent: 'space-between', flexWrap: 'wrap' }}>
                <button
                  type="button"
                  onClick={handleSendLink}
                  disabled={submitting}
                  style={{
                    padding: '8px 14px',
                    borderRadius: '6px',
                    border: '1px solid #d1d5db',
                    background: '#fff',
                    cursor: 'pointer',
                    fontSize: '13px',
                    color: '#475569',
                  }}
                >
                  Send link to borrower instead
                </button>
                <button
                  type="button"
                  onClick={handleConfirm}
                  disabled={!selectedSlot || submitting}
                  style={{
                    padding: '8px 18px',
                    borderRadius: '6px',
                    border: 'none',
                    background: selectedSlot ? '#3b82f6' : '#94a3b8',
                    color: '#fff',
                    cursor: selectedSlot ? 'pointer' : 'not-allowed',
                    fontSize: '13px',
                    fontWeight: 600,
                  }}
                >
                  {submitting ? 'Rescheduling...' : 'Confirm Reschedule'}
                </button>
              </div>
            </>
          )}

          {/* STEP: Send link to borrower */}
          {step === 'send_link' && (
            <div>
              <div style={{ fontSize: '14px', marginBottom: '12px', color: '#334155' }}>
                Share this link with the borrower. They can pick a new time without logging in.
                The link expires in 72 hours.
              </div>
              <div
                style={{
                  display: 'flex',
                  gap: '8px',
                  alignItems: 'center',
                  marginBottom: '16px',
                }}
              >
                <input
                  type="text"
                  value={rescheduleLink}
                  readOnly
                  onClick={(e) => e.target.select()}
                  aria-label="Reschedule link"
                  style={{
                    flex: 1,
                    padding: '8px 10px',
                    borderRadius: '6px',
                    border: '1px solid #d1d5db',
                    fontSize: '12px',
                    fontFamily: 'monospace',
                  }}
                />
                <button
                  type="button"
                  onClick={handleCopyLink}
                  style={{
                    padding: '8px 14px',
                    borderRadius: '6px',
                    border: '1px solid #d1d5db',
                    background: linkCopied ? '#dcfce7' : '#fff',
                    cursor: 'pointer',
                    fontSize: '13px',
                    fontWeight: 500,
                    whiteSpace: 'nowrap',
                  }}
                >
                  {linkCopied ? 'Copied' : 'Copy'}
                </button>
              </div>
              <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                <button
                  type="button"
                  onClick={handleClose}
                  style={{
                    padding: '8px 18px',
                    borderRadius: '6px',
                    border: '1px solid #d1d5db',
                    background: '#fff',
                    cursor: 'pointer',
                    fontSize: '13px',
                  }}
                >
                  Done
                </button>
              </div>
            </div>
          )}

          {/* STEP: Success */}
          {step === 'done' && successData && (
            <div style={{ textAlign: 'center', padding: '12px 0' }}>
              <div
                style={{
                  width: '48px',
                  height: '48px',
                  borderRadius: '50%',
                  background: '#dcfce7',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  margin: '0 auto 12px',
                  fontSize: '24px',
                }}
                aria-hidden="true"
              >
                &#10003;
              </div>
              <div style={{ fontSize: '16px', fontWeight: 600, marginBottom: '8px', color: '#166534' }}>
                Appointment Rescheduled
              </div>
              <div style={{ fontSize: '14px', color: '#475569', marginBottom: '4px' }}>
                New time: {formatSlotDate(successData.new_start)}{' '}
                at {formatSlotTime(successData.new_start)}
              </div>
              <div style={{ fontSize: '13px', color: '#94a3b8', marginBottom: '16px' }}>
                A confirmation email has been sent.
              </div>
              <button
                type="button"
                onClick={handleClose}
                style={{
                  padding: '8px 24px',
                  borderRadius: '6px',
                  border: 'none',
                  background: '#3b82f6',
                  color: '#fff',
                  cursor: 'pointer',
                  fontSize: '13px',
                  fontWeight: 600,
                }}
              >
                Close
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
});

export default RescheduleModal;
