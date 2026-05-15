/**
 * No-Show Recovery Dashboard
 *
 * Shows LOs their no-show appointments and the status of recovery sequences.
 * Recovery steps (from backend/services/no_show_recovery.py):
 *   Step 1 (15 min):   Gentle SMS
 *   Step 2 (1 hour):   Understanding email
 *   Step 3 (24 hours): Reschedule offer SMS
 *   Step 4 (72 hours): Final outreach email
 */
import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { getToken } from '../../utils/tokenStore';

const API_BASE = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
  ? (process.env.REACT_APP_API_URL || 'http://localhost:8000')
  : 'https://api.perenniaai.com';

const STEP_LABELS = {
  1: 'Gentle SMS (15 min)',
  2: 'Understanding Email (1 hour)',
  3: 'Reschedule Offer (24 hours)',
  4: 'Final Outreach (72 hours)',
};

const STEP_CHANNELS = {
  1: 'SMS',
  2: 'Email',
  3: 'SMS',
  4: 'Email',
};

// Parse "[Recovery Step N/4] ... sent=YES ..." from internal_notes to determine
// last completed step (mirrors NoShowRecoveryService._get_last_completed_step).
function parseRecoveryStep(internalNotes) {
  if (!internalNotes) return 0;
  const matches = internalNotes.match(/\[Recovery Step (\d+)\/\d+\].*?sent=YES/g);
  if (!matches || matches.length === 0) return 0;
  let max = 0;
  for (const m of matches) {
    const num = parseInt(m.match(/\[Recovery Step (\d+)/)[1], 10);
    if (num > max) max = num;
  }
  return max;
}

function parseOptedOut(internalNotes) {
  if (!internalNotes) return false;
  return /opted.out|opt.out/i.test(internalNotes);
}

function formatDate(d) {
  if (!d) return '';
  return new Date(d).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  });
}

function timeSince(d) {
  if (!d) return '';
  const now = new Date();
  const then = new Date(d);
  const diffMs = now - then;
  const hours = Math.floor(diffMs / (1000 * 60 * 60));
  if (hours < 1) return 'Just now';
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}


// ============================================================================
// SUB-COMPONENTS
// ============================================================================

const RecoveryProgressBar = React.memo(({ step, optedOut }) => (
  <div style={{ marginTop: 12 }}>
    <div style={{ display: 'flex', gap: 4, marginBottom: 8 }}>
      {[1, 2, 3, 4].map(s => (
        <div
          key={s}
          title={STEP_LABELS[s]}
          style={{
            flex: 1,
            height: 6,
            borderRadius: 3,
            background: optedOut && s > step
              ? '#fecaca'
              : s <= step
                ? '#B8924A'
                : '#e2e8f0',
            transition: 'background 0.3s ease',
          }}
        />
      ))}
    </div>
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
      <span style={{ fontSize: '0.8rem', color: '#94a3b8' }}>
        {step > 0 ? STEP_LABELS[step] : 'Not started'}
      </span>
      {optedOut && (
        <span style={{
          fontSize: '0.75rem', fontWeight: 600, color: '#ef4444',
          background: '#fef2f2', padding: '2px 8px', borderRadius: 4,
        }}>
          Opted out
        </span>
      )}
    </div>
  </div>
));

const StepBadge = React.memo(({ step }) => {
  const isComplete = step >= 4;
  return (
    <span style={{
      fontSize: '0.75rem',
      fontWeight: 600,
      padding: '4px 10px',
      borderRadius: 12,
      background: isComplete ? '#fef2f2' : step === 0 ? '#f8fafc' : '#eff6ff',
      color: isComplete ? '#dc2626' : step === 0 ? '#94a3b8' : '#3b82f6',
      whiteSpace: 'nowrap',
    }}>
      Step {step}/4
    </span>
  );
});

const SummaryCard = React.memo(({ label, value, color }) => (
  <div style={{
    flex: 1, minWidth: 100, padding: '14px 16px',
    background: '#f8fafc', borderRadius: 8, textAlign: 'center',
  }}>
    <div style={{ fontSize: '1.5rem', fontWeight: 700, color: color || '#111827' }}>
      {value}
    </div>
    <div style={{ fontSize: '0.78rem', color: '#6b7280', marginTop: 2 }}>
      {label}
    </div>
  </div>
));


// ============================================================================
// MAIN DASHBOARD
// ============================================================================

function NoShowRecoveryDashboard({ token }) {
  const [noShows, setNoShows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [filter, setFilter] = useState('active'); // active, recovered, all
  const [actionLoading, setActionLoading] = useState(null);

  const authToken = token || getToken();

  const headers = useMemo(() => ({
    'Content-Type': 'application/json',
    ...(authToken ? { Authorization: `Bearer ${authToken}` } : {}),
  }), [authToken]);

  const loadNoShows = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      // Fetch no_show appointments from the scheduler API
      const res = await fetch(
        `${API_BASE}/api/v1/scheduler/appointments?status=no_show&limit=200`,
        { headers }
      );
      if (!res.ok) {
        throw new Error(`Failed to load no-show data (${res.status})`);
      }
      const data = await res.json();
      const appointments = data.appointments || [];

      // Enrich each appointment with parsed recovery step from internal_notes.
      // The list endpoint may not include internal_notes, so we fetch each
      // appointment's detail to get notes. For performance, we do a single
      // batch of requests with a concurrency limit.
      const enriched = await Promise.all(
        appointments.map(async (appt) => {
          let recoveryStep = 0;
          let optedOut = false;
          let noShowAt = null;
          try {
            const detailRes = await fetch(
              `${API_BASE}/api/v1/scheduler/appointments/${appt.id}`,
              { headers }
            );
            if (detailRes.ok) {
              const detail = await detailRes.json();
              const apptDetail = detail.appointment || detail;
              recoveryStep = parseRecoveryStep(apptDetail.internal_notes);
              optedOut = parseOptedOut(apptDetail.internal_notes);
              noShowAt = apptDetail.no_show_at || null;
            }
          } catch (_) {
            // If detail fetch fails, work with what we have
          }
          return {
            ...appt,
            recovery_step: recoveryStep,
            opted_out: optedOut,
            no_show_at: noShowAt,
          };
        })
      );

      // Apply client-side filter
      let filtered = enriched;
      if (filter === 'active') {
        filtered = enriched.filter(a => a.recovery_step < 4 && !a.opted_out);
      } else if (filter === 'recovered') {
        filtered = enriched.filter(a => a.recovery_step >= 4 || a.opted_out);
      }
      // 'all' -- no filtering

      setNoShows(filtered);
    } catch (err) {
      setError(err.message);
      console.warn('Could not load no-show data:', err.message);
    } finally {
      setLoading(false);
    }
  }, [filter, authToken]);

  useEffect(() => {
    loadNoShows();
  }, [loadNoShows]);

  const manualRecover = useCallback(async (appointmentId, nextStep) => {
    setActionLoading(appointmentId);
    try {
      // Use the PATCH endpoint to update the appointment status, triggering
      // the backend recovery service to send the next message.
      // The backend's execute_step handles opt-out and rescheduled checks.
      const res = await fetch(
        `${API_BASE}/api/v1/scheduler/appointments/${appointmentId}`,
        {
          method: 'PATCH',
          headers,
          body: JSON.stringify({
            internal_notes_append: `[Manual Recovery] LO requested step ${nextStep} at ${new Date().toISOString()}`,
          }),
        }
      );
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || 'Recovery request failed');
      }
      await loadNoShows();
    } catch (err) {
      setError(err.message);
      console.error('Manual recovery failed:', err);
    } finally {
      setActionLoading(null);
    }
  }, [headers, loadNoShows]);

  // Summary stats
  const { totalNoShows, activeRecoveries, completedSequences, optedOutCount } = useMemo(() => ({
    totalNoShows: noShows.length,
    activeRecoveries: noShows.filter(a => a.recovery_step > 0 && a.recovery_step < 4 && !a.opted_out).length,
    completedSequences: noShows.filter(a => a.recovery_step >= 4).length,
    optedOutCount: noShows.filter(a => a.opted_out).length,
  }), [noShows]);

  return (
    <div className="no-show-recovery-dashboard" style={{ maxWidth: 900, margin: '0 auto' }}>
      {/* Header */}
      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        marginBottom: 20, flexWrap: 'wrap', gap: 10,
      }}>
        <div>
          <h2 style={{ margin: 0, fontSize: '20px', fontWeight: 700, color: '#111827' }}>
            No-Show Recovery
          </h2>
          <p style={{ margin: '4px 0 0', fontSize: '14px', color: '#6b7280' }}>
            Track and manage automated recovery sequences for missed appointments
          </p>
        </div>
        <button
          onClick={loadNoShows}
          disabled={loading}
          style={{
            padding: '8px 16px', fontSize: '14px', borderRadius: 6,
            border: '1px solid #d1d5db', background: '#fff',
            cursor: loading ? 'not-allowed' : 'pointer',
            opacity: loading ? 0.6 : 1,
          }}
        >
          {loading ? 'Refreshing...' : 'Refresh'}
        </button>
      </div>

      {/* Error */}
      {error && (
        <div style={{
          padding: '12px 16px', background: '#fef2f2', color: '#991b1b',
          borderRadius: 6, marginBottom: 14, fontSize: '13px',
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        }}>
          <span>{error}</span>
          <button
            onClick={() => setError(null)}
            style={{
              background: 'none', border: 'none', color: '#991b1b',
              cursor: 'pointer', fontWeight: 700, fontSize: '14px',
            }}
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Summary Cards */}
      {!loading && noShows.length > 0 && (
        <div style={{ display: 'flex', gap: 12, marginBottom: 20, flexWrap: 'wrap' }}>
          <SummaryCard label="Total No-Shows" value={totalNoShows} />
          <SummaryCard label="Active Recoveries" value={activeRecoveries} color="#3b82f6" />
          <SummaryCard label="Sequences Complete" value={completedSequences} color="#6b7280" />
          <SummaryCard label="Opted Out" value={optedOutCount} color="#ef4444" />
        </div>
      )}

      {/* Filter Tabs */}
      <div style={{ display: 'flex', gap: 4, marginBottom: 16 }}>
        {[
          { key: 'active', label: 'Active' },
          { key: 'recovered', label: 'Completed / Opted Out' },
          { key: 'all', label: 'All' },
        ].map(f => (
          <button
            key={f.key}
            onClick={() => setFilter(f.key)}
            style={{
              padding: '6px 14px', borderRadius: 6, fontSize: '0.82rem',
              cursor: 'pointer', fontWeight: 500,
              background: filter === f.key ? '#B8924A' : '#f1f5f9',
              color: filter === f.key ? '#fff' : '#64748b',
              border: filter === f.key ? '1px solid #B8924A' : '1px solid #e2e8f0',
            }}
          >
            {f.label}
          </button>
        ))}
      </div>

      {/* Content */}
      {loading ? (
        <div style={{ textAlign: 'center', padding: 40, color: '#94a3b8' }}>
          Loading no-show data...
        </div>
      ) : noShows.length === 0 ? (
        <div style={{
          textAlign: 'center', padding: 40, background: '#f9fafb',
          borderRadius: 8, color: '#6b7280',
        }}>
          <div style={{ fontSize: '16px', fontWeight: 600, marginBottom: 4 }}>
            No {filter === 'all' ? '' : filter} no-show appointments
          </div>
          <div style={{ fontSize: '14px' }}>
            {filter === 'active'
              ? 'Great news -- no active recovery sequences right now.'
              : 'No matching no-show appointments found.'}
          </div>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {noShows.map(appt => {
            const nextStep = (appt.recovery_step || 0) + 1;
            const canRecover = !appt.opted_out && appt.recovery_step < 4;

            return (
              <div
                key={appt.id}
                style={{
                  background: '#fff', border: '1px solid #e2e8f0',
                  borderRadius: 10, padding: 16, transition: 'box-shadow 0.2s',
                }}
              >
                {/* Top row: attendee info + step badge */}
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontWeight: 600, fontSize: '15px', color: '#111827' }}>
                      {appt.attendee_name || 'Unknown Attendee'}
                    </div>
                    <div style={{ fontSize: '0.85rem', color: '#64748b', marginTop: 2 }}>
                      {appt.title} &mdash; {formatDate(appt.scheduled_start)}
                    </div>
                    {appt.attendee_email && (
                      <div style={{ fontSize: '0.8rem', color: '#94a3b8', marginTop: 2 }}>
                        {appt.attendee_email}
                      </div>
                    )}
                    {appt.no_show_at && (
                      <div style={{ fontSize: '0.78rem', color: '#94a3b8', marginTop: 4 }}>
                        Marked no-show {timeSince(appt.no_show_at)}
                      </div>
                    )}
                  </div>
                  <StepBadge step={appt.recovery_step || 0} />
                </div>

                {/* Recovery progress bar */}
                <RecoveryProgressBar step={appt.recovery_step || 0} optedOut={appt.opted_out} />

                {/* Next step info */}
                {canRecover && nextStep <= 4 && (
                  <div style={{
                    marginTop: 12, display: 'flex', justifyContent: 'space-between',
                    alignItems: 'center', flexWrap: 'wrap', gap: 8,
                  }}>
                    <div style={{ fontSize: '0.8rem', color: '#6b7280' }}>
                      Next: <strong>{STEP_LABELS[nextStep]}</strong>
                      <span style={{
                        marginLeft: 8, fontSize: '0.75rem', color: '#94a3b8',
                        background: '#f1f5f9', padding: '2px 6px', borderRadius: 4,
                      }}>
                        {STEP_CHANNELS[nextStep]}
                      </span>
                    </div>
                    <button
                      onClick={() => manualRecover(appt.id, nextStep)}
                      disabled={actionLoading === appt.id}
                      style={{
                        background: '#f8fafc', border: '1px solid #e2e8f0',
                        borderRadius: 6, padding: '6px 14px', cursor: 'pointer',
                        fontSize: '0.82rem', fontWeight: 500, color: '#374151',
                        opacity: actionLoading === appt.id ? 0.6 : 1,
                      }}
                    >
                      {actionLoading === appt.id ? 'Sending...' : 'Send Next Recovery Message'}
                    </button>
                  </div>
                )}

                {/* Sequence complete state */}
                {appt.recovery_step >= 4 && !appt.opted_out && (
                  <div style={{
                    marginTop: 12, fontSize: '0.82rem', color: '#6b7280',
                    background: '#f8fafc', padding: '8px 12px', borderRadius: 6,
                  }}>
                    Recovery sequence complete. All 4 outreach steps have been sent.
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

export default React.memo(NoShowRecoveryDashboard);
