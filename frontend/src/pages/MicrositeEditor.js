/**
 * MicrositeEditor - Main microsite editing interface
 *
 * Provides a tabbed interface for:
 * - Template selection
 * - Content editing (via ContentEditor)
 * - Branding customization
 * - Compliance settings
 * - Publishing controls
 */

import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import ContentEditor from '../components/ContentEditor';
import MicrositePageManager from '../components/MicrositePageManager';
import { getAuthHeaders } from '../utils/auth';
import './MicrositeEditor.css';
import { getToken } from '../utils/tokenStore';

// API base URL
const API_BASE = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
  ? (process.env.REACT_APP_API_URL || 'http://localhost:8000')
  : 'https://api.perenniaai.com';

const MICROSITE_DOMAIN = 'microsites.perennia.ai';

const MicrositeEditor = () => {
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState('template');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [toast, setToast] = useState(null);

  // Data state
  const [microsite, setMicrosite] = useState(null);
  const [templates, setTemplates] = useState([]);
  const [selectedTemplate, setSelectedTemplate] = useState(null);
  const [contentJson, setContentJson] = useState({});
  const [brandingJson, setBrandingJson] = useState({});
  const [complianceJson, setComplianceJson] = useState({});
  const [orgSettings, setOrgSettings] = useState(null);
  const [analytics, setAnalytics] = useState(null);

  // Show toast message
  const showToast = useCallback((message, type = 'success') => {
    setToast({ message, type });
    setTimeout(() => setToast(null), 3000);
  }, []);

  // Fetch templates
  const fetchTemplates = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE}/api/v1/microsites/templates`, {
        headers: getAuthHeaders()
      });
      if (response.ok) {
        const data = await response.json();
        setTemplates(data.templates || data || []);
      }
    } catch (err) {
      console.error('Error fetching templates:', err);
    }
  }, [getAuthHeaders]);

  // Fetch user's microsite
  const fetchMicrosite = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE}/api/v1/microsites/my`, {
        headers: getAuthHeaders()
      });
      if (response.ok) {
        const data = await response.json();
        setMicrosite(data);
        setContentJson(data.content_json || {});
        setBrandingJson(data.branding_json || {});
        setComplianceJson(data.compliance_json || {});
        if (data.template_pack_id) {
          setSelectedTemplate(data.template_pack_id);
        }
      } else if (response.status === 404) {
        // No microsite yet
        setMicrosite(null);
      }
    } catch (err) {
      console.error('Error fetching microsite:', err);
      setError('Failed to load microsite');
    } finally {
      setLoading(false);
    }
  }, [getAuthHeaders]);

  // Fetch organization settings
  const fetchOrgSettings = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE}/api/v1/microsites/settings/org`, {
        headers: getAuthHeaders()
      });
      if (response.ok) {
        const data = await response.json();
        setOrgSettings(data);
      }
    } catch (err) {
      console.error('Error fetching org settings:', err);
    }
  }, [getAuthHeaders]);

  // Fetch analytics
  const fetchAnalytics = useCallback(async () => {
    if (!microsite) return;
    try {
      const response = await fetch(`${API_BASE}/api/v1/microsites/my/analytics?period=30`, {
        headers: getAuthHeaders()
      });
      if (response.ok) {
        const data = await response.json();
        setAnalytics(data);
      }
    } catch (err) {
      console.error('Error fetching analytics:', err);
    }
  }, [getAuthHeaders, microsite]);

  // Initial data load
  useEffect(() => {
    fetchTemplates();
    fetchMicrosite();
    fetchOrgSettings();
  }, [fetchTemplates, fetchMicrosite, fetchOrgSettings]);

  // Fetch analytics when microsite loads
  useEffect(() => {
    if (microsite) {
      fetchAnalytics();
    }
  }, [microsite, fetchAnalytics]);

  // Create new microsite
  const handleCreateMicrosite = async () => {
    if (!selectedTemplate) {
      showToast('Please select a template first', 'error');
      return;
    }

    setSaving(true);
    try {
      const response = await fetch(`${API_BASE}/api/v1/microsites/my`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({
          template_pack_id: selectedTemplate
        })
      });

      if (response.ok) {
        const data = await response.json();
        setMicrosite(data);
        setContentJson(data.content_json || {});
        setBrandingJson(data.branding_json || {});
        setComplianceJson(data.compliance_json || {});
        showToast('Microsite created successfully!');
        setActiveTab('content');
      } else {
        const err = await response.json();
        showToast(err.detail || 'Failed to create microsite', 'error');
      }
    } catch (err) {
      console.error('Error creating microsite:', err);
      showToast('Failed to create microsite', 'error');
    } finally {
      setSaving(false);
    }
  };

  // Save microsite changes
  const handleSave = async () => {
    setSaving(true);
    try {
      const response = await fetch(`${API_BASE}/api/v1/microsites/my`, {
        method: 'PUT',
        headers: getAuthHeaders(),
        body: JSON.stringify({
          template_pack_id: selectedTemplate,
          content_json: contentJson,
          branding_json: brandingJson,
          compliance_json: complianceJson
        })
      });

      if (response.ok) {
        const data = await response.json();
        setMicrosite(data);
        showToast('Changes saved successfully!');
      } else {
        const err = await response.json();
        showToast(err.detail || 'Failed to save changes', 'error');
      }
    } catch (err) {
      console.error('Error saving microsite:', err);
      showToast('Failed to save changes', 'error');
    } finally {
      setSaving(false);
    }
  };

  // Publish microsite
  const handlePublish = async () => {
    setSaving(true);
    try {
      const response = await fetch(`${API_BASE}/api/v1/microsites/my/publish`, {
        method: 'POST',
        headers: getAuthHeaders()
      });

      if (response.ok) {
        await fetchMicrosite();
        showToast('Microsite published successfully!');
      } else {
        const err = await response.json();
        showToast(err.detail || 'Failed to publish', 'error');
      }
    } catch (err) {
      console.error('Error publishing:', err);
      showToast('Failed to publish microsite', 'error');
    } finally {
      setSaving(false);
    }
  };

  // Unpublish microsite
  const handleUnpublish = async () => {
    setSaving(true);
    try {
      const response = await fetch(`${API_BASE}/api/v1/microsites/my/unpublish`, {
        method: 'POST',
        headers: getAuthHeaders()
      });

      if (response.ok) {
        await fetchMicrosite();
        showToast('Microsite unpublished');
      } else {
        const err = await response.json();
        showToast(err.detail || 'Failed to unpublish', 'error');
      }
    } catch (err) {
      console.error('Error unpublishing:', err);
      showToast('Failed to unpublish microsite', 'error');
    } finally {
      setSaving(false);
    }
  };

  // Handle template selection
  const handleTemplateSelect = async (templateId) => {
    setSelectedTemplate(templateId);

    // If microsite exists, update it
    if (microsite) {
      setSaving(true);
      try {
        const response = await fetch(`${API_BASE}/api/v1/microsites/my`, {
          method: 'PUT',
          headers: getAuthHeaders(),
          body: JSON.stringify({
            template_pack_id: templateId
          })
        });

        if (response.ok) {
          const data = await response.json();
          setMicrosite(data);
          // Load template's default content if current content is empty
          if (Object.keys(contentJson).length === 0) {
            setContentJson(data.content_json || {});
          }
          showToast('Template updated!');
        }
      } catch (err) {
        console.error('Error updating template:', err);
      } finally {
        setSaving(false);
      }
    }
  };

  // Handle content changes from ContentEditor
  const handleContentChange = (newContent) => {
    setContentJson(newContent);
  };

  // Handle branding changes
  const handleBrandingChange = (field, value) => {
    setBrandingJson(prev => ({
      ...prev,
      [field]: value
    }));
  };

  // Handle compliance changes
  const handleComplianceChange = (field, value) => {
    setComplianceJson(prev => ({
      ...prev,
      [field]: value
    }));
  };

  // Handle logo upload
  const handleLogoUpload = async (event) => {
    const file = event.target.files[0];
    if (!file) return;

    if (!file.type.startsWith('image/')) {
      showToast('Please select an image file', 'error');
      return;
    }

    if (file.size > 2 * 1024 * 1024) {
      showToast('Logo must be less than 2MB', 'error');
      return;
    }

    const formData = new FormData();
    formData.append('file', file);
    formData.append('asset_type', 'logo');

    setSaving(true);
    try {
      const response = await fetch(`${API_BASE}/api/v1/microsites/my/assets/upload`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${getToken()}`
        },
        body: formData
      });

      if (response.ok) {
        const data = await response.json();
        handleBrandingChange('logo_url', data.public_url);
        showToast('Logo uploaded successfully!');
      } else {
        showToast('Failed to upload logo', 'error');
      }
    } catch (err) {
      console.error('Error uploading logo:', err);
      showToast('Failed to upload logo', 'error');
    } finally {
      setSaving(false);
    }
  };

  // Copy URL to clipboard
  const copyUrl = () => {
    if (microsite?.slug) {
      navigator.clipboard.writeText(`https://${microsite.slug}.${MICROSITE_DOMAIN}`);
      showToast('URL copied to clipboard!');
    }
  };

  // Get current template
  const currentTemplate = templates.find(t => t.id === selectedTemplate);

  // Get publish checklist
  const getPublishChecklist = () => {
    const checks = [];

    // Template selected
    checks.push({
      label: 'Template Selected',
      description: currentTemplate?.name || 'Select a template',
      complete: !!selectedTemplate
    });

    // Required content filled
    const hasHeadline = contentJson?.hero?.headline;
    checks.push({
      label: 'Hero Headline',
      description: hasHeadline || 'Add a headline',
      complete: !!hasHeadline
    });

    // Contact info
    const hasPhone = contentJson?.contact?.phone || complianceJson?.phone;
    checks.push({
      label: 'Contact Phone',
      description: hasPhone || 'Add contact phone',
      complete: !!hasPhone
    });

    // NMLS
    const hasNmls = complianceJson?.individual_nmls || orgSettings?.locked_fields?.company_nmls;
    checks.push({
      label: 'NMLS Number',
      description: hasNmls || 'Add NMLS number',
      complete: !!hasNmls
    });

    return checks;
  };

  // Loading state
  if (loading) {
    return (
      <div className="microsite-editor">
        <div className="loading-state">
          <div className="loading-spinner"></div>
          <p>Loading your microsite...</p>
        </div>
      </div>
    );
  }

  // Error state
  if (error) {
    return (
      <div className="microsite-editor">
        <div className="error-state">
          <div className="error-icon">!</div>
          <p>{error}</p>
          <button onClick={() => window.location.reload()}>Retry</button>
        </div>
      </div>
    );
  }

  // No microsite yet - show template selection
  if (!microsite) {
    return (
      <div className="microsite-editor">
        <div className="microsite-editor-header">
          <div className="header-left">
            <h1>Create Your Microsite</h1>
            <p>Choose a template to get started</p>
          </div>
        </div>

        <div className="editor-content">
          <div className="tab-panel">
            <h2>Choose a Template</h2>
            <p>Select a professional template for your loan officer microsite</p>

            <div className="template-grid">
              {templates.map(template => (
                <div
                  key={template.id}
                  className={`template-card ${selectedTemplate === template.id ? 'selected' : ''}`}
                  onClick={() => setSelectedTemplate(template.id)}
                >
                  <div className="template-thumbnail">
                    {template.thumbnail_url ? (
                      <img src={template.thumbnail_url} alt={template.name} />
                    ) : (
                      <span className="placeholder">
                        {template.category === 'professional' ? '💼' : '✨'}
                      </span>
                    )}
                    {selectedTemplate === template.id && (
                      <div className="selected-check">✓</div>
                    )}
                  </div>
                  <div className="template-info">
                    <h3>{template.name}</h3>
                    <p>{template.description}</p>
                  </div>
                </div>
              ))}
            </div>

            <div className="save-section">
              <button
                className="btn-create"
                onClick={handleCreateMicrosite}
                disabled={!selectedTemplate || saving}
              >
                {saving ? 'Creating...' : 'Create Microsite'}
              </button>
            </div>
          </div>
        </div>

        {toast && (
          <div className={`toast ${toast.type}`}>{toast.message}</div>
        )}
      </div>
    );
  }

  return (
    <div className="microsite-editor">
      {/* Header */}
      <div className="microsite-editor-header">
        <div className="header-left">
          <h1>Edit Your Microsite</h1>
          <p>Customize your professional loan officer page</p>
        </div>
        <div className="header-right">
          <span className={`status-badge ${microsite.status}`}>
            {microsite.status}
          </span>
          {microsite.slug && (
            <button
              className="btn-preview"
              onClick={() => window.open(`https://${microsite.slug}.${MICROSITE_DOMAIN}`, '_blank')}
            >
              <span>Preview</span>
            </button>
          )}
          {microsite.status === 'published' ? (
            <button
              className="btn-unpublish"
              onClick={handleUnpublish}
              disabled={saving}
            >
              Unpublish
            </button>
          ) : (
            <button
              className="btn-publish"
              onClick={handlePublish}
              disabled={saving}
            >
              {saving ? 'Publishing...' : 'Publish'}
            </button>
          )}
        </div>
      </div>

      {/* Tabs */}
      <div className="editor-tabs">
        <button
          className={activeTab === 'template' ? 'active' : ''}
          onClick={() => setActiveTab('template')}
        >
          <span className="tab-icon">📋</span>
          Template
        </button>
        <button
          className={activeTab === 'pages' ? 'active' : ''}
          onClick={() => setActiveTab('pages')}
        >
          <span className="tab-icon">📄</span>
          Pages
        </button>
        <button
          className={activeTab === 'content' ? 'active' : ''}
          onClick={() => setActiveTab('content')}
        >
          <span className="tab-icon">✏️</span>
          Content
        </button>
        <button
          className={activeTab === 'branding' ? 'active' : ''}
          onClick={() => setActiveTab('branding')}
        >
          <span className="tab-icon">🎨</span>
          Branding
        </button>
        <button
          className={activeTab === 'compliance' ? 'active' : ''}
          onClick={() => setActiveTab('compliance')}
        >
          <span className="tab-icon">📜</span>
          Compliance
        </button>
        <button
          className={activeTab === 'publish' ? 'active' : ''}
          onClick={() => setActiveTab('publish')}
        >
          <span className="tab-icon">🚀</span>
          Publish
        </button>
      </div>

      {/* Editor Layout */}
      <div className="editor-layout">
        {/* Main Editor */}
        <div className="editor-content">
          {/* Template Tab */}
          {activeTab === 'template' && (
            <div className="tab-panel">
              <h2>Choose Template</h2>
              <p>Select a template for your microsite</p>

              <div className="template-grid">
                {templates.map(template => (
                  <div
                    key={template.id}
                    className={`template-card ${selectedTemplate === template.id ? 'selected' : ''}`}
                    onClick={() => handleTemplateSelect(template.id)}
                  >
                    <div className="template-thumbnail">
                      {template.thumbnail_url ? (
                        <img src={template.thumbnail_url} alt={template.name} />
                      ) : (
                        <span className="placeholder">
                          {template.category === 'professional' ? '💼' : '✨'}
                        </span>
                      )}
                      {selectedTemplate === template.id && (
                        <div className="selected-check">✓</div>
                      )}
                    </div>
                    <div className="template-info">
                      <h3>{template.name}</h3>
                      <p>{template.description}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Pages Tab */}
          {activeTab === 'pages' && (
            <div className="tab-panel">
              <h2>Website Pages</h2>
              <p>Add multiple pages to your microsite like About, Services, Testimonials, and Blog</p>

              <MicrositePageManager onToast={showToast} />
            </div>
          )}

          {/* Content Tab */}
          {activeTab === 'content' && currentTemplate && (
            <div className="tab-panel">
              <h2>Edit Content</h2>
              <p>Customize the content on your microsite</p>

              <ContentEditor
                schema={currentTemplate.schema_json}
                content={contentJson}
                onChange={handleContentChange}
                lockedFields={orgSettings?.locked_fields || {}}
              />

              <div className="save-section">
                <button
                  className="btn-save"
                  onClick={handleSave}
                  disabled={saving}
                >
                  {saving ? 'Saving...' : 'Save Changes'}
                </button>
              </div>
            </div>
          )}

          {/* Branding Tab */}
          {activeTab === 'branding' && (
            <div className="tab-panel">
              <h2>Brand Settings</h2>
              <p>Customize colors and logo to match your brand</p>

              {/* Logo */}
              <div className="branding-section">
                <h3>
                  <span>🖼️</span> Logo
                </h3>
                <input
                  type="file"
                  id="logo-upload"
                  accept="image/*"
                  onChange={handleLogoUpload}
                  style={{ display: 'none' }}
                />
                <label
                  htmlFor="logo-upload"
                  className={`logo-upload ${brandingJson.logo_url ? 'has-logo' : ''}`}
                >
                  {brandingJson.logo_url ? (
                    <>
                      <img src={brandingJson.logo_url} alt="Logo" />
                      <p>Click to change logo</p>
                    </>
                  ) : (
                    <>
                      <div className="upload-icon">📤</div>
                      <p>Click to upload your logo</p>
                      <p>Recommended: 300x80px, PNG or SVG</p>
                    </>
                  )}
                </label>
              </div>

              {/* Colors */}
              <div className="branding-section">
                <h3>
                  <span>🎨</span> Colors
                </h3>
                <div className="color-picker-group">
                  <div className="color-picker">
                    <label>Primary Color</label>
                    <div className="color-input-wrapper">
                      <input
                        type="color"
                        value={brandingJson.primary_color || '#c9a227'}
                        onChange={(e) => handleBrandingChange('primary_color', e.target.value)}
                      />
                      <input
                        type="text"
                        value={brandingJson.primary_color || '#c9a227'}
                        onChange={(e) => handleBrandingChange('primary_color', e.target.value)}
                        placeholder="#c9a227"
                      />
                    </div>
                  </div>

                  <div className="color-picker">
                    <label>Secondary Color</label>
                    <div className="color-input-wrapper">
                      <input
                        type="color"
                        value={brandingJson.secondary_color || '#1f2937'}
                        onChange={(e) => handleBrandingChange('secondary_color', e.target.value)}
                      />
                      <input
                        type="text"
                        value={brandingJson.secondary_color || '#1f2937'}
                        onChange={(e) => handleBrandingChange('secondary_color', e.target.value)}
                        placeholder="#1f2937"
                      />
                    </div>
                  </div>

                  <div className="color-picker">
                    <label>Accent Color</label>
                    <div className="color-input-wrapper">
                      <input
                        type="color"
                        value={brandingJson.accent_color || '#059669'}
                        onChange={(e) => handleBrandingChange('accent_color', e.target.value)}
                      />
                      <input
                        type="text"
                        value={brandingJson.accent_color || '#059669'}
                        onChange={(e) => handleBrandingChange('accent_color', e.target.value)}
                        placeholder="#059669"
                      />
                    </div>
                  </div>

                  <div className="color-picker">
                    <label>Background Color</label>
                    <div className="color-input-wrapper">
                      <input
                        type="color"
                        value={brandingJson.background_color || '#ffffff'}
                        onChange={(e) => handleBrandingChange('background_color', e.target.value)}
                      />
                      <input
                        type="text"
                        value={brandingJson.background_color || '#ffffff'}
                        onChange={(e) => handleBrandingChange('background_color', e.target.value)}
                        placeholder="#ffffff"
                      />
                    </div>
                  </div>
                </div>
              </div>

              <div className="save-section">
                <button
                  className="btn-save"
                  onClick={handleSave}
                  disabled={saving}
                >
                  {saving ? 'Saving...' : 'Save Changes'}
                </button>
              </div>
            </div>
          )}

          {/* Compliance Tab */}
          {activeTab === 'compliance' && (
            <div className="tab-panel">
              <h2>Compliance Settings</h2>
              <p>Required regulatory information for your microsite</p>

              {/* Organization Locked Fields */}
              {orgSettings?.locked_fields && (
                <div className="compliance-section">
                  <h3>
                    <span>🏢</span> Company Information (Organization Locked)
                  </h3>

                  <div className="compliance-field">
                    <label>
                      Company Name
                      <span className="locked-badge">🔒 Locked</span>
                    </label>
                    <input
                      type="text"
                      value={orgSettings.locked_fields.company_name || ''}
                      disabled
                    />
                  </div>

                  <div className="compliance-field">
                    <label>
                      Company NMLS #
                      <span className="locked-badge">🔒 Locked</span>
                    </label>
                    <input
                      type="text"
                      value={orgSettings.locked_fields.company_nmls || ''}
                      disabled
                    />
                  </div>

                  <div className="compliance-field">
                    <label>
                      Equal Housing Logo
                      <span className="locked-badge">🔒 Locked</span>
                    </label>
                    <input
                      type="text"
                      value={orgSettings.locked_fields.equal_housing_logo ? 'Required' : 'Optional'}
                      disabled
                    />
                  </div>
                </div>
              )}

              {/* Individual Fields */}
              <div className="compliance-section">
                <h3>
                  <span>👤</span> Your Information
                </h3>

                <div className="compliance-field">
                  <label>Your NMLS #</label>
                  <input
                    type="text"
                    value={complianceJson.individual_nmls || ''}
                    onChange={(e) => handleComplianceChange('individual_nmls', e.target.value)}
                    placeholder="Enter your NMLS number"
                  />
                </div>

                <div className="compliance-field">
                  <label>State Licenses</label>
                  <input
                    type="text"
                    value={complianceJson.state_licenses || ''}
                    onChange={(e) => handleComplianceChange('state_licenses', e.target.value)}
                    placeholder="e.g., CA DRE #01234567"
                  />
                </div>

                <div className="compliance-field">
                  <label>Compliance Footer Text</label>
                  <textarea
                    rows="3"
                    value={complianceJson.footer_text || ''}
                    onChange={(e) => handleComplianceChange('footer_text', e.target.value)}
                    placeholder="Additional compliance disclosures..."
                  />
                </div>
              </div>

              <div className="save-section">
                <button
                  className="btn-save"
                  onClick={handleSave}
                  disabled={saving}
                >
                  {saving ? 'Saving...' : 'Save Changes'}
                </button>
              </div>
            </div>
          )}

          {/* Publish Tab */}
          {activeTab === 'publish' && (
            <div className="tab-panel">
              <h2>Publish Settings</h2>
              <p>Review and publish your microsite</p>

              {/* Publish Checklist */}
              <div className="publish-checklist">
                {getPublishChecklist().map((item, index) => (
                  <div key={index} className="checklist-item">
                    <div className={`check-icon ${item.complete ? 'complete' : 'incomplete'}`}>
                      {item.complete ? '✓' : '!'}
                    </div>
                    <div className="item-text">
                      <strong>{item.label}</strong>
                      <span>{item.description}</span>
                    </div>
                  </div>
                ))}
              </div>

              {/* Published URL */}
              {microsite.status === 'published' && microsite.slug && (
                <div className="publish-url-section">
                  <h3>Your Microsite is Live!</h3>
                  <div className="publish-url">
                    <input
                      type="text"
                      value={`https://${microsite.slug}.${MICROSITE_DOMAIN}`}
                      readOnly
                    />
                    <button onClick={copyUrl}>Copy</button>
                  </div>
                </div>
              )}

              {/* Analytics Preview */}
              {analytics && (
                <div className="analytics-preview">
                  <h3>Performance (Last 30 Days)</h3>
                  <div className="analytics-grid">
                    <div className="analytics-card">
                      <div className="value">{analytics.page_views || 0}</div>
                      <div className="label">Page Views</div>
                    </div>
                    <div className="analytics-card">
                      <div className="value">{analytics.unique_visitors || 0}</div>
                      <div className="label">Visitors</div>
                    </div>
                    <div className="analytics-card">
                      <div className="value">{analytics.leads || 0}</div>
                      <div className="label">Leads</div>
                    </div>
                    <div className="analytics-card">
                      <div className="value">
                        {analytics.page_views > 0
                          ? ((analytics.leads / analytics.page_views) * 100).toFixed(1)
                          : 0}%
                      </div>
                      <div className="label">Conversion</div>
                    </div>
                  </div>
                </div>
              )}

              <div className="save-section">
                {microsite.status === 'published' ? (
                  <button
                    className="btn-unpublish"
                    onClick={handleUnpublish}
                    disabled={saving}
                  >
                    {saving ? 'Unpublishing...' : 'Unpublish Microsite'}
                  </button>
                ) : (
                  <button
                    className="btn-publish"
                    onClick={handlePublish}
                    disabled={saving || getPublishChecklist().some(c => !c.complete)}
                  >
                    {saving ? 'Publishing...' : 'Publish Microsite'}
                  </button>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Preview Panel */}
        <div className="preview-panel">
          <div className="preview-header">
            <div className="browser-dots">
              <span></span>
              <span></span>
              <span></span>
            </div>
            <div className="preview-url">
              {microsite.slug ? `${microsite.slug}.${MICROSITE_DOMAIN}` : 'your-name.microsites.perennia.ai'}
            </div>
          </div>
          <iframe
            className="preview-frame"
            src={microsite.slug ? `https://${microsite.slug}.${MICROSITE_DOMAIN}?preview=true` : 'about:blank'}
            title="Microsite Preview"
          />
        </div>
      </div>

      {/* Toast */}
      {toast && (
        <div className={`toast ${toast.type}`}>{toast.message}</div>
      )}
    </div>
  );
};

export default MicrositeEditor;
