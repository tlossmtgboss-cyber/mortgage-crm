import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { usePermissions } from '../contexts/PermissionContext';
import { useAsyncOperation, useFormSubmit, APIError } from '../utils/errorHandling';
import { toast } from '../utils/toast';
import './CompanyBrandingSettings.css';
import { getToken } from '../utils/tokenStore';

const API_BASE_URL = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
  ? 'http://localhost:8000'
  : 'https://api.perenniaai.com';

const CompanyBrandingSettings = () => {
  const navigate = useNavigate();
  const { userRole, hasAnyPermission, isAdmin } = usePermissions();

  // Permission check - only admins/site admins can manage company branding
  const canAccessBranding = isAdmin || hasAnyPermission(['admin.manage', 'settings.manage', 'branding.manage', 'system.admin']) ||
    userRole === 'admin' || userRole === 'site_admin' || userRole === 'management';

  const [activeTab, setActiveTab] = useState('company');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [hasChanges, setHasChanges] = useState(false);
  const [saving, setSaving] = useState(false);

  // Data states
  const [companyInfo, setCompanyInfo] = useState({});
  const [brandColors, setBrandColors] = useState({});
  const [typography, setTypography] = useState({});
  const [brandAssets, setBrandAssets] = useState({});
  const [emailBranding, setEmailBranding] = useState({});
  const [documentBranding, setDocumentBranding] = useState({});
  const [whiteLabel, setWhiteLabel] = useState({});
  const [socialMedia, setSocialMedia] = useState({});

  const getAuthHeaders = useCallback(() => {
    const token = getToken();
    return {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    };
  }, []);

  // Load all data
  const loadData = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);

      const endpoints = [
        'company', 'colors', 'typography', 'assets',
        'email', 'documents', 'white-label', 'social'
      ];

      const responses = await Promise.all(
        endpoints.map(endpoint =>
          fetch(`${API_BASE_URL}/api/v1/company-branding/${endpoint}`, { headers: getAuthHeaders() })
        )
      );

      const [
        companyRes, colorsRes, typographyRes, assetsRes,
        emailRes, documentsRes, whiteLabelRes, socialRes
      ] = responses;

      if (companyRes.ok) {
        const data = await companyRes.json();
        setCompanyInfo(data.data || {});
      }
      if (colorsRes.ok) {
        const data = await colorsRes.json();
        setBrandColors(data.data || {});
      }
      if (typographyRes.ok) {
        const data = await typographyRes.json();
        setTypography(data.data || {});
      }
      if (assetsRes.ok) {
        const data = await assetsRes.json();
        setBrandAssets(data.data || {});
      }
      if (emailRes.ok) {
        const data = await emailRes.json();
        setEmailBranding(data.data || {});
      }
      if (documentsRes.ok) {
        const data = await documentsRes.json();
        setDocumentBranding(data.data || {});
      }
      if (whiteLabelRes.ok) {
        const data = await whiteLabelRes.json();
        setWhiteLabel(data.data || {});
      }
      if (socialRes.ok) {
        const data = await socialRes.json();
        setSocialMedia(data.data || {});
      }

      setLoading(false);
    } catch (err) {
      setError(err.message);
      setLoading(false);
    }
  }, [getAuthHeaders]);

  useEffect(() => {
    loadData();
  }, [loadData]);


  // Save handlers
  const saveCompanyInfo = async () => {
    setSaving(true);
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/company-branding/company`, {
        method: 'PUT',
        headers: getAuthHeaders(),
        body: JSON.stringify(companyInfo)
      });
      if (!response.ok) {
        const error = await response.json();
        throw new APIError(error.detail?.message || 'Failed to save', response.status);
      }
      setHasChanges(false);
      toast.success('Company information saved successfully');
    } catch (err) {
      toast.error(err.message);
    }
    setSaving(false);
  };

  const saveBrandColors = async () => {
    setSaving(true);
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/company-branding/colors`, {
        method: 'PUT',
        headers: getAuthHeaders(),
        body: JSON.stringify(brandColors)
      });
      if (!response.ok) throw new APIError('Failed to save colors', response.status);
      setHasChanges(false);
      toast.success('Brand colors saved successfully');
    } catch (err) {
      toast.error(err.message);
    }
    setSaving(false);
  };

  const saveTypography = async () => {
    setSaving(true);
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/company-branding/typography`, {
        method: 'PUT',
        headers: getAuthHeaders(),
        body: JSON.stringify(typography)
      });
      if (!response.ok) throw new APIError('Failed to save typography', response.status);
      setHasChanges(false);
      toast.success('Typography saved successfully');
    } catch (err) {
      toast.error(err.message);
    }
    setSaving(false);
  };

  const saveEmailBranding = async () => {
    setSaving(true);
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/company-branding/email`, {
        method: 'PUT',
        headers: getAuthHeaders(),
        body: JSON.stringify(emailBranding)
      });
      if (!response.ok) throw new APIError('Failed to save email branding', response.status);
      setHasChanges(false);
      toast.success('Email branding saved successfully');
    } catch (err) {
      toast.error(err.message);
    }
    setSaving(false);
  };

  const saveDocumentBranding = async () => {
    setSaving(true);
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/company-branding/documents`, {
        method: 'PUT',
        headers: getAuthHeaders(),
        body: JSON.stringify(documentBranding)
      });
      if (!response.ok) throw new APIError('Failed to save document branding', response.status);
      setHasChanges(false);
      toast.success('Document branding saved successfully');
    } catch (err) {
      toast.error(err.message);
    }
    setSaving(false);
  };

  const saveWhiteLabel = async () => {
    setSaving(true);
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/company-branding/white-label`, {
        method: 'PUT',
        headers: getAuthHeaders(),
        body: JSON.stringify(whiteLabel)
      });
      if (!response.ok) throw new APIError('Failed to save white-label settings', response.status);
      setHasChanges(false);
      toast.success('White-label settings saved successfully');
    } catch (err) {
      toast.error(err.message);
    }
    setSaving(false);
  };

  const saveSocialMedia = async () => {
    setSaving(true);
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/company-branding/social`, {
        method: 'PUT',
        headers: getAuthHeaders(),
        body: JSON.stringify(socialMedia)
      });
      if (!response.ok) throw new APIError('Failed to save social media links', response.status);
      setHasChanges(false);
      toast.success('Social media links saved successfully');
    } catch (err) {
      toast.error(err.message);
    }
    setSaving(false);
  };

  const resetColors = async () => {
    if (!window.confirm('Reset all brand colors to defaults?')) return;
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/company-branding/colors/reset`, {
        method: 'POST',
        headers: getAuthHeaders()
      });
      if (response.ok) {
        const data = await response.json();
        setBrandColors(data.data);
        toast.success('Colors reset to defaults');
      }
    } catch (err) {
      toast.error(err.message);
    }
  };

  // Update handlers with change tracking
  const updateCompanyInfo = (field, value) => {
    setCompanyInfo(prev => ({ ...prev, [field]: value }));
    setHasChanges(true);
  };

  const updateBrandColors = (field, value) => {
    setBrandColors(prev => ({ ...prev, [field]: value }));
    setHasChanges(true);
  };

  const updateTypography = (field, value) => {
    setTypography(prev => ({ ...prev, [field]: value }));
    setHasChanges(true);
  };

  const updateEmailBranding = (field, value) => {
    setEmailBranding(prev => ({ ...prev, [field]: value }));
    setHasChanges(true);
  };

  const updateDocumentBranding = (field, value) => {
    setDocumentBranding(prev => ({ ...prev, [field]: value }));
    setHasChanges(true);
  };

  const updateWhiteLabel = (field, value) => {
    setWhiteLabel(prev => ({ ...prev, [field]: value }));
    setHasChanges(true);
  };

  const updateSocialMedia = (field, value) => {
    setSocialMedia(prev => ({ ...prev, [field]: value }));
    setHasChanges(true);
  };

  // Tabs configuration
  const tabs = [
    { id: 'company', label: 'Company Info', icon: '🏢' },
    { id: 'colors', label: 'Colors', icon: '🎨' },
    { id: 'typography', label: 'Typography', icon: '🔤' },
    { id: 'assets', label: 'Assets', icon: '🖼️' },
    { id: 'email', label: 'Email', icon: '📧' },
    { id: 'documents', label: 'Documents', icon: '📄' },
    { id: 'white-label', label: 'White Label', icon: '🏷️' },
    { id: 'social', label: 'Social', icon: '🌐' }
  ];

  if (loading) {
    return (
      <div className="company-branding-settings">
        <div className="loading-container">Loading branding settings...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="company-branding-settings">
        <div className="error-container">
          <p>Error loading settings: {error}</p>
          <button onClick={loadData}>Retry</button>
        </div>
      </div>
    );
  }

  // Access denied if user doesn't have branding permissions
  if (!canAccessBranding) {
    return (
      <div className="company-branding-settings">
        <div style={{ textAlign: 'center', padding: '60px 20px' }}>
          <h2>Access Denied</h2>
          <p>You don't have permission to manage company branding.</p>
          <button className="btn-primary" onClick={() => navigate('/dashboard')} style={{ marginTop: '16px' }}>
            Return to Dashboard
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="company-branding-settings">
      <div className="page-header">
        <div>
          <h1>Company & Branding</h1>
          <p>Manage your company information and brand identity</p>
        </div>
        <button className="btn-back" onClick={() => navigate('/settings')}>
          ← Back to Settings
        </button>
      </div>

      {/* Tabs */}
      <div className="tabs-container">
        {tabs.map(tab => (
          <button
            key={tab.id}
            className={`tab ${activeTab === tab.id ? 'active' : ''}`}
            onClick={() => setActiveTab(tab.id)}
          >
            <span className="tab-icon">{tab.icon}</span>
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      <div className="tab-content">
        {/* Company Info Tab */}
        {activeTab === 'company' && (
          <div className="company-tab">
            <h2>Company Information</h2>
            <div className="form-grid">
              <div className="form-group">
                <label>Company Name *</label>
                <input
                  type="text"
                  value={companyInfo.company_name || ''}
                  onChange={(e) => updateCompanyInfo('company_name', e.target.value)}
                />
              </div>
              <div className="form-group">
                <label>Legal Name</label>
                <input
                  type="text"
                  value={companyInfo.legal_name || ''}
                  onChange={(e) => updateCompanyInfo('legal_name', e.target.value)}
                />
              </div>
              <div className="form-group">
                <label>NMLS ID</label>
                <input
                  type="text"
                  value={companyInfo.nmls_id || ''}
                  onChange={(e) => updateCompanyInfo('nmls_id', e.target.value)}
                />
              </div>
              <div className="form-group">
                <label>Phone *</label>
                <input
                  type="tel"
                  value={companyInfo.phone || ''}
                  onChange={(e) => updateCompanyInfo('phone', e.target.value)}
                />
              </div>
              <div className="form-group full-width">
                <label>Address Line 1 *</label>
                <input
                  type="text"
                  value={companyInfo.address_line1 || ''}
                  onChange={(e) => updateCompanyInfo('address_line1', e.target.value)}
                />
              </div>
              <div className="form-group full-width">
                <label>Address Line 2</label>
                <input
                  type="text"
                  value={companyInfo.address_line2 || ''}
                  onChange={(e) => updateCompanyInfo('address_line2', e.target.value)}
                />
              </div>
              <div className="form-group">
                <label>City *</label>
                <input
                  type="text"
                  value={companyInfo.city || ''}
                  onChange={(e) => updateCompanyInfo('city', e.target.value)}
                />
              </div>
              <div className="form-group">
                <label>State *</label>
                <input
                  type="text"
                  value={companyInfo.state || ''}
                  onChange={(e) => updateCompanyInfo('state', e.target.value.toUpperCase())}
                  maxLength={2}
                />
              </div>
              <div className="form-group">
                <label>ZIP Code *</label>
                <input
                  type="text"
                  value={companyInfo.zip_code || ''}
                  onChange={(e) => updateCompanyInfo('zip_code', e.target.value)}
                />
              </div>
              <div className="form-group">
                <label>Email *</label>
                <input
                  type="email"
                  value={companyInfo.email || ''}
                  onChange={(e) => updateCompanyInfo('email', e.target.value)}
                />
              </div>
              <div className="form-group">
                <label>Website</label>
                <input
                  type="url"
                  value={companyInfo.website || ''}
                  onChange={(e) => updateCompanyInfo('website', e.target.value)}
                  placeholder="https://"
                />
              </div>
              <div className="form-group">
                <label>Timezone</label>
                <select
                  value={companyInfo.timezone || 'America/New_York'}
                  onChange={(e) => updateCompanyInfo('timezone', e.target.value)}
                >
                  <option value="America/New_York">Eastern Time</option>
                  <option value="America/Chicago">Central Time</option>
                  <option value="America/Denver">Mountain Time</option>
                  <option value="America/Los_Angeles">Pacific Time</option>
                </select>
              </div>
            </div>
            <div className="form-actions">
              <button className="btn-primary" onClick={saveCompanyInfo} disabled={saving}>
                {saving ? 'Saving...' : 'Save Company Info'}
              </button>
            </div>
          </div>
        )}

        {/* Colors Tab */}
        {activeTab === 'colors' && (
          <div className="colors-tab">
            <div className="section-header">
              <h2>Brand Colors</h2>
              <button className="btn-secondary" onClick={resetColors}>
                Reset to Defaults
              </button>
            </div>
            <div className="color-grid">
              {[
                { key: 'primary_color', label: 'Primary Color' },
                { key: 'secondary_color', label: 'Secondary Color' },
                { key: 'accent_color', label: 'Accent Color' },
                { key: 'success_color', label: 'Success Color' },
                { key: 'warning_color', label: 'Warning Color' },
                { key: 'error_color', label: 'Error Color' },
                { key: 'text_color', label: 'Text Color' },
                { key: 'background_color', label: 'Background Color' },
                { key: 'header_background', label: 'Header Background' },
                { key: 'sidebar_background', label: 'Sidebar Background' }
              ].map(({ key, label }) => (
                <div key={key} className="color-picker-group">
                  <label>{label}</label>
                  <div className="color-picker-row">
                    <input
                      type="color"
                      value={brandColors[key] || '#000000'}
                      onChange={(e) => updateBrandColors(key, e.target.value)}
                    />
                    <input
                      type="text"
                      value={brandColors[key] || ''}
                      onChange={(e) => updateBrandColors(key, e.target.value)}
                      placeholder="#000000"
                      pattern="^#[0-9a-fA-F]{6}$"
                    />
                    <div
                      className="color-preview"
                      style={{ backgroundColor: brandColors[key] }}
                    />
                  </div>
                </div>
              ))}
            </div>
            <div className="color-preview-section">
              <h3>Preview</h3>
              <div className="preview-box" style={{ backgroundColor: brandColors.background_color }}>
                <div className="preview-header" style={{ backgroundColor: brandColors.header_background }}>
                  <span style={{ color: '#fff' }}>Header</span>
                </div>
                <div className="preview-content">
                  <h4 style={{ color: brandColors.text_color }}>Sample Heading</h4>
                  <p style={{ color: brandColors.text_color }}>Sample text content</p>
                  <button style={{ backgroundColor: brandColors.primary_color, color: '#fff' }}>
                    Primary Button
                  </button>
                  <button style={{ backgroundColor: brandColors.accent_color, color: '#fff' }}>
                    Accent Button
                  </button>
                </div>
              </div>
            </div>
            <div className="form-actions">
              <button className="btn-primary" onClick={saveBrandColors} disabled={saving}>
                {saving ? 'Saving...' : 'Save Colors'}
              </button>
            </div>
          </div>
        )}

        {/* Typography Tab */}
        {activeTab === 'typography' && (
          <div className="typography-tab">
            <h2>Typography Settings</h2>
            <div className="form-grid">
              <div className="form-group">
                <label>Heading Font</label>
                <select
                  value={typography.heading_font || 'Inter'}
                  onChange={(e) => updateTypography('heading_font', e.target.value)}
                >
                  <option value="Inter">Inter</option>
                  <option value="Roboto">Roboto</option>
                  <option value="Open Sans">Open Sans</option>
                  <option value="Lato">Lato</option>
                  <option value="Poppins">Poppins</option>
                  <option value="Montserrat">Montserrat</option>
                </select>
              </div>
              <div className="form-group">
                <label>Body Font</label>
                <select
                  value={typography.body_font || 'Inter'}
                  onChange={(e) => updateTypography('body_font', e.target.value)}
                >
                  <option value="Inter">Inter</option>
                  <option value="Roboto">Roboto</option>
                  <option value="Open Sans">Open Sans</option>
                  <option value="Lato">Lato</option>
                  <option value="Poppins">Poppins</option>
                </select>
              </div>
              <div className="form-group">
                <label>Heading Weight</label>
                <select
                  value={typography.heading_weight || '600'}
                  onChange={(e) => updateTypography('heading_weight', e.target.value)}
                >
                  <option value="400">Regular (400)</option>
                  <option value="500">Medium (500)</option>
                  <option value="600">Semibold (600)</option>
                  <option value="700">Bold (700)</option>
                </select>
              </div>
              <div className="form-group">
                <label>Body Weight</label>
                <select
                  value={typography.body_weight || '400'}
                  onChange={(e) => updateTypography('body_weight', e.target.value)}
                >
                  <option value="300">Light (300)</option>
                  <option value="400">Regular (400)</option>
                  <option value="500">Medium (500)</option>
                </select>
              </div>
              <div className="form-group">
                <label>Base Font Size (px)</label>
                <input
                  type="number"
                  value={typography.base_font_size || 16}
                  onChange={(e) => updateTypography('base_font_size', parseInt(e.target.value))}
                  min={12}
                  max={24}
                />
              </div>
              <div className="form-group">
                <label>Line Height</label>
                <input
                  type="number"
                  step="0.1"
                  value={typography.line_height || 1.5}
                  onChange={(e) => updateTypography('line_height', parseFloat(e.target.value))}
                  min={1.0}
                  max={2.5}
                />
              </div>
            </div>
            <div className="typography-preview">
              <h3>Preview</h3>
              <div
                className="preview-content"
                style={{
                  fontFamily: typography.body_font,
                  fontSize: `${typography.base_font_size}px`,
                  lineHeight: typography.line_height
                }}
              >
                <h1 style={{ fontFamily: typography.heading_font, fontWeight: typography.heading_weight }}>
                  Heading 1
                </h1>
                <h2 style={{ fontFamily: typography.heading_font, fontWeight: typography.heading_weight }}>
                  Heading 2
                </h2>
                <p style={{ fontWeight: typography.body_weight }}>
                  This is sample body text. The quick brown fox jumps over the lazy dog.
                </p>
              </div>
            </div>
            <div className="form-actions">
              <button className="btn-primary" onClick={saveTypography} disabled={saving}>
                {saving ? 'Saving...' : 'Save Typography'}
              </button>
            </div>
          </div>
        )}

        {/* Assets Tab */}
        {activeTab === 'assets' && (
          <div className="assets-tab">
            <h2>Brand Assets</h2>
            <div className="assets-grid">
              {[
                { key: 'logo_url', label: 'Main Logo', desc: 'Used in header and documents' },
                { key: 'logo_dark_url', label: 'Dark Logo', desc: 'For dark backgrounds' },
                { key: 'icon_url', label: 'Icon', desc: 'Square icon for app shortcuts' },
                { key: 'favicon_url', label: 'Favicon', desc: 'Browser tab icon (16x16 or 32x32)' },
                { key: 'email_header_url', label: 'Email Header', desc: 'Header image for emails' },
                { key: 'email_footer_url', label: 'Email Footer', desc: 'Footer image for emails' },
                { key: 'document_letterhead_url', label: 'Letterhead', desc: 'Document header/letterhead' },
                { key: 'watermark_url', label: 'Watermark', desc: 'Document watermark image' }
              ].map(({ key, label, desc }) => (
                <div key={key} className="asset-upload-card">
                  <div className="asset-preview">
                    {brandAssets[key] ? (
                      <img src={brandAssets[key]} alt={label} />
                    ) : (
                      <div className="placeholder">No image</div>
                    )}
                  </div>
                  <div className="asset-info">
                    <h4>{label}</h4>
                    <p>{desc}</p>
                    <button className="btn-upload">Upload Image</button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Email Tab */}
        {activeTab === 'email' && (
          <div className="email-tab">
            <h2>Email Branding</h2>
            <div className="form-grid">
              <div className="form-group">
                <label>From Name *</label>
                <input
                  type="text"
                  value={emailBranding.from_name || ''}
                  onChange={(e) => updateEmailBranding('from_name', e.target.value)}
                />
              </div>
              <div className="form-group">
                <label>From Email *</label>
                <input
                  type="email"
                  value={emailBranding.from_email || ''}
                  onChange={(e) => updateEmailBranding('from_email', e.target.value)}
                />
              </div>
              <div className="form-group">
                <label>Reply-To Email</label>
                <input
                  type="email"
                  value={emailBranding.reply_to_email || ''}
                  onChange={(e) => updateEmailBranding('reply_to_email', e.target.value)}
                />
              </div>
              <div className="form-group full-width">
                <label>Email Footer Text</label>
                <textarea
                  value={emailBranding.email_footer_text || ''}
                  onChange={(e) => updateEmailBranding('email_footer_text', e.target.value)}
                  rows={3}
                />
              </div>
              <div className="form-group full-width">
                <label>Unsubscribe Text</label>
                <input
                  type="text"
                  value={emailBranding.unsubscribe_text || ''}
                  onChange={(e) => updateEmailBranding('unsubscribe_text', e.target.value)}
                />
              </div>
              <div className="form-group">
                <label>
                  <input
                    type="checkbox"
                    checked={emailBranding.include_social_links || false}
                    onChange={(e) => updateEmailBranding('include_social_links', e.target.checked)}
                  />
                  Include Social Links in Emails
                </label>
              </div>
            </div>
            <div className="form-actions">
              <button className="btn-primary" onClick={saveEmailBranding} disabled={saving}>
                {saving ? 'Saving...' : 'Save Email Settings'}
              </button>
            </div>
          </div>
        )}

        {/* Documents Tab */}
        {activeTab === 'documents' && (
          <div className="documents-tab">
            <h2>Document Branding</h2>
            <div className="form-grid">
              <div className="form-group">
                <label>
                  <input
                    type="checkbox"
                    checked={documentBranding.show_logo || false}
                    onChange={(e) => updateDocumentBranding('show_logo', e.target.checked)}
                  />
                  Show Logo on Documents
                </label>
              </div>
              <div className="form-group">
                <label>Logo Position</label>
                <select
                  value={documentBranding.logo_position || 'top-left'}
                  onChange={(e) => updateDocumentBranding('logo_position', e.target.value)}
                >
                  <option value="top-left">Top Left</option>
                  <option value="top-center">Top Center</option>
                  <option value="top-right">Top Right</option>
                </select>
              </div>
              <div className="form-group">
                <label>
                  <input
                    type="checkbox"
                    checked={documentBranding.show_company_info || false}
                    onChange={(e) => updateDocumentBranding('show_company_info', e.target.checked)}
                  />
                  Show Company Info
                </label>
              </div>
              <div className="form-group">
                <label>
                  <input
                    type="checkbox"
                    checked={documentBranding.show_nmls_id || false}
                    onChange={(e) => updateDocumentBranding('show_nmls_id', e.target.checked)}
                  />
                  Show NMLS ID
                </label>
              </div>
              <div className="form-group">
                <label>
                  <input
                    type="checkbox"
                    checked={documentBranding.show_equal_housing_logo || false}
                    onChange={(e) => updateDocumentBranding('show_equal_housing_logo', e.target.checked)}
                  />
                  Show Equal Housing Logo
                </label>
              </div>
              <div className="form-group">
                <label>
                  <input
                    type="checkbox"
                    checked={documentBranding.watermark_enabled || false}
                    onChange={(e) => updateDocumentBranding('watermark_enabled', e.target.checked)}
                  />
                  Enable Watermark
                </label>
              </div>
              {documentBranding.watermark_enabled && (
                <>
                  <div className="form-group">
                    <label>Watermark Text</label>
                    <input
                      type="text"
                      value={documentBranding.watermark_text || ''}
                      onChange={(e) => updateDocumentBranding('watermark_text', e.target.value)}
                    />
                  </div>
                  <div className="form-group">
                    <label>Watermark Opacity (%)</label>
                    <input
                      type="range"
                      min={5}
                      max={50}
                      value={documentBranding.watermark_opacity || 20}
                      onChange={(e) => updateDocumentBranding('watermark_opacity', parseInt(e.target.value))}
                    />
                    <span>{documentBranding.watermark_opacity || 20}%</span>
                  </div>
                </>
              )}
              <div className="form-group full-width">
                <label>Footer Disclaimer</label>
                <textarea
                  value={documentBranding.footer_disclaimer || ''}
                  onChange={(e) => updateDocumentBranding('footer_disclaimer', e.target.value)}
                  rows={3}
                />
              </div>
            </div>
            <div className="form-actions">
              <button className="btn-primary" onClick={saveDocumentBranding} disabled={saving}>
                {saving ? 'Saving...' : 'Save Document Settings'}
              </button>
            </div>
          </div>
        )}

        {/* White Label Tab */}
        {activeTab === 'white-label' && (
          <div className="white-label-tab">
            <h2>White Label Settings</h2>
            <div className="info-banner">
              White-labeling allows you to customize the platform appearance and remove Perennia branding.
            </div>
            <div className="form-grid">
              <div className="form-group">
                <label>
                  <input
                    type="checkbox"
                    checked={whiteLabel.enabled || false}
                    onChange={(e) => updateWhiteLabel('enabled', e.target.checked)}
                  />
                  Enable White Labeling
                </label>
              </div>
              {whiteLabel.enabled && (
                <>
                  <div className="form-group">
                    <label>Custom Domain</label>
                    <input
                      type="text"
                      value={whiteLabel.custom_domain || ''}
                      onChange={(e) => updateWhiteLabel('custom_domain', e.target.value)}
                      placeholder="app.yourcompany.com"
                    />
                  </div>
                  <div className="form-group">
                    <label>Custom Email Domain</label>
                    <input
                      type="text"
                      value={whiteLabel.custom_email_domain || ''}
                      onChange={(e) => updateWhiteLabel('custom_email_domain', e.target.value)}
                      placeholder="mail.yourcompany.com"
                    />
                  </div>
                  <div className="form-group">
                    <label>Browser Tab Title</label>
                    <input
                      type="text"
                      value={whiteLabel.browser_tab_title || ''}
                      onChange={(e) => updateWhiteLabel('browser_tab_title', e.target.value)}
                    />
                  </div>
                  <div className="form-group">
                    <label>
                      <input
                        type="checkbox"
                        checked={whiteLabel.hide_powered_by || false}
                        onChange={(e) => updateWhiteLabel('hide_powered_by', e.target.checked)}
                      />
                      Hide "Powered by Perennia"
                    </label>
                  </div>
                </>
              )}
            </div>
            <div className="form-actions">
              <button className="btn-primary" onClick={saveWhiteLabel} disabled={saving}>
                {saving ? 'Saving...' : 'Save White Label Settings'}
              </button>
            </div>
          </div>
        )}

        {/* Social Tab */}
        {activeTab === 'social' && (
          <div className="social-tab">
            <h2>Social Media Links</h2>
            <div className="form-grid">
              {[
                { key: 'facebook', label: 'Facebook', icon: '📘' },
                { key: 'twitter', label: 'Twitter/X', icon: '🐦' },
                { key: 'linkedin', label: 'LinkedIn', icon: '💼' },
                { key: 'instagram', label: 'Instagram', icon: '📷' },
                { key: 'youtube', label: 'YouTube', icon: '▶️' },
                { key: 'tiktok', label: 'TikTok', icon: '🎵' }
              ].map(({ key, label, icon }) => (
                <div key={key} className="form-group">
                  <label>{icon} {label}</label>
                  <input
                    type="url"
                    value={socialMedia[key] || ''}
                    onChange={(e) => updateSocialMedia(key, e.target.value)}
                    placeholder={`https://${key}.com/yourprofile`}
                  />
                </div>
              ))}
            </div>
            <div className="form-actions">
              <button className="btn-primary" onClick={saveSocialMedia} disabled={saving}>
                {saving ? 'Saving...' : 'Save Social Media Links'}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default CompanyBrandingSettings;
