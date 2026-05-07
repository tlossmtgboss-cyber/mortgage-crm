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

export function DashboardSnapshotSection({ snapshot, maxIssues }) {
  if (!snapshot) return null;

  const { production, pipeline_stats, efficiency, profitability, loan_issues, bottlenecks, team_stats, stage_performance } = snapshot;

  return (
    <div className="section-content dashboard-snapshot">
      {/* Production */}
      {production && (
        <div className="snapshot-subsection">
          <h5 className="snapshot-label">Production</h5>
          <div className="production-gauge">
            <div className="gauge-main">
              <span className="gauge-value">{production.monthlyActual || 0}</span>
              <span className="gauge-separator">/</span>
              <span className="gauge-goal">{production.monthlyGoal || 0}</span>
              <span className="gauge-label">this month</span>
            </div>
            <div className="gauge-bar">
              <div className="gauge-fill" style={{ width: `${Math.min(production.monthlyProgress || 0, 100)}%` }} />
            </div>
            <div className="gauge-secondary">
              <span>Daily: {production.dailyActual || 0}/{production.dailyGoal || 0}</span>
              <span>Weekly: {production.weeklyActual || 0}/{production.weeklyGoal || 0}</span>
              <span>Annual: {production.annualActual || 0}/{production.annualGoal || 0}</span>
            </div>
          </div>
        </div>
      )}

      {/* Pipeline */}
      {pipeline_stats && pipeline_stats.length > 0 && (
        <div className="snapshot-subsection">
          <h5 className="snapshot-label">Pipeline</h5>
          <div className="pipeline-compact">
            {pipeline_stats.filter(s => s.count > 0).map(s => (
              <div key={s.id} className="pipeline-item">
                <span className="pipeline-name">{s.name}</span>
                <span className="pipeline-count">{s.count}</span>
                {s.volume ? <span className="pipeline-vol">{formatVolume(s.volume)}</span> : null}
                {s.alerts > 0 && <span className="pipeline-alert">{s.alerts} {s.alert_text}</span>}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Efficiency */}
      {efficiency && (
        <div className="snapshot-subsection">
          <h5 className="snapshot-label">Efficiency</h5>
          <div className="metric-row">
            <div className="metric-item metric-score">
              <span className={`metric-value score-${efficiency.overallScore >= 70 ? 'good' : efficiency.overallScore >= 40 ? 'warn' : 'bad'}`}>
                {efficiency.overallScore}
              </span>
              <span className="metric-label">Score</span>
            </div>
            <div className="metric-item">
              <span className="metric-value">{efficiency.pullThroughRate}%</span>
              <span className="metric-label">Pull-Through</span>
            </div>
            <div className="metric-item">
              <span className="metric-value">{efficiency.avgTimeToClose}d</span>
              <span className="metric-label">Avg Close</span>
            </div>
            <div className="metric-item">
              <span className="metric-value">{efficiency.loansFallingBehind}</span>
              <span className="metric-label">Behind</span>
            </div>
          </div>
        </div>
      )}

      {/* Profitability */}
      {profitability && profitability.funded_ytd > 0 && (
        <div className="snapshot-subsection">
          <h5 className="snapshot-label">Profitability</h5>
          <div className="metric-row">
            <div className="metric-item">
              <span className="metric-value">{profitability.funded_ytd}</span>
              <span className="metric-label">Funded YTD</span>
            </div>
            <div className="metric-item">
              <span className="metric-value">{formatVolume(profitability.total_volume)}</span>
              <span className="metric-label">Volume</span>
            </div>
            <div className="metric-item">
              <span className="metric-value">{formatVolume(profitability.avg_loan_size)}</span>
              <span className="metric-label">Avg Size</span>
            </div>
            <div className="metric-item">
              <span className="metric-value">{profitability.gain_on_sale_display}</span>
              <span className="metric-label">Gain on Sale</span>
            </div>
          </div>
        </div>
      )}

      {/* Loan Issues */}
      {loan_issues && loan_issues.length > 0 && (
        <div className="snapshot-subsection">
          <h5 className="snapshot-label">Loan Issues ({loan_issues.length})</h5>
          <ul className="briefing-list">
            {loan_issues.slice(0, maxIssues || 10).map(issue => (
              <li key={issue.id}>
                <a href={`/loans/${issue.id}`} className="item-link"><strong>{issue.borrower_name}</strong></a>
                <span className="item-detail">{issue.issue}</span>
                <span className="item-badge warn">{issue.days_in_stage}d</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Bottlenecks */}
      {bottlenecks && bottlenecks.length > 0 && (
        <div className="snapshot-subsection">
          <h5 className="snapshot-label">Bottlenecks ({bottlenecks.length})</h5>
          <ul className="briefing-list">
            {bottlenecks.map((bn, i) => (
              <li key={i}>
                <span className="item-text">{bn.issue}</span>
                <span className="item-detail">{bn.affectedLoans} affected · {bn.avgDelay}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Team stats (manager/leadership) */}
      {team_stats && team_stats.has_team && (
        <div className="snapshot-subsection">
          <h5 className="snapshot-label">Team</h5>
          <div className="metric-row">
            <div className="metric-item">
              <span className="metric-value">{team_stats.avg_workload}</span>
              <span className="metric-label">Avg Workload</span>
            </div>
            <div className="metric-item">
              <span className="metric-value">{team_stats.backlog}</span>
              <span className="metric-label">Backlog</span>
            </div>
            <div className="metric-item">
              <span className="metric-value">{team_stats.sla_missed}</span>
              <span className="metric-label">SLA Missed</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
