import React, { useState, useEffect, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { leadsAPI } from '../../services/api';
import { daysBetween, LoadingSkeleton } from './helpers';

// =============================================================================
// Section 3: Lead Follow-Ups
// =============================================================================

export function LeadFollowUpSection() {
  const [leads, setLeads] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchLeads = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await leadsAPI.getAll();
      const allLeads = Array.isArray(data) ? data : [];

      // Filter to leads needing follow-up: last contact > 3 days or no contact,
      // exclude closed/funded stages
      const closedStages = ['Funded', 'Closed', 'Dead', 'Lost', 'Cancelled', 'Withdrawn'];
      const needsFollowUp = allLeads
        .filter((lead) => {
          if (closedStages.includes(lead.stage)) return false;
          const lastContact = lead.last_contact || lead.last_contacted_at || lead.updated_at;
          const daysSince = daysBetween(lastContact);
          return daysSince === null || daysSince >= 3;
        })
        .sort((a, b) => {
          // Sort by longest since contact first
          const aDays = daysBetween(a.last_contact || a.last_contacted_at || a.updated_at) || 999;
          const bDays = daysBetween(b.last_contact || b.last_contacted_at || b.updated_at) || 999;
          return bDays - aDays;
        })
        .slice(0, 10);

      setLeads(needsFollowUp);
    } catch (err) {
      console.error('Failed to fetch leads for follow-up:', err);
      setError(err.message || 'Failed to load leads');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchLeads();
  }, [fetchLeads]);

  function getInitial(lead) {
    const name = lead.first_name || lead.name || '?';
    return name.charAt(0).toUpperCase();
  }

  function getLeadName(lead) {
    if (lead.first_name && lead.last_name) return `${lead.first_name} ${lead.last_name}`;
    if (lead.first_name) return lead.first_name;
    return lead.name || 'Unknown';
  }

  function getContactDaysText(lead) {
    const lastContact = lead.last_contact || lead.last_contacted_at || lead.updated_at;
    const days = daysBetween(lastContact);
    if (days === null) return 'Never contacted';
    if (days === 0) return 'Contacted today';
    if (days === 1) return '1 day ago';
    return `${days} days ago`;
  }

  function getSuggestedAction(lead) {
    const days = daysBetween(lead.last_contact || lead.last_contacted_at || lead.updated_at);
    if (days === null || days >= 14) return 'Call';
    if (days >= 7) return 'Email';
    return 'Schedule';
  }

  return (
    <div className="lo-today__section">
      <div className="lo-today__section-header">
        <h2 className="lo-today__section-title">
          Lead Follow-Ups
          {leads.length > 0 && (
            <span className="lo-today__section-badge lo-today__section-badge--warning">{leads.length}</span>
          )}
        </h2>
        <Link to="/leads" style={{ fontSize: 13, color: '#3b82f6', textDecoration: 'none' }}>
          All Leads
        </Link>
      </div>
      <div className="lo-today__section-body">
        {loading ? (
          <LoadingSkeleton rows={4} />
        ) : error ? (
          <div className="lo-today__error">
            <p>{error}</p>
            <button className="lo-today__retry-btn" onClick={fetchLeads}>Retry</button>
          </div>
        ) : leads.length === 0 ? (
          <div className="lo-today__empty">
            <div className="lo-today__empty-icon">&#9734;</div>
            <div>All leads contacted recently</div>
            <div style={{ fontSize: 12, marginTop: 4 }}>No follow-ups needed right now</div>
          </div>
        ) : (
          leads.map((lead) => {
            const suggested = getSuggestedAction(lead);
            return (
              <div key={lead.id} className="lo-today__lead-item">
                <div className="lo-today__lead-avatar">{getInitial(lead)}</div>
                <div className="lo-today__lead-info">
                  <div className="lo-today__lead-name">{getLeadName(lead)}</div>
                  <div className="lo-today__lead-detail">
                    {getContactDaysText(lead)}
                    {lead.ai_score != null && ` · Score: ${lead.ai_score}`}
                  </div>
                </div>
                <div className="lo-today__lead-actions">
                  <Link
                    to={`/leads/${lead.id}`}
                    className={`lo-today__lead-action-btn ${suggested === 'Call' ? 'lo-today__lead-action-btn--primary' : ''}`}
                  >
                    {suggested}
                  </Link>
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}

export default LeadFollowUpSection;
