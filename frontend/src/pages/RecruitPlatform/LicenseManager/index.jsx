import React, { useState, useEffect } from 'react';
import { useRecruitPlatform } from '../../../contexts/RecruitPlatformContext';
import './LicenseManager.css';

const API_BASE = import.meta.env.VITE_API_URL || 'https://api.perenniaai.com';

function slugify(str) {
  return str.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
}

function useRecruitApi(path, deps = []) {
  const { recruitToken } = useRecruitPlatform();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const refetch = () => {
    setLoading(true);
    fetch(`${API_BASE}${path}`, {
      headers: { Authorization: `Bearer ${recruitToken}`, 'Content-Type': 'application/json' },
    })
      .then(r => r.ok ? r.json() : r.json().then(e => Promise.reject(e)))
      .then(setData)
      .catch(e => setError(e?.detail || 'Failed to load'))
      .finally(() => setLoading(false));
  };

  useEffect(refetch, deps);
  return { data, loading, error, refetch };
}

// ─── Invite Modal ──────────────────────────────────────────────────────────────
function InviteModal({ tenantId, onClose, recruitToken }) {
  const [form, setForm] = useState({ email: '', first_name: '', last_name: '' });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [credentials, setCredentials] = useState(null);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    try {
      const res = await fetch(`${API_BASE}/api/v1/recruit-platform/tenants/${tenantId}/invite`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${recruitToken}`, 'Content-Type': 'application/json' },
        body: JSON.stringify(form),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Failed to invite user');
      setCredentials(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="lm-modal-overlay" onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="lm-modal">
        {credentials ? (
          <>
            <h3>User Invited</h3>
            <p style={{ fontSize: 14, color: '#374151', marginBottom: 12 }}>
              Share these credentials with the new user — they should change their password after first login.
            </p>
            <div className="lm-credentials-box">
              Email: {credentials.email}<br />
              Temp Password: {credentials.temp_password}
            </div>
            <div className="lm-modal-actions">
              <button className="lm-btn lm-btn-primary" onClick={onClose}>Done</button>
            </div>
          </>
        ) : (
          <>
            <h3>Invite User</h3>
            {error && <div className="lm-error">{error}</div>}
            <form onSubmit={handleSubmit}>
              <div className="lm-form-group" style={{ marginBottom: 14 }}>
                <label>Email</label>
                <input type="email" required value={form.email}
                  onChange={e => setForm(f => ({ ...f, email: e.target.value }))} placeholder="user@company.com" />
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 14 }}>
                <div className="lm-form-group">
                  <label>First Name</label>
                  <input type="text" required value={form.first_name}
                    onChange={e => setForm(f => ({ ...f, first_name: e.target.value }))} />
                </div>
                <div className="lm-form-group">
                  <label>Last Name</label>
                  <input type="text" required value={form.last_name}
                    onChange={e => setForm(f => ({ ...f, last_name: e.target.value }))} />
                </div>
              </div>
              <div className="lm-modal-actions">
                <button type="button" className="lm-btn lm-btn-secondary" onClick={onClose}>Cancel</button>
                <button type="submit" disabled={loading} className="lm-btn lm-btn-primary">
                  {loading ? 'Inviting...' : 'Send Invite'}
                </button>
              </div>
            </form>
          </>
        )}
      </div>
    </div>
  );
}

// ─── Tenant Detail ─────────────────────────────────────────────────────────────
function TenantDetail({ tenant, recruitToken, onUpdated }) {
  const [tab, setTab] = useState('users');
  const [showInvite, setShowInvite] = useState(false);
  const [editing, setEditing] = useState(false);
  const [editForm, setEditForm] = useState({
    name: tenant.name,
    slug: tenant.slug,
    status: tenant.status || 'active',
  });
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState('');

  const { data: users, loading: usersLoading, refetch: refetchUsers } = useRecruitApi(
    `/api/v1/recruit-platform/tenants/${tenant.id}/users`, [tenant.id]
  );

  const handleSave = async () => {
    setSaving(true);
    setSaveError('');
    try {
      const res = await fetch(`${API_BASE}/api/v1/recruit-platform/tenants/${tenant.id}`, {
        method: 'PATCH',
        headers: { Authorization: `Bearer ${recruitToken}`, 'Content-Type': 'application/json' },
        body: JSON.stringify(editForm),
      });
      if (!res.ok) { const e = await res.json(); throw new Error(e.detail || 'Failed to update'); }
      setEditing(false);
      onUpdated();
    } catch (err) {
      setSaveError(err.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div>
      <div className="lm-detail-header">
        <h2>
          {tenant.name}
          <span className={`lm-badge ${tenant.status === 'active' ? 'lm-badge-active' : 'lm-badge-inactive'}`}>
            {tenant.status || 'active'}
          </span>
        </h2>
        <div style={{ display: 'flex', gap: 8 }}>
          {editing ? (
            <>
              <button className="lm-btn lm-btn-secondary lm-btn-sm" onClick={() => setEditing(false)}>Cancel</button>
              <button className="lm-btn lm-btn-primary lm-btn-sm" disabled={saving} onClick={handleSave}>
                {saving ? 'Saving...' : 'Save'}
              </button>
            </>
          ) : (
            <button className="lm-btn lm-btn-secondary lm-btn-sm" onClick={() => setEditing(true)}>Edit</button>
          )}
        </div>
      </div>

      {editing && (
        <div className="lm-form" style={{ marginBottom: 24 }}>
          {saveError && <div className="lm-error">{saveError}</div>}
          <div className="lm-form-grid">
            <div className="lm-form-group">
              <label>Organization Name</label>
              <input value={editForm.name} onChange={e => setEditForm(f => ({ ...f, name: e.target.value }))} />
            </div>
            <div className="lm-form-group">
              <label>Slug</label>
              <input value={editForm.slug} onChange={e => setEditForm(f => ({ ...f, slug: e.target.value }))} />
            </div>
            <div className="lm-form-group">
              <label>Status</label>
              <select value={editForm.status} onChange={e => setEditForm(f => ({ ...f, status: e.target.value }))}>
                <option value="active">Active</option>
                <option value="inactive">Inactive</option>
              </select>
            </div>
          </div>
        </div>
      )}

      <div className="lm-tabs">
        {['users', 'applicants', 'jobs'].map(t => (
          <button key={t} className={`lm-tab ${tab === t ? 'active' : ''}`} onClick={() => setTab(t)}>
            {t.charAt(0).toUpperCase() + t.slice(1)}
          </button>
        ))}
      </div>

      {tab === 'users' && (
        <div>
          <div className="lm-tab-header">
            <span style={{ fontSize: 14, color: '#374151', fontWeight: 600 }}>
              {users?.length || 0} users
            </span>
            <button className="lm-btn lm-btn-primary lm-btn-sm" onClick={() => setShowInvite(true)}>
              + Invite User
            </button>
          </div>
          {usersLoading ? (
            <div className="lm-loading">Loading users...</div>
          ) : (
            <div className="lm-table-wrap">
              <table className="lm-table">
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Email</th>
                    <th>Role</th>
                    <th>Joined</th>
                  </tr>
                </thead>
                <tbody>
                  {(users || []).length === 0 ? (
                    <tr><td colSpan={4} style={{ textAlign: 'center', color: '#94a3b8' }}>No users yet</td></tr>
                  ) : (users || []).map(u => (
                    <tr key={u.id}>
                      <td>{u.first_name} {u.last_name}</td>
                      <td>{u.email}</td>
                      <td><span className="lm-badge lm-badge-tier">{u.role}</span></td>
                      <td>{u.created_at ? new Date(u.created_at).toLocaleDateString() : '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {tab === 'applicants' && (
        <div>
          <p style={{ fontSize: 14, color: '#64748b' }}>
            {tenant.applicant_count || 0} applicants for this organization.{' '}
            <a href="/recruit/dashboard" style={{ color: '#1d4ed8' }}>View in pipeline →</a>
          </p>
        </div>
      )}

      {tab === 'jobs' && (
        <div>
          <p style={{ fontSize: 14, color: '#64748b' }}>
            <a href="/recruit/jobs" style={{ color: '#1d4ed8' }}>View job postings for {tenant.name} →</a>
          </p>
        </div>
      )}

      {showInvite && (
        <InviteModal
          tenantId={tenant.id}
          recruitToken={recruitToken}
          onClose={() => { setShowInvite(false); refetchUsers(); }}
        />
      )}
    </div>
  );
}

// ─── Create Tenant Form ────────────────────────────────────────────────────────
function CreateTenantForm({ recruitToken, onCreated, onCancel }) {
  const [form, setForm] = useState({
    name: '',
    slug: '',
    contact_email: '',
    subscription_tier: 'recruiting_starter',
  });
  const [slugManual, setSlugManual] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleNameChange = (e) => {
    const name = e.target.value;
    setForm(f => ({ ...f, name, slug: slugManual ? f.slug : slugify(name) }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    try {
      const res = await fetch(`${API_BASE}/api/v1/recruit-platform/tenants`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${recruitToken}`, 'Content-Type': 'application/json' },
        body: JSON.stringify(form),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Failed to create tenant');
      onCreated(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <h2 className="lm-section-title">Create Tenant</h2>
      <div className="lm-form">
        {error && <div className="lm-error">{error}</div>}
        <form onSubmit={handleSubmit}>
          <div className="lm-form-grid">
            <div className="lm-form-group full">
              <label>Organization Name *</label>
              <input type="text" required value={form.name} onChange={handleNameChange} placeholder="Acme Mortgage" />
            </div>
            <div className="lm-form-group full">
              <label>Slug *</label>
              <input
                type="text"
                required
                value={form.slug}
                onChange={e => { setSlugManual(true); setForm(f => ({ ...f, slug: e.target.value })); }}
                placeholder="acme-mortgage"
              />
              {form.slug && (
                <div className="lm-slug-preview">
                  Public URL: <span>recruit.perenniaai.com/apply/{form.slug}</span>
                </div>
              )}
            </div>
            <div className="lm-form-group full">
              <label>Contact Email</label>
              <input type="email" value={form.contact_email}
                onChange={e => setForm(f => ({ ...f, contact_email: e.target.value }))}
                placeholder="admin@company.com" />
            </div>
            <div className="lm-form-group full">
              <label>Subscription Tier</label>
              <select value={form.subscription_tier}
                onChange={e => setForm(f => ({ ...f, subscription_tier: e.target.value }))}>
                <option value="recruiting_starter">Recruiting Starter</option>
                <option value="recruiting_pro">Recruiting Pro</option>
                <option value="recruiting_enterprise">Recruiting Enterprise</option>
              </select>
            </div>
          </div>
          <div className="lm-form-actions">
            <button type="button" className="lm-btn lm-btn-secondary" onClick={onCancel}>Cancel</button>
            <button type="submit" disabled={loading} className="lm-btn lm-btn-primary">
              {loading ? 'Creating...' : 'Create Tenant'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ─── Main ──────────────────────────────────────────────────────────────────────
export default function LicenseManager() {
  const { recruitToken } = useRecruitPlatform();
  const [selectedTenant, setSelectedTenant] = useState(null);
  const [creating, setCreating] = useState(false);
  const { data: tenants, loading, error, refetch } = useRecruitApi('/api/v1/recruit-platform/tenants');

  const handleCreated = (tenant) => {
    refetch();
    setCreating(false);
    setSelectedTenant(tenant);
  };

  return (
    <div className="lm-layout">
      {/* Left sidebar — tenant list */}
      <div className="lm-sidebar">
        <div className="lm-sidebar-header">
          <h2>Tenants</h2>
          <button className="lm-btn lm-btn-primary lm-btn-sm" onClick={() => { setCreating(true); setSelectedTenant(null); }}>
            + New
          </button>
        </div>
        <div className="lm-tenant-list">
          {loading && <div className="lm-loading">Loading...</div>}
          {error && <div style={{ padding: '12px 16px', color: '#b91c1c', fontSize: 13 }}>{error}</div>}
          {(tenants || []).map(t => (
            <div
              key={t.id}
              className={`lm-tenant-row ${selectedTenant?.id === t.id ? 'active' : ''}`}
              onClick={() => { setSelectedTenant(t); setCreating(false); }}
            >
              <div className="lm-tenant-row-name">{t.name}</div>
              <div className="lm-tenant-row-meta">
                <span className={`lm-badge ${t.status === 'active' ? 'lm-badge-active' : 'lm-badge-inactive'}`}>
                  {t.status || 'active'}
                </span>
                <span>{t.user_count || 0} users</span>
                <span>{t.applicant_count || 0} applicants</span>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Right panel */}
      <div className="lm-panel">
        {creating ? (
          <CreateTenantForm
            recruitToken={recruitToken}
            onCreated={handleCreated}
            onCancel={() => setCreating(false)}
          />
        ) : selectedTenant ? (
          <TenantDetail
            tenant={selectedTenant}
            recruitToken={recruitToken}
            onUpdated={() => { refetch(); }}
          />
        ) : (
          <div className="lm-panel-empty">
            Select a tenant or create a new one to get started.
          </div>
        )}
      </div>
    </div>
  );
}
