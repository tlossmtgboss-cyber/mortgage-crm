import React, { useState, useEffect, useCallback } from 'react';
import './WebsiteBuilder.css';

const API = 'https://api.perenniaai.com';

function authHeaders() {
  const token = localStorage.getItem('recruit_auth_token');
  return {
    Authorization: `Bearer ${token}`,
    'Content-Type': 'application/json',
  };
}

function deriveColors(hex) {
  if (!hex || !/^#[0-9a-fA-F]{6}$/.test(hex)) return { dark: '', pale: '' };
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  const dark = '#' + [r, g, b].map(c => Math.max(0, Math.round(c * 0.82)).toString(16).padStart(2, '0')).join('');
  const pale = '#' + [r, g, b].map(c => Math.min(255, Math.round(c * 0.08 + 255 * 0.92)).toString(16).padStart(2, '0')).join('');
  return { dark, pale };
}

function toSlug(str) {
  return str.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');
}

const DEFAULT_CONFIG = {
  page_title: 'Careers — Apply Now',
  company_name: 'CMG Home Loans',
  location_display: 'Charleston & Columbia, SC',
  primary_color: '#6AAA26',
  primary_color_dark: '#578F1E',
  primary_color_pale: '#EFF7E1',
  logo_url: '',
  hero_headline: 'Build a <span class="red">six-figure</span><br>mortgage career<br>from <span class="italic">day one.</span>',
  hero_subheadline: "No mortgage experience required. We recruit driven, coachable people ready to earn what they're worth in one of America's most resilient industries.",
  signing_bonus: '$2,500',
  signing_bonus_month: 'July',
  signing_bonus_deadline: 'July 31st',
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
  manager_initials: 'TL',
  manager_name: 'Tim Loss',
  manager_title: 'Branch Manager · CMG Home Loans, Mt. Pleasant SC · NMLS# 187037',
  manager_nmls: '187037',
  contact_phone_display: '(843) 834-4997',
  contact_phone_tel: '+18438344997',
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
  const [pages, setPages] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedPage, setSelectedPage] = useState(null);
  const [formConfig, setFormConfig] = useState({});
  const [activeTab, setActiveTab] = useState('branding');
  const [saving, setSaving] = useState(false);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [newTitle, setNewTitle] = useState('');
  const [newSlug, setNewSlug] = useState('');
  const [creating, setCreating] = useState(false);
  const [toast, setToast] = useState(null);

  const showToast = useCallback((msg) => {
    setToast(msg);
    setTimeout(() => setToast(null), 2400);
  }, []);

  const loadPages = useCallback(async () => {
    try {
      const res = await fetch(`${API}/api/v1/recruit-platform/landing-pages/`, {
        headers: authHeaders(),
      });
      if (res.ok) {
        const data = await res.json();
        setPages(Array.isArray(data) ? data : (data.pages || data.items || []));
      }
    } catch {
      // silently fail — pages stay empty
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadPages(); }, [loadPages]);

  async function selectPage(page) {
    setSelectedPage(page);
    setActiveTab('branding');
    try {
      const res = await fetch(`${API}/api/v1/recruit-platform/landing-pages/${page.id}`, {
        headers: authHeaders(),
      });
      if (res.ok) {
        const data = await res.json();
        setFormConfig(data.config || data || {});
      } else {
        setFormConfig(page.config || {});
      }
    } catch {
      setFormConfig(page.config || {});
    }
  }

  function setField(key, value) {
    setFormConfig(prev => ({ ...prev, [key]: value }));
  }

  function handleColorChange(hex) {
    const derived = deriveColors(hex);
    setFormConfig(prev => ({
      ...prev,
      primary_color: hex,
      primary_color_dark: derived.dark,
      primary_color_pale: derived.pale,
    }));
  }

  async function saveDraft() {
    if (!selectedPage) return;
    setSaving(true);
    try {
      const res = await fetch(`${API}/api/v1/recruit-platform/landing-pages/${selectedPage.id}`, {
        method: 'PATCH',
        headers: authHeaders(),
        body: JSON.stringify({ config: formConfig, status: 'draft' }),
      });
      if (res.ok) {
        showToast('Draft saved');
        await loadPages();
      } else {
        showToast('Save failed — check connection');
      }
    } catch {
      showToast('Save failed — check connection');
    } finally {
      setSaving(false);
    }
  }

  async function togglePublish() {
    if (!selectedPage) return;
    const isPublished = selectedPage.status === 'published';
    const endpoint = isPublished ? 'unpublish' : 'publish';
    setSaving(true);
    try {
      const res = await fetch(`${API}/api/v1/recruit-platform/landing-pages/${selectedPage.id}/${endpoint}`, {
        method: 'POST',
        headers: authHeaders(),
      });
      if (res.ok) {
        showToast(isPublished ? 'Page unpublished' : 'Page published!');
        await loadPages();
        setSelectedPage(prev => ({ ...prev, status: isPublished ? 'draft' : 'published' }));
      } else {
        showToast('Action failed');
      }
    } catch {
      showToast('Action failed');
    } finally {
      setSaving(false);
    }
  }

  async function deletePage() {
    if (!selectedPage) return;
    if (!window.confirm(`Delete "${selectedPage.title}"? This cannot be undone.`)) return;
    try {
      const res = await fetch(`${API}/api/v1/recruit-platform/landing-pages/${selectedPage.id}`, {
        method: 'DELETE',
        headers: authHeaders(),
      });
      if (res.ok) {
        showToast('Page deleted');
        setSelectedPage(null);
        setFormConfig({});
        await loadPages();
      } else {
        showToast('Delete failed');
      }
    } catch {
      showToast('Delete failed');
    }
  }

  function copyPublicUrl() {
    if (!selectedPage) return;
    const url = `https://recruit.perenniaai.com/p/${selectedPage.slug}`;
    navigator.clipboard.writeText(url).then(() => showToast('URL copied!')).catch(() => showToast(url));
  }

  function openPreview() {
    if (!selectedPage) return;
    window.open(`${API}/api/v1/recruit-platform/landing-pages/${selectedPage.id}/preview`, '_blank');
  }

  async function createPage() {
    if (!newTitle.trim() || !newSlug.trim()) return;
    setCreating(true);
    try {
      const res = await fetch(`${API}/api/v1/recruit-platform/landing-pages/`, {
        method: 'POST',
        headers: authHeaders(),
        body: JSON.stringify({
          title: newTitle.trim(),
          slug: newSlug.trim(),
          status: 'draft',
          config: { ...DEFAULT_CONFIG, page_title: newTitle.trim() },
        }),
      });
      if (res.ok) {
        const created = await res.json();
        setShowCreateModal(false);
        setNewTitle('');
        setNewSlug('');
        await loadPages();
        selectPage(created);
        showToast('Page created');
      } else {
        const err = await res.json().catch(() => ({}));
        showToast(err.detail || 'Create failed');
      }
    } catch {
      showToast('Create failed');
    } finally {
      setCreating(false);
    }
  }

  function handleNewTitleChange(val) {
    setNewTitle(val);
    setNewSlug(toSlug(val));
  }

  const isPublished = selectedPage?.status === 'published';

  return (
    <div className="wb-shell">
      {/* ── Left sidebar: page list ── */}
      <div className="wb-sidebar">
        <div className="wb-sidebar-header">
          <div>
            <div className="wb-sidebar-title">Landing Pages</div>
            <div className="wb-sidebar-subtitle">{pages.length} page{pages.length !== 1 ? 's' : ''}</div>
          </div>
          <button className="wb-create-btn" onClick={() => { setShowCreateModal(true); setNewTitle(''); setNewSlug(''); }}>
            + New Page
          </button>
        </div>

        <div className="wb-page-list">
          {loading && (
            <div className="wb-loading">
              <span>Loading pages…</span>
            </div>
          )}
          {!loading && pages.length === 0 && (
            <div className="wb-empty-list">
              <div className="wb-empty-list-icon">🌐</div>
              <div>No landing pages yet.</div>
              <div>Create your first page to start capturing applicants.</div>
            </div>
          )}
          {pages.map(page => (
            <div
              key={page.id}
              className={`wb-page-item${selectedPage?.id === page.id ? ' selected' : ''}`}
              onClick={() => selectPage(page)}
            >
              <div className="wb-page-item-top">
                <div className="wb-page-item-title">{page.title}</div>
                <span className={`wb-badge ${page.status === 'published' ? 'published' : 'draft'}`}>
                  {page.status === 'published' ? '● Published' : '○ Draft'}
                </span>
              </div>
              <div className="wb-page-item-slug">/p/{page.slug}</div>
              <div className="wb-page-item-meta">
                <span className="wb-page-item-stat">👁 {page.view_count ?? 0} views</span>
                <span className="wb-page-item-stat">📝 {page.submission_count ?? 0} submissions</span>
              </div>
              <div className="wb-page-item-actions">
                <button
                  className="wb-page-item-action edit"
                  onClick={e => { e.stopPropagation(); selectPage(page); }}
                >
                  Edit
                </button>
                <button
                  className="wb-page-item-action copy"
                  onClick={e => {
                    e.stopPropagation();
                    const url = `https://recruit.perenniaai.com/p/${page.slug}`;
                    navigator.clipboard.writeText(url).then(() => showToast('URL copied!')).catch(() => showToast(url));
                  }}
                >
                  Copy Link
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* ── Main editor ── */}
      <div className="wb-main">
        {!selectedPage ? (
          <div className="wb-empty-state">
            <div className="wb-empty-state-icon">🌐</div>
            <h3>No page selected</h3>
            <p>Select a landing page from the list to edit it, or create a new one.</p>
            <button className="wb-create-btn" onClick={() => { setShowCreateModal(true); setNewTitle(''); setNewSlug(''); }}>
              + Create First Page
            </button>
          </div>
        ) : (
          <>
            <div className="wb-main-header">
              <div>
                <div className="wb-main-header-title">{selectedPage.title}</div>
                <div className="wb-main-header-slug">/p/{selectedPage.slug}</div>
              </div>
              <span className={`wb-badge ${isPublished ? 'published' : 'draft'}`}>
                {isPublished ? '● Published' : '○ Draft'}
              </span>
            </div>

            {/* Tabs */}
            <div className="wb-tabs">
              {TABS.map(t => (
                <button
                  key={t.id}
                  className={`wb-tab${activeTab === t.id ? ' active' : ''}`}
                  onClick={() => setActiveTab(t.id)}
                >
                  {t.label}
                </button>
              ))}
            </div>

            {/* Tab content */}
            <div className="wb-tab-content">
              {activeTab === 'branding' && (
                <BrandingTab config={formConfig} setField={setField} onColorChange={handleColorChange} />
              )}
              {activeTab === 'copy' && (
                <CopyTab config={formConfig} setField={setField} />
              )}
              {activeTab === 'earnings' && (
                <EarningsTab config={formConfig} setField={setField} />
              )}
              {activeTab === 'stats' && (
                <StatsTab config={formConfig} setField={setField} />
              )}
              {activeTab === 'contact' && (
                <ContactTab config={formConfig} setField={setField} />
              )}
            </div>

            {/* Action bar */}
            <div className="wb-action-bar">
              <button className="wb-btn danger" onClick={deletePage} disabled={saving} title="Delete page">
                🗑
              </button>
              <div className="spacer" />
              <button className="wb-btn draft" onClick={saveDraft} disabled={saving}>
                {saving ? 'Saving…' : 'Save Draft'}
              </button>
              <button className={`wb-btn ${isPublished ? 'unpublish' : 'publish'}`} onClick={togglePublish} disabled={saving}>
                {isPublished ? 'Unpublish' : 'Publish'}
              </button>
              <button className="wb-btn preview" onClick={openPreview}>
                Preview ↗
              </button>
              <button className="wb-btn copy-url" onClick={copyPublicUrl}>
                Copy URL
              </button>
            </div>
          </>
        )}
      </div>

      {/* ── Create Modal ── */}
      {showCreateModal && (
        <div className="wb-modal-overlay" onClick={() => setShowCreateModal(false)}>
          <div className="wb-modal" onClick={e => e.stopPropagation()}>
            <div className="wb-modal-title">New Landing Page</div>
            <div className="wb-modal-desc">Create a new recruitment landing page to run ad campaigns to.</div>

            <div className="wb-modal-template-note">
              🌱 <strong>Default template:</strong> Uses the CMG careers template with placeholder values. Customize the copy after creating.
            </div>

            <div className="wb-form-group">
              <label className="wb-label">Page Title</label>
              <input
                className="wb-input"
                placeholder="e.g. Charleston Careers — Summer Hiring"
                value={newTitle}
                onChange={e => handleNewTitleChange(e.target.value)}
                autoFocus
              />
            </div>

            <div className="wb-form-group">
              <label className="wb-label">
                URL Slug
                <span className="wb-label-hint">recruit.perenniaai.com/p/<strong>{newSlug || 'your-slug'}</strong></span>
              </label>
              <input
                className="wb-input"
                placeholder="charleston-careers-summer"
                value={newSlug}
                onChange={e => setNewSlug(toSlug(e.target.value))}
              />
            </div>

            <div className="wb-modal-actions">
              <button className="wb-modal-cancel" onClick={() => setShowCreateModal(false)}>Cancel</button>
              <button
                className="wb-modal-create"
                onClick={createPage}
                disabled={creating || !newTitle.trim() || !newSlug.trim()}
              >
                {creating ? 'Creating…' : 'Create Page'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Toast ── */}
      {toast && <div className="wb-toast">{toast}</div>}
    </div>
  );
}

/* ── Tab components ── */

function Field({ label, hint, children }) {
  return (
    <div className="wb-form-group">
      <label className="wb-label">
        {label}
        {hint && <span className="wb-label-hint">{hint}</span>}
      </label>
      {children}
    </div>
  );
}

function BrandingTab({ config, setField, onColorChange }) {
  return (
    <>
      <div className="wb-section-label">Identity</div>
      <div className="wb-form-row">
        <Field label="Page Title">
          <input className="wb-input" value={config.page_title || ''} onChange={e => setField('page_title', e.target.value)} placeholder="Careers — Apply Now" />
        </Field>
        <Field label="Company Name">
          <input className="wb-input" value={config.company_name || ''} onChange={e => setField('company_name', e.target.value)} placeholder="CMG Home Loans" />
        </Field>
      </div>

      <Field label="Logo URL" hint="Leave blank to use the default CMG SVG logo">
        <input className="wb-input" value={config.logo_url || ''} onChange={e => setField('logo_url', e.target.value)} placeholder="https://example.com/logo.svg" />
      </Field>

      <div className="wb-section-label" style={{ marginTop: 20 }}>Colors</div>

      <Field label="Primary Color">
        <div className="wb-color-row">
          <input
            type="color"
            className="wb-color-swatch"
            value={config.primary_color || '#6AAA26'}
            onChange={e => onColorChange(e.target.value)}
          />
          <input
            className="wb-input wb-color-hex"
            value={config.primary_color || '#6AAA26'}
            onChange={e => onColorChange(e.target.value)}
            placeholder="#6AAA26"
          />
        </div>
      </Field>

      <div className="wb-form-row">
        <Field label="Primary Dark" hint="Auto-derived, or override">
          <input className="wb-input" value={config.primary_color_dark || ''} onChange={e => setField('primary_color_dark', e.target.value)} placeholder="#578F1E" />
        </Field>
        <Field label="Primary Pale" hint="Auto-derived, or override">
          <input className="wb-input" value={config.primary_color_pale || ''} onChange={e => setField('primary_color_pale', e.target.value)} placeholder="#EFF7E1" />
        </Field>
      </div>
    </>
  );
}

function CopyTab({ config, setField }) {
  return (
    <>
      <div className="wb-section-label">Location & Hero</div>
      <Field label="Location Display">
        <input className="wb-input" value={config.location_display || ''} onChange={e => setField('location_display', e.target.value)} placeholder="Charleston & Columbia, SC" />
      </Field>

      <Field label="Hero Headline" hint="HTML allowed: <span class='red'>text</span>, <span class='italic'>text</span>, <br>">
        <textarea className="wb-textarea" rows={4} value={config.hero_headline || ''} onChange={e => setField('hero_headline', e.target.value)} placeholder='Build a <span class="red">six-figure</span><br>mortgage career' />
      </Field>

      <Field label="Hero Subheadline">
        <textarea className="wb-textarea" rows={3} value={config.hero_subheadline || ''} onChange={e => setField('hero_subheadline', e.target.value)} placeholder="No mortgage experience required…" />
      </Field>

      <div className="wb-section-label" style={{ marginTop: 20 }}>Signing Bonus</div>
      <div className="wb-form-row">
        <Field label="Bonus Amount">
          <input className="wb-input" value={config.signing_bonus || ''} onChange={e => setField('signing_bonus', e.target.value)} placeholder="$2,500" />
        </Field>
        <Field label="Bonus Month">
          <input className="wb-input" value={config.signing_bonus_month || ''} onChange={e => setField('signing_bonus_month', e.target.value)} placeholder="July" />
        </Field>
      </div>
      <Field label="Application Deadline">
        <input className="wb-input" value={config.signing_bonus_deadline || ''} onChange={e => setField('signing_bonus_deadline', e.target.value)} placeholder="July 31st" />
      </Field>
    </>
  );
}

function EarningsTab({ config, setField }) {
  return (
    <>
      <div className="wb-section-label">On-Target Earnings</div>
      <div className="wb-form-row">
        <Field label="Year 1 Range">
          <input className="wb-input" value={config.year1_range || ''} onChange={e => setField('year1_range', e.target.value)} placeholder="$65–90K" />
        </Field>
        <Field label="Year 2 Top Performer">
          <input className="wb-input" value={config.year2_top || ''} onChange={e => setField('year2_top', e.target.value)} placeholder="$120,000+" />
        </Field>
      </div>
      <div className="wb-form-row">
        <Field label="Senior Loan Officer">
          <input className="wb-input" value={config.senior_lo || ''} onChange={e => setField('senior_lo', e.target.value)} placeholder="$180,000+" />
        </Field>
        <Field label="Team Lead / Branch Mgr">
          <input className="wb-input" value={config.team_lead || ''} onChange={e => setField('team_lead', e.target.value)} placeholder="$250,000+" />
        </Field>
      </div>
    </>
  );
}

function StatsTab({ config, setField }) {
  const stats = [1, 2, 3, 4];
  return (
    <>
      <div className="wb-section-label">Hero Stats Bar</div>
      {stats.map(n => (
        <div key={n} className="wb-stat-row">
          <div>
            <div className="wb-stat-row-label">Stat {n} — Number</div>
            <input className="wb-input" value={config[`stat_${n}_num`] || ''} onChange={e => setField(`stat_${n}_num`, e.target.value)} placeholder={n === 1 ? '2,400+' : n === 2 ? '94%' : n === 3 ? '4.97 ★' : '8 Weeks'} />
          </div>
          <div>
            <div className="wb-stat-row-label">Stat {n} — Label</div>
            <input className="wb-input" value={config[`stat_${n}_label`] || ''} onChange={e => setField(`stat_${n}_label`, e.target.value)} placeholder={n === 1 ? 'Loans closed last year' : n === 2 ? 'Employees promoted within 18 months' : n === 3 ? 'Team borrower rating' : 'Fully paid training program'} />
          </div>
        </div>
      ))}
    </>
  );
}

function ContactTab({ config, setField }) {
  return (
    <>
      <div className="wb-section-label">Manager / Leadership</div>
      <div className="wb-form-row">
        <Field label="Initials">
          <input className="wb-input" value={config.manager_initials || ''} onChange={e => setField('manager_initials', e.target.value)} placeholder="TL" />
        </Field>
        <Field label="Full Name">
          <input className="wb-input" value={config.manager_name || ''} onChange={e => setField('manager_name', e.target.value)} placeholder="Tim Loss" />
        </Field>
      </div>
      <Field label="Title Line">
        <input className="wb-input" value={config.manager_title || ''} onChange={e => setField('manager_title', e.target.value)} placeholder="Branch Manager · CMG Home Loans · NMLS# 187037" />
      </Field>
      <Field label="NMLS #">
        <input className="wb-input" value={config.manager_nmls || ''} onChange={e => setField('manager_nmls', e.target.value)} placeholder="187037" />
      </Field>

      <div className="wb-section-label" style={{ marginTop: 20 }}>Branch Contact</div>
      <div className="wb-form-row">
        <Field label="Phone Display">
          <input className="wb-input" value={config.contact_phone_display || ''} onChange={e => setField('contact_phone_display', e.target.value)} placeholder="(843) 834-4997" />
        </Field>
        <Field label="Phone (tel: href)">
          <input className="wb-input" value={config.contact_phone_tel || ''} onChange={e => setField('contact_phone_tel', e.target.value)} placeholder="+18438344997" />
        </Field>
      </div>
      <Field label="Branch Address">
        <input className="wb-input" value={config.branch_address || ''} onChange={e => setField('branch_address', e.target.value)} placeholder="975 Johnnie Dodds Blvd. Suite A, Mt. Pleasant, SC 29464" />
      </Field>
      <Field label="Branch NMLS #">
        <input className="wb-input" value={config.branch_nmls || ''} onChange={e => setField('branch_nmls', e.target.value)} placeholder="1594871" />
      </Field>
    </>
  );
}
