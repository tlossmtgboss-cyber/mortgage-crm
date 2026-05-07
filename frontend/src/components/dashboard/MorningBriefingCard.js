import React, { useState, useEffect, useCallback } from 'react';
import api from '../../services/api';
import { toast } from '../../utils/toast';
import {
  healthLabel,
  SectionHeader,
  PipelineSection,
  AtRiskSection,
  ConditionsSection,
  StaleLeadsSection,
  AppointmentsSection,
  YesterdaySection,
  TeamSection,
} from '../briefing/shared';
import './MorningBriefingCard.css';

// ---------------------------------------------------------------------------
// Card-local helpers
// ---------------------------------------------------------------------------

function getLocalDateString() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

function TrendArrow({ value, invertColor }) {
  if (value === undefined || value === null) return null;
  const num = Number(value);
  if (num === 0) return <span className="trend-arrow neutral">--</span>;
  const up = num > 0;
  const colorClass = invertColor ? (up ? 'down' : 'up') : (up ? 'up' : 'down');
  return (
    <span className={`trend-arrow ${colorClass}`}>
      {up ? '\u25B2' : '\u25BC'} {Math.abs(num)}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function MorningBriefingCard() {
  const [briefing, setBriefing] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [collapsed, setCollapsed] = useState(() => {
    return localStorage.getItem('briefing_collapsed') === 'true';
  });
  const [dismissed, setDismissed] = useState(() => {
    const d = localStorage.getItem('briefing_dismissed_date');
    return d === getLocalDateString();
  });
  const [narrativeExpanded, setNarrativeExpanded] = useState(false);
  const [openSections, setOpenSections] = useState({
    pipeline: true,
    at_risk: true,
    conditions: true,
    stale_leads: false,
    appointments: true,
    yesterday: false,
    team: false,
  });

  // ----- Fetch today's briefing -----
  const fetchBriefing = useCallback(async () => {
    try {
      const res = await api.get('/api/v1/briefing/today', {
        validateStatus: (status) => status === 200 || status === 204,
      });
      if (res.status === 204) {
        // No briefing yet today
        setBriefing(null);
      } else if (res.data && res.data.status === 'delivered') {
        setBriefing(res.data);
        // Mark as viewed
        if (!res.data.viewed_in_app) {
          api.post(`/api/v1/briefing/${res.data.id}/viewed`).catch(() => {});
        }
      }
    } catch (_err) {
      // Silent -- briefings are supplementary
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!dismissed) fetchBriefing();
    else setLoading(false);
  }, [dismissed, fetchBriefing]);

  // ----- Actions -----
  const toggleCollapse = () => {
    const next = !collapsed;
    setCollapsed(next);
    localStorage.setItem('briefing_collapsed', String(next));
  };

  const dismiss = () => {
    setDismissed(true);
    localStorage.setItem('briefing_dismissed_date', getLocalDateString());
  };

  const toggleSection = (key) => {
    setOpenSections(prev => ({ ...prev, [key]: !prev[key] }));
  };

  const handleRefresh = async (e) => {
    e.stopPropagation();
    if (refreshing) return;
    setRefreshing(true);
    try {
      const res = await api.post('/api/v1/briefing/generate-now?force=true');
      if (res.status === 201) {
        toast.success('Briefing generated.');
        await fetchBriefing();
        setRefreshing(false);
      } else {
        toast.success('Briefing generation started — check back in a moment.');
        setTimeout(() => {
          fetchBriefing().finally(() => setRefreshing(false));
        }, 5000);
      }
    } catch (err) {
      const detail = err?.response?.data?.detail;
      toast.error(detail || 'Could not refresh briefing');
      setRefreshing(false);
    }
  };

  // ----- Compute health indicator -----
  const computeHealth = () => {
    if (!briefing) return 'green';
    const atRiskCount = (briefing.at_risk || []).length;
    const staleCount = (briefing.stale_leads || []).length;
    const pastDueConditions = (briefing.conditions || []).filter(c => c.past_due).length;
    if (pastDueConditions >= 2 || atRiskCount >= 3) return 'red';
    if (atRiskCount >= 1 || staleCount >= 3 || pastDueConditions >= 1) return 'yellow';
    return 'green';
  };

  // ----- Render guards -----
  if (loading || dismissed) return null;
  if (!briefing) return null;

  const {
    ai_narrative,
    pipeline,
    at_risk,
    stale_leads,
    appointments,
    conditions,
    yesterday,
    team,
    briefing_level,
    briefing_date,
  } = briefing;

  const health = computeHealth();
  const narrativeText = ai_narrative || '';
  const showNarrativeTruncated = narrativeText.length > 200 && !narrativeExpanded;

  return (
    <div className={`morning-briefing-card health-${health}`}>
      {/* --- Header --- */}
      <div className="briefing-header" onClick={toggleCollapse}>
        <div className="briefing-title">
          <span className={`health-indicator ${health}`} title={healthLabel(health)} />
          <h3>Morning Briefing</h3>
          <span className="health-label">{healthLabel(health)}</span>
          <span className="briefing-date">{briefing_date}</span>
        </div>
        <div className="briefing-actions">
          <button
            className="briefing-refresh-btn"
            onClick={handleRefresh}
            disabled={refreshing}
            title="Refresh briefing"
          >
            <span className={refreshing ? 'spin' : ''}>&#x21bb;</span>
          </button>
          <button className="briefing-collapse-btn" title={collapsed ? 'Expand' : 'Collapse'}>
            {collapsed ? '\u25B8' : '\u25BE'}
          </button>
          <button
            className="briefing-dismiss-btn"
            onClick={(e) => { e.stopPropagation(); dismiss(); }}
            title="Dismiss for today"
          >
            &#x2715;
          </button>
        </div>
      </div>

      {/* --- Body --- */}
      {!collapsed && (
        <div className="briefing-body">
          {/* AI Narrative */}
          {narrativeText && (
            <div className="briefing-narrative">
              <div className={`narrative-text ${showNarrativeTruncated ? 'truncated' : ''}`}>
                {showNarrativeTruncated ? narrativeText.slice(0, 200) + '...' : narrativeText}
              </div>
              {narrativeText.length > 200 && (
                <button
                  className="narrative-toggle"
                  onClick={() => setNarrativeExpanded(!narrativeExpanded)}
                >
                  {narrativeExpanded ? 'Show less' : 'Read more'}
                </button>
              )}
            </div>
          )}

          {/* Pipeline Health */}
          {pipeline && pipeline.active_count > 0 && (
            <div className="briefing-section">
              <SectionHeader
                title="Pipeline Health"
                icon="&#x1F4CA;"
                count={pipeline.active_count}
                isOpen={openSections.pipeline}
                onToggle={() => toggleSection('pipeline')}
              />
              {openSections.pipeline && <PipelineSection pipeline={pipeline} maxStages={5} />}
            </div>
          )}

          {/* SLA Alerts / At-Risk */}
          {at_risk && at_risk.length > 0 && (
            <div className="briefing-section section-warn">
              <SectionHeader
                title="SLA Alerts"
                icon="&#x26A0;"
                count={at_risk.length}
                isOpen={openSections.at_risk}
                onToggle={() => toggleSection('at_risk')}
              />
              {openSections.at_risk && <AtRiskSection items={at_risk} maxItems={5} />}
            </div>
          )}

          {/* Conditions */}
          {conditions && conditions.length > 0 && (
            <div className="briefing-section">
              <SectionHeader
                title="Open Conditions"
                icon="&#x1F4CB;"
                count={conditions.length}
                isOpen={openSections.conditions}
                onToggle={() => toggleSection('conditions')}
              />
              {openSections.conditions && <ConditionsSection conditions={conditions} maxItems={5} />}
            </div>
          )}

          {/* Stale Leads */}
          {stale_leads && stale_leads.length > 0 && (
            <div className="briefing-section section-caution">
              <SectionHeader
                title="Lead Activity"
                icon="&#x1F525;"
                count={stale_leads.length}
                isOpen={openSections.stale_leads}
                onToggle={() => toggleSection('stale_leads')}
              />
              {openSections.stale_leads && <StaleLeadsSection leads={stale_leads} maxItems={5} />}
            </div>
          )}

          {/* Appointments */}
          {appointments && appointments.length > 0 && (
            <div className="briefing-section">
              <SectionHeader
                title="Today's Schedule"
                icon="&#x1F4C5;"
                count={appointments.length}
                isOpen={openSections.appointments}
                onToggle={() => toggleSection('appointments')}
              />
              {openSections.appointments && <AppointmentsSection appointments={appointments} />}
            </div>
          )}

          {/* Yesterday Recap */}
          {yesterday && (yesterday.funded > 0 || yesterday.new_loans > 0 || yesterday.conversions > 0) && (
            <div className="briefing-section">
              <SectionHeader
                title="Yesterday Recap"
                icon="&#x1F4C8;"
                isOpen={openSections.yesterday}
                onToggle={() => toggleSection('yesterday')}
              />
              {openSections.yesterday && <YesterdaySection yesterday={yesterday} />}
            </div>
          )}

          {/* Team (Manager) / Org (Leadership) */}
          {team && (briefing_level === 'manager' || briefing_level === 'leadership') && (
            <div className="briefing-section section-team">
              <SectionHeader
                title={briefing_level === 'leadership' ? 'Organization Overview' : 'Your Team'}
                icon="&#x1F465;"
                isOpen={openSections.team}
                onToggle={() => toggleSection('team')}
              />
              {openSections.team && <TeamSection team={team} level={briefing_level} />}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
