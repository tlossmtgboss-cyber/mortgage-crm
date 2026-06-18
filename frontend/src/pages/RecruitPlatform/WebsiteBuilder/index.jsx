import React, { useState, useEffect, useCallback } from 'react';
import { useRecruitPlatform } from '../../../contexts/RecruitPlatformContext';
import './WebsiteBuilder.css';

const API_BASE = import.meta.env.VITE_API_URL || 'https://api.perenniaai.com';

function slugify(str) {
  return str.toLowerCase().trim().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
}

function deriveColors(hex) {
  // Darken by ~15%, lighten to pale (mix with white 85%)
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  const toHex = (n) => Math.max(0, Math.min(255, n)).toString(16).padStart(2, '0');
  const darkR = Math.round(r * 0.85);
  const darkG = Math.round(g * 0.85);
  const darkB = Math.round(b * 0.85);
  const paleR = Math.round(r + (255 - r) * 0.85);
  const paleG = Math.round(g + (255 - g) * 0.85);
  const paleB = Math.round(b + (255 - b) * 0.85);
  return {
    dark: `#${toHex(darkR)}${toHex(darkG)}${toHex(darkB)}`,
    pale: `#${toHex(paleR)}${toHex(paleG)}${toHex(paleB)}`,
  };
}

const DEFAULT_CONFIG = {
  primary_color: '#6AAA26',
  primary_color_dark: '#578F1E',
  primary_color_pale: '#EFF7E1',
  company_name: 'CMG Home Loans',
  company_nmls_id: '1820',
  location_display: 'Charleston & Columbia, SC',
  hero_headline: 'Build a <span class="red">six-figure</span><br>mortgage career<br>from <span class="italic">day one.</span>',
  hero_headline_plain: 'Build a six-figure mortgage career from day one.',
  signing_bonus: '$2,500 signing bonus for July hires',
  signing_bonus_amount: '$2,500',
  year1_range: '$65–90K',
  year2_top: '$120,000+',
  senior_lo: '$180,000+',
  team_lead: '$250,000+',
  stat_1_num: '2,400+',
  stat_1_label: 'Loans closed last year',
  stat_2_num: '94%',
  stat_2_label: 'Employees promoted within 18 months',
  stat_3_num: '4.97 ★',
  stat_3_label: 'Team borrower rating',
  stat_4_num: '8 Weeks',
  stat_4_label: 'Fully paid training program',
  manager_name: 'Tim Loss',
  manager_initials: 'TL',
  manager_title: 'Branch Manager · CMG Home Loans, Mt. Pleasant SC',
  manager_nmls: '187037',
  contact_phone_display: '(843) 834-4997',
  contact_phone_tel: '+18438344997',
  branch_name: 'CMG Home Loans',
  branch_address: '975 Johnnie Dodds Blvd. Suite A, Mt. Pleasant, SC 29464',
  branch_nmls: '1594871',
};

const TABS = [
  { id: 'branding', label: 'Branding' },
  { id: 'copy', label: 'Copy' },
  { id: 'earnings', label: 'Earnings' },
  { id: 'stats', label: 'Stats' },
  { id: 'contact', label: 'Contact' },
];

export default function WebsiteBuilder() {
  const { recruitToken } = useRecruitPlatform();
  const [pages, setPages] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [config, setConfig] = useState(DEFAULT_CONFIG);
  const [activeTab, setActiveTab] = useState('branding');
  const [saving, setSaving] = useState(false);
  const [showCreate, setShowCreate] = useState(false);
  const [createForm, setCreateForm] = useState({ title: '', slug: '' });
  const [error, setError] = useState('');
  const [saveMsg, setSaveMsg] = useState('');

  const authHeaders = {
    Authorization: `Bearer ${recruitToken}`,
    'Content-Type': 'application/json',
  };

  const loadPages = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/v1/recruit-platform/landing-pages`, { headers: authHeaders });
      if (res.ok) {
        const data = await res.json();
        setPages(data);
        if (data.length > 0 && !selectedId) {
          setSelectedId(data[0].id);
          setConfig({ ...DEFAULT_CONFIG, ...(data[0].config || {}) });
        }
      }
    } catch (e) {
      setError('Failed to load pages');
    }
  }, [recruitToken, selectedId]);

  useEffect(() => { loadPages(); }, []);

  const selectPage = (page) => {
    setSelectedId(page.id);
    setConfig({ ...DEFAULT_CONFIG, ...(page.config || {}) });
    setSaveMsg('');
    setError('');
  };

  const handleConfigChange = (field, value) => {
    setConfig((prev) => {
      const next = { ...prev, [field]: value };
      if (field === 'primary_color' && /^#[0-9a-fA-F]{6}$/.test(value)) {
        const { dark, pale } = deriveColors(value);
        next.primary_color_dark = dark;
        next.primary_color_pale = pale;
      }
      if (field === 'manager_name') {
        const parts = value.trim().split(/\s+/);
        next.manager_initials = parts.map((p) => p[0]?.toUpperCase() || '').slice(0, 2).join('');
      }
      return next;
    });
  };

  const saveDraft = async () => {
    if (!selectedId) return;
    setSaving(true);
    setError('');
    try {
      const res = await fetch(`${API_BASE}/api/v1/recruit-platform/landing-pages/${selectedId}`, {
        method: 'PUT',
        headers: authHeaders,
        body: JSON.stringify({ config }),
      });
      if (!res.ok) throw new Error((await res.json()).detail || 'Save failed');
      setSaveMsg('Saved');
      setTimeout(() => setSaveMsg(''), 2000);
      await loadPages();
    } catch (e) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  };

  const publishPage = async () => {
    if (!selectedId) return;
    setSaving(true);
    try {
      await saveDraft();
      const res = await fetch(`${API_BASE}/api/v1/recruit-platform/landing-pages/${selectedId}/publish`, {
        method: 'POST',
        headers: authHeaders,
      });
      if (!res.ok) throw new Error((await res.json()).detail || 'Publish failed');
      await loadPages();
      setSaveMsg('Published');
      setTimeout(() => setSaveMsg(''), 3000);
    } catch (e) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  };

  const unpublishPage = async () => {
    if (!selectedId) return;
    setSaving(true);
    try {
      const res = await fetch(`${API_BASE}/api/v1/recruit-platform/landing-pages/${selectedId}/unpublish`, {
        method: 'POST',
        headers: authHeaders,
      });
      if (!res.ok) throw new Error((await res.json()).detail || 'Failed');
      await loadPages();
    } catch (e) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  };

  const previewPage = () => {
    if (!selectedId) return;
    window.open(`${API_BASE}/api/v1/recruit-platform/landing-pages/${selectedId}/preview`, '_blank');
  };

  const copyUrl = () => {
    const page = pages.find((p) => p.id === selectedId);
    if (!page) return;
    const url = `https://recruit.perenniaai.com/${page.slug}`;
    navigator.clipboard.writeText(url).then(() => {
      setSaveMsg('URL copied');
      setTimeout(() => setSaveMsg(''), 2000);
    });
  };

  const deletePage = async () => {
    if (!selectedId) return;
    if (!window.confirm('Delete this page?')) return;
    try {
      await fetch(`${API_BASE}/api/v1/recruit-platform/landing-pages/${selectedId}`, {
        method: 'DELETE',
        headers: authHeaders,
      });
      setSelectedId(null);
      setConfig(DEFAULT_CONFIG);
      await loadPages();
    } catch (e) {
      setError(e.message);
    }
  };

  const createPage = async () => {
    if (!createForm.title || !createForm.slug) return;
    try {
      const res = await fetch(`${API_BASE}/api/v1/recruit-platform/landing-pages`, {
        method: 'POST',
        headers: authHeaders,
        body: JSON.stringify({ title: createForm.title, slug: createForm.slug, config: DEFAULT_CONFIG }),
      });
      if (!res.ok) throw new Error((await res.json()).detail || 'Create failed');
      const created = await res.json();
      setShowCreate(false);
      setCreateForm({ title: '', slug: '' });
      await loadPages();
      setSelectedId(created.id);
      setConfig({ ...DEFAULT_CONFIG, ...(created.config || {}) });
    } catch (e) {
      setError(e.message);
    }
  };

  const selectedPage = pages.find((p) => p.id === selectedId);
  const isPublished = selectedPage?.status === 'published';

  return (
    <div className="wb-container">
      {/* Left panel: page list */}
      <div className="wb-sidebar">
        <div className="wb-sidebar-header">
          <span className="wb-sidebar-title">Landing Pages</span>
          <button className="wb-new-btn" onClick={() => setShowCreate(true)}>+ New</button>
        </div>

        {pages.length === 0 && (
          <div className="wb-empty">No pages yet. Create your first landing page.</div>
        )}

        {pages.map((page) => (
          <div
            key={page.id}
            className={`wb-page-item${page.id === selectedId ? ' active' : ''}`}
            onClick={() => selectPage(page)}
          >
            <div className="wb-page-item-title">{page.title}</div>
            <div className="wb-page-item-meta">
              <span className={`wb-status-badge ${page.status}`}>{page.status}</span>
              <span className="wb-page-stats">{page.view_count} views · {page.submission_count} leads</span>
            </div>
            <div className="wb-page-slug">recruit.perenniaai.com/{page.slug}</div>
          </div>
        ))}
      </div>

      {/* Right panel: editor */}
      <div className="wb-editor">
        {!selectedId ? (
          <div className="wb-no-selection">
            <p>Select a page to edit or create a new one.</p>
          </div>
        ) : (
          <>
            {/* Action bar */}
            <div className="wb-action-bar">
              <div className="wb-action-left">
                <span className="wb-editing-title">{selectedPage?.title}</span>
                {saveMsg && <span className="wb-save-msg">{saveMsg}</span>}
                {error && <span className="wb-error-msg">{error}</span>}
              </div>
              <div className="wb-action-right">
                <button className="wb-btn wb-btn-ghost" onClick={previewPage}>Preview</button>
                <button className="wb-btn wb-btn-ghost" onClick={copyUrl}>Copy URL</button>
                <button className="wb-btn wb-btn-secondary" onClick={saveDraft} disabled={saving}>
                  Save Draft
                </button>
                {isPublished ? (
                  <button className="wb-btn wb-btn-warning" onClick={unpublishPage} disabled={saving}>
                    Unpublish
                  </button>
                ) : (
                  <button className="wb-btn wb-btn-primary" onClick={publishPage} disabled={saving}>
                    Publish
                  </button>
                )}
                <button className="wb-btn wb-btn-danger" onClick={deletePage}>Delete</button>
              </div>
            </div>

            {/* Tabs */}
            <div className="wb-tabs">
              {TABS.map((tab) => (
                <button
                  key={tab.id}
                  className={`wb-tab${activeTab === tab.id ? ' active' : ''}`}
                  onClick={() => setActiveTab(tab.id)}
                >
                  {tab.label}
                </button>
              ))}
            </div>

            {/* Tab content */}
            <div className="wb-tab-content">
              {activeTab === 'branding' && (
                <BrandingTab config={config} onChange={handleConfigChange} />
              )}
              {activeTab === 'copy' && (
                <CopyTab config={config} onChange={handleConfigChange} />
              )}
              {activeTab === 'earnings' && (
                <EarningsTab config={config} onChange={handleConfigChange} />
              )}
              {activeTab === 'stats' && (
                <StatsTab config={config} onChange={handleConfigChange} />
              )}
              {activeTab === 'contact' && (
                <ContactTab config={config} onChange={handleConfigChange} />
              )}
            </div>
          </>
        )}
      </div>

      {/* Create modal */}
      {showCreate && (
        <div className="wb-modal-overlay" onClick={() => setShowCreate(false)}>
          <div className="wb-modal" onClick={(e) => e.stopPropagation()}>
            <h3>Create Landing Page</h3>
            <div className="wb-form-group">
              <label>Page Title</label>
              <input
                className="wb-input"
                placeholder="e.g. Call Center – Charleston"
                value={createForm.title}
                onChange={(e) => setCreateForm((f) => ({
                  ...f,
                  title: e.target.value,
                  slug: slugify(e.target.value),
                }))}
              />
            </div>
            <div className="wb-form-group">
              <label>URL Slug</label>
              <div className="wb-slug-preview">recruit.perenniaai.com/<strong>{createForm.slug || 'your-slug'}</strong></div>
              <input
                className="wb-input"
                placeholder="e.g. callcenter"
                value={createForm.slug}
                onChange={(e) => setCreateForm((f) => ({ ...f, slug: slugify(e.target.value) }))}
              />
            </div>
            {error && <div className="wb-error-msg">{error}</div>}
            <div className="wb-modal-actions">
              <button className="wb-btn wb-btn-ghost" onClick={() => { setShowCreate(false); setError(''); }}>
                Cancel
              </button>
              <button className="wb-btn wb-btn-primary" onClick={createPage}
                disabled={!createForm.title || !createForm.slug}>
                Create
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Tab components ──────────────────────────────────────────────────────────

function Field({ label, value, onChange, type = 'text', hint }) {
  return (
    <div className="wb-form-group">
      <label>{label}</label>
      <input
        className="wb-input"
        type={type}
        value={value || ''}
        onChange={(e) => onChange(e.target.value)}
      />
      {hint && <div className="wb-hint">{hint}</div>}
    </div>
  );
}

function BrandingTab({ config, onChange }) {
  return (
    <div className="wb-tab-section">
      <h4>Brand Colors</h4>
      <div className="wb-color-row">
        <div className="wb-form-group">
          <label>Primary Color</label>
          <div className="wb-color-input-wrap">
            <input type="color" className="wb-color-picker" value={config.primary_color || '#6AAA26'}
              onChange={(e) => onChange('primary_color', e.target.value)} />
            <input className="wb-input wb-color-text" value={config.primary_color || ''}
              onChange={(e) => onChange('primary_color', e.target.value)} />
          </div>
          <div className="wb-hint">Dark and pale variants auto-calculated</div>
        </div>
        <div className="wb-form-group">
          <label>Dark Variant</label>
          <input className="wb-input" value={config.primary_color_dark || ''} readOnly />
        </div>
        <div className="wb-form-group">
          <label>Pale Variant</label>
          <input className="wb-input" value={config.primary_color_pale || ''} readOnly />
        </div>
      </div>

      <div className="wb-color-preview">
        <div className="wb-swatch" style={{ background: config.primary_color }}>Primary</div>
        <div className="wb-swatch" style={{ background: config.primary_color_dark }}>Dark</div>
        <div className="wb-swatch" style={{ background: config.primary_color_pale, color: '#333' }}>Pale</div>
      </div>

      <h4>Company</h4>
      <Field label="Company Name" value={config.company_name} onChange={(v) => onChange('company_name', v)} />
      <Field label="Company NMLS ID" value={config.company_nmls_id} onChange={(v) => onChange('company_nmls_id', v)} />
    </div>
  );
}

function CopyTab({ config, onChange }) {
  return (
    <div className="wb-tab-section">
      <Field label="Location Display" value={config.location_display}
        onChange={(v) => onChange('location_display', v)}
        hint="e.g. Charleston & Columbia, SC" />
      <div className="wb-form-group">
        <label>Hero Headline (HTML allowed)</label>
        <textarea className="wb-input wb-textarea" value={config.hero_headline || ''}
          onChange={(e) => onChange('hero_headline', e.target.value)} rows={3} />
        <div className="wb-hint">Use &lt;span class="red"&gt;text&lt;/span&gt; for accent color</div>
      </div>
      <Field label="Hero Headline (plain text, for page title)"
        value={config.hero_headline_plain}
        onChange={(v) => onChange('hero_headline_plain', v)} />
      <Field label="Signing Bonus Text" value={config.signing_bonus}
        onChange={(v) => onChange('signing_bonus', v)}
        hint="Shown as hero checklist item" />
      <Field label="Signing Bonus Amount" value={config.signing_bonus_amount}
        onChange={(v) => onChange('signing_bonus_amount', v)}
        hint="e.g. $2,500 — shown in earnings table" />
    </div>
  );
}

function EarningsTab({ config, onChange }) {
  return (
    <div className="wb-tab-section">
      <h4>Earnings Figures</h4>
      <Field label="Year 1 OTE" value={config.year1_range}
        onChange={(v) => onChange('year1_range', v)} hint="e.g. $65–90K" />
      <Field label="Year 2 Top Performer" value={config.year2_top}
        onChange={(v) => onChange('year2_top', v)} hint="e.g. $120,000+" />
      <Field label="Senior LO" value={config.senior_lo}
        onChange={(v) => onChange('senior_lo', v)} hint="e.g. $180,000+" />
      <Field label="Team Lead / Manager" value={config.team_lead}
        onChange={(v) => onChange('team_lead', v)} hint="e.g. $250,000+" />
    </div>
  );
}

function StatsTab({ config, onChange }) {
  return (
    <div className="wb-tab-section">
      <h4>Hero Stats (shown below the headline)</h4>
      <div className="wb-stat-row">
        <Field label="Stat 1 Number" value={config.stat_1_num} onChange={(v) => onChange('stat_1_num', v)} />
        <Field label="Stat 1 Label" value={config.stat_1_label} onChange={(v) => onChange('stat_1_label', v)} />
      </div>
      <div className="wb-stat-row">
        <Field label="Stat 2 Number" value={config.stat_2_num} onChange={(v) => onChange('stat_2_num', v)} />
        <Field label="Stat 2 Label" value={config.stat_2_label} onChange={(v) => onChange('stat_2_label', v)} />
      </div>
      <div className="wb-stat-row">
        <Field label="Stat 3 Number" value={config.stat_3_num} onChange={(v) => onChange('stat_3_num', v)} />
        <Field label="Stat 3 Label" value={config.stat_3_label} onChange={(v) => onChange('stat_3_label', v)} />
      </div>
      <div className="wb-stat-row">
        <Field label="Stat 4 Number" value={config.stat_4_num} onChange={(v) => onChange('stat_4_num', v)} />
        <Field label="Stat 4 Label" value={config.stat_4_label} onChange={(v) => onChange('stat_4_label', v)} />
      </div>
    </div>
  );
}

function ContactTab({ config, onChange }) {
  return (
    <div className="wb-tab-section">
      <h4>Hiring Manager</h4>
      <Field label="Manager Name" value={config.manager_name}
        onChange={(v) => onChange('manager_name', v)} />
      <Field label="Manager Initials" value={config.manager_initials}
        onChange={(v) => onChange('manager_initials', v)}
        hint="Auto-calculated from name, or override" />
      <Field label="Manager Title" value={config.manager_title}
        onChange={(v) => onChange('manager_title', v)} hint="e.g. Branch Manager · CMG, Mt. Pleasant SC" />
      <Field label="Manager NMLS#" value={config.manager_nmls}
        onChange={(v) => onChange('manager_nmls', v)} />

      <h4>Branch Contact</h4>
      <Field label="Phone Display" value={config.contact_phone_display}
        onChange={(v) => onChange('contact_phone_display', v)} hint="e.g. (843) 834-4997" />
      <Field label="Phone (tel: href)" value={config.contact_phone_tel}
        onChange={(v) => onChange('contact_phone_tel', v)} hint="e.g. +18438344997" />
      <Field label="Branch Name" value={config.branch_name}
        onChange={(v) => onChange('branch_name', v)} />
      <Field label="Branch Address" value={config.branch_address}
        onChange={(v) => onChange('branch_address', v)} />
      <Field label="Branch NMLS#" value={config.branch_nmls}
        onChange={(v) => onChange('branch_nmls', v)} />
    </div>
  );
}
