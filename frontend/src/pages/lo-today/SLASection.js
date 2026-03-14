import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { Link } from 'react-router-dom';
import { loansAPI } from '../../services/api';
import { daysBetween, SLA_TARGETS_BY_STAGE, LoadingSkeleton } from './helpers';

// =============================================================================
// Section 4: SLA Alerts
// =============================================================================

export function SLASection() {
  const [alerts, setAlerts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchAlerts = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await loansAPI.getAll();
      const allLoans = Array.isArray(data) ? data : [];

      // Build SLA alerts from loans in active stages
      const slaAlerts = [];
      const terminalStages = ['FUNDED', 'CANCELLED', 'DENIED', 'DEAD', 'WITHDRAWN', 'DOES_NOT_QUALIFY'];

      for (const loan of allLoans) {
        const stage = (loan.stage || '').toUpperCase();
        if (terminalStages.includes(stage)) continue;

        const stageChangedAt = loan.stage_changed_at || loan.updated_at;
        if (!stageChangedAt) continue;

        const daysInStage = daysBetween(stageChangedAt);
        if (daysInStage === null) continue;

        const target = SLA_TARGETS_BY_STAGE[stage] || 7;
        const daysRemaining = target - daysInStage;

        // Only show if approaching (<=2 days remaining) or past SLA
        if (daysRemaining <= 2) {
          slaAlerts.push({
            id: loan.id,
            loan_number: loan.loan_number,
            borrower_name: loan.borrower_name || loan.borrower || '',
            stage,
            days_in_stage: daysInStage,
            target_days: target,
            days_remaining: daysRemaining,
            urgency: daysRemaining < 0 ? 'overdue' : daysRemaining === 0 ? 'warning' : 'approaching',
          });
        }
      }

      // Sort: overdue first, then by most days overdue
      slaAlerts.sort((a, b) => a.days_remaining - b.days_remaining);

      setAlerts(slaAlerts.slice(0, 15));
    } catch (err) {
      console.error('Failed to compute SLA alerts:', err);
      setError(err.message || 'Failed to load SLA data');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchAlerts();
  }, [fetchAlerts]);

  const overdueCount = useMemo(
    () => alerts.filter((a) => a.urgency === 'overdue').length,
    [alerts]
  );

  function getIndicatorClass(alert) {
    if (alert.days_remaining < 0) return 'lo-today__sla-indicator--overdue';
    if (alert.days_remaining <= 1) return 'lo-today__sla-indicator--warning';
    return 'lo-today__sla-indicator--ok';
  }

  function getDaysNumberClass(alert) {
    if (alert.days_remaining < 0) return 'lo-today__sla-days-number--overdue';
    if (alert.days_remaining <= 1) return 'lo-today__sla-days-number--warning';
    return 'lo-today__sla-days-number--ok';
  }

  function formatStage(stage) {
    return stage
      .replace(/_/g, ' ')
      .replace(/\b\w/g, (c) => c.toUpperCase());
  }

  return (
    <div className="lo-today__section">
      <div className="lo-today__section-header">
        <h2 className="lo-today__section-title">
          SLA Alerts
          {overdueCount > 0 && (
            <span className="lo-today__section-badge lo-today__section-badge--danger">{overdueCount}</span>
          )}
        </h2>
        <Link to="/pipeline-efficiency" style={{ fontSize: 13, color: '#3b82f6', textDecoration: 'none' }}>
          Pipeline
        </Link>
      </div>
      <div className="lo-today__section-body">
        {loading ? (
          <LoadingSkeleton rows={4} />
        ) : error ? (
          <div className="lo-today__error">
            <p>{error}</p>
            <button className="lo-today__retry-btn" onClick={fetchAlerts}>Retry</button>
          </div>
        ) : alerts.length === 0 ? (
          <div className="lo-today__empty">
            <div className="lo-today__empty-icon">&#9989;</div>
            <div>All loans within SLA</div>
            <div style={{ fontSize: 12, marginTop: 4 }}>No approaching or missed deadlines</div>
          </div>
        ) : (
          alerts.map((alert) => (
            <Link
              key={alert.id}
              to={`/loans/${alert.id}`}
              className={`lo-today__sla-item ${alert.urgency === 'overdue' ? 'lo-today__sla-item--critical' : ''}`}
              style={{ textDecoration: 'none' }}
            >
              <div className={`lo-today__sla-indicator ${getIndicatorClass(alert)}`}>
                {alert.days_in_stage}d
              </div>
              <div className="lo-today__sla-info">
                <div className="lo-today__sla-loan">
                  {alert.loan_number ? `#${alert.loan_number}` : 'Loan'}
                </div>
                {alert.borrower_name && (
                  <div className="lo-today__sla-borrower">{alert.borrower_name}</div>
                )}
                <span className="lo-today__sla-stage">{formatStage(alert.stage)}</span>
              </div>
              <div className="lo-today__sla-days">
                <div className={`lo-today__sla-days-number ${getDaysNumberClass(alert)}`}>
                  {alert.days_remaining < 0
                    ? `${Math.abs(alert.days_remaining)}d`
                    : `${alert.days_remaining}d`}
                </div>
                <div className="lo-today__sla-days-label">
                  {alert.days_remaining < 0 ? 'overdue' : 'remaining'}
                </div>
              </div>
            </Link>
          ))
        )}
      </div>
    </div>
  );
}

export default SLASection;
