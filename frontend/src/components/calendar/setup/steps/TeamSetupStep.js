/**
 * TeamSetupStep - Step 8 of Smart Calendar guided setup
 *
 * For managers/admins: assignment strategy, team member routing, overflow settings.
 * For individual LOs: simplified "you're all set" view with a note to contact manager.
 *
 * Saves to: PUT /api/v1/scheduler/settings/team
 */

import React, { useState, useEffect, useCallback } from 'react';
import { calendarSettingsAPI } from '../../../../services/api';
import { toast } from '../../../../utils/toast';
import './TeamSetupStep.css';

// ============================================================================
// Constants
// ============================================================================

const ASSIGNMENT_STRATEGIES = [
  {
    value: 'round_robin',
    label: 'Round Robin',
    description: 'Distribute evenly across team',
    icon: 'fa-sync-alt',
    detail: 'Each new appointment goes to the next team member in rotation, ensuring an even workload.',
  },
  {
    value: 'load_balanced',
    label: 'Load Balanced',
    description: 'Assign to least busy team member',
    icon: 'fa-balance-scale',
    detail: 'Appointments route to the team member with the fewest upcoming meetings that day.',
  },
  {
    value: 'ai_optimized',
    label: 'AI Optimized',
    description: 'AI picks the best match based on borrower needs',
    icon: 'fa-brain',
    detail: 'Uses loan type, language preference, and expertise to match borrowers with the right LO.',
    badge: 'Premium',
  },
  {
    value: 'manual',
    label: 'Manual',
    description: 'Admin assigns all appointments',
    icon: 'fa-hand-pointer',
    detail: 'All incoming bookings go to a queue for manual assignment by a manager.',
  },
];

// ============================================================================
// Sub-components
// ============================================================================

const StrategyCard = ({ strategy, isSelected, onSelect }) => (
  <button
    type="button"
    className={`tss-strategy-card ${isSelected ? 'tss-strategy-card--selected' : ''}`}
    onClick={() => onSelect(strategy.value)}
    aria-pressed={isSelected}
  >
    <div className="tss-strategy-card__icon">
      <i className={`fas ${strategy.icon}`} aria-hidden="true" />
    </div>
    <div className="tss-strategy-card__body">
      <div className="tss-strategy-card__header">
        <span className="tss-strategy-card__label">{strategy.label}</span>
        {strategy.badge && (
          <span className="tss-strategy-card__badge">{strategy.badge}</span>
        )}
      </div>
      <p className="tss-strategy-card__desc">{strategy.description}</p>
      {isSelected && (
        <p className="tss-strategy-card__detail">{strategy.detail}</p>
      )}
    </div>
    <div className="tss-strategy-card__check">
      {isSelected && <i className="fas fa-check-circle" aria-hidden="true" />}
    </div>
  </button>
);

const TeamMemberRow = ({ member, onToggleRouting, onCapacityChange }) => {
  const capacityPct = member.max_daily_appointments > 0
    ? Math.min(100, Math.round((member.upcoming_appointments / member.max_daily_appointments) * 100))
    : 0;

  return (
    <div className="tss-member-row">
      <div className="tss-member-info">
        <div className="tss-member-avatar">
          {(member.name || '?').charAt(0).toUpperCase()}
        </div>
        <div className="tss-member-details">
          <span className="tss-member-name">{member.name}</span>
          <span className="tss-member-role">{member.role || 'Loan Officer'}</span>
        </div>
      </div>

      <div className="tss-member-capacity">
        <div className="tss-capacity-bar-wrapper">
          <div
            className={`tss-capacity-bar ${capacityPct >= 90 ? 'tss-capacity-bar--full' : capacityPct >= 70 ? 'tss-capacity-bar--high' : ''}`}
            style={{ width: `${capacityPct}%` }}
          />
        </div>
        <span className="tss-capacity-label">
          {member.upcoming_appointments || 0}/{member.max_daily_appointments || 0} today
        </span>
      </div>

      <div className="tss-member-controls">
        <label className="tss-member-toggle" title="Include in auto-routing">
          <input
            type="checkbox"
            checked={member.is_accepting_appointments}
            onChange={(e) => onToggleRouting(member.user_id, e.target.checked)}
          />
          <span className="tss-toggle-track">
            <span className="tss-toggle-thumb" />
          </span>
        </label>

        <div className="tss-max-daily">
          <label className="tss-max-daily-label" htmlFor={`max-${member.user_id}`}>
            Max daily
          </label>
          <input
            id={`max-${member.user_id}`}
            type="number"
            className="tss-max-daily-input"
            min="1"
            max="24"
            value={member.max_daily_appointments}
            onChange={(e) => onCapacityChange(member.user_id, parseInt(e.target.value, 10) || 1)}
          />
        </div>
      </div>
    </div>
  );
};

const IndividualView = () => (
  <div className="tss-individual-view">
    <div className="tss-individual-icon">
      <i className="fas fa-user-check" aria-hidden="true" />
    </div>
    <h3 className="tss-individual-title">You're all set!</h3>
    <p className="tss-individual-desc">
      Your calendar is configured for individual use. All appointments will be booked
      directly on your schedule.
    </p>
    <div className="tss-individual-note">
      <i className="fas fa-info-circle" aria-hidden="true" />
      <span>Contact your manager to set up team scheduling and appointment routing.</span>
    </div>
  </div>
);

// ============================================================================
// Main component
// ============================================================================

const TeamSetupStep = ({ onComplete, onBack, isManager: isManagerProp }) => {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [isManager, setIsManager] = useState(isManagerProp || false);

  const [strategy, setStrategy] = useState('round_robin');
  const [members, setMembers] = useState([]);
  const [overflowEnabled, setOverflowEnabled] = useState(false);
  const [maxOverflowPct, setMaxOverflowPct] = useState(20);

  // --------------------------------------------------------------------------
  // Load team data
  // --------------------------------------------------------------------------

  const loadTeamData = useCallback(async () => {
    setLoading(true);
    try {
      const res = await calendarSettingsAPI.getTeam();
      if (res?.data) {
        setIsManager(true);
        setStrategy(res.data.assignment_strategy || 'round_robin');
        setMembers(res.data.members || []);
        if (res.data.overflow_enabled !== undefined) {
          setOverflowEnabled(res.data.overflow_enabled);
        }
        if (res.data.max_overflow_pct !== undefined) {
          setMaxOverflowPct(res.data.max_overflow_pct);
        }
      }
    } catch (err) {
      if (err.response?.status === 403) {
        setIsManager(false);
      } else {
        console.error('Failed to load team data:', err);
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadTeamData();
  }, [loadTeamData]);

  // --------------------------------------------------------------------------
  // Member updates
  // --------------------------------------------------------------------------

  const handleToggleRouting = useCallback((userId, accepting) => {
    setMembers(prev =>
      prev.map(m => m.user_id === userId ? { ...m, is_accepting_appointments: accepting } : m)
    );
  }, []);

  const handleCapacityChange = useCallback((userId, maxDaily) => {
    setMembers(prev =>
      prev.map(m => m.user_id === userId ? { ...m, max_daily_appointments: maxDaily } : m)
    );
  }, []);

  // --------------------------------------------------------------------------
  // Save
  // --------------------------------------------------------------------------

  const handleSave = async () => {
    setSaving(true);
    try {
      await calendarSettingsAPI.updateTeam({
        assignment_strategy: strategy,
        members: members.map(m => ({
          user_id: m.user_id,
          max_daily_appointments: m.max_daily_appointments,
          is_accepting_appointments: m.is_accepting_appointments,
        })),
        overflow_enabled: overflowEnabled,
        max_overflow_pct: maxOverflowPct,
      });
      toast.success('Team settings saved');
      if (onComplete) onComplete();
    } catch (err) {
      console.error('Failed to save team settings:', err);
      toast.error('Failed to save team settings');
    } finally {
      setSaving(false);
    }
  };

  // --------------------------------------------------------------------------
  // Render
  // --------------------------------------------------------------------------

  if (loading) {
    return (
      <div className="tss-loading">
        <div className="tss-spinner" />
        <span>Loading team settings...</span>
      </div>
    );
  }

  // Individual LO view
  if (!isManager) {
    return (
      <div className="tss-step">
        <div className="tss-header">
          <div className="tss-step-badge">Step 8</div>
          <h2 className="tss-title">Team & Routing</h2>
          <p className="tss-subtitle">Configure how appointments are distributed across your team.</p>
        </div>

        <IndividualView />

        <div className="tss-actions">
          {onBack && (
            <button type="button" className="tss-btn tss-btn--secondary" onClick={onBack}>
              <i className="fas fa-arrow-left" aria-hidden="true" /> Back
            </button>
          )}
          <button type="button" className="tss-btn tss-btn--primary" onClick={onComplete}>
            Continue <i className="fas fa-arrow-right" aria-hidden="true" />
          </button>
        </div>
      </div>
    );
  }

  const activeRoutingCount = members.filter(m => m.is_accepting_appointments).length;

  return (
    <div className="tss-step">
      {/* Header */}
      <div className="tss-header">
        <div className="tss-step-badge">Step 8</div>
        <h2 className="tss-title">Team & Routing</h2>
        <p className="tss-subtitle">
          Configure how appointments are distributed across your team of {members.length} loan officers.
        </p>
      </div>

      {/* Assignment Strategy */}
      <section className="tss-section">
        <h3 className="tss-section-title">
          <i className="fas fa-random" aria-hidden="true" />
          Assignment Strategy
        </h3>
        <p className="tss-section-desc">
          Choose how new appointment bookings are assigned to team members.
        </p>
        <div className="tss-strategy-grid">
          {ASSIGNMENT_STRATEGIES.map(s => (
            <StrategyCard
              key={s.value}
              strategy={s}
              isSelected={strategy === s.value}
              onSelect={setStrategy}
            />
          ))}
        </div>
      </section>

      {/* Team Members */}
      <section className="tss-section">
        <h3 className="tss-section-title">
          <i className="fas fa-users" aria-hidden="true" />
          Team Members
          <span className="tss-section-count">
            {activeRoutingCount} of {members.length} active
          </span>
        </h3>
        <p className="tss-section-desc">
          Toggle team members on or off for auto-routing and set their daily capacity.
        </p>

        {members.length === 0 ? (
          <div className="tss-empty-members">
            <i className="fas fa-user-plus" aria-hidden="true" />
            <p>No team members found. Add loan officers to your organization to enable team routing.</p>
          </div>
        ) : (
          <div className="tss-members-list">
            {members.map(member => (
              <TeamMemberRow
                key={member.user_id}
                member={member}
                onToggleRouting={handleToggleRouting}
                onCapacityChange={handleCapacityChange}
              />
            ))}
          </div>
        )}
      </section>

      {/* Overflow Settings */}
      <section className="tss-section">
        <h3 className="tss-section-title">
          <i className="fas fa-layer-group" aria-hidden="true" />
          Overflow Settings
        </h3>
        <p className="tss-section-desc">
          Control what happens when all team members are at capacity.
        </p>

        <div className="tss-overflow-toggle">
          <label className="tss-overflow-label">
            <span className="tss-overflow-text">
              <strong>Accept overflow bookings</strong>
              <span>Allow bookings beyond daily capacity limits when all team members are full.</span>
            </span>
            <label className="tss-member-toggle">
              <input
                type="checkbox"
                checked={overflowEnabled}
                onChange={(e) => setOverflowEnabled(e.target.checked)}
              />
              <span className="tss-toggle-track">
                <span className="tss-toggle-thumb" />
              </span>
            </label>
          </label>
        </div>

        {overflowEnabled && (
          <div className="tss-overflow-config">
            <label className="tss-overflow-pct-label" htmlFor="overflow-pct">
              Maximum overflow percentage
            </label>
            <div className="tss-overflow-pct-row">
              <input
                id="overflow-pct"
                type="range"
                min="5"
                max="50"
                step="5"
                value={maxOverflowPct}
                onChange={(e) => setMaxOverflowPct(parseInt(e.target.value, 10))}
                className="tss-overflow-slider"
              />
              <span className="tss-overflow-pct-value">{maxOverflowPct}%</span>
            </div>
            <p className="tss-overflow-hint">
              Team members can accept up to {maxOverflowPct}% more appointments beyond their daily max.
            </p>
          </div>
        )}
      </section>

      {/* Actions */}
      <div className="tss-actions">
        {onBack && (
          <button type="button" className="tss-btn tss-btn--secondary" onClick={onBack}>
            <i className="fas fa-arrow-left" aria-hidden="true" /> Back
          </button>
        )}
        <button
          type="button"
          className="tss-btn tss-btn--primary"
          onClick={handleSave}
          disabled={saving}
        >
          {saving ? (
            <><i className="fas fa-spinner fa-spin" aria-hidden="true" /> Saving...</>
          ) : (
            <>Save & Continue <i className="fas fa-arrow-right" aria-hidden="true" /></>
          )}
        </button>
      </div>
    </div>
  );
};

export default TeamSetupStep;
