import React, { useState, useEffect, useCallback } from 'react';
import api from '../services/api';
import { toast } from '../utils/toast';
import {
  healthLabel,
  formatVolume,
  SectionHeader,
  PipelineSection,
  AtRiskSection,
  ConditionsSection,
  StaleLeadsSection,
  AppointmentsSection,
  YesterdaySection,
  TeamSection,
} from '../components/briefing/shared';
import './BriefingPage.css';

// ---------------------------------------------------------------------------
// Today Tab
// ---------------------------------------------------------------------------

function TodayTab() {
  const [briefing, setBriefing] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [openSections, setOpenSections] = useState({
    pipeline: true,
    at_risk: true,
    conditions: true,
    stale_leads: true,
    appointments: true,
    yesterday: true,
    team: true,
  });

  const fetchBriefing = useCallback(async () => {
    try {
      const res = await api.get('/api/v1/briefing/today', {
        validateStatus: (status) => status === 200 || status === 204,
      });
      if (res.status === 204) {
        setBriefing(null);
      } else if (res.status === 200 && res.data && res.data.status === 'delivered') {
        setBriefing(res.data);
        if (res.data.id && !res.data.viewed_in_app) {
          api.post(`/api/v1/briefing/${res.data.id}/viewed`).catch(() => {});
        }
      } else if (res.data && res.data.status === 'generating') {
        setBriefing('generating');
      } else {
        setBriefing(null);
      }
    } catch (_err) {
      // Silent failure - briefings are supplementary
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchBriefing(); }, [fetchBriefing]);

  const toggleSection = (key) => {
    setOpenSections(prev => ({ ...prev, [key]: !prev[key] }));
  };

  const handleRefresh = async () => {
    if (refreshing) return;
    setRefreshing(true);
    try {
      await api.post('/api/v1/briefing/generate-now?force=true');
      toast.success('Briefing refresh started -- it may take a moment.');
      setTimeout(async () => {
        await fetchBriefing();
        setRefreshing(false);
      }, 4000);
    } catch (err) {
      const detail = err?.response?.data?.detail;
      toast.error(detail || 'Could not refresh briefing');
      setRefreshing(false);
    }
  };

  const computeHealth = () => {
    if (!briefing) return 'green';
    const atRiskCount = (briefing.at_risk || []).length;
    const staleCount = (briefing.stale_leads || []).length;
    const pastDueConditions = (briefing.conditions || []).filter(c => c.past_due).length;
    if (pastDueConditions >= 2 || atRiskCount >= 3) return 'red';
    if (atRiskCount >= 1 || staleCount >= 3 || pastDueConditions >= 1) return 'yellow';
    return 'green';
  };

  if (loading) {
    return <div className="briefing-page-loading">Loading today's briefing...</div>;
  }

  if (briefing === 'generating') {
    return (
      <div className="briefing-page-loading">
        <p>Your briefing is being generated — check back in a moment.</p>
        <button className="bp-btn bp-btn-secondary" onClick={handleRefresh} disabled={refreshing}>
          {refreshing ? 'Checking...' : 'Check Again'}
        </button>
      </div>
    );
  }

  if (!briefing) {
    return (
      <div className="briefing-page-empty">
        <p>No briefing available for today yet.</p>
        <button className="bp-btn bp-btn-primary" onClick={handleRefresh} disabled={refreshing}>
          {refreshing ? 'Generating...' : 'Generate Now'}
        </button>
      </div>
    );
  }

  const {
    ai_narrative, pipeline, at_risk, stale_leads,
    appointments, conditions, yesterday, team,
    briefing_level, briefing_date,
  } = briefing;

  const health = computeHealth();

  return (
    <div className="bp-today">
      <div className="bp-today-header">
        <div className="bp-today-title">
          <span className={`health-indicator ${health}`} title={healthLabel(health)} />
          <h2>{briefing_date || "Today's Briefing"}</h2>
          <span className="health-label">{healthLabel(health)}</span>
        </div>
        <button
          className="bp-btn bp-btn-secondary"
          onClick={handleRefresh}
          disabled={refreshing}
        >
          {refreshing ? 'Refreshing...' : 'Refresh'}
        </button>
      </div>

      {ai_narrative && (
        <div className="briefing-narrative">
          <div className="narrative-text">{ai_narrative}</div>
        </div>
      )}

      {pipeline && pipeline.active_count > 0 && (
        <div className="briefing-section">
          <SectionHeader
            title="Pipeline Health"
            icon=""
            count={pipeline.active_count}
            isOpen={openSections.pipeline}
            onToggle={() => toggleSection('pipeline')}
          />
          {openSections.pipeline && <PipelineSection pipeline={pipeline} maxStages={8} />}
        </div>
      )}

      {at_risk && at_risk.length > 0 && (
        <div className="briefing-section section-warn">
          <SectionHeader
            title="SLA Alerts"
            icon=""
            count={at_risk.length}
            isOpen={openSections.at_risk}
            onToggle={() => toggleSection('at_risk')}
          />
          {openSections.at_risk && <AtRiskSection items={at_risk} />}
        </div>
      )}

      {conditions && conditions.length > 0 && (
        <div className="briefing-section">
          <SectionHeader
            title="Open Conditions"
            icon=""
            count={conditions.length}
            isOpen={openSections.conditions}
            onToggle={() => toggleSection('conditions')}
          />
          {openSections.conditions && <ConditionsSection conditions={conditions} />}
        </div>
      )}

      {stale_leads && stale_leads.length > 0 && (
        <div className="briefing-section section-caution">
          <SectionHeader
            title="Lead Activity"
            icon=""
            count={stale_leads.length}
            isOpen={openSections.stale_leads}
            onToggle={() => toggleSection('stale_leads')}
          />
          {openSections.stale_leads && <StaleLeadsSection leads={stale_leads} />}
        </div>
      )}

      {appointments && appointments.length > 0 && (
        <div className="briefing-section">
          <SectionHeader
            title="Today's Schedule"
            icon=""
            count={appointments.length}
            isOpen={openSections.appointments}
            onToggle={() => toggleSection('appointments')}
          />
          {openSections.appointments && <AppointmentsSection appointments={appointments} />}
        </div>
      )}

      {yesterday && (yesterday.funded > 0 || yesterday.new_loans > 0 || yesterday.conversions > 0) && (
        <div className="briefing-section">
          <SectionHeader
            title="Yesterday Recap"
            icon=""
            isOpen={openSections.yesterday}
            onToggle={() => toggleSection('yesterday')}
          />
          {openSections.yesterday && <YesterdaySection yesterday={yesterday} />}
        </div>
      )}

      {team && (briefing_level === 'manager' || briefing_level === 'leadership') && (
        <div className="briefing-section section-team">
          <SectionHeader
            title={briefing_level === 'leadership' ? 'Organization Overview' : 'Your Team'}
            icon=""
            isOpen={openSections.team}
            onToggle={() => toggleSection('team')}
          />
          {openSections.team && <TeamSection team={team} level={briefing_level} />}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// History Tab
// ---------------------------------------------------------------------------

function HistoryTab() {
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(true);
  const [expandedId, setExpandedId] = useState(null);
  const perPage = 10;

  const fetchHistory = useCallback(async (pg) => {
    try {
      setLoading(true);
      const res = await api.get(`/api/v1/briefing/history?page=${pg}&per_page=${perPage}`);
      const items = res.data?.items || res.data || [];
      if (pg === 1) {
        setHistory(items);
      } else {
        setHistory(prev => [...prev, ...items]);
      }
      setHasMore(items.length === perPage);
    } catch (err) {
      toast.error('Failed to load briefing history');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchHistory(1); }, [fetchHistory]);

  const loadMore = () => {
    const nextPage = page + 1;
    setPage(nextPage);
    fetchHistory(nextPage);
  };

  const toggleExpand = (id) => {
    setExpandedId(prev => prev === id ? null : id);
  };

  if (loading && history.length === 0) {
    return <div className="briefing-page-loading">Loading history...</div>;
  }

  if (history.length === 0) {
    return <div className="briefing-page-empty"><p>No briefing history available.</p></div>;
  }

  return (
    <div className="bp-history">
      <div className="bp-history-list">
        {history.map((item) => (
          <div
            key={item.id}
            className={`bp-history-item ${expandedId === item.id ? 'expanded' : ''}`}
          >
            <button
              className="bp-history-row"
              onClick={() => toggleExpand(item.id)}
              type="button"
            >
              <span className="bp-history-date">{item.briefing_date || 'Unknown date'}</span>
              <span className={`bp-history-level ${item.briefing_level || 'lo'}`}>
                {item.briefing_level || 'lo'}
              </span>
              <span className={`bp-history-status ${item.status || 'unknown'}`}>
                {item.status || 'unknown'}
              </span>
              {item.viewed_in_app && <span className="bp-history-viewed">Viewed</span>}
              <span className="bp-history-narrative-preview">
                {(item.ai_narrative || '').slice(0, 100)}
                {(item.ai_narrative || '').length > 100 ? '...' : ''}
              </span>
              <span className="section-chevron">
                {expandedId === item.id ? '\u25BE' : '\u25B8'}
              </span>
            </button>
            {expandedId === item.id && (
              <div className="bp-history-detail">
                {item.ai_narrative && (
                  <div className="briefing-narrative">
                    <div className="narrative-text">{item.ai_narrative}</div>
                  </div>
                )}
                {item.pipeline && (
                  <div className="bp-detail-section">
                    <h4>Pipeline</h4>
                    <p>Active: {item.pipeline.active_count}, Volume: {formatVolume(item.pipeline.total_volume)}</p>
                  </div>
                )}
                {item.at_risk && item.at_risk.length > 0 && (
                  <div className="bp-detail-section">
                    <h4>At Risk ({item.at_risk.length})</h4>
                    <ul className="briefing-list">
                      {item.at_risk.map((loan, i) => (
                        <li key={i}>{loan.borrower} - {loan.reason}</li>
                      ))}
                    </ul>
                  </div>
                )}
                {item.stale_leads && item.stale_leads.length > 0 && (
                  <div className="bp-detail-section">
                    <h4>Stale Leads ({item.stale_leads.length})</h4>
                    <ul className="briefing-list">
                      {item.stale_leads.map((lead, i) => (
                        <li key={i}>{lead.name} - {Math.round(lead.days_silent || 0)} days</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}
          </div>
        ))}
      </div>
      {hasMore && (
        <div className="bp-load-more">
          <button className="bp-btn bp-btn-secondary" onClick={loadMore} disabled={loading}>
            {loading ? 'Loading...' : 'Load More'}
          </button>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Preferences Tab
// ---------------------------------------------------------------------------

const SECTION_TOGGLES = [
  { key: 'pipeline', label: 'Pipeline Health' },
  { key: 'at_risk', label: 'At-Risk / SLA Alerts' },
  { key: 'stale_leads', label: 'Stale Leads' },
  { key: 'appointments', label: 'Appointments' },
  { key: 'conditions', label: 'Open Conditions' },
  { key: 'yesterday', label: 'Yesterday Recap' },
];

const TONE_OPTIONS = [
  { value: 'concise', label: 'Concise' },
  { value: 'balanced', label: 'Balanced' },
  { value: 'detailed', label: 'Detailed' },
];

function PreferencesTab() {
  const [prefs, setPrefs] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const fetchPrefs = useCallback(async () => {
    try {
      const res = await api.get('/api/v1/briefing/preferences');
      setPrefs(res.data || {});
    } catch (err) {
      toast.error('Failed to load preferences');
      setPrefs({});
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchPrefs(); }, [fetchPrefs]);

  const handleChange = (field, value) => {
    setPrefs(prev => ({ ...prev, [field]: value }));
  };

  const handleSectionToggle = (key) => {
    const sections = { ...(prefs.sections || {}) };
    sections[key] = !sections[key];
    setPrefs(prev => ({ ...prev, sections }));
  };

  const handleThresholdChange = (key, value) => {
    const thresholds = { ...(prefs.thresholds || {}) };
    thresholds[key] = parseInt(value, 10) || 0;
    setPrefs(prev => ({ ...prev, thresholds }));
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      await api.put('/api/v1/briefing/preferences', prefs);
      toast.success('Preferences saved');
    } catch (err) {
      toast.error('Failed to save preferences');
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return <div className="briefing-page-loading">Loading preferences...</div>;
  }

  const sections = prefs.sections || {};
  const thresholds = prefs.thresholds || {};

  return (
    <div className="bp-preferences">
      <div className="bp-pref-group">
        <h3>General</h3>
        <label className="bp-toggle-row">
          <span>Briefing Enabled</span>
          <input
            type="checkbox"
            checked={prefs.briefing_enabled !== false}
            onChange={(e) => handleChange('briefing_enabled', e.target.checked)}
          />
        </label>
        <label className="bp-field-row">
          <span>Briefing Hour (0-23)</span>
          <input
            type="number"
            min="0"
            max="23"
            value={prefs.briefing_hour ?? 7}
            onChange={(e) => handleChange('briefing_hour', parseInt(e.target.value, 10) || 0)}
            className="bp-input-number"
          />
        </label>
        <label className="bp-field-row">
          <span>AI Tone</span>
          <select
            value={prefs.ai_tone || 'balanced'}
            onChange={(e) => handleChange('ai_tone', e.target.value)}
            className="bp-select"
          >
            {TONE_OPTIONS.map(opt => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>
        </label>
      </div>

      <div className="bp-pref-group">
        <h3>Sections</h3>
        {SECTION_TOGGLES.map(({ key, label }) => (
          <label key={key} className="bp-toggle-row">
            <span>{label}</span>
            <input
              type="checkbox"
              checked={sections[key] !== false}
              onChange={() => handleSectionToggle(key)}
            />
          </label>
        ))}
      </div>

      <div className="bp-pref-group">
        <h3>Thresholds</h3>
        <label className="bp-field-row">
          <span>At-Risk Days</span>
          <input
            type="number"
            min="1"
            max="90"
            value={thresholds.at_risk_days ?? 7}
            onChange={(e) => handleThresholdChange('at_risk_days', e.target.value)}
            className="bp-input-number"
          />
        </label>
        <label className="bp-field-row">
          <span>Stale Lead Days</span>
          <input
            type="number"
            min="1"
            max="90"
            value={thresholds.stale_lead_days ?? 14}
            onChange={(e) => handleThresholdChange('stale_lead_days', e.target.value)}
            className="bp-input-number"
          />
        </label>
        <label className="bp-field-row">
          <span>Stale Lead (High Score) Days</span>
          <input
            type="number"
            min="1"
            max="90"
            value={thresholds.stale_lead_high_score_days ?? 7}
            onChange={(e) => handleThresholdChange('stale_lead_high_score_days', e.target.value)}
            className="bp-input-number"
          />
        </label>
        <label className="bp-field-row">
          <span>Lock Expiring Days</span>
          <input
            type="number"
            min="1"
            max="30"
            value={thresholds.lock_expiring_days ?? 5}
            onChange={(e) => handleThresholdChange('lock_expiring_days', e.target.value)}
            className="bp-input-number"
          />
        </label>
      </div>

      <div className="bp-pref-actions">
        <button className="bp-btn bp-btn-primary" onClick={handleSave} disabled={saving}>
          {saving ? 'Saving...' : 'Save Preferences'}
        </button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main BriefingPage
// ---------------------------------------------------------------------------

const TABS = [
  { key: 'today', label: 'Today' },
  { key: 'history', label: 'History' },
  { key: 'preferences', label: 'Preferences' },
];

export default function BriefingPage() {
  const [activeTab, setActiveTab] = useState('today');

  return (
    <div className="briefing-page">
      <div className="bp-page-header">
        <h1>Morning Briefing</h1>
      </div>

      <div className="bp-tabs">
        {TABS.map(tab => (
          <button
            key={tab.key}
            className={`bp-tab ${activeTab === tab.key ? 'active' : ''}`}
            onClick={() => setActiveTab(tab.key)}
            type="button"
          >
            {tab.label}
          </button>
        ))}
      </div>

      <div className="bp-tab-content">
        {activeTab === 'today' && <TodayTab />}
        {activeTab === 'history' && <HistoryTab />}
        {activeTab === 'preferences' && <PreferencesTab />}
      </div>
    </div>
  );
}
