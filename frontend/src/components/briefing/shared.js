/**
 * Shared briefing helpers and sub-components.
 * Used by both MorningBriefingCard (dashboard) and BriefingPage (full page).
 */
import React from 'react';

// ---------------------------------------------------------------------------
// Pure helpers
// ---------------------------------------------------------------------------

export function healthLabel(level) {
  if (level === 'red') return 'Needs Attention';
  if (level === 'yellow') return 'Monitor';
  return 'On Track';
}

export function formatVolume(v) {
  if (!v) return '$0';
  if (v >= 1_000_000) return `$${(v / 1_000_000).toFixed(1)}M`;
  if (v >= 1_000) return `$${(v / 1_000).toFixed(0)}K`;
  return `$${v.toFixed(0)}`;
}

// ---------------------------------------------------------------------------
// Shared section components
// maxItems: optional cap on list length (card uses 5, page passes undefined = no cap)
// ---------------------------------------------------------------------------

export function SectionHeader({ title, icon, count, isOpen, onToggle }) {
  return (
    <button className="briefing-section-header" onClick={onToggle} type="button">
      <span className="section-icon">{icon}</span>
      <span className="section-title">{title}</span>
      {count !== undefined && count > 0 && (
        <span className="section-badge">{count}</span>
      )}
      <span className="section-chevron">{isOpen ? '▾' : '▸'}</span>
    </button>
  );
}

export function PipelineSection({ pipeline, maxStages }) {
  if (!pipeline || pipeline.active_count === 0) return null;
  const byStage = pipeline.by_stage || {};
  const stageEntries = maxStages
    ? Object.entries(byStage).slice(0, maxStages)
    : Object.entries(byStage);
  return (
    <div className="section-content">
      <div className="metric-row">
        <div className="metric-item">
          <span className="metric-value">{pipeline.active_count}</span>
          <span className="metric-label">Active Loans</span>
        </div>
        <div className="metric-item">
          <span className="metric-value">{formatVolume(pipeline.total_volume)}</span>
          <span className="metric-label">Pipeline Volume</span>
        </div>
        <div className="metric-item">
          <span className="metric-value">{pipeline.closing_soon || 0}</span>
          <span className="metric-label">Closing Soon</span>
        </div>
      </div>
      {stageEntries.length > 0 && (
        <div className="stage-pills">
          {stageEntries.map(([stage, count]) => (
            <span className="stage-pill" key={stage}>
              {stage.replace(/_/g, ' ')} <strong>{count}</strong>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

export function AtRiskSection({ items, maxItems }) {
  if (!items || items.length === 0) return <p className="section-empty">No at-risk loans</p>;
  const displayed = maxItems ? items.slice(0, maxItems) : items;
  return (
    <div className="section-content">
      <ul className="briefing-list at-risk-list">
        {displayed.map((loan, i) => (
          <li key={loan.loan_id || i}>
            <a href={`/loans/${loan.loan_id}`} className="item-link">
              <strong>{loan.borrower}</strong>
            </a>
            <span className="item-detail">{loan.reason}</span>
            {loan.days_in_stage && (
              <span className="item-badge warn">{Math.round(loan.days_in_stage)}d</span>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

export function ConditionsSection({ conditions, maxItems }) {
  if (!conditions || conditions.length === 0) return <p className="section-empty">No open conditions</p>;
  const pastDueCount = conditions.filter(c => c.past_due).length;
  const displayed = maxItems ? conditions.slice(0, maxItems) : conditions;
  return (
    <div className="section-content">
      {pastDueCount > 0 && (
        <div className="past-due-banner">{pastDueCount} past due</div>
      )}
      <ul className="briefing-list conditions-list">
        {displayed.map((c, i) => (
          <li key={i} className={c.past_due ? 'past-due' : ''}>
            <span className={`severity-dot ${c.severity || 'medium'}`} />
            <span className="item-text">{c.title}</span>
            {c.loan_number && <span className="item-loan">#{c.loan_number}</span>}
          </li>
        ))}
      </ul>
    </div>
  );
}

export function StaleLeadsSection({ leads, maxItems }) {
  if (!leads || leads.length === 0) return <p className="section-empty">No stale leads</p>;
  const displayed = maxItems ? leads.slice(0, maxItems) : leads;
  return (
    <div className="section-content">
      <ul className="briefing-list leads-list">
        {displayed.map((lead, i) => (
          <li key={lead.lead_id || i}>
            <a href={`/leads/${lead.lead_id}`} className="item-link">
              <strong>{lead.name}</strong>
            </a>
            {lead.score && <span className="item-badge score">Score {lead.score}</span>}
            <span className="item-detail">{Math.round(lead.days_silent || 0)} days silent</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function AppointmentsSection({ appointments }) {
  if (!appointments || appointments.length === 0) return <p className="section-empty">No appointments today</p>;
  return (
    <div className="section-content">
      <ul className="briefing-list appointments-list">
        {appointments.map((appt, i) => (
          <li key={appt.id || i}>
            <span className="appt-time">{appt.time}</span>
            <span className="item-text">{appt.attendee}</span>
            <span className="item-detail">{appt.type}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function YesterdaySection({ yesterday }) {
  if (!yesterday) return null;
  const { funded, new_loans, conversions } = yesterday;
  if (!funded && !new_loans && !conversions) return <p className="section-empty">No activity yesterday</p>;
  return (
    <div className="section-content">
      <div className="metric-row">
        {funded > 0 && (
          <div className="metric-item">
            <span className="metric-value">{funded}</span>
            <span className="metric-label">Funded</span>
          </div>
        )}
        {new_loans > 0 && (
          <div className="metric-item">
            <span className="metric-value">{new_loans}</span>
            <span className="metric-label">New Loans</span>
          </div>
        )}
        {conversions > 0 && (
          <div className="metric-item">
            <span className="metric-value">{conversions}</span>
            <span className="metric-label">Conversions</span>
          </div>
        )}
      </div>
    </div>
  );
}

export function TeamSection({ team, level }) {
  if (!team) return null;

  if (level === 'manager' && team.members) {
    return (
      <div className="section-content">
        <table className="briefing-table">
          <thead>
            <tr><th>Name</th><th>Loans</th><th>Volume</th><th>Health</th></tr>
          </thead>
          <tbody>
            {team.members.map((m, i) => (
              <tr key={i}>
                <td><span className={`health-dot ${m.health}`} /> {m.name}</td>
                <td>{m.loan_count}</td>
                <td>{formatVolume(m.volume)}</td>
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
                <li key={i}><strong>{item.user_name}</strong> -- {item.issue}</li>
              ))}
            </ul>
          </div>
        )}
      </div>
    );
  }

  if (level === 'leadership' && team.branches) {
    return (
      <div className="section-content">
        {team.org_snapshot && (
          <div className="metric-row">
            <div className="metric-item">
              <span className="metric-value">{team.org_snapshot.active_count}</span>
              <span className="metric-label">Active Loans</span>
            </div>
            <div className="metric-item">
              <span className="metric-value">{formatVolume(team.org_snapshot.total_volume)}</span>
              <span className="metric-label">Pipeline</span>
            </div>
            <div className="metric-item">
              <span className="metric-value">{team.org_snapshot.funded_this_week}</span>
              <span className="metric-label">Funded This Week</span>
            </div>
          </div>
        )}
        <table className="briefing-table">
          <thead>
            <tr><th>Branch</th><th>Loans</th><th>Volume</th><th>Health</th></tr>
          </thead>
          <tbody>
            {team.branches.map((b, i) => (
              <tr key={i}>
                <td><span className={`health-dot ${b.health}`} /> {b.name}</td>
                <td>{b.loan_count}</td>
                <td>{formatVolume(b.volume)}</td>
                <td>{b.health}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }

  return null;
}
