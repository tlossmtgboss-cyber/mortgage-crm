/**
 * Embeddable Booking Widget
 *
 * A self-contained booking component that can be:
 * 1. Embedded in the app directly
 * 2. Served as a standalone page for iframe embedding
 * 3. Used in the borrower portal
 *
 * Usage: <EmbeddableBookingWidget slug="booking-slug" />
 * Or via URL: /embed/book/{slug}
 */
import { useState, useEffect } from 'react';

const WIDGET_STYLES = {
  container: {
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
    maxWidth: 'min(480px, 100%)',
    width: '100%',
    margin: '0 auto',
    padding: 16,
    background: '#fff',
    borderRadius: 12,
    boxShadow: '0 1px 3px rgba(0,0,0,0.1)',
    boxSizing: 'border-box',
  },
  header: {
    textAlign: 'center',
    marginBottom: 24,
  },
  dateGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(3, 1fr)',
    gap: 8,
    marginBottom: 20,
  },
  dateBtn: (selected) => ({
    padding: '12px 8px',
    border: `2px solid ${selected ? '#6366f1' : '#e2e8f0'}`,
    borderRadius: 8,
    background: selected ? '#eef2ff' : '#fff',
    cursor: 'pointer',
    textAlign: 'center',
    fontSize: '0.85rem',
  }),
  timeGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(3, 1fr)',
    gap: 8,
    marginBottom: 20,
  },
  timeBtn: (selected) => ({
    padding: '10px',
    border: `2px solid ${selected ? '#6366f1' : '#e2e8f0'}`,
    borderRadius: 8,
    background: selected ? '#eef2ff' : '#fff',
    cursor: 'pointer',
    textAlign: 'center',
    fontSize: '0.9rem',
    fontWeight: selected ? 600 : 400,
  }),
  submitBtn: {
    width: '100%',
    padding: '14px',
    background: '#6366f1',
    color: '#fff',
    border: 'none',
    borderRadius: 8,
    fontSize: '1rem',
    fontWeight: 600,
    cursor: 'pointer',
  },
  input: {
    width: '100%',
    padding: '10px 12px',
    border: '1px solid #e2e8f0',
    borderRadius: 6,
    fontSize: '0.9rem',
    marginBottom: 12,
    boxSizing: 'border-box',
  },
};

export default function EmbeddableBookingWidget({ slug, onBooked, theme = {} }) {
  const [step, setStep] = useState('loading'); // loading, dates, times, form, confirm, success
  const [bookingLink, setBookingLink] = useState(null);
  const [dates, setDates] = useState([]);
  const [slots, setSlots] = useState([]);
  const [selectedDate, setSelectedDate] = useState(null);
  const [selectedSlot, setSelectedSlot] = useState(null);
  const [form, setForm] = useState({ name: '', email: '', phone: '' });
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  const apiBase = '/api/v1/scheduler/public/book';

  useEffect(() => { loadBookingLink(); }, [slug]);

  const loadBookingLink = async () => {
    try {
      const res = await fetch(`${apiBase}/${slug}`);
      if (!res.ok) throw new Error('Booking link not found');
      const data = await res.json();
      setBookingLink(data);
      await loadSlots();
      setStep('dates');
    } catch (err) {
      setError(err.message);
      setStep('error');
    }
  };

  const loadSlots = async () => {
    try {
      const today = new Date();
      const end = new Date(today);
      end.setDate(end.getDate() + 14);
      const res = await fetch(
        `${apiBase}/${slug}/slots?start_date=${today.toISOString().split('T')[0]}&end_date=${end.toISOString().split('T')[0]}`
      );
      if (res.ok) {
        const data = await res.json();
        const slotList = data.slots || data.available_slots || [];
        // Group by date
        const byDate = {};
        slotList.forEach(s => {
          const d = new Date(s.start || s.start_time).toISOString().split('T')[0];
          if (!byDate[d]) byDate[d] = [];
          byDate[d].push(s);
        });
        setDates(Object.keys(byDate).sort());
        setSlots(byDate);
      }
    } catch (err) {
      console.error('Failed to load slots:', err);
    }
  };

  const selectDate = (date) => {
    setSelectedDate(date);
    setSelectedSlot(null);
    setStep('times');
  };

  const selectSlot = (slot) => {
    setSelectedSlot(slot);
    setStep('form');
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!form.name || !form.email) return;
    setSubmitting(true);
    try {
      const res = await fetch(`${apiBase}/${slug}/confirm`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          start_time: selectedSlot.start || selectedSlot.start_time,
          duration_minutes: selectedSlot.duration_minutes || 30,
          attendee_name: form.name,
          attendee_email: form.email,
          attendee_phone: form.phone || undefined,
        }),
      });
      if (res.ok) {
        setStep('success');
        if (onBooked) onBooked(await res.json());
      } else {
        const data = await res.json();
        setError(data.detail || 'Booking failed. Please try again.');
      }
    } catch (err) {
      setError('Connection error. Please try again.');
    } finally {
      setSubmitting(false);
    }
  };

  const formatDate = (dateStr) => {
    const d = new Date(dateStr + 'T12:00:00');
    return d.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' });
  };

  const formatTime = (slot) => {
    const d = new Date(slot.start || slot.start_time);
    return d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' });
  };

  if (step === 'error') return <div style={WIDGET_STYLES.container}><p style={{ color: '#ef4444' }}>{error}</p></div>;
  if (step === 'loading') return <div style={WIDGET_STYLES.container}><p>Loading available times...</p></div>;

  if (step === 'success') {
    return (
      <div style={WIDGET_STYLES.container}>
        <div style={{ textAlign: 'center', padding: 20 }}>
          <div style={{ fontSize: 48, marginBottom: 12 }}>&#10003;</div>
          <h2 style={{ color: '#22c55e', marginBottom: 8 }}>Booked!</h2>
          <p style={{ color: '#64748b' }}>You will receive a confirmation email shortly.</p>
        </div>
      </div>
    );
  }

  return (
    <div style={{ ...WIDGET_STYLES.container, ...theme }}>
      <div style={WIDGET_STYLES.header}>
        <h2 style={{ margin: '0 0 4px', fontSize: '1.3rem' }}>
          {bookingLink?.title || 'Schedule a Meeting'}
        </h2>
        <p style={{ margin: 0, color: '#64748b', fontSize: '0.9rem' }}>
          {bookingLink?.description || 'Select a date and time that works for you'}
        </p>
      </div>

      {error && <div style={{ background: '#fef2f2', color: '#dc2626', padding: 12, borderRadius: 8, marginBottom: 16, fontSize: '0.85rem' }}>{error}</div>}

      {step === 'dates' && (
        <>
          <h3 style={{ fontSize: '0.95rem', marginBottom: 12 }}>Select a Date</h3>
          <div style={WIDGET_STYLES.dateGrid}>
            {dates.slice(0, 9).map(date => (
              <button key={date} style={WIDGET_STYLES.dateBtn(selectedDate === date)} onClick={() => selectDate(date)}>
                {formatDate(date)}
              </button>
            ))}
          </div>
        </>
      )}

      {step === 'times' && selectedDate && (
        <>
          <button onClick={() => setStep('dates')} style={{ background: 'none', border: 'none', color: '#6366f1', cursor: 'pointer', marginBottom: 12 }}>
            &larr; Back to dates
          </button>
          <h3 style={{ fontSize: '0.95rem', marginBottom: 12 }}>{formatDate(selectedDate)}</h3>
          <div style={WIDGET_STYLES.timeGrid}>
            {(slots[selectedDate] || []).map((slot, i) => (
              <button key={i} style={WIDGET_STYLES.timeBtn(selectedSlot === slot)} onClick={() => selectSlot(slot)}>
                {formatTime(slot)}
              </button>
            ))}
          </div>
        </>
      )}

      {step === 'form' && (
        <>
          <button onClick={() => setStep('times')} style={{ background: 'none', border: 'none', color: '#6366f1', cursor: 'pointer', marginBottom: 12 }}>
            &larr; Back to times
          </button>
          <p style={{ fontSize: '0.9rem', color: '#64748b', marginBottom: 16 }}>
            {formatDate(selectedDate)} at {formatTime(selectedSlot)}
          </p>
          <form onSubmit={handleSubmit}>
            <input style={WIDGET_STYLES.input} placeholder="Your name *" value={form.name} onChange={e => setForm(f => ({...f, name: e.target.value}))} required />
            <input style={WIDGET_STYLES.input} type="email" placeholder="Email address *" value={form.email} onChange={e => setForm(f => ({...f, email: e.target.value}))} required />
            <input style={WIDGET_STYLES.input} type="tel" placeholder="Phone number (optional)" value={form.phone} onChange={e => setForm(f => ({...f, phone: e.target.value}))} />
            <button type="submit" style={{...WIDGET_STYLES.submitBtn, opacity: submitting ? 0.7 : 1}} disabled={submitting}>
              {submitting ? 'Booking...' : 'Confirm Booking'}
            </button>
          </form>
        </>
      )}
    </div>
  );
}
