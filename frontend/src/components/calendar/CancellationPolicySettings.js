import React, { useState, useEffect, useCallback } from 'react';
import { getToken } from '../../utils/tokenStore';

const API_BASE = process.env.REACT_APP_API_URL || '';

async function apiFetch(path, options = {}) {
  const token = getToken();
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

function Toggle({ checked, onChange, label }) {
  return (
    <label style={{ display: 'flex', alignItems: 'center', gap: 10, cursor: 'pointer' }}>
      <span
        style={{
          position: 'relative', display: 'inline-block', width: 44, height: 24,
        }}
      >
        <input
          type="checkbox"
          checked={checked}
          onChange={e => onChange(e.target.checked)}
          style={{ opacity: 0, width: 0, height: 0, position: 'absolute' }}
          aria-label={label}
        />
        <span
          style={{
            position: 'absolute', cursor: 'pointer', top: 0, left: 0, right: 0, bottom: 0,
            backgroundColor: checked ? '#3b82f6' : '#d1d5db',
            borderRadius: 24, transition: 'background-color 0.2s',
          }}
        >
          <span
            style={{
              position: 'absolute', height: 18, width: 18,
              left: checked ? 22 : 3, bottom: 3,
              backgroundColor: '#fff', borderRadius: '50%', transition: 'left 0.2s',
            }}
          />
        </span>
      </span>
      <span style={{ fontSize: 14, fontWeight: 500, color: '#374151' }}>{label}</span>
    </label>
  );
}

function ReasonsList({ reasons, onChange }) {
  const [newReason, setNewReason] = useState('');

  const handleAdd = () => {
    const trimmed = newReason.trim();
    if (!trimmed) return;
    if (reasons.includes(trimmed)) return;
    onChange([...reasons, trimmed]);
    setNewReason('');
  };

  const handleRemove = (index) => {
    onChange(reasons.filter((_, i) => i !== index));
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      handleAdd();
    }
  };

  return (
    <div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 8 }}>
        {reasons.map((reason, i) => (
          <span
            key={i}
            style={{
              display: 'inline-flex', alignItems: 'center', gap: 4,
              padding: '4px 10px', borderRadius: 16,
              background: '#f3f4f6', border: '1px solid #e5e7eb',
              fontSize: 13, color: '#374151',
            }}
          >
            {reason}
            <button
              onClick={() => handleRemove(i)}
              style={{
                background: 'none', border: 'none', cursor: 'pointer',
                color: '#9ca3af', fontSize: 14, padding: '0 2px', lineHeight: 1,
              }}
              aria-label={`Remove reason: ${reason}`}
              title="Remove"
            >
              x
            </button>
          </span>
        ))}
      </div>
      <div style={{ display: 'flex', gap: 8 }}>
        <input
          type="text"
          value={newReason}
          onChange={e => setNewReason(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Add a reason..."
          maxLength={200}
          style={{
            flex: 1, padding: '8px 12px', borderRadius: 8,
            border: '1px solid #d1d5db', fontSize: 14, boxSizing: 'border-box',
          }}
        />
        <button
          onClick={handleAdd}
          disabled={!newReason.trim()}
          style={{
            padding: '8px 16px', borderRadius: 8, border: '1px solid #d1d5db',
            background: newReason.trim() ? '#f9fafb' : '#f3f4f6',
            cursor: newReason.trim() ? 'pointer' : 'default',
            fontSize: 14, color: '#374151',
          }}
        >
          Add
        </button>
      </div>
    </div>
  );
}

export default function CancellationPolicySettings() {
  const [policy, setPolicy] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [dirty, setDirty] = useState(false);

  // Fetch policy on mount
  const fetchPolicy = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const data = await apiFetch('/api/v1/scheduler/cancellation-policy');
      setPolicy(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchPolicy();
  }, [fetchPolicy]);

  const handleChange = useCallback((field, value) => {
    setPolicy(prev => ({ ...prev, [field]: value }));
    setDirty(true);
    setSuccess('');
  }, []);

  const handleSave = useCallback(async () => {
    if (!policy) return;
    setSaving(true);
    setError('');
    setSuccess('');
    try {
      const data = await apiFetch('/api/v1/scheduler/cancellation-policy', {
        method: 'PUT',
        body: JSON.stringify({
          min_notice_hours: policy.min_notice_hours,
          max_cancellations_per_borrower: policy.max_cancellations_per_borrower,
          allow_borrower_cancel: policy.allow_borrower_cancel,
          require_reason: policy.require_reason,
          cancellation_reasons: policy.cancellation_reasons,
          late_cancel_message: policy.late_cancel_message,
        }),
      });
      setPolicy(data);
      setDirty(false);
      setSuccess('Cancellation policy saved successfully');
      setTimeout(() => setSuccess(''), 4000);
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }, [policy]);

  if (loading) {
    return (
      <div style={{ maxWidth: 640, margin: '0 auto', padding: 20, textAlign: 'center', color: '#6b7280' }}>
        Loading cancellation policy...
      </div>
    );
  }

  if (!policy) {
    return (
      <div style={{ maxWidth: 640, margin: '0 auto', padding: 20 }}>
        {error && (
          <div style={{ padding: '8px 12px', background: '#fef2f2', color: '#dc2626', borderRadius: 8, fontSize: 13 }}>
            {error}
          </div>
        )}
      </div>
    );
  }

  return (
    <div style={{ maxWidth: 640, margin: '0 auto' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
        <h3 style={{ margin: 0, fontSize: 18, fontWeight: 600 }}>Cancellation Policy</h3>
        <button
          onClick={handleSave}
          disabled={saving || !dirty}
          style={{
            padding: '8px 20px', borderRadius: 8, border: 'none',
            background: dirty ? '#3b82f6' : '#d1d5db',
            color: '#fff', cursor: dirty && !saving ? 'pointer' : 'default',
            fontSize: 14, fontWeight: 500, opacity: saving ? 0.7 : 1,
          }}
        >
          {saving ? 'Saving...' : 'Save Policy'}
        </button>
      </div>

      {error && (
        <div style={{
          padding: '8px 12px', background: '#fef2f2', color: '#dc2626',
          borderRadius: 8, marginBottom: 12, fontSize: 13,
        }}>
          {error}
          <button
            onClick={() => setError('')}
            style={{ float: 'right', background: 'none', border: 'none', cursor: 'pointer', fontWeight: 600, color: '#dc2626' }}
          >
            X
          </button>
        </div>
      )}

      {success && (
        <div style={{
          padding: '8px 12px', background: '#f0fdf4', color: '#16a34a',
          borderRadius: 8, marginBottom: 12, fontSize: 13,
        }}>
          {success}
        </div>
      )}

      {/* Notice Period */}
      <div style={{
        border: '1px solid #e5e7eb', borderRadius: 12, padding: 16, marginBottom: 16, background: '#fff',
      }}>
        <label style={{ display: 'block', fontSize: 14, fontWeight: 600, marginBottom: 4, color: '#111827' }}>
          Minimum Notice Period
        </label>
        <p style={{ fontSize: 13, color: '#6b7280', marginTop: 0, marginBottom: 10 }}>
          Cancellations within this window are flagged as "late" cancellations.
        </p>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <input
            type="number"
            min={0}
            max={720}
            value={policy.min_notice_hours}
            onChange={e => handleChange('min_notice_hours', parseInt(e.target.value, 10) || 0)}
            style={{
              width: 80, padding: '8px 12px', borderRadius: 8,
              border: '1px solid #d1d5db', fontSize: 14, textAlign: 'center',
            }}
          />
          <span style={{ fontSize: 14, color: '#6b7280' }}>hours before appointment</span>
        </div>
      </div>

      {/* Max Cancellations */}
      <div style={{
        border: '1px solid #e5e7eb', borderRadius: 12, padding: 16, marginBottom: 16, background: '#fff',
      }}>
        <label style={{ display: 'block', fontSize: 14, fontWeight: 600, marginBottom: 4, color: '#111827' }}>
          Maximum Cancellations Per Borrower
        </label>
        <p style={{ fontSize: 13, color: '#6b7280', marginTop: 0, marginBottom: 10 }}>
          Rolling 30-day limit on how many appointments a borrower can cancel. Set to 0 for unlimited.
        </p>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <input
            type="number"
            min={0}
            max={100}
            value={policy.max_cancellations_per_borrower}
            onChange={e => handleChange('max_cancellations_per_borrower', parseInt(e.target.value, 10) || 0)}
            style={{
              width: 80, padding: '8px 12px', borderRadius: 8,
              border: '1px solid #d1d5db', fontSize: 14, textAlign: 'center',
            }}
          />
          <span style={{ fontSize: 14, color: '#6b7280' }}>cancellations per 30 days</span>
        </div>
      </div>

      {/* Toggles */}
      <div style={{
        border: '1px solid #e5e7eb', borderRadius: 12, padding: 16, marginBottom: 16, background: '#fff',
        display: 'flex', flexDirection: 'column', gap: 16,
      }}>
        <div>
          <Toggle
            checked={policy.allow_borrower_cancel}
            onChange={v => handleChange('allow_borrower_cancel', v)}
            label="Allow borrower self-cancellation"
          />
          <p style={{ fontSize: 13, color: '#6b7280', margin: '4px 0 0 54px' }}>
            When disabled, only staff can cancel appointments.
          </p>
        </div>
        <div>
          <Toggle
            checked={policy.require_reason}
            onChange={v => handleChange('require_reason', v)}
            label="Require cancellation reason"
          />
          <p style={{ fontSize: 13, color: '#6b7280', margin: '4px 0 0 54px' }}>
            When enabled, a reason must be selected to proceed with cancellation.
          </p>
        </div>
      </div>

      {/* Cancellation Reasons */}
      <div style={{
        border: '1px solid #e5e7eb', borderRadius: 12, padding: 16, marginBottom: 16, background: '#fff',
      }}>
        <label style={{ display: 'block', fontSize: 14, fontWeight: 600, marginBottom: 4, color: '#111827' }}>
          Cancellation Reasons
        </label>
        <p style={{ fontSize: 13, color: '#6b7280', marginTop: 0, marginBottom: 10 }}>
          Preset reasons shown in the cancellation dropdown. Borrowers select from this list.
        </p>
        <ReasonsList
          reasons={policy.cancellation_reasons || []}
          onChange={v => handleChange('cancellation_reasons', v)}
        />
      </div>

      {/* Late Cancel Message */}
      <div style={{
        border: '1px solid #e5e7eb', borderRadius: 12, padding: 16, marginBottom: 16, background: '#fff',
      }}>
        <label style={{ display: 'block', fontSize: 14, fontWeight: 600, marginBottom: 4, color: '#111827' }}>
          Late Cancellation Message
        </label>
        <p style={{ fontSize: 13, color: '#6b7280', marginTop: 0, marginBottom: 10 }}>
          Shown to users when cancelling within the minimum notice period.
        </p>
        <textarea
          value={policy.late_cancel_message || ''}
          onChange={e => handleChange('late_cancel_message', e.target.value)}
          rows={3}
          maxLength={2000}
          style={{
            width: '100%', padding: '8px 12px', borderRadius: 8,
            border: '1px solid #d1d5db', fontSize: 14, fontFamily: 'inherit',
            resize: 'vertical', boxSizing: 'border-box',
          }}
          placeholder="Message shown for late cancellations..."
        />
      </div>
    </div>
  );
}
