import React, { useState, useEffect, useCallback } from 'react';
import api from '../../services/api';
import './MorningBriefingCard.css';

export default function MorningBriefingCard() {
  const [briefing, setBriefing] = useState(null);
  const [loading, setLoading] = useState(true);
  const [collapsed, setCollapsed] = useState(() => {
    return localStorage.getItem('briefing_collapsed') === 'true';
  });
  const [dismissed, setDismissed] = useState(() => {
    const d = localStorage.getItem('briefing_dismissed_date');
    return d === new Date().toISOString().split('T')[0];
  });

  const fetchBriefing = useCallback(async () => {
    try {
      const res = await api.get('/api/v1/briefing/today', {
        validateStatus: (status) => status === 200 || status === 204,
      });
      if (res.status === 204) {
        // No briefing yet — nothing to display
      } else if (res.data && res.data.status === 'delivered') {
        setBriefing(res.data);
        // Mark as viewed
        if (!res.data.viewed_in_app) {
          api.post(`/api/v1/briefing/${res.data.id}/viewed`).catch(() => {});
        }
      }
    } catch (err) {
      // Silent failure — briefings are supplementary
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!dismissed) fetchBriefing();
    else setLoading(false);
  }, [dismissed, fetchBriefing]);

  const toggleCollapse = () => {
    const next = !collapsed;
    setCollapsed(next);
    localStorage.setItem('briefing_collapsed', String(next));
  };

  const dismiss = () => {
    setDismissed(true);
    localStorage.setItem('briefing_dismissed_date', new Date().toISOString().split('T')[0]);
  };

  if (loading || dismissed || !briefing) return null;

  const { ai_narrative, pipeline, at_risk, stale_leads, appointments, team, briefing_level } = briefing;

  return (
    <div className="morning-briefing-card">
      <div className="briefing-header" onClick={toggleCollapse}>
        <div className="briefing-title">
          <span className="briefing-icon">&#9728;</span>
          <h3>Morning Briefing</h3>
          <span className="briefing-date">{briefing.briefing_date}</span>
        </div>
        <div className="briefing-actions">
          <button className="briefing-collapse-btn" title={collapsed ? 'Expand' : 'Collapse'}>
            {collapsed ? '▸' : '▾'}
          </button>
          <button className="briefing-dismiss-btn" onClick={(e) => { e.stopPropagation(); dismiss(); }} title="Dismiss for today">
            ✕
          </button>
        </div>
      </div>

      {!collapsed && (
        <div className="briefing-body">
          {/* AI Priorities */}
          {ai_narrative && (
            <div className="briefing-section priorities">
              <h4>Top 3 Priorities</h4>
              <div className="priorities-text">{ai_narrative}</div>
            </div>
          )}

          {/* Pipeline */}
          {pipeline && pipeline.active_count > 0 && (
            <div className="briefing-section">
              <h4>Pipeline</h4>
              <div className="briefing-stats">
                <span><strong>{pipeline.active_count}</strong> active</span>
                <span><strong>${(pipeline.total_volume / 1000000).toFixed(1)}M</strong> volume</span>
                <span><strong>{pipeline.closing_soon}</strong> closing soon</span>
              </div>
            </div>
          )}

          {/* At-Risk */}
          {at_risk && at_risk.length > 0 && (
            <div className="briefing-section at-risk">
              <h4>&#9888; At-Risk ({at_risk.length})</h4>
              <ul>
                {at_risk.slice(0, 3).map((loan, i) => (
                  <li key={i}>
                    <a href={`/loans/${loan.loan_id}`}><strong>{loan.borrower}</strong></a>
                    {' — '}{loan.reason}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Stale Leads */}
          {stale_leads && stale_leads.length > 0 && (
            <div className="briefing-section stale-leads">
              <h4>&#128293; Leads Going Cold ({stale_leads.length})</h4>
              <ul>
                {stale_leads.slice(0, 3).map((lead, i) => (
                  <li key={i}>
                    <a href={`/leads/${lead.lead_id}`}><strong>{lead.name}</strong></a>
                    {' (score '}{lead.score}{') — '}{lead.days_silent} days quiet
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Appointments */}
          {appointments && appointments.length > 0 && (
            <div className="briefing-section">
              <h4>&#128197; Today ({appointments.length})</h4>
              <ul>
                {appointments.map((appt, i) => (
                  <li key={i}><strong>{appt.time}</strong> — {appt.attendee}, {appt.type}</li>
                ))}
              </ul>
            </div>
          )}

          {/* Team Section (Manager) */}
          {briefing_level === 'manager' && team && team.members && (
            <div className="briefing-section team-section">
              <h4>Your Team</h4>
              <table className="briefing-table">
                <thead>
                  <tr><th>Name</th><th>Loans</th><th>Volume</th><th>Health</th></tr>
                </thead>
                <tbody>
                  {team.members.map((m, i) => (
                    <tr key={i}>
                      <td><span className={`health-dot ${m.health}`}></span> {m.name}</td>
                      <td>{m.loan_count}</td>
                      <td>${(m.volume / 1000).toFixed(0)}K</td>
                      <td>{m.health}{m.at_risk_count > 0 ? ` · ${m.at_risk_count} at-risk` : ''}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {team.attention_items && team.attention_items.length > 0 && (
                <div className="attention-items">
                  <h5>Attention Needed</h5>
                  <ul>
                    {team.attention_items.map((item, i) => (
                      <li key={i}><strong>{item.user_name}</strong> — {item.issue}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}

          {/* Org Section (Leadership) */}
          {briefing_level === 'leadership' && team && team.branches && (
            <div className="briefing-section org-section">
              <h4>Organization Overview</h4>
              {team.org_snapshot && (
                <div className="briefing-stats">
                  <span><strong>{team.org_snapshot.active_count}</strong> active loans</span>
                  <span><strong>${(team.org_snapshot.total_volume / 1000000).toFixed(1)}M</strong> pipeline</span>
                  <span><strong>{team.org_snapshot.funded_this_week}</strong> funded this week</span>
                </div>
              )}
              <table className="briefing-table">
                <thead>
                  <tr><th>Branch</th><th>Loans</th><th>Volume</th><th>Health</th></tr>
                </thead>
                <tbody>
                  {team.branches.map((b, i) => (
                    <tr key={i}>
                      <td><span className={`health-dot ${b.health}`}></span> {b.name}</td>
                      <td>{b.loan_count}</td>
                      <td>${(b.volume / 1000000).toFixed(1)}M</td>
                      <td>{b.health}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
