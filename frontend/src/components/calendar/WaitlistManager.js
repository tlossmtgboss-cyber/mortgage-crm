import React, { useState, useEffect, useCallback, useRef } from 'react';

const API_BASE = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
  ? (process.env.REACT_APP_API_URL || 'http://localhost:8000')
  : 'https://api.perenniaai.com';

const STATUS_COLORS = {
  waiting: '#2563eb',
  offered: '#f59e0b',
  accepted: '#16a34a',
  expired: '#9ca3af',
  cancelled: '#dc2626',
};

const STATUS_LABELS = {
  waiting: 'Waiting',
  offered: 'Offered',
  accepted: 'Accepted',
  expired: 'Expired',
  cancelled: 'Cancelled',
};

function formatDate(isoString) {
  if (!isoString) return '--';
  return new Date(isoString).toLocaleDateString('en-US', {
    month: 'short', day: 'numeric', year: 'numeric',
  });
}

function formatDateTime(isoString) {
  if (!isoString) return '--';
  return new Date(isoString).toLocaleString('en-US', {
    month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit',
  });
}

function getTimeRemaining(expiresAt) {
  if (!expiresAt) return null;
  const now = new Date();
  const exp = new Date(expiresAt);
  const diff = exp - now;
  if (diff <= 0) return 'Expired';
  const hours = Math.floor(diff / (1000 * 60 * 60));
  const minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));
  return `${hours}h ${minutes}m`;
}

const StatusBadge = ({ status }) => (
  <span
    className="waitlist-status-badge"
    style={{
      backgroundColor: `${STATUS_COLORS[status] || '#6b7280'}20`,
      color: STATUS_COLORS[status] || '#6b7280',
      padding: '2px 8px',
      borderRadius: '12px',
      fontSize: '12px',
      fontWeight: 600,
      display: 'inline-block',
    }}
  >
    {STATUS_LABELS[status] || status}
  </span>
);

const OfferCountdown = ({ expiresAt }) => {
  const [remaining, setRemaining] = useState(getTimeRemaining(expiresAt));

  useEffect(() => {
    if (!expiresAt) return;
    const interval = setInterval(() => {
      setRemaining(getTimeRemaining(expiresAt));
    }, 60000); // Update every minute
    return () => clearInterval(interval);
  }, [expiresAt]);

  if (!remaining) return null;
  const isExpired = remaining === 'Expired';

  return (
    <span
      style={{
        fontSize: '11px',
        color: isExpired ? '#dc2626' : '#f59e0b',
        fontWeight: 500,
      }}
    >
      {isExpired ? 'Expired' : `Expires in ${remaining}`}
    </span>
  );
};

const WaitlistManager = ({ appointmentTypeId, token }) => {
  const [entries, setEntries] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [statusFilter, setStatusFilter] = useState('');
  const [offerModalEntry, setOfferModalEntry] = useState(null);
  const [offerSlotTime, setOfferSlotTime] = useState('');
  const [offerSubmitting, setOfferSubmitting] = useState(false);
  const dragItem = useRef(null);
  const dragOverItem = useRef(null);

  const headers = {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };

  const fetchWaitlist = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      if (appointmentTypeId) params.set('appointment_type_id', appointmentTypeId);
      if (statusFilter) params.set('status', statusFilter);
      params.set('limit', '200');

      const res = await fetch(`${API_BASE}/api/v1/scheduler/waitlist?${params}`, { headers });
      if (!res.ok) throw new Error('Failed to load waitlist');
      const data = await res.json();
      setEntries(data.entries || []);
      setTotal(data.total || 0);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [appointmentTypeId, statusFilter, token]);

  useEffect(() => {
    fetchWaitlist();
  }, [fetchWaitlist]);

  // Drag and drop handlers
  const handleDragStart = (index) => {
    dragItem.current = index;
  };

  const handleDragEnter = (index) => {
    dragOverItem.current = index;
  };

  const handleDragEnd = async () => {
    if (dragItem.current === null || dragOverItem.current === null) return;
    if (dragItem.current === dragOverItem.current) return;

    const entry = entries[dragItem.current];
    if (entry.status !== 'waiting') return; // Only reorder waiting entries

    const newPosition = entries[dragOverItem.current].position || (dragOverItem.current + 1);

    try {
      const res = await fetch(`${API_BASE}/api/v1/scheduler/waitlist/${entry.id}/reorder`, {
        method: 'POST',
        headers,
        body: JSON.stringify({ new_position: newPosition }),
      });
      if (res.ok) {
        fetchWaitlist();
      }
    } catch (err) {
      console.error('Reorder failed:', err);
    }

    dragItem.current = null;
    dragOverItem.current = null;
  };

  const handleRemoveEntry = async (entryId) => {
    if (!window.confirm('Remove this entry from the waitlist?')) return;
    try {
      const res = await fetch(`${API_BASE}/api/v1/scheduler/waitlist/${entryId}`, {
        method: 'DELETE',
        headers,
      });
      if (res.ok) {
        fetchWaitlist();
      }
    } catch (err) {
      console.error('Remove failed:', err);
    }
  };

  const handleOfferSlot = async () => {
    if (!offerModalEntry || !offerSlotTime) return;
    setOfferSubmitting(true);
    try {
      const res = await fetch(`${API_BASE}/api/v1/scheduler/waitlist/${offerModalEntry.id}/offer`, {
        method: 'POST',
        headers,
        body: JSON.stringify({ slot_time: new Date(offerSlotTime).toISOString() }),
      });
      if (res.ok) {
        setOfferModalEntry(null);
        setOfferSlotTime('');
        fetchWaitlist();
      } else {
        const data = await res.json();
        alert(data.detail || 'Failed to offer slot');
      }
    } catch (err) {
      console.error('Offer failed:', err);
    } finally {
      setOfferSubmitting(false);
    }
  };

  const handleExpireOffers = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/v1/scheduler/waitlist/expire-offers`, {
        method: 'POST',
        headers,
      });
      if (res.ok) {
        const data = await res.json();
        if (data.expired_count > 0) {
          fetchWaitlist();
        }
      }
    } catch (err) {
      console.error('Expire failed:', err);
    }
  };

  const handleNotifyAll = async () => {
    // Notify all is a convenience action: expire stale offers, then refresh
    if (!window.confirm('This will expire stale offers and refresh the queue. Continue?')) return;
    await handleExpireOffers();
    fetchWaitlist();
  };

  return (
    <div className="waitlist-manager" style={{ padding: '16px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
        <h3 style={{ margin: 0 }}>Waitlist Queue ({total})</h3>
        <div style={{ display: 'flex', gap: '8px' }}>
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            style={{ padding: '6px 10px', borderRadius: '6px', border: '1px solid #d1d5db', fontSize: '13px' }}
          >
            <option value="">All Statuses</option>
            <option value="waiting">Waiting</option>
            <option value="offered">Offered</option>
            <option value="accepted">Accepted</option>
            <option value="expired">Expired</option>
            <option value="cancelled">Cancelled</option>
          </select>
          <button
            onClick={handleNotifyAll}
            style={{
              padding: '6px 14px', borderRadius: '6px',
              backgroundColor: '#2563eb', color: '#fff',
              border: 'none', cursor: 'pointer', fontSize: '13px',
            }}
          >
            Refresh Queue
          </button>
        </div>
      </div>

      {error && (
        <div style={{ padding: '12px', backgroundColor: '#fef2f2', color: '#dc2626', borderRadius: '8px', marginBottom: '12px' }}>
          {error}
        </div>
      )}

      {loading ? (
        <div style={{ textAlign: 'center', padding: '40px', color: '#6b7280' }}>Loading waitlist...</div>
      ) : entries.length === 0 ? (
        <div style={{ textAlign: 'center', padding: '40px', color: '#6b7280' }}>No entries on the waitlist</div>
      ) : (
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '14px' }}>
          <thead>
            <tr style={{ borderBottom: '2px solid #e5e7eb', textAlign: 'left' }}>
              <th style={{ padding: '8px 4px', width: '40px' }}>#</th>
              <th style={{ padding: '8px 4px' }}>Name</th>
              <th style={{ padding: '8px 4px' }}>Email</th>
              <th style={{ padding: '8px 4px' }}>Preferences</th>
              <th style={{ padding: '8px 4px' }}>Status</th>
              <th style={{ padding: '8px 4px' }}>Joined</th>
              <th style={{ padding: '8px 4px', width: '120px' }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {entries.map((entry, index) => (
              <tr
                key={entry.id}
                draggable={entry.status === 'waiting'}
                onDragStart={() => handleDragStart(index)}
                onDragEnter={() => handleDragEnter(index)}
                onDragEnd={handleDragEnd}
                onDragOver={(e) => e.preventDefault()}
                style={{
                  borderBottom: '1px solid #f3f4f6',
                  cursor: entry.status === 'waiting' ? 'grab' : 'default',
                  opacity: entry.status === 'cancelled' || entry.status === 'expired' ? 0.5 : 1,
                }}
              >
                <td style={{ padding: '10px 4px', fontWeight: 600, color: '#6b7280' }}>
                  {entry.position || '--'}
                </td>
                <td style={{ padding: '10px 4px', fontWeight: 500 }}>{entry.name}</td>
                <td style={{ padding: '10px 4px', color: '#6b7280' }}>{entry.email}</td>
                <td style={{ padding: '10px 4px', fontSize: '12px', color: '#6b7280' }}>
                  {entry.preferred_dates && entry.preferred_dates.length > 0 && (
                    <div>Dates: {entry.preferred_dates.slice(0, 3).join(', ')}{entry.preferred_dates.length > 3 ? '...' : ''}</div>
                  )}
                  {entry.preferred_times && entry.preferred_times.length > 0 && (
                    <div>Times: {entry.preferred_times.join(', ')}</div>
                  )}
                </td>
                <td style={{ padding: '10px 4px' }}>
                  <StatusBadge status={entry.status} />
                  {entry.status === 'offered' && entry.expires_at && (
                    <div style={{ marginTop: '2px' }}>
                      <OfferCountdown expiresAt={entry.expires_at} />
                    </div>
                  )}
                  {entry.offered_slot_time && entry.status === 'offered' && (
                    <div style={{ fontSize: '11px', color: '#4b5563', marginTop: '2px' }}>
                      Slot: {formatDateTime(entry.offered_slot_time)}
                    </div>
                  )}
                </td>
                <td style={{ padding: '10px 4px', fontSize: '12px', color: '#6b7280' }}>
                  {formatDate(entry.created_at)}
                </td>
                <td style={{ padding: '10px 4px' }}>
                  <div style={{ display: 'flex', gap: '4px' }}>
                    {entry.status === 'waiting' && (
                      <button
                        onClick={() => { setOfferModalEntry(entry); setOfferSlotTime(''); }}
                        title="Offer a slot"
                        style={{
                          padding: '4px 8px', borderRadius: '4px', fontSize: '11px',
                          backgroundColor: '#dbeafe', color: '#2563eb', border: 'none', cursor: 'pointer',
                        }}
                      >
                        Offer Slot
                      </button>
                    )}
                    {(entry.status === 'waiting' || entry.status === 'offered') && (
                      <button
                        onClick={() => handleRemoveEntry(entry.id)}
                        title="Remove from waitlist"
                        style={{
                          padding: '4px 8px', borderRadius: '4px', fontSize: '11px',
                          backgroundColor: '#fee2e2', color: '#dc2626', border: 'none', cursor: 'pointer',
                        }}
                      >
                        Remove
                      </button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {/* Offer Slot Modal */}
      {offerModalEntry && (
        <div
          style={{
            position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
            backgroundColor: 'rgba(0,0,0,0.5)', display: 'flex',
            alignItems: 'center', justifyContent: 'center', zIndex: 1000,
          }}
          onClick={() => setOfferModalEntry(null)}
        >
          <div
            style={{
              backgroundColor: '#fff', borderRadius: '12px', padding: '24px',
              width: '400px', maxWidth: '90vw',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <h3 style={{ margin: '0 0 16px 0' }}>Offer Slot to {offerModalEntry.name}</h3>
            <p style={{ color: '#6b7280', fontSize: '14px', margin: '0 0 16px 0' }}>
              Select a date and time to offer this person.
            </p>
            {offerModalEntry.preferred_dates && offerModalEntry.preferred_dates.length > 0 && (
              <p style={{ fontSize: '13px', color: '#4b5563', margin: '0 0 8px 0' }}>
                Preferred dates: {offerModalEntry.preferred_dates.join(', ')}
              </p>
            )}
            {offerModalEntry.preferred_times && offerModalEntry.preferred_times.length > 0 && (
              <p style={{ fontSize: '13px', color: '#4b5563', margin: '0 0 16px 0' }}>
                Preferred times: {offerModalEntry.preferred_times.join(', ')}
              </p>
            )}
            <input
              type="datetime-local"
              value={offerSlotTime}
              onChange={(e) => setOfferSlotTime(e.target.value)}
              style={{
                width: '100%', padding: '10px', borderRadius: '8px',
                border: '1px solid #d1d5db', fontSize: '14px', marginBottom: '16px',
                boxSizing: 'border-box',
              }}
            />
            <div style={{ display: 'flex', gap: '8px', justifyContent: 'flex-end' }}>
              <button
                onClick={() => setOfferModalEntry(null)}
                style={{
                  padding: '8px 16px', borderRadius: '8px', border: '1px solid #d1d5db',
                  backgroundColor: '#fff', cursor: 'pointer', fontSize: '14px',
                }}
              >
                Cancel
              </button>
              <button
                onClick={handleOfferSlot}
                disabled={!offerSlotTime || offerSubmitting}
                style={{
                  padding: '8px 16px', borderRadius: '8px', border: 'none',
                  backgroundColor: '#2563eb', color: '#fff', cursor: 'pointer',
                  fontSize: '14px', opacity: !offerSlotTime || offerSubmitting ? 0.5 : 1,
                }}
              >
                {offerSubmitting ? 'Offering...' : 'Send Offer'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default WaitlistManager;
