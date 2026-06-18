import React, { useState, useEffect, useCallback } from 'react';
import { getToken } from '../../utils/tokenStore';
import { API_BASE_URL } from '../../services/api';
import RecruitingPlatformLayout from './RecruitingPlatformLayout';
import './RecruitingPlatform.css';

const MILESTONE_LABELS = {
  start_date: 'Start Date',
  '30_day_checkin': '30-Day Check-In',
  '90_day_checkin': '90-Day Check-In',
  license_renewal: 'License Renewal',
  background_check_due: 'Background Check Due',
  onboarding_complete: 'Onboarding Complete',
  probation_end: 'Probation End',
  custom: 'Custom',
};

function MilestoneCard({ item, onComplete, onEdit }) {
  const [completing, setCompleting] = useState(false);

  const handleComplete = async () => {
    setCompleting(true);
    await onComplete(item.id);
    setCompleting(false);
  };

  return (
    <div className="rp-milestone-card">
      <div className="rp-milestone-card-name">
        {item.candidate_name || `Candidate #${item.candidate_id}`}
      </div>
      <div className="rp-milestone-card-type">
        {MILESTONE_LABELS[item.milestone_type] || item.milestone_type}
      </div>
      {item.scheduled_date && (
        <div className="rp-milestone-card-date">
          {new Date(item.scheduled_date).toLocaleDateString('en-US', {
            month: 'short', day: 'numeric', year: 'numeric',
          })}
        </div>
      )}
      {item.notes && (
        <div style={{ fontSize: 11, color: '#9ca3af', marginTop: 4 }}>{item.notes}</div>
      )}
      <div className="rp-milestone-card-actions">
        <button
          className="rp-btn-xs rp-btn-xs--green"
          onClick={handleComplete}
          disabled={completing}
        >
          {completing ? '...' : 'Complete'}
        </button>
      </div>
    </div>
  );
}

export default function MilestonesBoard() {
  const [data, setData] = useState({ overdue: [], this_week: [], later: [] });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [days, setDays] = useState(14);

  const fetchMilestones = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const token = getToken();
      const res = await fetch(
        `${API_BASE_URL}/api/v1/recruit-calendar/milestones/upcoming?days=${days}`,
        { headers: { Authorization: `Bearer ${token}` } }
      );
      if (!res.ok) throw new Error('Failed to load milestones');
      setData(await res.json());
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [days]);

  useEffect(() => { fetchMilestones(); }, [fetchMilestones]);

  const handleComplete = async (milestoneId) => {
    try {
      const token = getToken();
      await fetch(
        `${API_BASE_URL}/api/v1/recruit-calendar/milestones/${milestoneId}/complete`,
        { method: 'POST', headers: { Authorization: `Bearer ${token}` } }
      );
      fetchMilestones();
    } catch (e) {
      console.error('Complete milestone error:', e);
    }
  };

  const totalCount =
    (data.overdue?.length || 0) +
    (data.this_week?.length || 0) +
    (data.later?.length || 0);

  const columns = [
    { key: 'overdue', label: 'Overdue', modifier: 'overdue', items: data.overdue || [] },
    { key: 'this_week', label: 'This Week', modifier: 'this-week', items: data.this_week || [] },
    { key: 'later', label: 'Coming Up', modifier: 'later', items: data.later || [] },
  ];

  return (
    <RecruitingPlatformLayout>
      <div className="rp-page-header">
        <div>
          <div className="rp-page-title">Milestones</div>
          <div className="rp-page-sub">
            {totalCount} upcoming milestones in the next{' '}
            <select
              value={days}
              onChange={e => setDays(Number(e.target.value))}
              style={{ border: 'none', background: 'none', color: '#B8924A', fontWeight: 600, cursor: 'pointer', fontSize: 13 }}
            >
              <option value={7}>7 days</option>
              <option value={14}>14 days</option>
              <option value={30}>30 days</option>
              <option value={60}>60 days</option>
            </select>
          </div>
        </div>
      </div>

      {error && <div className="rp-error">{error}</div>}

      {loading ? (
        <div className="rp-loading">Loading milestones...</div>
      ) : totalCount === 0 ? (
        <div className="rp-card">
          <div className="rp-empty">No upcoming milestones — all caught up.</div>
        </div>
      ) : (
        <div className="rp-milestone-board">
          {columns.map(col => (
            <div key={col.key} className="rp-milestone-col">
              <div className={`rp-milestone-col-header rp-milestone-col-header--${col.modifier}`}>
                {col.label}
                <span className="rp-milestone-badge">{col.items.length}</span>
              </div>
              <div className="rp-milestone-cards">
                {col.items.length === 0 ? (
                  <div className="rp-empty" style={{ padding: '20px 0' }}>None</div>
                ) : (
                  col.items.map(item => (
                    <MilestoneCard
                      key={item.id}
                      item={item}
                      onComplete={handleComplete}
                    />
                  ))
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </RecruitingPlatformLayout>
  );
}
