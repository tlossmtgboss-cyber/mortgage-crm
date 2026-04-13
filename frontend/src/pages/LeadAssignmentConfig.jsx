import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { toast } from 'react-toastify';
import { usePermissions } from '../contexts/PermissionContext';
import { getAuthHeaders } from '../utils/auth';
import { API_BASE_URL } from '../services/api';

const API = '/api/v1/admin/lead-assignment';

/*
 * ═══════════════════════════════════════════════════════════════════════════
 *  UNIFIED TEAM & LEAD ASSIGNMENT
 *
 *  Single page that combines:
 *    1. Workflow Team Setup  → assign people to workflow roles
 *    2. Assignment Pool      → who is eligible for new lead distribution
 *    3. Distribution Config  → how new leads are routed (strategy + rules)
 *    4. Exceptions           → PTO / blocks
 *    5. Test / Audit / Stats → operational visibility
 * ═══════════════════════════════════════════════════════════════════════════
 */

// ─── Constants ────────────────────────────────────────────────────────────────

const STRATEGIES = [
  { value: 'round_robin',   label: 'Round Robin',   icon: '🔄', desc: 'Rotate evenly through pool members' },
  { value: 'weighted',      label: 'Weighted',      icon: '⚖️',  desc: 'Distribute based on weight percentages' },
  { value: 'geographic',    label: 'Geographic',    icon: '🗺️',  desc: 'Route by lead state to specific LOs' },
  { value: 'load_balanced', label: 'Load Balanced', icon: '📊', desc: 'Assign to LO with fewest active leads' },
  { value: 'rule_based',    label: 'Rule Based',    icon: '🎯', desc: 'Evaluate custom rules in priority order' },
  { value: 'manual',        label: 'Manual',        icon: '✋', desc: 'No auto-assignment — unassigned queue' },
];

const CONDITION_FIELDS = [
  { value: 'loan_amount',   label: 'Loan Amount',   type: 'number' },
  { value: 'loan_purpose',  label: 'Loan Purpose',  type: 'select', options: ['purchase','refinance','cash_out','heloc'] },
  { value: 'loan_type',     label: 'Loan Type',     type: 'select', options: ['conventional','fha','va','usda','jumbo','non_qm'] },
  { value: 'property_type', label: 'Property Type',  type: 'select', options: ['single_family','condo','townhouse','multi_family'] },
  { value: 'state',         label: 'State',          type: 'text' },
  { value: 'credit_score',  label: 'Credit Score',   type: 'number' },
  { value: 'source',        label: 'Lead Source',     type: 'text' },
  { value: 'ai_score',      label: 'AI Score',        type: 'number' },
];

const OPERATORS = [
  { value: 'eq',   label: '=' },
  { value: 'neq',  label: '!=' },
  { value: 'gt',   label: '>' },
  { value: 'gte',  label: '>=' },
  { value: 'lt',   label: '<' },
  { value: 'lte',  label: '<=' },
  { value: 'in',   label: 'in' },
  { value: 'contains', label: 'contains' },
];

const ROLE_META = {
  'Loan Officer':           { icon: '👔', desc: 'Primary borrower contact' },
  'Production Assistant 1': { icon: '📋', desc: 'Initial paperwork & doc collection' },
  'Production Assistant 2': { icon: '📝', desc: 'Processing assistance & follow-ups' },
  'Processor':              { icon: '⚙️',  desc: 'Prepares loan file for underwriting' },
  'Underwriter':            { icon: '🔍', desc: 'Reviews and approves the loan' },
  'Closer':                 { icon: '✅', desc: 'Prepares closing documents' },
  'Funder':                 { icon: '💰', desc: 'Handles funding & disbursement' },
  'Post-Closer':            { icon: '📦', desc: 'Manages post-closing tasks' },
  'Concierge':              { icon: '🎯', desc: 'Client experience & coordination' },
  'Team Lead':              { icon: '👑', desc: 'Oversees team operations' },
  'Branch Manager':         { icon: '🏢', desc: 'Branch-level oversight' },
};

const US_STATES = [
  'AL','AK','AZ','AR','CA','CO','CT','DE','FL','GA','HI','ID','IL','IN','IA',
  'KS','KY','LA','ME','MD','MA','MI','MN','MS','MO','MT','NE','NV','NH','NJ',
  'NM','NY','NC','ND','OH','OK','OR','PA','RI','SC','SD','TN','TX','UT','VT',
  'VA','WA','WV','WI','WY','DC',
];

// ─── Main Component ───────────────────────────────────────────────────────────

export default function LeadAssignmentConfig() {
  const navigate = useNavigate();
  const { userRole, hasAnyPermission, isAdmin } = usePermissions();

  // Permission check - only admins/managers can configure lead assignment
  const canAccessLeadAssignment = isAdmin || hasAnyPermission(['admin.manage', 'leads.assign', 'leads.manage', 'system.admin']) ||
    userRole === 'admin' || userRole === 'site_admin' || userRole === 'management';

  const [section, setSection] = useState('team');
  const [loading, setLoading] = useState(true);

  // Workflow roles
  const [roleAssignments, setRoleAssignments] = useState([]);
  const [teamMembers, setTeamMembers] = useState([]);

  // Lead assignment
  const [config, setConfig] = useState(null);
  const [pool, setPool] = useState([]);
  const [rules, setRules] = useState([]);
  const [exceptions, setExceptions] = useState([]);

  const authHeaders = useCallback(() => getAuthHeaders(), []);
  const jsonHeaders = useCallback(() => ({
    ...getAuthHeaders(),
    'Content-Type': 'application/json',
  }), []);

  // ── Load everything in parallel ──
  const loadAll = useCallback(async () => {
    setLoading(true);
    try {
      const h = authHeaders();
      const [rolesRes, membersRes, cfgRes, poolRes, rulesRes, excRes] = await Promise.allSettled([
        fetch(`${API_BASE_URL}/api/v1/settings/team-roles`, { headers: h }),
        fetch(`${API_BASE_URL}/api/v1/team/members`, { headers: h }),
        fetch(`${API}/config`, { headers: h }),
        fetch(`${API}/pool`, { headers: h }),
        fetch(`${API}/rules`, { headers: h }),
        fetch(`${API}/exceptions`, { headers: h }),
      ]);

      const parse = async (r) => r.status === 'fulfilled' && r.value.ok ? r.value.json() : null;

      const roles   = await parse(rolesRes);
      const members = await parse(membersRes);
      const cfg     = await parse(cfgRes);
      const pl      = await parse(poolRes);
      const rl      = await parse(rulesRes);
      const ex      = await parse(excRes);

      if (roles)   setRoleAssignments(roles.assignments || roles || []);
      if (members) setTeamMembers(members.team_members || members || []);
      if (cfg?.success)   setConfig(cfg.data);
      if (pl?.success)    setPool(pl.data || []);
      if (rl?.success)    setRules(rl.data || []);
      if (ex?.success)    setExceptions(ex.data || []);
    } catch (err) {
      toast.error('Failed to load configuration');
    } finally {
      setLoading(false);
    }
  }, [authHeaders]);

  useEffect(() => { loadAll(); }, [loadAll]);

  const sections = [
    { key: 'team',       label: 'Workflow Team',     icon: '👥' },
    { key: 'pool',       label: 'Assignment Pool',   icon: '🏊' },
    { key: 'strategy',   label: 'Distribution',      icon: '🔀' },
    { key: 'rules',      label: 'Routing Rules',     icon: '🎯' },
    { key: 'exceptions', label: 'Exceptions',        icon: '🚫' },
    { key: 'test',       label: 'Test',              icon: '🧪' },
    { key: 'audit',      label: 'Audit Log',         icon: '📋' },
    { key: 'stats',      label: 'Stats',             icon: '📊' },
  ];

  // Access denied if user doesn't have lead assignment permissions
  if (!canAccessLeadAssignment) {
    return (
      <div style={s.container}>
        <div style={{ textAlign: 'center', padding: '60px 20px' }}>
          <h2>Access Denied</h2>
          <p>You don't have permission to configure lead assignment.</p>
          <button onClick={() => navigate('/dashboard')} style={{ marginTop: '16px', padding: '10px 24px', backgroundColor: '#3b82f6', color: '#fff', border: 'none', borderRadius: '8px', cursor: 'pointer' }}>
            Return to Dashboard
          </button>
        </div>
      </div>
    );
  }

  if (loading) return <div style={s.container}><div style={s.loading}>Loading team &amp; assignment configuration...</div></div>;

  return (
    <div style={s.container}>
      {/* ── Page Header ── */}
      <div style={s.pageHeader}>
        <div>
          <h1 style={s.pageTitle}>Team &amp; Lead Assignment</h1>
          <p style={s.pageSubtitle}>
            Set up your workflow team, configure how new leads are distributed, and manage routing rules
          </p>
        </div>
        <div style={s.headerBadge}>
          <span style={s.badgeStrategy}>{config?.strategy?.replace('_', ' ') || 'round robin'}</span>
          <span style={s.badgeCount}>{pool.length} in pool</span>
        </div>
      </div>

      {/* ── Section Nav ── */}
      <div style={s.nav}>
        {sections.map(sec => (
          <button
            key={sec.key}
            onClick={() => setSection(sec.key)}
            style={{
              ...s.navBtn,
              ...(section === sec.key ? s.navBtnActive : {}),
            }}
          >
            <span style={s.navIcon}>{sec.icon}</span>
            {sec.label}
          </button>
        ))}
      </div>

      {/* ── Content ── */}
      <div style={s.content}>
        {section === 'team'       && <WorkflowTeam assignments={roleAssignments} members={teamMembers} onRefresh={loadAll} authHeaders={authHeaders} jsonHeaders={jsonHeaders} />}
        {section === 'pool'       && <AssignmentPool pool={pool} members={teamMembers} onRefresh={loadAll} jsonHeaders={jsonHeaders} authHeaders={authHeaders} />}
        {section === 'strategy'   && <StrategyConfig config={config} onRefresh={loadAll} jsonHeaders={jsonHeaders} />}
        {section === 'rules'      && <RoutingRules rules={rules} onRefresh={loadAll} jsonHeaders={jsonHeaders} authHeaders={authHeaders} />}
        {section === 'exceptions' && <Exceptions exceptions={exceptions} onRefresh={loadAll} jsonHeaders={jsonHeaders} authHeaders={authHeaders} />}
        {section === 'test'       && <TestPanel jsonHeaders={jsonHeaders} />}
        {section === 'audit'      && <AuditLog authHeaders={authHeaders} />}
        {section === 'stats'      && <Stats authHeaders={authHeaders} />}
      </div>
    </div>
  );
}


// ═══════════════════════════════════════════════════════════════════════════════
//  SECTION 1 — WORKFLOW TEAM
// ═══════════════════════════════════════════════════════════════════════════════

function WorkflowTeam({ assignments, members, onRefresh, authHeaders, jsonHeaders }) {
  const [saving, setSaving] = useState({});

  const displayRoles = assignments.filter(a => a.role_name in ROLE_META);
  const finalRoles = displayRoles.length > 0 ? displayRoles : assignments;

  const handleAssign = async (roleId, userId) => {
    setSaving(p => ({ ...p, [roleId]: true }));
    try {
      if (userId) {
        const res = await fetch(`${API_BASE_URL}/api/v1/settings/team-roles/${roleId}`, {
          method: 'POST', headers: jsonHeaders(),
          body: JSON.stringify({ user_id: parseInt(userId) }),
        });
        if (res.ok) toast.success('Role assigned');
        else toast.error('Failed to assign role');
      } else {
        const res = await fetch(`${API_BASE_URL}/api/v1/settings/team-roles/${roleId}`, {
          method: 'DELETE', headers: authHeaders(),
        });
        if (res.ok) toast.success('Assignment removed');
        else toast.error('Failed to remove');
      }
      onRefresh();
    } catch { toast.error('Failed to update'); }
    finally { setSaving(p => ({ ...p, [roleId]: false })); }
  };

  return (
    <div>
      <SectionHeader
        title="Workflow Team Assignments"
        subtitle="Assign team members to org-wide workflow roles. These apply to ALL loans and leads."
      />
      <div style={s.roleGrid}>
        {finalRoles.map(role => {
          const meta = ROLE_META[role.role_name] || { icon: '👤', desc: 'Team member' };
          const assigned = role.user_id;
          return (
            <div key={role.role_id} style={{ ...s.roleCard, ...(assigned ? s.roleCardAssigned : {}) }}>
              <div style={s.roleTop}>
                <div style={s.roleIconBox}>{meta.icon}</div>
                <div style={s.roleInfo}>
                  <div style={s.roleName}>{role.role_name}</div>
                  <div style={s.roleDesc}>{meta.desc}</div>
                </div>
              </div>
              <div style={s.roleControl}>
                <select
                  style={s.roleSelect}
                  value={role.user_id || ''}
                  onChange={e => handleAssign(role.role_id, e.target.value)}
                  disabled={saving[role.role_id]}
                >
                  <option value="">-- Not Assigned --</option>
                  {members.map(m => (
                    <option key={m.id} value={m.id}>
                      {m.name || `${m.first_name || ''} ${m.last_name || ''}`.trim()}
                    </option>
                  ))}
                </select>
                {assigned && !saving[role.role_id] && <span style={s.assignedPill}>Assigned</span>}
                {saving[role.role_id] && <span style={s.savingDot} />}
              </div>
            </div>
          );
        })}
      </div>
      {finalRoles.length === 0 && <EmptyState icon="📋" message="No workflow roles configured yet." />}
    </div>
  );
}


// ═══════════════════════════════════════════════════════════════════════════════
//  SECTION 2 — ASSIGNMENT POOL
// ═══════════════════════════════════════════════════════════════════════════════

function AssignmentPool({ pool, members, onRefresh, jsonHeaders, authHeaders }) {
  const [showAdd, setShowAdd] = useState(false);
  const [form, setForm] = useState({ user_id: '', weight: 100, max_daily_leads: 50, geographic_states: [] });
  const [editId, setEditId] = useState(null);

  const memberName = (userId) => {
    const m = members.find(m => m.id === userId);
    return m ? (m.name || `${m.first_name || ''} ${m.last_name || ''}`.trim()) : `User ${userId}`;
  };

  const save = async () => {
    if (!form.user_id) { toast.error('Select a team member'); return; }
    const body = {
      user_id: parseInt(form.user_id),
      weight: form.weight,
      max_daily_leads: form.max_daily_leads,
      geographic_states: form.geographic_states.length ? form.geographic_states : null,
    };
    try {
      const url = editId ? `${API}/pool/${editId}` : `${API}/pool`;
      const res = await fetch(url, {
        method: editId ? 'PUT' : 'POST',
        headers: jsonHeaders(),
        body: JSON.stringify(body),
      });
      const data = await res.json();
      if (data.success) {
        toast.success(editId ? 'Updated' : 'Added to pool');
        setShowAdd(false); setEditId(null);
        setForm({ user_id: '', weight: 100, max_daily_leads: 50, geographic_states: [] });
        onRefresh();
      } else toast.error(data.detail || 'Failed');
    } catch { toast.error('Failed to save'); }
  };

  const remove = async (id) => {
    try {
      const res = await fetch(`${API}/pool/${id}`, { method: 'DELETE', headers: authHeaders() });
      const data = await res.json();
      if (data.success) { toast.success('Removed'); onRefresh(); }
    } catch { toast.error('Failed to remove'); }
  };

  const startEdit = (m) => {
    setForm({ user_id: m.user_id, weight: m.weight, max_daily_leads: m.max_daily_leads, geographic_states: m.geographic_states || [] });
    setEditId(m.id);
    setShowAdd(true);
  };

  // Members not already in pool
  const available = members.filter(m => !pool.find(p => p.user_id === m.id && p.is_active));

  const totalWeight = pool.filter(p => p.is_active).reduce((sum, p) => sum + (p.weight || 0), 0);

  return (
    <div>
      <SectionHeader
        title="Assignment Pool"
        subtitle="Team members eligible to receive new leads via automatic distribution."
        action={<button style={s.primaryBtn} onClick={() => { setShowAdd(!showAdd); setEditId(null); }}>{showAdd ? 'Cancel' : '+ Add to Pool'}</button>}
      />

      {showAdd && (
        <div style={s.formCard}>
          <div style={s.formRow}>
            <label style={s.label}>
              Team Member
              <select style={s.input} value={form.user_id} onChange={e => setForm({ ...form, user_id: e.target.value })}>
                <option value="">-- Select --</option>
                {(editId ? members : available).map(m => (
                  <option key={m.id} value={m.id}>{m.name || `${m.first_name||''} ${m.last_name||''}`.trim()}</option>
                ))}
              </select>
            </label>
            <label style={s.label}>
              Weight
              <input type="number" style={s.input} value={form.weight} onChange={e => setForm({ ...form, weight: parseInt(e.target.value) || 100 })} min={1} max={1000} />
            </label>
            <label style={s.label}>
              Max Daily Leads
              <input type="number" style={s.input} value={form.max_daily_leads} onChange={e => setForm({ ...form, max_daily_leads: parseInt(e.target.value) || 50 })} min={1} max={500} />
            </label>
          </div>
          <label style={s.label}>
            Geographic States (optional — leave empty for all states)
            <div style={s.stateGrid}>
              {US_STATES.map(st => (
                <label key={st} style={s.stateCheckbox}>
                  <input
                    type="checkbox"
                    checked={(form.geographic_states || []).includes(st)}
                    onChange={e => {
                      const states = form.geographic_states || [];
                      setForm({ ...form, geographic_states: e.target.checked ? [...states, st] : states.filter(s => s !== st) });
                    }}
                  />
                  {st}
                </label>
              ))}
            </div>
          </label>
          <button style={s.primaryBtn} onClick={save}>{editId ? 'Update' : 'Add to Pool'}</button>
        </div>
      )}

      {/* Pool table */}
      <div style={s.tableWrap}>
        <table style={s.table}>
          <thead>
            <tr>
              <th style={s.th}>Member</th>
              <th style={s.th}>Weight</th>
              <th style={s.th}>Share</th>
              <th style={s.th}>Capacity</th>
              <th style={s.th}>Today</th>
              <th style={s.th}>States</th>
              <th style={s.th}>Status</th>
              <th style={s.th}></th>
            </tr>
          </thead>
          <tbody>
            {pool.map(m => {
              const pct = totalWeight > 0 ? ((m.weight / totalWeight) * 100).toFixed(0) : 0;
              return (
                <tr key={m.id} style={!m.is_active ? s.rowInactive : {}}>
                  <td style={s.td}><strong>{m.user_name || memberName(m.user_id)}</strong></td>
                  <td style={s.td}>{m.weight}</td>
                  <td style={s.td}>
                    <div style={s.barOuter}><div style={{ ...s.barInner, width: `${pct}%` }} /></div>
                    <span style={s.barLabel}>{pct}%</span>
                  </td>
                  <td style={s.td}>{m.max_daily_leads}/day</td>
                  <td style={s.td}>
                    <span style={m.current_daily_leads >= m.max_daily_leads ? s.countDanger : s.countOk}>
                      {m.current_daily_leads || 0}
                    </span>
                  </td>
                  <td style={s.td}>{m.geographic_states ? m.geographic_states.join(', ') : <span style={s.muted}>All</span>}</td>
                  <td style={s.td}><span style={m.is_active ? s.badgeGreen : s.badgeGray}>{m.is_active ? 'Active' : 'Inactive'}</span></td>
                  <td style={s.td}>
                    <button style={s.linkBtn} onClick={() => startEdit(m)}>Edit</button>
                    <button style={s.dangerLink} onClick={() => remove(m.id)}>Remove</button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {pool.length === 0 && <EmptyState icon="🏊" message="No pool members yet. Add LOs to enable automatic lead distribution." />}
    </div>
  );
}


// ═══════════════════════════════════════════════════════════════════════════════
//  SECTION 3 — STRATEGY CONFIG
// ═══════════════════════════════════════════════════════════════════════════════

function StrategyConfig({ config, onRefresh, jsonHeaders }) {
  const [form, setForm] = useState(config || {});
  const [saving, setSaving] = useState(false);

  useEffect(() => { if (config) setForm(config); }, [config]);

  const handleSave = async () => {
    setSaving(true);
    try {
      const res = await fetch(`${API}/config`, { method: 'PUT', headers: jsonHeaders(), body: JSON.stringify(form) });
      const data = await res.json();
      if (data.success) { toast.success('Strategy updated'); onRefresh(); }
      else toast.error(data.detail || 'Failed');
    } catch { toast.error('Failed to save'); }
    finally { setSaving(false); }
  };

  return (
    <div>
      <SectionHeader
        title="Distribution Strategy"
        subtitle="Choose how new leads are automatically distributed to your assignment pool."
      />

      <div style={s.stratGrid}>
        {STRATEGIES.map(st => (
          <div
            key={st.value}
            onClick={() => setForm({ ...form, strategy: st.value })}
            style={{ ...s.stratCard, ...(form.strategy === st.value ? s.stratCardActive : {}) }}
          >
            <div style={s.stratIcon}>{st.icon}</div>
            <div style={s.stratLabel}>{st.label}</div>
            <div style={s.stratDesc}>{st.desc}</div>
          </div>
        ))}
      </div>

      <div style={s.divider} />

      <h3 style={s.subTitle}>Global Settings</h3>
      <div style={s.settingsGrid}>
        <label style={s.label}>
          Max daily leads / user
          <input type="number" style={s.input} value={form.max_daily_leads_per_user || 50}
            onChange={e => setForm({ ...form, max_daily_leads_per_user: parseInt(e.target.value) || 50 })} min={1} max={500} />
        </label>
        <label style={s.label}>
          Fallback user ID
          <input type="number" style={s.input} value={form.fallback_user_id || ''} placeholder="None"
            onChange={e => setForm({ ...form, fallback_user_id: e.target.value ? parseInt(e.target.value) : null })} />
        </label>
      </div>
      <div style={s.checkRow}>
        <Check label="Respect capacity limits" checked={form.respect_capacity !== false} onChange={v => setForm({ ...form, respect_capacity: v })} />
        <Check label="Notify LO on assignment" checked={form.notify_on_assignment !== false} onChange={v => setForm({ ...form, notify_on_assignment: v })} />
        <Check label="Business hours only" checked={form.business_hours_only === true} onChange={v => setForm({ ...form, business_hours_only: v })} />
        <Check label="Enable deduplication" checked={form.dedup_enabled !== false} onChange={v => setForm({ ...form, dedup_enabled: v })} />
      </div>

      <button style={s.primaryBtn} onClick={handleSave} disabled={saving}>{saving ? 'Saving...' : 'Save Configuration'}</button>
    </div>
  );
}


// ═══════════════════════════════════════════════════════════════════════════════
//  SECTION 4 — ROUTING RULES
// ═══════════════════════════════════════════════════════════════════════════════

function RoutingRules({ rules, onRefresh, jsonHeaders, authHeaders }) {
  const [showAdd, setShowAdd] = useState(false);
  const [newRule, setNewRule] = useState({
    rule_name: '', priority: 100,
    conditions: [{ field: 'loan_amount', op: 'gte', value: '' }],
    match_type: 'ALL', target_type: 'USER', target_config: { user_id: '' },
  });

  const addCond = () => setNewRule({ ...newRule, conditions: [...newRule.conditions, { field: 'loan_amount', op: 'gte', value: '' }] });
  const rmCond = (i) => setNewRule({ ...newRule, conditions: newRule.conditions.filter((_,j) => j !== i) });
  const updCond = (i, k, v) => { const c = [...newRule.conditions]; c[i] = { ...c[i], [k]: v }; setNewRule({ ...newRule, conditions: c }); };

  const saveRule = async () => {
    if (!newRule.rule_name) { toast.error('Name required'); return; }
    const body = {
      ...newRule,
      conditions: newRule.conditions.map(c => ({
        ...c,
        value: c.op === 'in' ? c.value.split(',').map(v => v.trim()) : (isNaN(c.value) ? c.value : Number(c.value)),
      })),
    };
    try {
      const res = await fetch(`${API}/rules`, { method: 'POST', headers: jsonHeaders(), body: JSON.stringify(body) });
      const data = await res.json();
      if (data.success) { toast.success('Rule created'); setShowAdd(false); onRefresh(); }
      else toast.error(data.detail || 'Failed');
    } catch { toast.error('Failed to save'); }
  };

  const delRule = async (id) => {
    try {
      const res = await fetch(`${API}/rules/${id}`, { method: 'DELETE', headers: authHeaders() });
      const data = await res.json();
      if (data.success) { toast.success('Rule deactivated'); onRefresh(); }
    } catch { toast.error('Failed'); }
  };

  return (
    <div>
      <SectionHeader
        title="Routing Rules"
        subtitle="Rules are evaluated in priority order (lowest number = highest priority). First match wins."
        action={<button style={s.primaryBtn} onClick={() => setShowAdd(!showAdd)}>{showAdd ? 'Cancel' : '+ New Rule'}</button>}
      />

      {showAdd && (
        <div style={s.formCard}>
          <div style={s.formRow}>
            <label style={{ ...s.label, flex: 2 }}>
              Rule Name
              <input style={s.input} value={newRule.rule_name} onChange={e => setNewRule({ ...newRule, rule_name: e.target.value })} />
            </label>
            <label style={s.label}>
              Priority
              <input type="number" style={s.input} value={newRule.priority} onChange={e => setNewRule({ ...newRule, priority: parseInt(e.target.value) || 100 })} />
            </label>
            <label style={s.label}>
              Match
              <select style={s.input} value={newRule.match_type} onChange={e => setNewRule({ ...newRule, match_type: e.target.value })}>
                <option value="ALL">ALL</option>
                <option value="ANY">ANY</option>
              </select>
            </label>
          </div>

          <div style={s.condLabel}>Conditions</div>
          {newRule.conditions.map((c, i) => (
            <div key={i} style={s.condRow}>
              <select style={s.inputSm} value={c.field} onChange={e => updCond(i, 'field', e.target.value)}>
                {CONDITION_FIELDS.map(f => <option key={f.value} value={f.value}>{f.label}</option>)}
              </select>
              <select style={s.inputSm} value={c.op} onChange={e => updCond(i, 'op', e.target.value)}>
                {OPERATORS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
              </select>
              <input style={s.inputSm} placeholder="Value" value={c.value} onChange={e => updCond(i, 'value', e.target.value)} />
              {newRule.conditions.length > 1 && <button style={s.iconBtn} onClick={() => rmCond(i)}>✕</button>}
            </div>
          ))}
          <button style={s.textBtn} onClick={addCond}>+ Add condition</button>

          <div style={s.condLabel}>Target</div>
          <div style={s.formRow}>
            <select style={s.input} value={newRule.target_type} onChange={e => setNewRule({ ...newRule, target_type: e.target.value, target_config: {} })}>
              <option value="USER">Specific User</option>
              <option value="ROUND_ROBIN">Round Robin</option>
              <option value="ROLE">Role</option>
            </select>
            <input style={s.input}
              placeholder={newRule.target_type === 'ROLE' ? 'Role name' : 'User ID(s, comma-sep)'}
              onChange={e => {
                const v = e.target.value;
                if (newRule.target_type === 'ROLE') setNewRule({ ...newRule, target_config: { role: v } });
                else if (newRule.target_type === 'ROUND_ROBIN') setNewRule({ ...newRule, target_config: { user_ids: v.split(',').map(x => parseInt(x.trim())).filter(Boolean) } });
                else setNewRule({ ...newRule, target_config: { user_id: parseInt(v) || '' } });
              }}
            />
          </div>
          <button style={s.primaryBtn} onClick={saveRule}>Save Rule</button>
        </div>
      )}

      <div style={s.tableWrap}>
        <table style={s.table}>
          <thead><tr>
            <th style={s.th}>#</th><th style={s.th}>Name</th><th style={s.th}>Conditions</th><th style={s.th}>Target</th><th style={s.th}>Status</th><th style={s.th}></th>
          </tr></thead>
          <tbody>
            {rules.map(r => (
              <tr key={r.id} style={!r.is_active ? s.rowInactive : {}}>
                <td style={s.td}>{r.priority}</td>
                <td style={s.td}><strong>{r.rule_name}</strong></td>
                <td style={s.td}>{(r.conditions||[]).map((c,i) => <span key={i} style={s.condBadge}>{c.field} {c.op} {JSON.stringify(c.value)}</span>)}</td>
                <td style={s.td}>{r.target_type}: {JSON.stringify(r.target_config)}</td>
                <td style={s.td}><span style={r.is_active ? s.badgeGreen : s.badgeGray}>{r.is_active ? 'Active' : 'Off'}</span></td>
                <td style={s.td}><button style={s.dangerLink} onClick={() => delRule(r.id)}>Delete</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {rules.length === 0 && <EmptyState icon="🎯" message="No routing rules. Rules are used with the 'Rule Based' strategy." />}
    </div>
  );
}


// ═══════════════════════════════════════════════════════════════════════════════
//  SECTION 5 — EXCEPTIONS
// ═══════════════════════════════════════════════════════════════════════════════

function Exceptions({ exceptions, onRefresh, jsonHeaders, authHeaders }) {
  const [showAdd, setShowAdd] = useState(false);
  const [form, setForm] = useState({
    user_id: '', exception_type: 'PTO', reason: '',
    starts_at: new Date().toISOString().slice(0, 16), ends_at: '',
  });

  const create = async () => {
    if (!form.user_id) { toast.error('User ID required'); return; }
    const body = { ...form, user_id: parseInt(form.user_id), starts_at: new Date(form.starts_at).toISOString(), ends_at: form.ends_at ? new Date(form.ends_at).toISOString() : null };
    try {
      const res = await fetch(`${API}/exceptions`, { method: 'POST', headers: jsonHeaders(), body: JSON.stringify(body) });
      const data = await res.json();
      if (data.success) { toast.success('Exception created'); setShowAdd(false); onRefresh(); }
      else toast.error(data.detail || 'Failed');
    } catch { toast.error('Failed'); }
  };

  const cancel = async (id) => {
    try {
      const res = await fetch(`${API}/exceptions/${id}`, { method: 'DELETE', headers: authHeaders() });
      const data = await res.json();
      if (data.success) { toast.success('Cancelled'); onRefresh(); }
    } catch { toast.error('Failed'); }
  };

  return (
    <div>
      <SectionHeader title="Exceptions" subtitle="Temporarily exclude team members from lead assignment (PTO, training, etc.)."
        action={<button style={s.primaryBtn} onClick={() => setShowAdd(!showAdd)}>{showAdd ? 'Cancel' : '+ Add Exception'}</button>} />

      {showAdd && (
        <div style={s.formCard}>
          <div style={s.formRow}>
            <label style={s.label}>User ID<input type="number" style={s.input} value={form.user_id} onChange={e => setForm({ ...form, user_id: e.target.value })} /></label>
            <label style={s.label}>Type
              <select style={s.input} value={form.exception_type} onChange={e => setForm({ ...form, exception_type: e.target.value })}>
                <option value="PTO">PTO / Vacation</option><option value="CAPACITY_OVERRIDE">Capacity Override</option>
                <option value="BLOCKED">Blocked</option><option value="TRAINING">Training</option>
              </select>
            </label>
            <label style={s.label}>Reason<input style={s.input} value={form.reason} onChange={e => setForm({ ...form, reason: e.target.value })} /></label>
          </div>
          <div style={s.formRow}>
            <label style={s.label}>Starts<input type="datetime-local" style={s.input} value={form.starts_at} onChange={e => setForm({ ...form, starts_at: e.target.value })} /></label>
            <label style={s.label}>Ends (optional)<input type="datetime-local" style={s.input} value={form.ends_at} onChange={e => setForm({ ...form, ends_at: e.target.value })} /></label>
          </div>
          <button style={s.primaryBtn} onClick={create}>Create Exception</button>
        </div>
      )}

      <div style={s.tableWrap}>
        <table style={s.table}>
          <thead><tr><th style={s.th}>User</th><th style={s.th}>Type</th><th style={s.th}>Reason</th><th style={s.th}>Start</th><th style={s.th}>End</th><th style={s.th}></th></tr></thead>
          <tbody>
            {exceptions.map(e => (
              <tr key={e.id}>
                <td style={s.td}>User {e.user_id}</td>
                <td style={s.td}><span style={s.condBadge}>{e.exception_type}</span></td>
                <td style={s.td}>{e.reason || '-'}</td>
                <td style={s.td}>{e.starts_at ? new Date(e.starts_at).toLocaleDateString() : '-'}</td>
                <td style={s.td}>{e.ends_at ? new Date(e.ends_at).toLocaleDateString() : 'Indefinite'}</td>
                <td style={s.td}><button style={s.dangerLink} onClick={() => cancel(e.id)}>Cancel</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {exceptions.length === 0 && <EmptyState icon="🚫" message="No active exceptions." />}
    </div>
  );
}


// ═══════════════════════════════════════════════════════════════════════════════
//  SECTION 6 — TEST PANEL
// ═══════════════════════════════════════════════════════════════════════════════

function TestPanel({ jsonHeaders }) {
  const [form, setForm] = useState({});
  const [result, setResult] = useState(null);
  const [testing, setTesting] = useState(false);

  const run = async () => {
    setTesting(true);
    try {
      const res = await fetch(`${API}/test`, { method: 'POST', headers: jsonHeaders(), body: JSON.stringify(form) });
      const data = await res.json();
      if (data.success) setResult(data.data);
      else toast.error(data.detail || 'Test failed');
    } catch { toast.error('Test failed'); }
    finally { setTesting(false); }
  };

  return (
    <div>
      <SectionHeader title="Test Assignment (Dry Run)" subtitle="Simulate which LO would receive a lead with these attributes. No data is changed." />
      <div style={s.settingsGrid}>
        {CONDITION_FIELDS.map(f => (
          <label key={f.value} style={s.label}>
            {f.label}
            {f.type === 'select'
              ? <select style={s.input} value={form[f.value]||''} onChange={e => setForm({ ...form, [f.value]: e.target.value||undefined })}>
                  <option value="">-- Any --</option>
                  {f.options.map(o => <option key={o} value={o}>{o}</option>)}
                </select>
              : <input type={f.type} style={s.input} value={form[f.value]||''} placeholder={f.label}
                  onChange={e => setForm({ ...form, [f.value]: f.type==='number' ? (e.target.value ? Number(e.target.value) : undefined) : (e.target.value||undefined) })} />
            }
          </label>
        ))}
      </div>
      <button style={s.primaryBtn} onClick={run} disabled={testing}>{testing ? 'Testing...' : 'Run Test'}</button>

      {result && (
        <div style={s.resultCard}>
          <div style={s.resultRow}><span style={s.resultLabel}>Assigned to:</span> <strong>{result.assigned_user_name || result.assigned_user_id || 'Unassigned'}</strong></div>
          <div style={s.resultRow}><span style={s.resultLabel}>Strategy:</span> {result.strategy_used}</div>
          <div style={s.resultRow}><span style={s.resultLabel}>Candidates:</span> {result.candidates_evaluated}</div>
          <div style={s.dryRunTag}>DRY RUN — no lead was assigned</div>
        </div>
      )}
    </div>
  );
}


// ═══════════════════════════════════════════════════════════════════════════════
//  SECTION 7 — AUDIT LOG
// ═══════════════════════════════════════════════════════════════════════════════

function AuditLog({ authHeaders }) {
  const [entries, setEntries] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const res = await fetch(`${API}/audit-log?limit=100`, { headers: authHeaders() });
        const data = await res.json();
        if (data.success) setEntries(data.data.entries || []);
      } catch { toast.error('Failed to load audit log'); }
      finally { setLoading(false); }
    })();
  }, [authHeaders]);

  if (loading) return <div style={s.loading}>Loading...</div>;

  return (
    <div>
      <SectionHeader title="Audit Log" subtitle="Every assignment decision is recorded here." />
      <div style={s.tableWrap}>
        <table style={s.table}>
          <thead><tr><th style={s.th}>Date</th><th style={s.th}>Action</th><th style={s.th}>Lead</th><th style={s.th}>From</th><th style={s.th}>To</th><th style={s.th}>Strategy</th><th style={s.th}>Reason</th></tr></thead>
          <tbody>
            {entries.map(e => (
              <tr key={e.id}>
                <td style={s.td}>{e.created_at ? new Date(e.created_at).toLocaleString() : '-'}</td>
                <td style={s.td}><span style={s.condBadge}>{e.action}</span></td>
                <td style={s.td}>{e.lead_id || '-'}</td>
                <td style={s.td}>{e.from_user_id || '-'}</td>
                <td style={s.td}>{e.to_user_id || '-'}</td>
                <td style={s.td}>{e.strategy_used || '-'}</td>
                <td style={{ ...s.td, maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis' }}>{e.decision_reason || '-'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {entries.length === 0 && <EmptyState icon="📋" message="No audit entries yet." />}
    </div>
  );
}


// ═══════════════════════════════════════════════════════════════════════════════
//  SECTION 8 — STATS
// ═══════════════════════════════════════════════════════════════════════════════

function Stats({ authHeaders }) {
  const [stats, setStats] = useState(null);
  const [days, setDays] = useState(30);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      setLoading(true);
      try {
        const res = await fetch(`${API}/stats?days=${days}`, { headers: authHeaders() });
        const data = await res.json();
        if (data.success) setStats(data.data);
      } catch { toast.error('Failed'); }
      finally { setLoading(false); }
    })();
  }, [days, authHeaders]);

  if (loading) return <div style={s.loading}>Loading...</div>;

  return (
    <div>
      <SectionHeader title="Assignment Statistics" subtitle={`Last ${days} days`}
        action={
          <select style={s.input} value={days} onChange={e => setDays(parseInt(e.target.value))}>
            <option value={7}>7 days</option><option value={30}>30 days</option><option value={90}>90 days</option>
          </select>
        } />

      {stats && (
        <>
          <div style={s.kpiRow}>
            <KPI value={stats.total_assignments} label="Total" />
            <KPI value={stats.unique_los} label="Unique LOs" />
            <KPI value={stats.auto_assigned} label="Auto" />
            <KPI value={stats.manual_assigned} label="Manual" />
            <KPI value={stats.reassigned} label="Reassigned" />
            <KPI value={stats.fallback_used} label="Fallback" />
          </div>
          {stats.distribution?.length > 0 && (
            <>
              <h3 style={s.subTitle}>Distribution by LO</h3>
              <div style={s.tableWrap}>
                <table style={s.table}>
                  <thead><tr><th style={s.th}>User</th><th style={s.th}>Leads</th><th style={s.th}>Share</th></tr></thead>
                  <tbody>
                    {stats.distribution.map(d => (
                      <tr key={d.user_id}>
                        <td style={s.td}>User {d.user_id}</td>
                        <td style={s.td}>{d.count}</td>
                        <td style={s.td}>{stats.total_assignments > 0 ? ((d.count / stats.total_assignments) * 100).toFixed(1) : 0}%</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </>
      )}
      {!stats && <EmptyState icon="📊" message="No stats available." />}
    </div>
  );
}


// ═══════════════════════════════════════════════════════════════════════════════
//  SHARED COMPONENTS
// ═══════════════════════════════════════════════════════════════════════════════

function SectionHeader({ title, subtitle, action }) {
  return (
    <div style={s.sectionHeader}>
      <div>
        <h2 style={s.sectionTitle}>{title}</h2>
        {subtitle && <p style={s.sectionSub}>{subtitle}</p>}
      </div>
      {action}
    </div>
  );
}

function EmptyState({ icon, message }) {
  return <div style={s.empty}><span style={s.emptyIcon}>{icon}</span><p>{message}</p></div>;
}

function Check({ label, checked, onChange }) {
  return (
    <label style={s.checkLabel}>
      <input type="checkbox" checked={checked} onChange={e => onChange(e.target.checked)} />
      {label}
    </label>
  );
}

function KPI({ value, label }) {
  return <div style={s.kpi}><div style={s.kpiVal}>{value ?? 0}</div><div style={s.kpiLabel}>{label}</div></div>;
}


// ═══════════════════════════════════════════════════════════════════════════════
//  STYLES
// ═══════════════════════════════════════════════════════════════════════════════

const BRAND = '#218D8D';
const BRAND_BG = '#e8f5f5';

const s = {
  // Page layout
  container: { maxWidth: 1200, margin: '0 auto', padding: '24px 20px', fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif' },
  pageHeader: { display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 24, flexWrap: 'wrap', gap: 12 },
  pageTitle: { fontSize: 26, fontWeight: 700, margin: 0, color: '#1a1a2e' },
  pageSubtitle: { fontSize: 14, color: '#666', margin: '4px 0 0' },
  headerBadge: { display: 'flex', gap: 8, alignItems: 'center' },
  badgeStrategy: { padding: '6px 14px', background: BRAND_BG, color: BRAND, borderRadius: 20, fontSize: 13, fontWeight: 600, textTransform: 'capitalize' },
  badgeCount: { padding: '6px 14px', background: '#f3f4f6', color: '#555', borderRadius: 20, fontSize: 13, fontWeight: 500 },

  // Navigation
  nav: { display: 'flex', gap: 2, borderBottom: `2px solid #e5e7eb`, marginBottom: 28, overflowX: 'auto', paddingBottom: 0 },
  navBtn: {
    padding: '12px 18px', border: 'none', background: 'none', cursor: 'pointer',
    fontSize: 13, fontWeight: 500, color: '#666', borderBottom: '2px solid transparent',
    marginBottom: -2, transition: 'all 0.15s', display: 'flex', alignItems: 'center', gap: 6, whiteSpace: 'nowrap',
  },
  navBtnActive: { color: BRAND, borderBottomColor: BRAND, fontWeight: 600 },
  navIcon: { fontSize: 15 },
  content: { minHeight: 400 },

  // Section headers
  sectionHeader: { display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 20, flexWrap: 'wrap', gap: 12 },
  sectionTitle: { fontSize: 18, fontWeight: 600, margin: 0, color: '#1a1a2e' },
  sectionSub: { fontSize: 13, color: '#666', margin: '4px 0 0' },
  subTitle: { fontSize: 15, fontWeight: 600, margin: '24px 0 12px', color: '#1a1a2e' },
  divider: { borderTop: '1px solid #e5e7eb', margin: '28px 0' },

  // Workflow team grid
  roleGrid: { display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: 14 },
  roleCard: { background: '#f8f9fa', border: '2px solid #e9ecef', borderRadius: 10, padding: 16, transition: 'all 0.2s' },
  roleCardAssigned: { background: BRAND_BG, borderColor: BRAND },
  roleTop: { display: 'flex', gap: 12, marginBottom: 12 },
  roleIconBox: { width: 40, height: 40, background: '#fff', borderRadius: 10, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 22, boxShadow: '0 1px 4px rgba(0,0,0,0.06)' },
  roleInfo: { flex: 1 },
  roleName: { fontSize: 14, fontWeight: 600, color: '#1a1a2e' },
  roleDesc: { fontSize: 12, color: '#666', marginTop: 2 },
  roleControl: { display: 'flex', alignItems: 'center', gap: 10 },
  roleSelect: {
    flex: 1, padding: '9px 32px 9px 12px', border: '1px solid #ddd', borderRadius: 8,
    fontSize: 13, background: '#fff', cursor: 'pointer', appearance: 'none',
    backgroundImage: "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'%3E%3Cpath fill='%23666' d='M6 8L1 3h10z'/%3E%3C/svg%3E\")",
    backgroundRepeat: 'no-repeat', backgroundPosition: 'right 10px center',
  },
  assignedPill: { padding: '3px 10px', background: BRAND, color: '#fff', borderRadius: 20, fontSize: 11, fontWeight: 600, whiteSpace: 'nowrap' },
  savingDot: { width: 16, height: 16, border: `2px solid #e0e0e0`, borderTopColor: BRAND, borderRadius: '50%', animation: 'spin 0.7s linear infinite' },

  // Forms
  formCard: { padding: 20, background: '#f9fafb', borderRadius: 10, border: '1px solid #e5e7eb', marginBottom: 20 },
  formRow: { display: 'flex', gap: 12, marginBottom: 14, flexWrap: 'wrap' },
  label: { display: 'flex', flexDirection: 'column', fontSize: 13, fontWeight: 500, color: '#333', flex: 1, minWidth: 160, gap: 4 },
  input: { padding: '9px 12px', border: '1px solid #d1d5db', borderRadius: 7, fontSize: 13, outline: 'none', width: '100%', boxSizing: 'border-box' },
  inputSm: { padding: '7px 10px', border: '1px solid #d1d5db', borderRadius: 6, fontSize: 12, flex: 1, minWidth: 80 },
  settingsGrid: { display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: 14, marginBottom: 20 },
  checkRow: { display: 'flex', flexWrap: 'wrap', gap: 20, marginBottom: 24 },
  checkLabel: { display: 'flex', alignItems: 'center', gap: 7, fontSize: 13, color: '#333', cursor: 'pointer' },

  // State picker
  stateGrid: { display: 'flex', flexWrap: 'wrap', gap: 4, marginTop: 6, marginBottom: 12 },
  stateCheckbox: { display: 'flex', alignItems: 'center', gap: 3, fontSize: 11, width: 52 },

  // Strategy cards
  stratGrid: { display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))', gap: 12, marginBottom: 8 },
  stratCard: { padding: 16, border: '2px solid #e5e7eb', borderRadius: 10, cursor: 'pointer', transition: 'all 0.15s', textAlign: 'center' },
  stratCardActive: { borderColor: BRAND, background: BRAND_BG },
  stratIcon: { fontSize: 28, marginBottom: 6 },
  stratLabel: { fontWeight: 600, fontSize: 14, marginBottom: 4, color: '#1a1a2e' },
  stratDesc: { fontSize: 11, color: '#666', lineHeight: 1.4 },

  // Condition rows
  condLabel: { fontSize: 13, fontWeight: 600, margin: '14px 0 8px', color: '#333' },
  condRow: { display: 'flex', gap: 8, marginBottom: 8, alignItems: 'center' },
  condBadge: { display: 'inline-block', padding: '2px 7px', background: '#eff6ff', color: '#2563eb', borderRadius: 4, fontSize: 11, marginRight: 4 },

  // Buttons
  primaryBtn: { padding: '10px 22px', background: BRAND, color: '#fff', border: 'none', borderRadius: 7, fontSize: 13, fontWeight: 600, cursor: 'pointer', transition: 'opacity 0.15s' },
  textBtn: { padding: '6px 0', background: 'none', border: 'none', color: BRAND, fontSize: 12, fontWeight: 500, cursor: 'pointer' },
  iconBtn: { width: 28, height: 28, border: '1px solid #e5e7eb', borderRadius: 6, background: '#fff', cursor: 'pointer', fontSize: 13, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#999' },
  linkBtn: { padding: '4px 8px', background: 'none', border: 'none', color: BRAND, fontSize: 12, fontWeight: 500, cursor: 'pointer' },
  dangerLink: { padding: '4px 8px', background: 'none', border: 'none', color: '#dc2626', fontSize: 12, fontWeight: 500, cursor: 'pointer' },

  // Table
  tableWrap: { overflowX: 'auto' },
  table: { width: '100%', borderCollapse: 'collapse', marginTop: 8 },
  th: { textAlign: 'left', padding: '10px 12px', fontSize: 11, fontWeight: 600, color: '#888', borderBottom: '2px solid #e5e7eb', textTransform: 'uppercase', letterSpacing: 0.5 },
  td: { padding: '10px 12px', fontSize: 13, borderBottom: '1px solid #f0f0f0', verticalAlign: 'middle' },
  rowInactive: { opacity: 0.45 },

  // Badges
  badgeGreen: { display: 'inline-block', padding: '2px 8px', background: '#dcfce7', color: '#16a34a', borderRadius: 4, fontSize: 11, fontWeight: 600 },
  badgeGray: { display: 'inline-block', padding: '2px 8px', background: '#f3f4f6', color: '#999', borderRadius: 4, fontSize: 11, fontWeight: 600 },
  muted: { color: '#bbb', fontSize: 12 },

  // Pool bars
  barOuter: { width: 60, height: 6, background: '#e5e7eb', borderRadius: 3, overflow: 'hidden', display: 'inline-block', verticalAlign: 'middle', marginRight: 6 },
  barInner: { height: '100%', background: BRAND, borderRadius: 3, transition: 'width 0.3s' },
  barLabel: { fontSize: 11, color: '#666' },
  countOk: { fontWeight: 600, color: '#16a34a' },
  countDanger: { fontWeight: 600, color: '#dc2626' },

  // Result card
  resultCard: { marginTop: 16, padding: 16, background: '#f0fdf4', border: '1px solid #bbf7d0', borderRadius: 8 },
  resultRow: { marginBottom: 6, fontSize: 14 },
  resultLabel: { color: '#666', marginRight: 8 },
  dryRunTag: { marginTop: 10, padding: '4px 10px', background: '#fef9c3', color: '#a16207', borderRadius: 4, fontSize: 12, display: 'inline-block', fontWeight: 500 },

  // KPIs
  kpiRow: { display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(130px, 1fr))', gap: 12, marginBottom: 24 },
  kpi: { padding: 18, background: '#f9fafb', border: '1px solid #e5e7eb', borderRadius: 10, textAlign: 'center' },
  kpiVal: { fontSize: 30, fontWeight: 700, color: '#1a1a2e' },
  kpiLabel: { fontSize: 12, color: '#666', marginTop: 4 },

  // Empty & loading
  loading: { textAlign: 'center', padding: 50, color: '#999', fontSize: 14 },
  empty: { textAlign: 'center', padding: '40px 20px', color: '#999' },
  emptyIcon: { fontSize: 40, display: 'block', marginBottom: 12, opacity: 0.5 },
};
