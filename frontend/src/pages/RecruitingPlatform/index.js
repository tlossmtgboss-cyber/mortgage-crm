import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { getToken } from '../../utils/tokenStore';
import { API_BASE_URL } from '../../services/api';
import RecruitingPlatformLayout from './RecruitingPlatformLayout';
import './RecruitingPlatform.css';

export default function RecruitingPlatform() {
  const navigate = useNavigate();
  const [stats, setStats] = useState(null);
  const [upcoming, setUpcoming] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      const token = getToken();
      const headers = { Authorization: `Bearer ${token}` };
      const today = new Date();

      try {
        const [interviewsRes, milestonesRes] = await Promise.allSettled([
          fetch(
            `${API_BASE_URL}/api/v1/recruit-calendar/interviews/calendar?year=${today.getFullYear()}&month=${today.getMonth() + 1}`,
            { headers }
          ).then(r => r.json()),
          fetch(
            `${API_BASE_URL}/api/v1/recruit-calendar/milestones/upcoming?days=7`,
            { headers }
          ).then(r => r.json()),
        ]);

        const evts = interviewsRes.status === 'fulfilled' ? (interviewsRes.value.events || []) : [];
        const mils = milestonesRes.status === 'fulfilled' ? milestonesRes.value : {};

        setStats({
          interviews_this_month: evts.length,
          milestones_overdue: (mils.overdue || []).length,
          milestones_this_week: (mils.this_week || []).length,
        });

        const now = new Date();
        const soon = evts
          .filter(e => e.start && new Date(e.start) >= now)
          .sort((a, b) => new Date(a.start) - new Date(b.start))
          .slice(0, 5);
        setUpcoming(soon);
      } catch (e) {
        console.error('Dashboard load error:', e);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  return (
    <RecruitingPlatformLayout>
      <div className="rp-page-header">
        <div>
          <div className="rp-page-title">Recruiting Platform</div>
          <div className="rp-page-sub">Interview scheduling, milestones, and candidate pipeline</div>
        </div>
        <button
          className="rp-btn rp-btn--primary"
          onClick={() => navigate('/master-manager')}
        >
          Open Pipeline
        </button>
      </div>

      {loading ? (
        <div className="rp-loading">Loading dashboard...</div>
      ) : (
        <>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 16, marginBottom: 24 }}>
            {[
              { label: 'Interviews This Month', value: stats?.interviews_this_month ?? '—', action: () => navigate('/recruiting/interviews') },
              { label: 'Milestones Overdue', value: stats?.milestones_overdue ?? '—', warn: (stats?.milestones_overdue || 0) > 0, action: () => navigate('/recruiting/milestones') },
              { label: 'Due This Week', value: stats?.milestones_this_week ?? '—', action: () => navigate('/recruiting/milestones') },
            ].map(stat => (
              <div
                key={stat.label}
                className="rp-card"
                style={{ cursor: 'pointer', borderColor: stat.warn ? '#fca5a5' : undefined }}
                onClick={stat.action}
              >
                <div style={{ fontSize: 28, fontWeight: 700, color: stat.warn ? '#b91c1c' : '#1a1f2e', marginBottom: 4 }}>
                  {stat.value}
                </div>
                <div style={{ fontSize: 12, color: '#6b7280' }}>{stat.label}</div>
              </div>
            ))}
          </div>

          <div className="rp-card">
            <div className="rp-card-title">Upcoming Interviews</div>
            {upcoming.length === 0 ? (
              <div className="rp-empty">No upcoming interviews this month.</div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {upcoming.map(ev => (
                  <div
                    key={ev.id}
                    style={{
                      display: 'flex', alignItems: 'center', gap: 12, padding: '10px 12px',
                      background: '#f9fafb', borderRadius: 8, cursor: 'pointer',
                    }}
                    onClick={() => navigate(`/recruiting/interviews/${ev.id}`)}
                  >
                    <div
                      style={{
                        width: 8, height: 8, borderRadius: '50%', flexShrink: 0,
                        background: ev.status === 'completed' ? '#22c55e' : '#B8924A',
                      }}
                    />
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontSize: 13, fontWeight: 600, color: '#111827', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                        {ev.title}
                      </div>
                      <div style={{ fontSize: 11, color: '#9ca3af' }}>
                        {ev.start ? new Date(ev.start).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : '—'}
                      </div>
                    </div>
                    <div style={{ fontSize: 11, color: '#6b7280', flexShrink: 0 }}>
                      {ev.interview_type?.replace('_', ' ')}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginTop: 0 }}>
            <div
              className="rp-card"
              style={{ cursor: 'pointer' }}
              onClick={() => navigate('/recruiting/interviews')}
            >
              <div className="rp-card-title">Interview Calendar</div>
              <div style={{ fontSize: 13, color: '#6b7280', lineHeight: 1.5 }}>
                View all scheduled interviews, create new ones, and send candidate booking links.
              </div>
              <div style={{ marginTop: 12 }}>
                <span style={{ fontSize: 12, color: '#B8924A', fontWeight: 600 }}>Open →</span>
              </div>
            </div>

            <div
              className="rp-card"
              style={{ cursor: 'pointer' }}
              onClick={() => navigate('/recruiting/milestones')}
            >
              <div className="rp-card-title">Milestone Tracker</div>
              <div style={{ fontSize: 13, color: '#6b7280', lineHeight: 1.5 }}>
                Track start dates, 30/90-day check-ins, license renewals, and onboarding milestones.
              </div>
              <div style={{ marginTop: 12 }}>
                <span style={{ fontSize: 12, color: '#B8924A', fontWeight: 600 }}>Open →</span>
              </div>
            </div>
          </div>
        </>
      )}
    </RecruitingPlatformLayout>
  );
}

export { default as InterviewCalendar } from './InterviewCalendar';
export { default as MilestonesBoard } from './MilestonesBoard';
export { default as CandidateBookingPage } from './CandidateBookingPage';
