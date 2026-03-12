import React, { useState, useEffect, useCallback } from 'react';

const API_BASE = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
  ? (process.env.REACT_APP_API_URL || 'http://localhost:8000')
  : 'https://api.perenniaai.com';

/**
 * JoinWaitlist - Public-facing component for joining a waitlist.
 *
 * Shown on the PublicBooking page when no appointment slots are available.
 * Allows the visitor to submit their contact info and preferred dates/times,
 * and then displays their queue position after joining.
 *
 * Props:
 *   organizationId: int - The organization ID
 *   appointmentTypeId: int - The appointment type ID
 *   appointmentTypeName: string - Display name of the appointment type (optional)
 *   onClose: function - Called when user dismisses the form (optional)
 */
const JoinWaitlist = ({ organizationId, appointmentTypeId, appointmentTypeName, onClose }) => {
  const [step, setStep] = useState('form'); // 'form' | 'success' | 'check'
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const [entryId, setEntryId] = useState(null);
  const [position, setPosition] = useState(null);
  const [totalWaiting, setTotalWaiting] = useState(null);
  const [status, setStatus] = useState(null);

  const [form, setForm] = useState({
    name: '',
    email: '',
    phone: '',
    preferred_dates: [],
    preferred_times: [],
    notes: '',
  });

  const [dateInput, setDateInput] = useState('');

  const handleAddDate = () => {
    if (dateInput && !form.preferred_dates.includes(dateInput)) {
      setForm((prev) => ({
        ...prev,
        preferred_dates: [...prev.preferred_dates, dateInput],
      }));
      setDateInput('');
    }
  };

  const handleRemoveDate = (dateToRemove) => {
    setForm((prev) => ({
      ...prev,
      preferred_dates: prev.preferred_dates.filter((d) => d !== dateToRemove),
    }));
  };

  const handleToggleTime = (timePref) => {
    setForm((prev) => {
      const current = prev.preferred_times;
      if (current.includes(timePref)) {
        return { ...prev, preferred_times: current.filter((t) => t !== timePref) };
      }
      return { ...prev, preferred_times: [...current, timePref] };
    });
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setSubmitting(true);

    try {
      const res = await fetch(`${API_BASE}/api/v1/scheduler/public/waitlist/join`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          organization_id: organizationId,
          appointment_type_id: appointmentTypeId,
          name: form.name.trim(),
          email: form.email.trim(),
          phone: form.phone.trim() || null,
          preferred_dates: form.preferred_dates,
          preferred_times: form.preferred_times,
          notes: form.notes.trim() || null,
        }),
      });

      const data = await res.json();

      if (!res.ok) {
        setError(data.detail || 'Failed to join waitlist');
        return;
      }

      setEntryId(data.entry_id);
      setPosition(data.position);
      setStep('success');
    } catch (err) {
      setError('Something went wrong. Please try again.');
    } finally {
      setSubmitting(false);
    }
  };

  const checkPosition = useCallback(async () => {
    if (!entryId) return;
    try {
      const res = await fetch(`${API_BASE}/api/v1/scheduler/public/waitlist/${entryId}/position`);
      if (res.ok) {
        const data = await res.json();
        setPosition(data.position);
        setTotalWaiting(data.total_waiting);
        setStatus(data.status);
      }
    } catch (err) {
      // Silently ignore position check errors
    }
  }, [entryId]);

  // Poll position every 30 seconds when in success/check mode
  useEffect(() => {
    if (step !== 'success' && step !== 'check') return;
    checkPosition();
    const interval = setInterval(checkPosition, 30000);
    return () => clearInterval(interval);
  }, [step, checkPosition]);

  const timePreferences = [
    { value: 'morning', label: 'Morning (9am-12pm)' },
    { value: 'afternoon', label: 'Afternoon (12pm-5pm)' },
    { value: 'evening', label: 'Evening (5pm-8pm)' },
  ];

  // Success view
  if (step === 'success') {
    return (
      <div className="waitlist-join" style={{ textAlign: 'center', padding: '24px' }}>
        <div style={{
          width: '56px', height: '56px', borderRadius: '50%',
          backgroundColor: '#dbeafe', display: 'flex', alignItems: 'center',
          justifyContent: 'center', margin: '0 auto 16px',
        }}>
          <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#2563eb" strokeWidth="2">
            <path d="M5 13l4 4L19 7" />
          </svg>
        </div>
        <h3 style={{ margin: '0 0 8px 0', fontSize: '20px' }}>You're on the Waitlist!</h3>
        <p style={{ color: '#6b7280', margin: '0 0 20px 0', fontSize: '15px' }}>
          We'll notify you at <strong>{form.email}</strong> when a spot opens up.
        </p>

        <div style={{
          backgroundColor: '#f0f9ff', borderRadius: '12px', padding: '20px',
          marginBottom: '20px',
        }}>
          <div style={{ fontSize: '36px', fontWeight: 700, color: '#2563eb' }}>
            #{position}
          </div>
          <div style={{ color: '#6b7280', fontSize: '14px' }}>
            Your position in the queue
            {totalWaiting !== null && ` of ${totalWaiting}`}
          </div>
          {status === 'offered' && (
            <div style={{
              marginTop: '12px', padding: '8px 16px',
              backgroundColor: '#fef3c7', borderRadius: '8px',
              color: '#92400e', fontWeight: 500, fontSize: '14px',
            }}>
              A slot has been offered to you! Check your email.
            </div>
          )}
        </div>

        <button
          onClick={checkPosition}
          style={{
            padding: '10px 20px', borderRadius: '8px', border: '1px solid #d1d5db',
            backgroundColor: '#fff', cursor: 'pointer', fontSize: '14px',
            marginRight: '8px',
          }}
        >
          Refresh Position
        </button>
        {onClose && (
          <button
            onClick={onClose}
            style={{
              padding: '10px 20px', borderRadius: '8px', border: 'none',
              backgroundColor: '#2563eb', color: '#fff', cursor: 'pointer', fontSize: '14px',
            }}
          >
            Done
          </button>
        )}
      </div>
    );
  }

  // Form view
  return (
    <div className="waitlist-join" style={{ padding: '24px' }}>
      <div style={{ textAlign: 'center', marginBottom: '20px' }}>
        <h3 style={{ margin: '0 0 8px 0', fontSize: '20px' }}>
          Join the Waitlist
        </h3>
        <p style={{ color: '#6b7280', margin: 0, fontSize: '14px' }}>
          {appointmentTypeName
            ? `No slots available for ${appointmentTypeName} right now.`
            : 'No slots are currently available.'
          }
          {' '}We'll notify you when one opens up.
        </p>
      </div>

      {error && (
        <div style={{
          padding: '10px 14px', backgroundColor: '#fef2f2',
          color: '#dc2626', borderRadius: '8px', marginBottom: '16px', fontSize: '14px',
        }}>
          {error}
        </div>
      )}

      <form onSubmit={handleSubmit}>
        <div style={{ marginBottom: '14px' }}>
          <label style={{ display: 'block', marginBottom: '4px', fontSize: '14px', fontWeight: 500 }}>
            Name *
          </label>
          <input
            type="text"
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
            placeholder="Your full name"
            required
            style={{
              width: '100%', padding: '10px', borderRadius: '8px',
              border: '1px solid #d1d5db', fontSize: '14px', boxSizing: 'border-box',
            }}
          />
        </div>

        <div style={{ marginBottom: '14px' }}>
          <label style={{ display: 'block', marginBottom: '4px', fontSize: '14px', fontWeight: 500 }}>
            Email *
          </label>
          <input
            type="email"
            value={form.email}
            onChange={(e) => setForm({ ...form, email: e.target.value })}
            placeholder="you@email.com"
            required
            style={{
              width: '100%', padding: '10px', borderRadius: '8px',
              border: '1px solid #d1d5db', fontSize: '14px', boxSizing: 'border-box',
            }}
          />
        </div>

        <div style={{ marginBottom: '14px' }}>
          <label style={{ display: 'block', marginBottom: '4px', fontSize: '14px', fontWeight: 500 }}>
            Phone
          </label>
          <input
            type="tel"
            value={form.phone}
            onChange={(e) => setForm({ ...form, phone: e.target.value })}
            placeholder="(555) 123-4567"
            style={{
              width: '100%', padding: '10px', borderRadius: '8px',
              border: '1px solid #d1d5db', fontSize: '14px', boxSizing: 'border-box',
            }}
          />
        </div>

        <div style={{ marginBottom: '14px' }}>
          <label style={{ display: 'block', marginBottom: '4px', fontSize: '14px', fontWeight: 500 }}>
            Preferred Dates
          </label>
          <div style={{ display: 'flex', gap: '8px', marginBottom: '8px' }}>
            <input
              type="date"
              value={dateInput}
              onChange={(e) => setDateInput(e.target.value)}
              min={new Date().toISOString().split('T')[0]}
              style={{
                flex: 1, padding: '8px', borderRadius: '8px',
                border: '1px solid #d1d5db', fontSize: '14px',
              }}
            />
            <button
              type="button"
              onClick={handleAddDate}
              disabled={!dateInput}
              style={{
                padding: '8px 14px', borderRadius: '8px', border: '1px solid #d1d5db',
                backgroundColor: '#f9fafb', cursor: dateInput ? 'pointer' : 'default',
                fontSize: '14px',
              }}
            >
              Add
            </button>
          </div>
          {form.preferred_dates.length > 0 && (
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
              {form.preferred_dates.map((d) => (
                <span
                  key={d}
                  style={{
                    display: 'inline-flex', alignItems: 'center', gap: '4px',
                    padding: '4px 10px', borderRadius: '16px',
                    backgroundColor: '#eff6ff', color: '#2563eb', fontSize: '13px',
                  }}
                >
                  {new Date(d + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
                  <button
                    type="button"
                    onClick={() => handleRemoveDate(d)}
                    style={{
                      background: 'none', border: 'none', color: '#2563eb',
                      cursor: 'pointer', padding: 0, fontSize: '14px', lineHeight: 1,
                    }}
                  >
                    x
                  </button>
                </span>
              ))}
            </div>
          )}
        </div>

        <div style={{ marginBottom: '14px' }}>
          <label style={{ display: 'block', marginBottom: '6px', fontSize: '14px', fontWeight: 500 }}>
            Preferred Times
          </label>
          <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
            {timePreferences.map((tp) => (
              <button
                key={tp.value}
                type="button"
                onClick={() => handleToggleTime(tp.value)}
                style={{
                  padding: '8px 14px', borderRadius: '20px',
                  border: form.preferred_times.includes(tp.value) ? '2px solid #2563eb' : '1px solid #d1d5db',
                  backgroundColor: form.preferred_times.includes(tp.value) ? '#eff6ff' : '#fff',
                  color: form.preferred_times.includes(tp.value) ? '#2563eb' : '#374151',
                  cursor: 'pointer', fontSize: '13px', fontWeight: 500,
                }}
              >
                {tp.label}
              </button>
            ))}
          </div>
        </div>

        <div style={{ marginBottom: '20px' }}>
          <label style={{ display: 'block', marginBottom: '4px', fontSize: '14px', fontWeight: 500 }}>
            Notes
          </label>
          <textarea
            value={form.notes}
            onChange={(e) => setForm({ ...form, notes: e.target.value })}
            placeholder="Anything else we should know?"
            rows={2}
            maxLength={1000}
            style={{
              width: '100%', padding: '10px', borderRadius: '8px',
              border: '1px solid #d1d5db', fontSize: '14px', resize: 'vertical',
              boxSizing: 'border-box',
            }}
          />
        </div>

        <button
          type="submit"
          disabled={submitting || !form.name || !form.email}
          style={{
            width: '100%', padding: '12px', borderRadius: '8px', border: 'none',
            backgroundColor: '#2563eb', color: '#fff', fontSize: '16px',
            fontWeight: 600, cursor: submitting ? 'default' : 'pointer',
            opacity: submitting || !form.name || !form.email ? 0.6 : 1,
          }}
        >
          {submitting ? 'Joining...' : 'Join Waitlist'}
        </button>
      </form>
    </div>
  );
};

export default JoinWaitlist;
