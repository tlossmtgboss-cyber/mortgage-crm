import React, { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { API_BASE_URL } from '../../services/api';
import './RecruitingPlatform.css';

const INTERVIEW_TYPE_LABELS = {
  phone_screen: 'Phone Screen',
  video_interview: 'Video Interview',
  panel_interview: 'Panel Interview',
  culture_fit: 'Culture Fit',
  reference_check: 'Reference Check',
  offer_call: 'Offer Call',
  interview: 'Interview',
};

function formatSlot(isoStart) {
  const d = new Date(isoStart);
  return d.toLocaleString('en-US', {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    timeZoneName: 'short',
  });
}

export default function CandidateBookingPage() {
  const { token } = useParams();
  const [pageData, setPageData] = useState(null);
  const [slots, setSlots] = useState([]);
  const [selectedSlot, setSelectedSlot] = useState(null);
  const [step, setStep] = useState('loading'); // loading | select-slot | fill-form | confirming | done | error
  const [form, setForm] = useState({ name: '', email: '', notes: '' });
  const [error, setError] = useState(null);

  useEffect(() => {
    async function load() {
      try {
        const res = await fetch(
          `${API_BASE_URL}/api/v1/recruit-calendar/booking/links/${token}`
        );
        if (res.status === 404 || res.status === 410) {
          setError(res.status === 410 ? 'This booking link has expired.' : 'Booking link not found.');
          setStep('error');
          return;
        }
        if (!res.ok) throw new Error('Failed to load booking page');
        const data = await res.json();
        setPageData(data);

        // Fetch available slots from the scheduler
        if (data.assigned_user_id) {
          const slotsRes = await fetch(
            `${API_BASE_URL}/api/v1/recruit-calendar/availability/${data.assigned_user_id}/slots?duration_minutes=${data.duration_minutes || 30}`
          );
          if (slotsRes.ok) {
            const slotsData = await slotsRes.json();
            setSlots(slotsData.slots || []);
          }
        }
        setStep('select-slot');
      } catch (e) {
        setError(e.message);
        setStep('error');
      }
    }
    load();
  }, [token]);

  const handleConfirm = async () => {
    if (!selectedSlot || !form.name.trim() || !form.email.trim()) return;
    setStep('confirming');
    try {
      const res = await fetch(
        `${API_BASE_URL}/api/v1/recruit-calendar/booking/links/${token}/book`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            slot_start: selectedSlot.start,
            slot_end: selectedSlot.end,
            candidate_name: form.name,
            candidate_email: form.email,
            notes: form.notes || null,
          }),
        }
      );
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || 'Booking failed. Please try again.');
      }
      setStep('done');
    } catch (e) {
      setError(e.message);
      setStep('fill-form');
    }
  };

  if (step === 'loading') {
    return (
      <div className="rp-booking-page">
        <div className="rp-booking-card">
          <div className="rp-loading" style={{ padding: 60 }}>Loading...</div>
        </div>
      </div>
    );
  }

  if (step === 'error') {
    return (
      <div className="rp-booking-page">
        <div className="rp-booking-card">
          <div className="rp-booking-hero">
            <div className="rp-booking-hero-title">Booking Unavailable</div>
          </div>
          <div className="rp-booking-body">
            <div className="rp-error">{error}</div>
            <p style={{ fontSize: 13, color: '#6b7280' }}>
              Please contact your recruiter for a new scheduling link.
            </p>
          </div>
        </div>
      </div>
    );
  }

  if (step === 'done') {
    return (
      <div className="rp-booking-page">
        <div className="rp-booking-card">
          <div className="rp-booking-hero" style={{ background: 'linear-gradient(135deg, #065f46, #047857)' }}>
            <div className="rp-booking-hero-title">Interview Confirmed!</div>
            <div className="rp-booking-hero-sub">
              {formatSlot(selectedSlot.start)}
            </div>
          </div>
          <div className="rp-booking-body">
            <p style={{ fontSize: 14, color: '#374151', lineHeight: 1.6 }}>
              Your interview has been scheduled. A confirmation will be sent to{' '}
              <strong>{form.email}</strong>.
            </p>
            <p style={{ fontSize: 13, color: '#9ca3af' }}>
              You'll receive a calendar invite and any video call details from{' '}
              {pageData?.interviewer_name || 'your recruiter'}.
            </p>
          </div>
        </div>
      </div>
    );
  }

  const interviewTypeLabel =
    INTERVIEW_TYPE_LABELS[pageData?.interview_type] || pageData?.interview_type || 'Interview';

  return (
    <div className="rp-booking-page">
      <div className="rp-booking-card">
        <div className="rp-booking-hero">
          <div className="rp-booking-hero-org">
            {pageData?.org_name || 'Recruiting Team'}
          </div>
          <div className="rp-booking-hero-title">
            {pageData?.title || interviewTypeLabel}
          </div>
          <div className="rp-booking-hero-sub">
            {pageData?.duration_minutes || 30} min ·{' '}
            with {pageData?.interviewer_name || 'Recruiter'}
            {pageData?.expires_at && (
              <span style={{ marginLeft: 8, opacity: .7 }}>
                · Link expires {new Date(pageData.expires_at).toLocaleDateString()}
              </span>
            )}
          </div>
        </div>

        <div className="rp-booking-body">
          {error && <div className="rp-error">{error}</div>}

          {step === 'select-slot' && (
            <>
              <div style={{ fontSize: 13, fontWeight: 600, color: '#374151', marginBottom: 12 }}>
                Select a time
              </div>
              {slots.length === 0 ? (
                <div className="rp-empty">
                  No available slots found. Please contact your recruiter.
                </div>
              ) : (
                <>
                  <div className="rp-time-slots">
                    {slots.slice(0, 20).map((slot, idx) => (
                      <button
                        key={idx}
                        className={`rp-time-slot${selectedSlot === slot ? ' rp-time-slot--selected' : ''}`}
                        onClick={() => setSelectedSlot(slot)}
                      >
                        {formatSlot(slot.start || slot)}
                      </button>
                    ))}
                  </div>
                  <button
                    className="rp-btn rp-btn--primary"
                    style={{ width: '100%', marginTop: 16 }}
                    disabled={!selectedSlot}
                    onClick={() => setStep('fill-form')}
                  >
                    Continue →
                  </button>
                </>
              )}
            </>
          )}

          {step === 'fill-form' && (
            <>
              <div style={{ fontSize: 13, color: '#6b7280', marginBottom: 16 }}>
                <strong>Selected:</strong> {formatSlot(selectedSlot.start || selectedSlot)}
                <button
                  onClick={() => { setStep('select-slot'); setError(null); }}
                  style={{ marginLeft: 8, fontSize: 11, color: '#B8924A', border: 'none', background: 'none', cursor: 'pointer' }}
                >
                  Change
                </button>
              </div>

              <div className="rp-booking-form">
                <div>
                  <label className="rp-label">Your Name *</label>
                  <input
                    className="rp-input"
                    value={form.name}
                    onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
                    placeholder="Full name"
                    autoFocus
                  />
                </div>
                <div>
                  <label className="rp-label">Email Address *</label>
                  <input
                    className="rp-input"
                    type="email"
                    value={form.email}
                    onChange={e => setForm(f => ({ ...f, email: e.target.value }))}
                    placeholder="your@email.com"
                  />
                </div>
                <div>
                  <label className="rp-label">Notes (optional)</label>
                  <textarea
                    className="rp-input"
                    rows={3}
                    value={form.notes}
                    onChange={e => setForm(f => ({ ...f, notes: e.target.value }))}
                    placeholder="Anything you'd like the interviewer to know?"
                    style={{ resize: 'vertical' }}
                  />
                </div>
              </div>

              <button
                className="rp-btn rp-btn--primary"
                style={{ width: '100%', marginTop: 20 }}
                disabled={!form.name.trim() || !form.email.trim()}
                onClick={handleConfirm}
              >
                Confirm Interview
              </button>
            </>
          )}

          {step === 'confirming' && (
            <div className="rp-loading">Confirming your interview...</div>
          )}
        </div>
      </div>
    </div>
  );
}
