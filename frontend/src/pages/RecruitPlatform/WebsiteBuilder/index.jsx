import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useRecruitPlatform } from '../../../contexts/RecruitPlatformContext';
import './WebsiteBuilder.css';

const API_BASE = import.meta.env.VITE_API_URL || 'https://api.perenniaai.com';

function slugify(str) {
  return str.toLowerCase().trim().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
}

function deriveColors(hex) {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  const h = (n) => Math.max(0, Math.min(255, n)).toString(16).padStart(2, '0');
  return {
    dark: `#${h(Math.round(r * 0.85))}${h(Math.round(g * 0.85))}${h(Math.round(b * 0.85))}`,
    pale: `#${h(Math.round(r + (255 - r) * 0.85))}${h(Math.round(g + (255 - g) * 0.85))}${h(Math.round(b + (255 - b) * 0.85))}`,
  };
}

const DEFAULT_CONFIG = {
  primary_color: '#6AAA26',
  primary_color_dark: '#578F1E',
  primary_color_pale: '#EFF7E1',
  company_name: 'CMG Home Loans',
  company_nmls_id: '1820',
  location_display: 'Charleston, SC',
  hero_headline: 'Build a <span class="red">six-figure</span><br>mortgage career<br>from <span class="italic">day one.</span>',
  hero_headline_plain: 'Build a six-figure mortgage career from day one.',
  hero_subheadline: '',
  signing_bonus: '',
  signing_bonus_amount: '',
  year1_range: '$65–90K',
  year2_top: '$120,000+',
  senior_lo: '$180,000+',
  team_lead: '$250,000+',
  stat_1_num: '2,400+', stat_1_label: 'Loans closed last year',
  stat_2_num: '94%', stat_2_label: 'Employees promoted within 18 months',
  stat_3_num: '4.97 ★', stat_3_label: 'Team borrower rating',
  stat_4_num: '8 Weeks', stat_4_label: 'Fully paid training program',
  manager_name: 'Tim Loss',
  manager_initials: 'TL',
  manager_title: 'Branch Manager · CMG Home Loans, Mt. Pleasant SC',
  manager_nmls: '187037',
  contact_phone_display: '(843) 834-4997',
  contact_phone_tel: '+18438344997',
  branch_name: 'CMG Home Loans',
  branch_address: '975 Johnnie Dodds Blvd. Suite A, Mt. Pleasant, SC 29464',
  branch_nmls: '1594871',
  training_1_week: 'Weeks 1–2',
  training_1_title: 'Industry Foundations',
  training_1_desc: 'Understand mortgages end-to-end — loan types, rates, credit, and the SC housing market.',
  training_1_items: 'NMLS pre-licensing education (fully paid by CMG)\nSC mortgage law and compliance overview\nFull product catalog deep dive\nShadowing licensed LOs on live calls',
  training_2_week: 'Weeks 3–4',
  training_2_title: 'Sales Skills & Scripts',
  training_2_desc: "Build your frameworks. Practice until they feel natural. CMG's playbook is built from 10,000+ SC conversations.",
  training_2_items: 'Call recording and live coaching feedback\nComplete objection handling library\nPre-qualification scripting techniques\nDaily role-play with your cohort',
  training_3_week: 'Weeks 5–6',
  training_3_title: 'CRM & Technology Mastery',
  training_3_desc: "Learn every tool you'll use daily — so technology accelerates you instead of slowing you down.",
  training_3_items: 'Encompass LOS certification\nSalesforce pipeline management\nLead routing and prioritization\nAutomated follow-up sequences',
  training_4_week: 'Weeks 7–8',
  training_4_title: 'Live Pipeline Launch',
  training_4_desc: "You're licensed, trained, and ready. Work real leads with a senior coach in your corner.",
  training_4_items: 'First live borrower conversations\nFirst closed loan milestone bonus\n90-day personalized coaching plan\nFull team integration and onboarding',
  // Hero checks
  hero_check_1: 'No mortgage license required to start — CMG pays for it',
  hero_check_2: 'Warm, pre-qualified leads delivered to your pipeline daily',
  hero_check_3: 'Fully paid 8-week training program with live coaching',
  hero_check_4: 'Competitive base + uncapped commission from day one',
  // Earnings card labels
  earnings_label: 'Year 1 On-Target Earnings',
  earnings_note: 'base salary + commission',
  // Career path
  career_title: 'A real path forward —<br>not just another job.',
  career_sub: 'Every CMG loan officer in South Carolina starts at the same place. Where you go depends entirely on your drive and coachability.',
  career_1_timeline: 'Month 1–2', career_1_title: 'Loan Officer Trainee',
  career_1_desc: 'Paid training. Learn products, systems, compliance, and SC market dynamics.',
  career_1_salary: '$45K base',
  career_2_timeline: 'Month 3–12', career_2_title: 'Junior Loan Officer',
  career_2_desc: 'Live warm leads. Building pipeline. Coached on every deal you work.',
  career_2_salary: '$65–90K OTE',
  career_3_timeline: 'Year 2–3', career_3_title: 'Senior Loan Officer',
  career_3_desc: 'Referral network. Complex purchase loans. Mentoring incoming hires.',
  career_3_salary: '$120–180K OTE',
  career_4_timeline: 'Year 3+', career_4_title: 'Team Lead / Branch Mgr',
  career_4_desc: 'Build and lead your own team. Override income. Equity in the platform.',
  career_4_salary: '$250K+ OTE',
  // Training section headers
  training_section_title: 'Eight weeks that change<br>your career trajectory.',
  training_section_sub: "CMG's Mortgage Academy is nationally recognized. You'll be licensed, certified, and pipeline-ready before you take your first live borrower call.",
  // Testimonials
  testimonials_html: '',
  // Video / manager
  video_label: '3-minute message from our Regional Director',
  video_headline: '“We built this team to create careers, not fill seats.”',
  video_body: "<p>When we opened the South Carolina call center, the goal wasn't volume — it was building a team of mortgage professionals who'd still be here, and thriving, five years from now.</p>\n<p>Watch this short message to hear what our top performers have in common and what your first 90 days will actually look like.</p>",
  // CTA
  cta_headline: 'Your application takes under 3 minutes.',
  cta_body: 'No cover letter. No lengthy questionnaire. Just your name, phone, and a bit about yourself. A recruiter will be in touch within one business day.',
  cta_btn: 'Apply Now — It’s Free →',
  // Other pages
  why_hero_headline: 'The platform that lets<br>great producers <span>win.</span>',
  why_hero_body: "Tools, leads, coaching, and culture. Here's why CMG loan officers outperform the market — and why they stay.",
  apply_sidebar_headline: 'Tell us about <span>yourself.</span>',
  apply_sidebar_body: "Your application takes under 3 minutes. No resume required to start. A recruiter will contact you within one business day — and you'll schedule your intro call right here.",
  // Footer
  footer_legal: '',
};

const TABS = [
  { id: 'hero', label: 'Hero' },
  { id: 'branding', label: 'Branding' },
  { id: 'earnings', label: 'Earnings' },
  { id: 'stats', label: 'Stats' },
  { id: 'career', label: 'Career Path' },
  { id: 'manager', label: 'Manager' },
  { id: 'training', label: 'Training' },
  { id: 'cta', label: 'CTA' },
  { id: 'pages', label: 'Pages 2–4' },
  { id: 'content', label: 'Testimonials' },
  { id: 'footer', label: 'Footer' },
];

export default function WebsiteBuilder() {
  const { recruitToken, fetchWithAuth } = useRecruitPlatform();
  const [pages, setPages] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [config, setConfig] = useState(DEFAULT_CONFIG);
  const [activeTab, setActiveTab] = useState('hero');
  const [saving, setSaving] = useState(false);
  const [showCreate, setShowCreate] = useState(false);
  const [createForm, setCreateForm] = useState({ title: '', slug: '' });
  const [error, setError] = useState('');
  const [listError, setListError] = useState('');
  const [saveMsg, setSaveMsg] = useState('');
  const [previewHtml, setPreviewHtml] = useState('');
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewMobile, setPreviewMobile] = useState(false);
  const [seeding, setSeeding] = useState(false);
  const iframeRef = useRef(null);

  const loadPages = useCallback(async () => {
    if (!recruitToken) return;
    setListError('');
    try {
      const res = await fetchWithAuth(`${API_BASE}/api/v1/recruit-platform/landing-pages`);
      if (res.ok) {
        const data = await res.json();
        setPages(data);
        if (data.length > 0 && !selectedId) {
          setSelectedId(data[0].id);
          setConfig({ ...DEFAULT_CONFIG, ...(data[0].config || {}) });
        }
      } else {
        const body = await res.json().catch(() => ({}));
        setListError(body.detail || `API error ${res.status}`);
      }
    } catch (e) {
      setListError('Failed to connect to API');
    }
  }, [recruitToken, fetchWithAuth]);

  useEffect(() => { loadPages(); }, [loadPages]);

  const loadPreview = useCallback(async (pageId) => {
    if (!pageId || !recruitToken) return;
    setPreviewLoading(true);
    try {
      const res = await fetchWithAuth(
        `${API_BASE}/api/v1/recruit-platform/landing-pages/${pageId}/preview`,
        { headers: {} },
      );
      if (res.ok) setPreviewHtml(await res.text());
    } catch (_) {
      // preview fails silently
    } finally {
      setPreviewLoading(false);
    }
  }, [recruitToken, fetchWithAuth]);

  useEffect(() => {
    if (selectedId) loadPreview(selectedId);
  }, [selectedId, loadPreview]);

  useEffect(() => {
    const handler = (e) => {
      if (!e.data || e.data.type !== 'wb-field-click') return;
      const { field, tab } = e.data;
      if (tab) setActiveTab(tab);
      setTimeout(() => {
        const el = document.querySelector(`[data-field="${field}"]`);
        if (el) {
          el.scrollIntoView({ behavior: 'smooth', block: 'center' });
          el.focus();
          el.style.outline = '2px solid #6AAA26';
          setTimeout(() => { el.style.outline = ''; }, 1500);
        }
      }, 100);
    };
    window.addEventListener('message', handler);
    return () => window.removeEventListener('message', handler);
  }, []);

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

  const doSave = async () => {
    const res = await fetchWithAuth(`${API_BASE}/api/v1/recruit-platform/landing-pages/${selectedId}`, {
      method: 'PUT',
      body: JSON.stringify({ config }),
    });
    if (!res.ok) throw new Error((await res.json()).detail || 'Save failed');
  };

  const saveDraft = async () => {
    if (!selectedId) return;
    setSaving(true);
    setError('');
    try {
      await doSave();
      setSaveMsg('Saved');
      setTimeout(() => setSaveMsg(''), 2000);
      await Promise.all([loadPages(), loadPreview(selectedId)]);
    } catch (e) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  };

  const publishPage = async () => {
    if (!selectedId) return;
    setSaving(true);
    setError('');
    try {
      await doSave();
      const res = await fetchWithAuth(
        `${API_BASE}/api/v1/recruit-platform/landing-pages/${selectedId}/publish`,
        { method: 'POST' },
      );
      if (!res.ok) throw new Error((await res.json()).detail || 'Publish failed');
      setSaveMsg('Published');
      setTimeout(() => setSaveMsg(''), 3000);
      await Promise.all([loadPages(), loadPreview(selectedId)]);
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
      const res = await fetchWithAuth(
        `${API_BASE}/api/v1/recruit-platform/landing-pages/${selectedId}/unpublish`,
        { method: 'POST' },
      );
      if (!res.ok) throw new Error((await res.json()).detail || 'Failed');
      await loadPages();
    } catch (e) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  };

  const deletePage = async () => {
    if (!selectedId || !window.confirm('Delete this page?')) return;
    try {
      await fetchWithAuth(`${API_BASE}/api/v1/recruit-platform/landing-pages/${selectedId}`, {
        method: 'DELETE',
      });
      setSelectedId(null);
      setConfig(DEFAULT_CONFIG);
      setPreviewHtml('');
      await loadPages();
    } catch (e) {
      setError(e.message);
    }
  };

  const createPage = async () => {
    if (!createForm.title || !createForm.slug) return;
    setError('');
    try {
      const res = await fetchWithAuth(`${API_BASE}/api/v1/recruit-platform/landing-pages`, {
        method: 'POST',
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

  const seedCallcenter = async () => {
    setSeeding(true);
    setListError('');
    try {
      const res = await fetchWithAuth(`${API_BASE}/api/v1/recruit-platform/landing-pages/seed-callcenter`, {
        method: 'POST',
      });
      if (!res.ok) throw new Error((await res.json()).detail || 'Seed failed');
      await loadPages();
    } catch (e) {
      setListError(e.message);
    } finally {
      setSeeding(false);
    }
  };

  const copyUrl = () => {
    const page = pages.find((p) => p.id === selectedId);
    if (!page) return;
    navigator.clipboard.writeText(`https://api.perenniaai.com/careers/${page.slug}`).then(() => {
      setSaveMsg('URL copied');
      setTimeout(() => setSaveMsg(''), 2000);
    });
  };

  const openPage = () => {
    const page = pages.find((p) => p.id === selectedId);
    if (page) window.open(`https://api.perenniaai.com/careers/${page.slug}`, '_blank');
  };

  const selectedPage = pages.find((p) => p.id === selectedId);
  const isPublished = selectedPage?.status === 'published';

  return (
    <div className="wb-container">
      {/* ── Page list ── */}
      <div className="wb-sidebar">
        <div className="wb-sidebar-header">
          <span className="wb-sidebar-title">Landing Pages</span>
          <button className="wb-new-btn" onClick={() => setShowCreate(true)}>+ New</button>
        </div>

        {listError && <div className="wb-list-error">{listError}</div>}

        {pages.length === 0 && !listError && (
          <div className="wb-empty">
            <p>No pages yet.</p>
            <button className="wb-seed-btn" onClick={seedCallcenter} disabled={seeding}>
              {seeding ? 'Loading…' : 'Load Starter Page'}
            </button>
          </div>
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
            <div className="wb-page-slug">api.perenniaai.com/careers/{page.slug}</div>
          </div>
        ))}
      </div>

      {/* ── Form editor ── */}
      <div className="wb-editor">
        {!selectedId ? (
          <div className="wb-no-selection">
            <p>Select a page to edit or create a new one.</p>
          </div>
        ) : (
          <>
            <div className="wb-action-bar">
              <div className="wb-action-left">
                <span className="wb-editing-title">{selectedPage?.title}</span>
                {saveMsg && <span className="wb-save-msg">{saveMsg}</span>}
                {error && <span className="wb-error-msg">{error}</span>}
              </div>
              <div className="wb-action-right">
                <button className="wb-btn wb-btn-ghost" onClick={copyUrl}>Copy URL</button>
                <button className="wb-btn wb-btn-secondary" onClick={saveDraft} disabled={saving}>
                  {saving ? '…' : 'Save Draft'}
                </button>
                {isPublished ? (
                  <button className="wb-btn wb-btn-warning" onClick={unpublishPage} disabled={saving}>Unpublish</button>
                ) : (
                  <button className="wb-btn wb-btn-primary" onClick={publishPage} disabled={saving}>Publish</button>
                )}
                <button className="wb-btn wb-btn-danger" onClick={deletePage}>Delete</button>
              </div>
            </div>

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

            <div className="wb-tab-content">
              {activeTab === 'hero'       && <HeroTab       config={config} onChange={handleConfigChange} />}
              {activeTab === 'branding'   && <BrandingTab   config={config} onChange={handleConfigChange} />}
              {activeTab === 'earnings'   && <EarningsTab   config={config} onChange={handleConfigChange} />}
              {activeTab === 'stats'      && <StatsTab      config={config} onChange={handleConfigChange} />}
              {activeTab === 'career'     && <CareerTab     config={config} onChange={handleConfigChange} />}
              {activeTab === 'manager'    && <ManagerTab    config={config} onChange={handleConfigChange} />}
              {activeTab === 'training'   && <TrainingTab   config={config} onChange={handleConfigChange} />}
              {activeTab === 'cta'        && <CtaTab        config={config} onChange={handleConfigChange} />}
              {activeTab === 'pages'      && <PagesTab      config={config} onChange={handleConfigChange} />}
              {activeTab === 'content'    && <ContentTab    config={config} onChange={handleConfigChange} />}
              {activeTab === 'footer'     && <FooterTab     config={config} onChange={handleConfigChange} />}
            </div>
          </>
        )}
      </div>

      {/* ── Live preview ── */}
      <div className="wb-preview-panel">
        <div className="wb-preview-toolbar">
          <span className="wb-preview-label">Live Preview</span>
          <div className="wb-preview-controls">
            <button
              className={`wb-preview-toggle${!previewMobile ? ' active' : ''}`}
              onClick={() => setPreviewMobile(false)}
              title="Desktop view"
            >
              <IconDesktop />
            </button>
            <button
              className={`wb-preview-toggle${previewMobile ? ' active' : ''}`}
              onClick={() => setPreviewMobile(true)}
              title="Mobile view"
            >
              <IconMobile />
            </button>
            <button
              className="wb-preview-toggle"
              onClick={() => selectedId && loadPreview(selectedId)}
              title="Refresh preview"
            >
              <IconRefresh />
            </button>
            <button className="wb-preview-toggle" onClick={openPage} title="Open live page">
              <IconExternalLink />
            </button>
          </div>
        </div>

        <div className="wb-preview-frame-wrap">
          {!selectedId ? (
            <div className="wb-preview-empty">Select a page to preview</div>
          ) : previewLoading ? (
            <div className="wb-preview-empty">Loading preview…</div>
          ) : previewHtml ? (
            <div className={`wb-preview-scaler${previewMobile ? ' mobile' : ''}`}>
              <iframe
                ref={iframeRef}
                srcDoc={previewHtml}
                className="wb-preview-iframe"
                title="Page preview"
                sandbox="allow-same-origin allow-scripts allow-forms"
              />
            </div>
          ) : (
            <div className="wb-preview-empty">Save the page to load a preview</div>
          )}
        </div>
      </div>

      {/* ── Create modal ── */}
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
                onChange={(e) => setCreateForm((f) => ({ ...f, title: e.target.value, slug: slugify(e.target.value) }))}
              />
            </div>
            <div className="wb-form-group">
              <label>URL Slug</label>
              <div className="wb-slug-preview">
                api.perenniaai.com/careers/<strong>{createForm.slug || 'your-slug'}</strong>
              </div>
              <input
                className="wb-input"
                placeholder="e.g. callcenter"
                value={createForm.slug}
                onChange={(e) => setCreateForm((f) => ({ ...f, slug: slugify(e.target.value) }))}
              />
            </div>
            {error && <div className="wb-error-msg">{error}</div>}
            <div className="wb-modal-actions">
              <button className="wb-btn wb-btn-ghost" onClick={() => { setShowCreate(false); setError(''); }}>Cancel</button>
              <button
                className="wb-btn wb-btn-primary"
                onClick={createPage}
                disabled={!createForm.title || !createForm.slug}
              >
                Create
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ─── SVG icons ────────────────────────────────────────────────────────────────

function IconDesktop() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="2" y="3" width="20" height="14" rx="2"/>
      <line x1="8" y1="21" x2="16" y2="21"/>
      <line x1="12" y1="17" x2="12" y2="21"/>
    </svg>
  );
}

function IconMobile() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="7" y="2" width="10" height="20" rx="2"/>
      <circle cx="12" cy="18" r="1" fill="currentColor" stroke="none"/>
    </svg>
  );
}

function IconRefresh() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="23 4 23 10 17 10"/>
      <path d="M20.49 15a9 9 0 11-2.12-9.36L23 10"/>
    </svg>
  );
}

function IconExternalLink() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6"/>
      <polyline points="15 3 21 3 21 9"/>
      <line x1="10" y1="14" x2="21" y2="3"/>
    </svg>
  );
}

// ─── Tab components ───────────────────────────────────────────────────────────

function Field({ label, value, onChange, type = 'text', hint, id }) {
  return (
    <div className="wb-form-group">
      <label>{label}</label>
      <input
        id={id}
        data-field={id}
        className="wb-input"
        type={type}
        value={value || ''}
        onChange={(e) => onChange(e.target.value)}
      />
      {hint && <div className="wb-hint">{hint}</div>}
    </div>
  );
}

function TextArea({ label, value, onChange, hint, rows = 3, id }) {
  return (
    <div className="wb-form-group">
      <label>{label}</label>
      <textarea
        id={id}
        data-field={id}
        className="wb-input wb-textarea"
        value={value || ''}
        onChange={(e) => onChange(e.target.value)}
        rows={rows}
      />
      {hint && <div className="wb-hint">{hint}</div>}
    </div>
  );
}

function HeroTab({ config, onChange }) {
  return (
    <div className="wb-tab-section">
      <h4>Headline</h4>
      <TextArea
        id="hero_headline"
        label="Hero Headline (HTML allowed)"
        value={config.hero_headline}
        onChange={(v) => onChange('hero_headline', v)}
        hint='Use <span class="red">text</span> for accent, <span class="italic">text</span> for italic'
        rows={3}
      />
      <Field
        id="hero_headline_plain"
        label="Page Title (plain text, for browser tab)"
        value={config.hero_headline_plain}
        onChange={(v) => onChange('hero_headline_plain', v)}
        hint="No HTML — used in <title> tag"
      />
      <h4>Subheadline</h4>
      <TextArea
        id="hero_subheadline"
        label="Hero Subheadline (HTML allowed)"
        value={config.hero_subheadline}
        onChange={(v) => onChange('hero_subheadline', v)}
        hint='Wrap each paragraph in <p class="hero-sub">…</p>. Use <span style="color:#8ec94a;font-weight:600">text</span> for green highlights.'
        rows={8}
      />
      <h4>Location</h4>
      <Field
        id="location_display"
        label="Location Display"
        value={config.location_display}
        onChange={(v) => onChange('location_display', v)}
        hint="Shown in the hero eyebrow — e.g. Charleston, SC"
      />
      <h4>Hero Checklist (4 bullets under headline)</h4>
      <Field id="hero_check_1" label="Check 1" value={config.hero_check_1} onChange={(v) => onChange('hero_check_1', v)} />
      <Field id="hero_check_2" label="Check 2" value={config.hero_check_2} onChange={(v) => onChange('hero_check_2', v)} />
      <Field id="hero_check_3" label="Check 3" value={config.hero_check_3} onChange={(v) => onChange('hero_check_3', v)} />
      <Field id="hero_check_4" label="Check 4" value={config.hero_check_4} onChange={(v) => onChange('hero_check_4', v)} />
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
            <input
              type="color"
              className="wb-color-picker"
              value={config.primary_color || '#6AAA26'}
              onChange={(e) => onChange('primary_color', e.target.value)}
            />
            <input
              className="wb-input wb-color-text"
              value={config.primary_color || ''}
              onChange={(e) => onChange('primary_color', e.target.value)}
            />
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

function EarningsTab({ config, onChange }) {
  return (
    <div className="wb-tab-section">
      <h4>Earnings Card Label</h4>
      <Field id="earnings_label" label="Card Label" value={config.earnings_label} onChange={(v) => onChange('earnings_label', v)} hint="e.g. Year 1 On-Target Earnings" />
      <Field id="earnings_note" label="Card Note" value={config.earnings_note} onChange={(v) => onChange('earnings_note', v)} hint="e.g. base salary + commission" />
      <h4>Earnings Figures</h4>
      <Field id="year1_range" label="Year 1 OTE" value={config.year1_range} onChange={(v) => onChange('year1_range', v)} hint="e.g. $65–90K" />
      <Field id="year2_top" label="Year 2 Top Performer" value={config.year2_top} onChange={(v) => onChange('year2_top', v)} hint="e.g. $120,000+" />
      <Field id="senior_lo" label="Senior LO" value={config.senior_lo} onChange={(v) => onChange('senior_lo', v)} hint="e.g. $180,000+" />
      <Field id="team_lead" label="Team Lead / Manager" value={config.team_lead} onChange={(v) => onChange('team_lead', v)} hint="e.g. $250,000+" />
    </div>
  );
}

function StatsTab({ config, onChange }) {
  return (
    <div className="wb-tab-section">
      <h4>Hero Stats (shown below headline)</h4>
      {[1, 2, 3, 4].map((n) => (
        <div key={n} className="wb-stat-row">
          <Field
            id={`stat_${n}_num`}
            label={`Stat ${n} — Number`}
            value={config[`stat_${n}_num`]}
            onChange={(v) => onChange(`stat_${n}_num`, v)}
          />
          <Field
            id={`stat_${n}_label`}
            label={`Stat ${n} — Label`}
            value={config[`stat_${n}_label`]}
            onChange={(v) => onChange(`stat_${n}_label`, v)}
          />
        </div>
      ))}
    </div>
  );
}

function ManagerTab({ config, onChange }) {
  return (
    <div className="wb-tab-section">
      <h4>Hiring Manager</h4>
      <Field label="Manager Name" value={config.manager_name} onChange={(v) => onChange('manager_name', v)} />
      <Field
        label="Manager Initials"
        value={config.manager_initials}
        onChange={(v) => onChange('manager_initials', v)}
        hint="Auto-calculated from name, or override"
      />
      <Field label="Manager Title" value={config.manager_title} onChange={(v) => onChange('manager_title', v)} />
      <Field label="Manager NMLS#" value={config.manager_nmls} onChange={(v) => onChange('manager_nmls', v)} />
      <h4>Branch</h4>
      <Field label="Phone Display" value={config.contact_phone_display} onChange={(v) => onChange('contact_phone_display', v)} hint="e.g. (843) 834-4997" />
      <Field label="Phone (tel: href)" value={config.contact_phone_tel} onChange={(v) => onChange('contact_phone_tel', v)} hint="e.g. +18438344997" />
      <Field label="Branch Name" value={config.branch_name} onChange={(v) => onChange('branch_name', v)} />
      <Field label="Branch Address" value={config.branch_address} onChange={(v) => onChange('branch_address', v)} />
      <Field label="Branch NMLS#" value={config.branch_nmls} onChange={(v) => onChange('branch_nmls', v)} />
      <h4>Video Section</h4>
      <Field id="video_label" label="Video Label" value={config.video_label} onChange={(v) => onChange('video_label', v)} hint="e.g. 3-minute message from our Regional Director" />
      <Field id="video_headline" label="Video Headline" value={config.video_headline} onChange={(v) => onChange('video_headline', v)} />
      <TextArea id="video_body" label="Video Body (HTML allowed)" value={config.video_body} onChange={(v) => onChange('video_body', v)} rows={5} hint="Wrap paragraphs in <p>…</p>" />
    </div>
  );
}

function TrainingCard({ n, config, onChange }) {
  return (
    <div className="wb-training-card-editor">
      <div className="wb-training-card-header">
        <Field
          id={`training_${n}_week`}
          label="Week Range"
          value={config[`training_${n}_week`]}
          onChange={(v) => onChange(`training_${n}_week`, v)}
          hint="e.g. Weeks 1–2"
        />
        <Field
          id={`training_${n}_title`}
          label="Card Title"
          value={config[`training_${n}_title`]}
          onChange={(v) => onChange(`training_${n}_title`, v)}
        />
      </div>
      <TextArea
        id={`training_${n}_desc`}
        label="Description"
        value={config[`training_${n}_desc`]}
        onChange={(v) => onChange(`training_${n}_desc`, v)}
        rows={2}
      />
      <TextArea
        id={`training_${n}_items`}
        label="Bullet Points (one per line)"
        value={config[`training_${n}_items`]}
        onChange={(v) => onChange(`training_${n}_items`, v)}
        rows={4}
      />
    </div>
  );
}

function TrainingTab({ config, onChange }) {
  return (
    <div className="wb-tab-section">
      <h4>Section Header</h4>
      <Field id="training_section_title" label="Section Title (HTML allowed)" value={config.training_section_title} onChange={(v) => onChange('training_section_title', v)} hint="Use <br> for line breaks" />
      <TextArea id="training_section_sub" label="Section Subtitle" value={config.training_section_sub} onChange={(v) => onChange('training_section_sub', v)} rows={3} />
      <h4>Training Program Cards</h4>
      <p className="wb-hint" style={{ marginBottom: 16 }}>Click any training card in the preview to jump here. Edit each card's title, description, and bullet points.</p>
      {[1, 2, 3, 4].map((n) => (
        <TrainingCard key={n} n={n} config={config} onChange={onChange} />
      ))}
    </div>
  );
}

function CareerTab({ config, onChange }) {
  return (
    <div className="wb-tab-section">
      <h4>Section Header</h4>
      <Field id="career_title" label="Section Title (HTML allowed)" value={config.career_title} onChange={(v) => onChange('career_title', v)} hint="Use <br> for line breaks" />
      <TextArea id="career_sub" label="Section Subtitle" value={config.career_sub} onChange={(v) => onChange('career_sub', v)} rows={3} />
      <h4>Career Path Steps</h4>
      {[1, 2, 3, 4].map((n) => (
        <div key={n} className="wb-training-card-editor">
          <div className="wb-training-card-header">
            <Field id={`career_${n}_timeline`} label="Timeline" value={config[`career_${n}_timeline`]} onChange={(v) => onChange(`career_${n}_timeline`, v)} hint="e.g. Month 1–2" />
            <Field id={`career_${n}_title`} label="Step Title" value={config[`career_${n}_title`]} onChange={(v) => onChange(`career_${n}_title`, v)} />
          </div>
          <TextArea id={`career_${n}_desc`} label="Description" value={config[`career_${n}_desc`]} onChange={(v) => onChange(`career_${n}_desc`, v)} rows={2} />
          <Field id={`career_${n}_salary`} label="Salary / OTE" value={config[`career_${n}_salary`]} onChange={(v) => onChange(`career_${n}_salary`, v)} hint="e.g. $45K base" />
        </div>
      ))}
    </div>
  );
}

function CtaTab({ config, onChange }) {
  return (
    <div className="wb-tab-section">
      <h4>Page 1 — CTA Banner</h4>
      <Field id="cta_headline" label="CTA Headline" value={config.cta_headline} onChange={(v) => onChange('cta_headline', v)} />
      <TextArea id="cta_body" label="CTA Body" value={config.cta_body} onChange={(v) => onChange('cta_body', v)} rows={3} />
      <Field id="cta_btn" label="Button Text" value={config.cta_btn} onChange={(v) => onChange('cta_btn', v)} hint="e.g. Apply Now — It's Free →" />
    </div>
  );
}

function PagesTab({ config, onChange }) {
  return (
    <div className="wb-tab-section">
      <h4>Page 2 — Why CMG Hero</h4>
      <Field id="why_hero_headline" label="Headline (HTML allowed)" value={config.why_hero_headline} onChange={(v) => onChange('why_hero_headline', v)} hint='Use <span>text</span> for green accent, <br> for breaks' />
      <TextArea id="why_hero_body" label="Body" value={config.why_hero_body} onChange={(v) => onChange('why_hero_body', v)} rows={3} />
      <h4>Page 4 — Apply Sidebar</h4>
      <Field id="apply_sidebar_headline" label="Sidebar Headline (HTML allowed)" value={config.apply_sidebar_headline} onChange={(v) => onChange('apply_sidebar_headline', v)} hint='Use <span>text</span> for green accent' />
      <TextArea id="apply_sidebar_body" label="Sidebar Body" value={config.apply_sidebar_body} onChange={(v) => onChange('apply_sidebar_body', v)} rows={3} />
    </div>
  );
}

function ContentTab({ config, onChange }) {
  return (
    <div className="wb-tab-section">
      <h4>Testimonials</h4>
      <p className="wb-hint" style={{ marginBottom: 12 }}>
        Paste raw HTML for the testimonial cards. Each card uses:<br />
        <code style={{ fontSize: 11 }}>&lt;div class="tcard"&gt;&lt;div class="tcard-stars"&gt;★★★★★&lt;/div&gt;&lt;div class="tcard-quote"&gt;…&lt;/div&gt;&lt;div class="tcard-author"&gt;&lt;div class="tcard-avatar" style="background:#6AAA26"&gt;AB&lt;/div&gt;&lt;div&gt;&lt;div class="tcard-name"&gt;Name&lt;/div&gt;&lt;div class="tcard-detail"&gt;Role&lt;/div&gt;&lt;/div&gt;&lt;/div&gt;&lt;/div&gt;</code>
      </p>
      <TextArea
        id="testimonials_html"
        label="Testimonials HTML"
        value={config.testimonials_html}
        onChange={(v) => onChange('testimonials_html', v)}
        rows={14}
        hint="Leave blank to hide the section entirely"
      />
    </div>
  );
}

function FooterTab({ config, onChange }) {
  return (
    <div className="wb-tab-section">
      <h4>Footer Legal Disclaimer</h4>
      <TextArea
        id="footer_legal"
        label="Legal Disclaimer (HTML allowed)"
        value={config.footer_legal}
        onChange={(v) => onChange('footer_legal', v)}
        rows={8}
        hint="Shown in the footer. Use <a href=…> for links. Leave blank to hide."
      />
    </div>
  );
}
