/**
 * TeamSection - Calendar Settings
 *
 * Handles team member management (table/card views), assignment strategy,
 * capacity settings, team availability grid, and role definitions.
 * Manager-only section.
 */
import React, { useState } from 'react';
import { calendarSettingsAPI } from '../../services/api';
import { toast } from '../../utils/toast';

const DEFAULT_COLORS = ['#218D8D', '#3b82f6', '#8b5cf6', '#ec4899', '#f59e0b', '#10b981', '#ef4444', '#6366f1'];

const ASSIGNMENT_STRATEGIES = [
  {
    value: 'round_robin', label: 'Round Robin', tagline: 'Distribute evenly',
    description: 'Appointments rotate through team members in order, ensuring everyone gets an equal share regardless of schedule density.',
    icon: 'fa-sync-alt',
  },
  {
    value: 'load_balanced', label: 'Load Balanced', tagline: 'Assign to least busy',
    description: 'Each new appointment goes to the team member with the fewest upcoming bookings, keeping workloads even across the team.',
    icon: 'fa-balance-scale',
  },
  {
    value: 'ai_optimized', label: 'AI Optimized', tagline: 'AI picks best match',
    description: 'AI considers borrower needs, LO specialties, historical close rates, and workload to find the ideal match for each appointment.',
    icon: 'fa-brain', recommended: true,
  },
  {
    value: 'manual', label: 'Manual', tagline: 'Admin assigns all',
    description: 'No automatic assignment. A manager must manually assign every incoming appointment to a team member.',
    icon: 'fa-hand-pointer',
  },
];

const SPECIALTY_OPTIONS = ['FHA', 'VA', 'Jumbo', 'Conventional', 'USDA', 'Non-QM', 'Refinance', 'First-Time Buyer', 'Investment', 'Reverse'];
const TEAM_SORT_OPTIONS = [
  { value: 'name', label: 'Name' },
  { value: 'load', label: 'Current Load' },
  { value: 'capacity', label: 'Capacity' },
];

const TEAM_TABS = [
  { id: 'members', label: 'Members', icon: 'fa-users' },
  { id: 'strategy', label: 'Assignment Strategy', icon: 'fa-random' },
  { id: 'capacity', label: 'Capacity', icon: 'fa-tachometer-alt' },
  { id: 'availability', label: 'Availability', icon: 'fa-calendar-check' },
  { id: 'roles', label: 'Roles', icon: 'fa-user-tag' },
];

export default function TeamSection({
  team,
  setTeam,
  isManager,
  appointmentTypes,
  markChanged,
  loadTabData,
}) {
  const [teamSearch, setTeamSearch] = useState('');
  const [teamSort, setTeamSort] = useState('name');
  const [showInviteForm, setShowInviteForm] = useState(false);
  const [inviteEmail, setInviteEmail] = useState('');
  const [inviting, setInviting] = useState(false);
  const [teamViewMode, setTeamViewMode] = useState('table');
  const [editingMember, setEditingMember] = useState(null);
  const [teamActiveTab, setTeamActiveTab] = useState('members');
  const [teamCapacity, setTeamCapacity] = useState({
    global_max_daily: 8,
    utilization_target: 80,
    overbooking_policy: 'warn',
  });
  const [teamRoles, setTeamRoles] = useState([
    { id: 'lo', name: 'Loan Officer', color: '#218D8D', default_capacity: 8, appointment_types: [], auto_assign: true },
    { id: 'processor', name: 'Processor', color: '#3b82f6', default_capacity: 6, appointment_types: [], auto_assign: true },
    { id: 'closer', name: 'Closer', color: '#8b5cf6', default_capacity: 4, appointment_types: [], auto_assign: false },
  ]);
  const [editingRole, setEditingRole] = useState(null);
  const [showNewRoleForm, setShowNewRoleForm] = useState(false);
  const [selectedAvailDay, setSelectedAvailDay] = useState(null);
  const [priorityDragIdx, setPriorityDragIdx] = useState(null);

  // ---- Helpers ----
  const getTeamMemberInitials = (name) => {
    if (!name) return '?';
    const parts = name.trim().split(/\s+/);
    return parts.length >= 2 ? (parts[0][0] + parts[parts.length - 1][0]).toUpperCase() : name.slice(0, 2).toUpperCase();
  };

  const getRoleColor = (role) => {
    const found = teamRoles.find(r => r.name === role || r.id === role);
    return found?.color || '#64748b';
  };

  const getMemberStatus = (member) => {
    if (!member.is_accepting_appointments) return 'out';
    const load = (member.upcoming_appointments || 0) / (member.max_daily_appointments || 8);
    return load >= 1 ? 'busy' : 'available';
  };

  const getMemberStatusLabel = (status) => {
    if (status === 'out') return 'Out of Office';
    if (status === 'busy') return 'Busy';
    return 'Available';
  };

  const getFilteredTeamMembers = () => {
    let members = [...(team.members || [])];
    if (teamSearch.trim()) {
      const q = teamSearch.toLowerCase();
      members = members.filter(m =>
        (m.name || '').toLowerCase().includes(q) ||
        (m.email || '').toLowerCase().includes(q) ||
        (m.role || '').toLowerCase().includes(q)
      );
    }
    members.sort((a, b) => {
      if (teamSort === 'load') return (b.upcoming_appointments || 0) - (a.upcoming_appointments || 0);
      if (teamSort === 'capacity') return (b.max_daily_appointments || 0) - (a.max_daily_appointments || 0);
      return (a.name || '').localeCompare(b.name || '');
    });
    return members;
  };

  const getMemberAvailabilityForDay = (member, dayIndex) => {
    if (!member.is_accepting_appointments) return 'off';
    const dayNames = ['sunday', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday'];
    const day = dayNames[dayIndex];
    if (member.availability && member.availability[day]) {
      return member.availability[day].enabled ? 'available' : 'off';
    }
    return (dayIndex >= 1 && dayIndex <= 5) ? 'available' : 'off';
  };

  const getUnassignedCount = () => {
    return team.members?.reduce((acc, m) => acc + Math.max(0, (m.max_daily_appointments || 8) - (m.upcoming_appointments || 0)), 0) || 0;
  };

  // ---- Handlers ----
  const handleInviteTeamMember = async () => {
    if (!inviteEmail.trim()) return;
    setInviting(true);
    try {
      await calendarSettingsAPI.inviteTeamMember({ email: inviteEmail.trim() });
      toast.success(`Invitation sent to ${inviteEmail}`);
      setInviteEmail('');
      setShowInviteForm(false);
      loadTabData('team');
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to send invitation');
    } finally {
      setInviting(false);
    }
  };

  const handleRemoveMember = (memberId) => {
    if (!window.confirm('Remove this team member from calendar assignments?')) return;
    setTeam(prev => ({ ...prev, members: prev.members.filter(m => m.user_id !== memberId), total_members: Math.max(0, prev.total_members - 1) }));
    markChanged();
  };

  const handlePriorityDragStart = (idx) => setPriorityDragIdx(idx);
  const handlePriorityDragOver = (e, idx) => {
    e.preventDefault();
    if (priorityDragIdx === null || priorityDragIdx === idx) return;
    setTeam(prev => { const members = [...prev.members]; const [moved] = members.splice(priorityDragIdx, 1); members.splice(idx, 0, moved); return { ...prev, members }; });
    setPriorityDragIdx(idx);
    markChanged();
  };
  const handlePriorityDragEnd = () => setPriorityDragIdx(null);

  const handleAddRole = (roleData) => {
    const id = roleData.name.toLowerCase().replace(/\s+/g, '_') + '_' + Date.now();
    setTeamRoles(prev => [...prev, { ...roleData, id }]);
    setShowNewRoleForm(false);
    markChanged();
  };

  const handleUpdateRole = (roleId, data) => {
    setTeamRoles(prev => prev.map(r => r.id === roleId ? { ...r, ...data } : r));
    setEditingRole(null);
    markChanged();
  };

  const handleDeleteRole = (roleId) => {
    if (!window.confirm('Delete this role?')) return;
    setTeamRoles(prev => prev.filter(r => r.id !== roleId));
    markChanged();
  };

  // ---- Not a manager ----
  if (!isManager) {
    return (
      <section className="cal-settings-section" role="tabpanel" id="panel-team" aria-labelledby="calnav-team">
        <div className="empty-state">
          <i className="fas fa-lock"></i>
          <p>Team calendar settings are available to managers only.</p>
        </div>
      </section>
    );
  }

  const filteredMembers = getFilteredTeamMembers();

  return (
    <section className="cal-settings-section" role="tabpanel" id="panel-team" aria-labelledby="calnav-team">
      <div className="team-sub-tabs" role="tablist" aria-label="Team settings sections">
        {TEAM_TABS.map(tab => (
          <button key={tab.id} role="tab" aria-selected={teamActiveTab === tab.id} className={`team-sub-tab ${teamActiveTab === tab.id ? 'active' : ''}`} onClick={() => setTeamActiveTab(tab.id)}>
            <i className={`fas ${tab.icon}`}></i> <span>{tab.label}</span>
          </button>
        ))}
      </div>

      {/* ---- Members Tab ---- */}
      {teamActiveTab === 'members' && (
        <div className="team-tab-content">
          <div className="team-toolbar">
            <div className="team-search-wrap">
              <i className="fas fa-search team-search-icon"></i>
              <input type="text" placeholder="Search by name, email, or role..." value={teamSearch} onChange={(e) => setTeamSearch(e.target.value)} className="team-search-input" />
              {teamSearch && <button className="team-search-clear" onClick={() => setTeamSearch('')} aria-label="Clear search"><i className="fas fa-times"></i></button>}
            </div>
            <div className="team-toolbar-actions">
              <select value={teamSort} onChange={(e) => setTeamSort(e.target.value)} className="team-sort-select" aria-label="Sort team members">
                {TEAM_SORT_OPTIONS.map(opt => <option key={opt.value} value={opt.value}>{opt.label}</option>)}
              </select>
              <div className="team-view-toggle" role="radiogroup" aria-label="View mode">
                <button className={`view-toggle-btn ${teamViewMode === 'table' ? 'active' : ''}`} onClick={() => setTeamViewMode('table')} aria-label="Table view"><i className="fas fa-list"></i></button>
                <button className={`view-toggle-btn ${teamViewMode === 'card' ? 'active' : ''}`} onClick={() => setTeamViewMode('card')} aria-label="Card view"><i className="fas fa-th-large"></i></button>
              </div>
              <button className="btn-primary btn-sm" onClick={() => setShowInviteForm(true)}><i className="fas fa-plus"></i> Invite</button>
            </div>
          </div>
          {showInviteForm && (
            <div className="team-invite-form">
              <input type="email" placeholder="Enter email address..." value={inviteEmail} onChange={(e) => setInviteEmail(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && handleInviteTeamMember()} className="invite-email-input" autoFocus />
              <button className="btn-primary btn-sm" onClick={handleInviteTeamMember} disabled={inviting || !inviteEmail.trim()}>{inviting ? 'Sending...' : 'Send Invite'}</button>
              <button className="btn-secondary btn-sm" onClick={() => { setShowInviteForm(false); setInviteEmail(''); }}>Cancel</button>
            </div>
          )}

          {teamViewMode === 'table' && (
            <div className="team-table-wrap">
              <table className="team-table team-table-enhanced">
                <thead><tr><th className="th-member">Member</th><th className="th-role">Role</th><th className="th-capacity">Capacity</th><th className="th-status">Status</th><th className="th-actions">Actions</th></tr></thead>
                <tbody>
                  {filteredMembers.map(member => {
                    const status = getMemberStatus(member);
                    const load = member.upcoming_appointments || 0;
                    const cap = member.max_daily_appointments || 8;
                    const pct = Math.min(100, Math.round((load / cap) * 100));
                    return (
                      <tr key={member.user_id} className={editingMember === member.user_id ? 'editing-row' : ''}>
                        <td className="td-member">
                          <div className="member-identity">
                            <div className="member-avatar" style={{ backgroundColor: getRoleColor(member.role) }} title={member.name}>{getTeamMemberInitials(member.name)}</div>
                            <div className="member-info"><span className="member-name">{member.name}</span><span className="member-email">{member.email}</span></div>
                          </div>
                        </td>
                        <td className="td-role"><span className="role-badge" style={{ '--role-color': getRoleColor(member.role) }}>{member.role || 'Loan Officer'}</span></td>
                        <td className="td-capacity">
                          <div className="capacity-bar-wrap"><div className="capacity-bar"><div className={`capacity-bar-fill ${pct >= 90 ? 'critical' : pct >= 70 ? 'warning' : ''}`} style={{ width: `${pct}%` }}></div></div><span className="capacity-label">{load}/{cap}</span></div>
                        </td>
                        <td className="td-status"><span className={`status-badge status-${status}`}><span className="status-dot-indicator"></span>{getMemberStatusLabel(status)}</span></td>
                        <td className="td-actions">
                          <button className="btn-icon-sm" onClick={() => setEditingMember(editingMember === member.user_id ? null : member.user_id)} title="Edit member"><i className="fas fa-pen"></i></button>
                          <button className="btn-icon-sm btn-icon-danger" onClick={() => handleRemoveMember(member.user_id)} title="Remove member"><i className="fas fa-times"></i></button>
                        </td>
                      </tr>
                    );
                  })}
                  {filteredMembers.length === 0 && <tr><td colSpan={5} className="empty-row">{teamSearch ? 'No members match your search' : 'No team members found'}</td></tr>}
                </tbody>
              </table>
            </div>
          )}

          {teamViewMode === 'card' && (
            <div className="team-cards-grid">
              {filteredMembers.map(member => {
                const status = getMemberStatus(member);
                const load = member.upcoming_appointments || 0;
                const cap = member.max_daily_appointments || 8;
                const pct = Math.min(100, Math.round((load / cap) * 100));
                return (
                  <div key={member.user_id} className="team-member-card">
                    <div className="member-card-header">
                      <div className="member-avatar member-avatar-lg" style={{ backgroundColor: getRoleColor(member.role) }}>{getTeamMemberInitials(member.name)}</div>
                      <span className={`status-badge status-${status}`}><span className="status-dot-indicator"></span>{getMemberStatusLabel(status)}</span>
                    </div>
                    <h4 className="member-card-name">{member.name}</h4>
                    <span className="role-badge" style={{ '--role-color': getRoleColor(member.role) }}>{member.role || 'Loan Officer'}</span>
                    <span className="member-card-email">{member.email}</span>
                    <div className="member-card-capacity">
                      <div className="capacity-bar-wrap"><div className="capacity-bar"><div className={`capacity-bar-fill ${pct >= 90 ? 'critical' : pct >= 70 ? 'warning' : ''}`} style={{ width: `${pct}%` }}></div></div><span className="capacity-label">{load}/{cap} appts</span></div>
                    </div>
                    <div className="member-card-actions">
                      <button className="btn-secondary btn-sm" onClick={() => setEditingMember(member.user_id)}><i className="fas fa-pen"></i> Edit</button>
                      <button className="btn-secondary btn-sm btn-danger-outline" onClick={() => handleRemoveMember(member.user_id)}><i className="fas fa-times"></i> Remove</button>
                    </div>
                  </div>
                );
              })}
              {filteredMembers.length === 0 && <div className="empty-state"><i className="fas fa-users"></i><p>{teamSearch ? 'No members match' : 'No team members'}</p></div>}
            </div>
          )}

          {editingMember && (() => { const member = team.members.find(m => m.user_id === editingMember); if (!member) return null; return (
            <div className="member-edit-panel">
              <div className="member-edit-header"><h4>Edit: {member.name}</h4><button className="btn-icon-sm" onClick={() => setEditingMember(null)}><i className="fas fa-times"></i></button></div>
              <div className="member-edit-body">
                <div className="form-field"><label>Max Daily Appointments</label><input type="number" min="0" max="24" value={member.max_daily_appointments} className="capacity-input" onChange={(e) => { const val = parseInt(e.target.value) || 0; setTeam(prev => ({ ...prev, members: prev.members.map(m => m.user_id === member.user_id ? { ...m, max_daily_appointments: val } : m) })); markChanged(); }} /></div>
                <div className="form-field"><label>Accepting Appointments</label><label className="toggle-switch"><input type="checkbox" checked={member.is_accepting_appointments} onChange={(e) => { setTeam(prev => ({ ...prev, members: prev.members.map(m => m.user_id === member.user_id ? { ...m, is_accepting_appointments: e.target.checked } : m) })); markChanged(); }} /><span className="toggle-slider"></span></label></div>
                <div className="form-field"><label>Specialties</label><div className="specialty-chips">{SPECIALTY_OPTIONS.map(spec => { const active = (member.specialties || []).includes(spec); return (<button key={spec} type="button" className={`specialty-chip ${active ? 'active' : ''}`} onClick={() => { const newSpecs = active ? (member.specialties || []).filter(s => s !== spec) : [...(member.specialties || []), spec]; setTeam(prev => ({ ...prev, members: prev.members.map(m => m.user_id === member.user_id ? { ...m, specialties: newSpecs } : m) })); markChanged(); }}>{spec}</button>); })}</div></div>
              </div>
            </div>
          ); })()}
        </div>
      )}

      {/* ---- Strategy Tab ---- */}
      {teamActiveTab === 'strategy' && (
        <div className="team-tab-content">
          <p className="section-description">Choose how new appointments are distributed across your team.</p>
          <div className="strategy-cards-grid">
            {ASSIGNMENT_STRATEGIES.map(strategy => {
              const isSelected = team.assignment_strategy === strategy.value;
              return (
                <label key={strategy.value} className={`strategy-card ${isSelected ? 'selected' : ''}`}>
                  <input type="radio" name="assignment_strategy" value={strategy.value} checked={isSelected} onChange={() => { setTeam(prev => ({ ...prev, assignment_strategy: strategy.value })); markChanged(); }} className="sr-only" />
                  <div className="strategy-card-radio"><span className={`radio-circle ${isSelected ? 'checked' : ''}`}></span></div>
                  <div className="strategy-card-icon"><i className={`fas ${strategy.icon}`}></i></div>
                  <div className="strategy-card-body">
                    <h4>{strategy.label}</h4>
                    <p className="strategy-card-desc">{strategy.description}</p>
                    {strategy.value === 'round_robin' && isSelected && (
                      <div className="strategy-detail"><div className="rr-animation">{(team.members || []).slice(0, 4).map((m, i) => (<div key={m.user_id} className={`rr-dot ${i === 0 ? 'rr-active' : ''}`}><div className="member-avatar member-avatar-xs" style={{ backgroundColor: getRoleColor(m.role) }}>{getTeamMemberInitials(m.name)}</div></div>))}<div className="rr-arrow"><i className="fas fa-long-arrow-alt-right"></i></div></div></div>
                    )}
                    {strategy.value === 'load_balanced' && isSelected && (
                      <div className="strategy-detail"><div className="lb-bars">{(team.members || []).slice(0, 4).map(m => { const p = Math.min(100, Math.round(((m.upcoming_appointments || 0) / (m.max_daily_appointments || 8)) * 100)); return (<div key={m.user_id} className="lb-bar-item"><span className="lb-bar-name">{(m.name || '').split(' ')[0]}</span><div className="lb-bar-track"><div className="lb-bar-fill" style={{ width: `${p}%` }}></div></div><span className="lb-bar-pct">{p}%</span></div>); })}</div></div>
                    )}
                    {strategy.value === 'ai_optimized' && isSelected && (
                      <div className="strategy-detail"><div className="strategy-detail-note"><i className="fas fa-brain"></i><span>Drag to reorder member priority.</span></div><div className="priority-list">{(team.members || []).map((m, idx) => (<div key={m.user_id} className={`priority-item ${priorityDragIdx === idx ? 'dragging' : ''}`} draggable onDragStart={() => handlePriorityDragStart(idx)} onDragOver={(e) => handlePriorityDragOver(e, idx)} onDragEnd={handlePriorityDragEnd}><span className="priority-rank">#{idx + 1}</span><i className="fas fa-grip-vertical priority-grip"></i><span className="priority-name">{m.name}</span></div>))}</div></div>
                    )}
                    {strategy.value === 'manual' && isSelected && (
                      <div className="strategy-detail"><div className="strategy-detail-note manual-note"><i className="fas fa-hand-pointer"></i><span>{getUnassignedCount()} open slots for manual assignment</span></div></div>
                    )}
                  </div>
                </label>
              );
            })}
          </div>
          <div className="strategy-option-row"><label className="checkbox-label"><input type="checkbox" checked={team.apply_to_new_only} onChange={(e) => { setTeam(prev => ({ ...prev, apply_to_new_only: e.target.checked })); markChanged(); }} /> Only apply to new appointments</label></div>
        </div>
      )}

      {/* ---- Capacity Tab ---- */}
      {teamActiveTab === 'capacity' && (
        <div className="team-tab-content">
          <p className="section-description">Control how many appointments your team can handle.</p>
          <div className="capacity-global-section">
            <h3 className="subsection-title">Global Defaults</h3>
            <div className="capacity-form-grid">
              <div className="form-field"><label htmlFor="global-max-daily">Max Appointments Per Day (Per Member)</label><input id="global-max-daily" type="number" min="1" max="24" value={teamCapacity.global_max_daily} onChange={(e) => { setTeamCapacity(prev => ({ ...prev, global_max_daily: parseInt(e.target.value) || 1 })); markChanged(); }} /><span className="form-hint">Applies to members without an override</span></div>
              <div className="form-field"><label htmlFor="util-target">Utilization Goal</label><div className="input-with-suffix"><input id="util-target" type="number" min="10" max="100" value={teamCapacity.utilization_target} onChange={(e) => { setTeamCapacity(prev => ({ ...prev, utilization_target: parseInt(e.target.value) || 80 })); markChanged(); }} /><span className="input-suffix">%</span></div><span className="form-hint">Target percentage of capacity</span></div>
              <div className="form-field"><label htmlFor="overbook-policy">Overbooking Policy</label><select id="overbook-policy" value={teamCapacity.overbooking_policy} onChange={(e) => { setTeamCapacity(prev => ({ ...prev, overbooking_policy: e.target.value })); markChanged(); }}><option value="block">Block - Prevent when full</option><option value="warn">Warn - Allow with warning</option><option value="allow">Allow - No restrictions</option></select><span className="form-hint">When a member reaches max capacity</span></div>
            </div>
          </div>
          <div className="capacity-overrides-section">
            <h3 className="subsection-title">Per-Member Capacity</h3>
            <div className="capacity-member-list">
              {(team.members || []).map(member => {
                const load = member.upcoming_appointments || 0;
                const cap = member.max_daily_appointments || teamCapacity.global_max_daily;
                const pct = Math.min(100, Math.round((load / cap) * 100));
                return (
                  <div key={member.user_id} className="capacity-member-row">
                    <div className="member-identity member-identity-compact"><div className="member-avatar member-avatar-sm" style={{ backgroundColor: getRoleColor(member.role) }}>{getTeamMemberInitials(member.name)}</div><span className="member-name">{member.name}</span></div>
                    <div className="capacity-member-controls">
                      <input type="number" min="0" max="24" value={cap} className="capacity-input" onChange={(e) => { const val = parseInt(e.target.value) || 0; setTeam(prev => ({ ...prev, members: prev.members.map(m => m.user_id === member.user_id ? { ...m, max_daily_appointments: val } : m) })); markChanged(); }} />
                      <div className="capacity-bar-wide-wrap"><div className="capacity-bar capacity-bar-wide"><div className={`capacity-bar-fill ${pct >= 90 ? 'critical' : pct >= 70 ? 'warning' : ''}`} style={{ width: `${pct}%` }}></div><div className="capacity-bar-target" style={{ left: `${teamCapacity.utilization_target}%` }}></div></div><div className="capacity-bar-labels"><span>{load} booked</span><span>{pct}%</span></div></div>
                    </div>
                  </div>
                );
              })}
              {(!team.members || team.members.length === 0) && <div className="empty-state-inline">No team members to configure</div>}
            </div>
          </div>
          <div className="capacity-overflow-section">
            <h3 className="subsection-title">Overflow Handling</h3>
            <div className="form-field"><label className="checkbox-label"><input type="checkbox" checked={team.overflow?.enabled || false} onChange={(e) => { setTeam(prev => ({ ...prev, overflow: { ...prev.overflow, enabled: e.target.checked } })); markChanged(); }} /> Enable overflow when all members are at capacity</label></div>
            {team.overflow?.enabled && <div className="form-field"><label>Max Overflow %</label><div className="input-with-suffix"><input type="number" min="0" max="100" value={team.overflow.max_overflow_pct} onChange={(e) => { setTeam(prev => ({ ...prev, overflow: { ...prev.overflow, max_overflow_pct: parseInt(e.target.value) || 0 } })); markChanged(); }} /><span className="input-suffix">%</span></div></div>}
          </div>
        </div>
      )}

      {/* ---- Availability Tab ---- */}
      {teamActiveTab === 'availability' && (
        <div className="team-tab-content">
          <p className="section-description">Weekly availability overview for each team member.</p>
          <div className="team-availability-grid-wrap">
            <div className="team-availability-grid" role="grid">
              <div className="avail-grid-header" role="row"><div className="avail-grid-corner" role="columnheader">Member</div>{['Mon','Tue','Wed','Thu','Fri','Sat','Sun'].map(d => <div key={d} className="avail-grid-day-header" role="columnheader">{d}</div>)}</div>
              {(team.members || []).map(member => (
                <div key={member.user_id} className="avail-grid-row" role="row">
                  <div className="avail-grid-member" role="rowheader"><div className="member-avatar member-avatar-xs" style={{ backgroundColor: getRoleColor(member.role) }}>{getTeamMemberInitials(member.name)}</div><span>{(member.name || '').split(' ')[0]}</span></div>
                  {[1,2,3,4,5,6,0].map(dayIdx => {
                    const avail = getMemberAvailabilityForDay(member, dayIdx);
                    const isSel = selectedAvailDay?.memberId === member.user_id && selectedAvailDay?.day === dayIdx;
                    return <button key={dayIdx} className={`avail-grid-cell avail-${avail} ${isSel ? 'avail-selected' : ''}`} role="gridcell" onClick={() => setSelectedAvailDay(isSel ? null : { memberId: member.user_id, day: dayIdx })} title={avail}>{avail === 'available' ? <i className="fas fa-check"></i> : avail === 'busy' ? <i className="fas fa-clock"></i> : <i className="fas fa-minus"></i>}</button>;
                  })}
                </div>
              ))}
              {(!team.members || team.members.length === 0) && <div className="avail-grid-empty">No team members</div>}
            </div>
            <div className="avail-legend"><span className="avail-legend-item"><span className="avail-dot avail-dot-available"></span> Available</span><span className="avail-legend-item"><span className="avail-dot avail-dot-busy"></span> Busy</span><span className="avail-legend-item"><span className="avail-dot avail-dot-off"></span> Off</span></div>
            {selectedAvailDay && (() => { const member = team.members.find(m => m.user_id === selectedAvailDay.memberId); if (!member) return null; const dn = ['Sunday','Monday','Tuesday','Wednesday','Thursday','Friday','Saturday']; return (
              <div className="avail-detail-panel"><div className="avail-detail-header"><h4>{member.name} - {dn[selectedAvailDay.day]}</h4><button className="btn-icon-sm" onClick={() => setSelectedAvailDay(null)}><i className="fas fa-times"></i></button></div><div className="avail-detail-body"><p><strong>Status:</strong> {getMemberAvailabilityForDay(member, selectedAvailDay.day) === 'available' ? 'Available' : getMemberAvailabilityForDay(member, selectedAvailDay.day) === 'busy' ? 'Busy' : 'Off'}</p><p><strong>Max Daily:</strong> {member.max_daily_appointments || 8}</p><p><strong>Current Load:</strong> {member.upcoming_appointments || 0}</p>{(member.specialties || []).length > 0 && <p><strong>Specialties:</strong> {member.specialties.join(', ')}</p>}</div></div>
            ); })()}
          </div>
        </div>
      )}

      {/* ---- Roles Tab ---- */}
      {teamActiveTab === 'roles' && (
        <div className="team-tab-content">
          <p className="section-description">Define roles, default capacities, and auto-assignment eligibility.</p>
          <div className="roles-list">
            {teamRoles.map(role => {
              const isEd = editingRole === role.id;
              return (
                <div key={role.id} className={`role-card ${isEd ? 'role-editing' : ''}`}>
                  <div className="role-card-header">
                    <div className="role-card-identity"><span className="role-color-dot" style={{ backgroundColor: role.color }}></span>{isEd ? <input type="text" value={role.name} className="role-name-input" onChange={(e) => setTeamRoles(prev => prev.map(r => r.id === role.id ? { ...r, name: e.target.value } : r))} autoFocus /> : <h4 className="role-card-name">{role.name}</h4>}</div>
                    <div className="role-card-actions">{isEd ? (<><button className="btn-primary btn-sm" onClick={() => handleUpdateRole(role.id, role)}>Save</button><button className="btn-secondary btn-sm" onClick={() => setEditingRole(null)}>Cancel</button></>) : (<><button className="btn-icon-sm" onClick={() => setEditingRole(role.id)} title="Edit"><i className="fas fa-pen"></i></button><button className="btn-icon-sm btn-icon-danger" onClick={() => handleDeleteRole(role.id)} title="Delete"><i className="fas fa-trash"></i></button></>)}</div>
                  </div>
                  {isEd && (
                    <div className="role-card-edit-body">
                      <div className="form-field"><label>Color</label><div className="color-picker">{DEFAULT_COLORS.map(c => <button key={c} type="button" className={`color-swatch ${role.color === c ? 'selected' : ''}`} style={{ backgroundColor: c }} onClick={() => setTeamRoles(prev => prev.map(r => r.id === role.id ? { ...r, color: c } : r))} />)}</div></div>
                      <div className="form-field"><label>Default Max Daily</label><input type="number" min="1" max="24" value={role.default_capacity} className="capacity-input" onChange={(e) => setTeamRoles(prev => prev.map(r => r.id === role.id ? { ...r, default_capacity: parseInt(e.target.value) || 1 } : r))} /></div>
                      <div className="form-field"><label>Appointment Types</label><div className="specialty-chips">{(appointmentTypes || []).map(at => { const act = (role.appointment_types || []).includes(at.id); return <button key={at.id} type="button" className={`specialty-chip ${act ? 'active' : ''}`} onClick={() => { const nt = act ? role.appointment_types.filter(id => id !== at.id) : [...(role.appointment_types || []), at.id]; setTeamRoles(prev => prev.map(r => r.id === role.id ? { ...r, appointment_types: nt } : r)); }}>{at.type_name}</button>; })}{(!appointmentTypes || appointmentTypes.length === 0) && <span className="form-hint">No appointment types defined</span>}</div></div>
                      <div className="form-field"><label className="checkbox-label"><input type="checkbox" checked={role.auto_assign} onChange={(e) => setTeamRoles(prev => prev.map(r => r.id === role.id ? { ...r, auto_assign: e.target.checked } : r))} /> Eligible for auto-assignment</label></div>
                    </div>
                  )}
                  {!isEd && <div className="role-card-meta"><span className="role-meta-item"><i className="fas fa-calendar-day"></i> {role.default_capacity} max/day</span><span className="role-meta-item"><i className={`fas ${role.auto_assign ? 'fa-check-circle' : 'fa-times-circle'}`}></i> {role.auto_assign ? 'Auto-assign on' : 'Auto-assign off'}</span><span className="role-meta-item"><i className="fas fa-users"></i> {(team.members || []).filter(m => m.role === role.name || m.role === role.id).length} members</span></div>}
                </div>
              );
            })}
          </div>
          {showNewRoleForm ? (
            <div className="role-card role-new-form">
              <div className="role-card-edit-body">
                <div className="form-field"><label>Role Name</label><input type="text" placeholder="e.g. Senior Loan Officer" className="role-name-input" id="new-role-name" autoFocus /></div>
                <div className="form-field"><label>Default Max Daily</label><input type="number" min="1" max="24" defaultValue={8} className="capacity-input" id="new-role-cap" /></div>
                <div className="form-actions"><button className="btn-secondary btn-sm" onClick={() => setShowNewRoleForm(false)}>Cancel</button><button className="btn-primary btn-sm" onClick={() => { const n = document.getElementById('new-role-name')?.value?.trim(); if (!n) { toast.error('Name required'); return; } handleAddRole({ name: n, color: '#64748b', default_capacity: parseInt(document.getElementById('new-role-cap')?.value) || 8, appointment_types: [], auto_assign: true }); }}>Create Role</button></div>
              </div>
            </div>
          ) : <button className="btn-outline add-role-btn" onClick={() => setShowNewRoleForm(true)}><i className="fas fa-plus"></i> Add Role</button>}
        </div>
      )}
    </section>
  );
}
