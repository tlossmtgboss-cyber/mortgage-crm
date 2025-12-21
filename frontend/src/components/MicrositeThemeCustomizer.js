/**
 * MicrositeThemeCustomizer - Comprehensive Theme Customization Component
 *
 * Allows users to customize their microsite including:
 * - Logo and headshot uploads (Branding)
 * - Colors and fonts (Theme)
 * - Social media links
 * - Footer content
 * - Page management
 */

import React, { useState, useEffect, useCallback, useRef } from 'react';
import './MicrositeThemeCustomizer.css';

// API base URL
const API_BASE = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
  ? (process.env.REACT_APP_API_URL || 'http://localhost:8000')
  : 'https://mortgage-crm-production-7a9a.up.railway.app';

// Preset color palettes
const COLOR_PRESETS = [
  { name: 'Classic Blue', primary: '#2563eb', secondary: '#1e40af' },
  { name: 'Bold Red', primary: '#dc2626', secondary: '#1e3a5f' },
  { name: 'Modern Purple', primary: '#8b5cf6', secondary: '#ec4899' },
  { name: 'Forest Green', primary: '#059669', secondary: '#047857' },
  { name: 'Warm Orange', primary: '#ea580c', secondary: '#c2410c' },
  { name: 'Elegant Gold', primary: '#ca8a04', secondary: '#854d0e' },
  { name: 'Slate Gray', primary: '#475569', secondary: '#334155' },
  { name: 'Ocean Teal', primary: '#0891b2', secondary: '#0e7490' },
];

// Font options
const FONT_OPTIONS = [
  { value: 'inter', label: 'Inter', family: "'Inter', -apple-system, sans-serif" },
  { value: 'roboto', label: 'Roboto', family: "'Roboto', sans-serif" },
  { value: 'poppins', label: 'Poppins', family: "'Poppins', sans-serif" },
  { value: 'open-sans', label: 'Open Sans', family: "'Open Sans', sans-serif" },
  { value: 'lato', label: 'Lato', family: "'Lato', sans-serif" },
  { value: 'montserrat', label: 'Montserrat', family: "'Montserrat', sans-serif" },
  { value: 'source-sans', label: 'Source Sans Pro', family: "'Source Sans Pro', sans-serif" },
  { value: 'playfair', label: 'Playfair Display', family: "'Playfair Display', serif" },
];

// Social media platforms
const SOCIAL_PLATFORMS = [
  { key: 'facebook', label: 'Facebook', icon: 'fb', placeholder: 'https://facebook.com/yourpage' },
  { key: 'linkedin', label: 'LinkedIn', icon: 'li', placeholder: 'https://linkedin.com/in/yourprofile' },
  { key: 'instagram', label: 'Instagram', icon: 'ig', placeholder: 'https://instagram.com/yourhandle' },
  { key: 'tiktok', label: 'TikTok', icon: 'tt', placeholder: 'https://tiktok.com/@yourhandle' },
  { key: 'youtube', label: 'YouTube', icon: 'yt', placeholder: 'https://youtube.com/@yourchannel' },
  { key: 'twitter', label: 'X (Twitter)', icon: 'x', placeholder: 'https://x.com/yourhandle' },
];

const MicrositeThemeCustomizer = ({ theme, currentConfig, onConfigChange, onSave, micrositeId }) => {
  const [config, setConfig] = useState({
    primaryColor: '#2563eb',
    secondaryColor: '#1e40af',
    fontFamily: 'inter',
    ...currentConfig
  });
  const [saving, setSaving] = useState(false);
  const [hasChanges, setHasChanges] = useState(false);
  const [activeTab, setActiveTab] = useState('branding');
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState({ type: '', text: '' });

  // Branding state
  const [logoUrl, setLogoUrl] = useState('');
  const [headshotUrl, setHeadshotUrl] = useState('');
  const [uploadingLogo, setUploadingLogo] = useState(false);
  const [uploadingHeadshot, setUploadingHeadshot] = useState(false);
  const logoInputRef = useRef(null);
  const headshotInputRef = useRef(null);

  // Social links state
  const [socialLinks, setSocialLinks] = useState({
    facebook: '',
    linkedin: '',
    instagram: '',
    tiktok: '',
    youtube: '',
    twitter: '',
  });

  // Footer state
  const [footerContent, setFooterContent] = useState({
    companyName: '',
    nmls: '',
    disclaimer: '',
    showEqualHousing: true,
  });

  // Pages state
  const [pages, setPages] = useState([]);
  const [editingPage, setEditingPage] = useState(null);
  const [showPageModal, setShowPageModal] = useState(false);
  const [pageForm, setPageForm] = useState({ title: '', slug: '', content: '', isPublished: true });

  // Profile content state
  const [profileContent, setProfileContent] = useState({
    headline: '',
    tagline: '',
    bioExtended: '',
    yearsExperience: '',
    totalLoansFunded: '',
    specialties: [],
    ctaText: 'Get Started Today',
    ctaSecondaryText: 'Check Your Rate',
  });

  // Fetch existing profile data
  useEffect(() => {
    fetchProfileData();
  }, []);

  const fetchProfileData = async () => {
    try {
      setLoading(true);
      const token = localStorage.getItem('token');

      // Fetch microsite profile
      const response = await fetch(`${API_BASE}/api/v1/microsites/my`, {
        headers: {
          'Authorization': `Bearer ${token}`,
        }
      });

      if (response.ok) {
        const data = await response.json();
        const content = data.content_json || {};
        const branding = data.branding_json || {};

        // Set branding from branding_json
        setLogoUrl(branding.logoUrl || '');
        setHeadshotUrl(branding.heroImageUrl || '');

        // Set theme config from branding_json
        if (branding.primaryColor || branding.secondaryColor || branding.fontFamily) {
          setConfig(prev => ({
            ...prev,
            primaryColor: branding.primaryColor || prev.primaryColor,
            secondaryColor: branding.secondaryColor || prev.secondaryColor,
            fontFamily: branding.fontFamily || prev.fontFamily,
          }));
        }

        // Set social links from content_json
        const socialData = content.socialLinks || {};
        setSocialLinks({
          facebook: socialData.facebook || '',
          linkedin: socialData.linkedin || '',
          instagram: socialData.instagram || '',
          tiktok: socialData.tiktok || '',
          youtube: socialData.youtube || '',
          twitter: socialData.twitter || '',
        });

        // Set footer content from content_json
        setFooterContent({
          companyName: content.companyName || '',
          nmls: content.nmls || '',
          disclaimer: content.disclaimer || '',
          showEqualHousing: content.showEqualHousing !== false,
        });

        // Set profile content from content_json
        setProfileContent({
          headline: content.headline || '',
          tagline: content.tagline || '',
          bioExtended: content.bioExtended || '',
          yearsExperience: content.yearsExperience || '',
          totalLoansFunded: content.totalLoansFunded || '',
          specialties: content.specialties || [],
          ctaText: content.ctaText || 'Get Started Today',
          ctaSecondaryText: content.ctaSecondaryText || 'Check Your Rate',
        });
      }

      // Pages are managed separately - skip for now if endpoint doesn't exist
      try {
        const pagesResponse = await fetch(`${API_BASE}/api/v1/microsites/my/pages`, {
          headers: {
            'Authorization': `Bearer ${token}`,
          }
        });

        if (pagesResponse.ok) {
          const pagesData = await pagesResponse.json();
          setPages(pagesData.pages || pagesData || []);
        }
      } catch (pageErr) {
        console.log('Pages endpoint not available yet');
        setPages([]);
      }
    } catch (err) {
      console.error('Error fetching profile:', err);
    } finally {
      setLoading(false);
    }
  };

  // Initialize config from current settings
  useEffect(() => {
    if (currentConfig) {
      setConfig(prev => ({ ...prev, ...currentConfig }));
    }
  }, [currentConfig]);

  // Track changes
  useEffect(() => {
    const configString = JSON.stringify(config);
    const currentString = JSON.stringify(currentConfig || {});
    setHasChanges(configString !== currentString);
  }, [config, currentConfig]);

  // Update config
  const updateConfig = useCallback((key, value) => {
    setConfig(prev => {
      const updated = { ...prev, [key]: value };
      if (onConfigChange) {
        onConfigChange(updated);
      }
      return updated;
    });
    setHasChanges(true);
  }, [onConfigChange]);

  // Apply preset
  const applyPreset = (preset) => {
    setConfig(prev => {
      const updated = {
        ...prev,
        primaryColor: preset.primary,
        secondaryColor: preset.secondary
      };
      if (onConfigChange) {
        onConfigChange(updated);
      }
      return updated;
    });
    setHasChanges(true);
  };

  // Show message helper
  const showMessage = (type, text) => {
    setMessage({ type, text });
    setTimeout(() => setMessage({ type: '', text: '' }), 3000);
  };

  // Handle logo upload
  const handleLogoUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;

    // Validate file
    if (!file.type.startsWith('image/')) {
      showMessage('error', 'Please select an image file');
      return;
    }
    if (file.size > 5 * 1024 * 1024) {
      showMessage('error', 'File size must be less than 5MB');
      return;
    }

    setUploadingLogo(true);
    try {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('type', 'logo');

      const response = await fetch(`${API_BASE}/api/v1/microsites/my/assets/upload`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`,
        },
        body: formData
      });

      if (response.ok) {
        const data = await response.json();
        setLogoUrl(data.url);
        showMessage('success', 'Logo uploaded successfully');
        setHasChanges(true);
      } else {
        throw new Error('Upload failed');
      }
    } catch (err) {
      console.error('Logo upload error:', err);
      showMessage('error', 'Failed to upload logo');
    } finally {
      setUploadingLogo(false);
    }
  };

  // Handle headshot upload
  const handleHeadshotUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;

    // Validate file
    if (!file.type.startsWith('image/')) {
      showMessage('error', 'Please select an image file');
      return;
    }
    if (file.size > 5 * 1024 * 1024) {
      showMessage('error', 'File size must be less than 5MB');
      return;
    }

    setUploadingHeadshot(true);
    try {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('type', 'headshot');

      const response = await fetch(`${API_BASE}/api/v1/microsites/my/assets/upload`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`,
        },
        body: formData
      });

      if (response.ok) {
        const data = await response.json();
        setHeadshotUrl(data.url);
        showMessage('success', 'Photo uploaded successfully');
        setHasChanges(true);
      } else {
        throw new Error('Upload failed');
      }
    } catch (err) {
      console.error('Headshot upload error:', err);
      showMessage('error', 'Failed to upload photo');
    } finally {
      setUploadingHeadshot(false);
    }
  };

  // Remove logo
  const handleRemoveLogo = () => {
    setLogoUrl('');
    setHasChanges(true);
  };

  // Remove headshot
  const handleRemoveHeadshot = () => {
    setHeadshotUrl('');
    setHasChanges(true);
  };

  // Update social link
  const updateSocialLink = (platform, value) => {
    setSocialLinks(prev => ({ ...prev, [platform]: value }));
    setHasChanges(true);
  };

  // Update footer content
  const updateFooterContent = (key, value) => {
    setFooterContent(prev => ({ ...prev, [key]: value }));
    setHasChanges(true);
  };

  // Update profile content
  const updateProfileContent = (key, value) => {
    setProfileContent(prev => ({ ...prev, [key]: value }));
    setHasChanges(true);
  };

  // Save all changes
  const handleSaveAll = async () => {
    setSaving(true);
    try {
      const token = localStorage.getItem('token');

      // Build content_json with all profile data
      const content_json = {
        // Profile content
        headline: profileContent.headline,
        tagline: profileContent.tagline,
        bioExtended: profileContent.bioExtended,
        yearsExperience: profileContent.yearsExperience,
        totalLoansFunded: profileContent.totalLoansFunded,
        specialties: profileContent.specialties,
        ctaText: profileContent.ctaText,
        ctaSecondaryText: profileContent.ctaSecondaryText,
        // Social links
        socialLinks,
        // Footer content
        companyName: footerContent.companyName,
        nmls: footerContent.nmls,
        disclaimer: footerContent.disclaimer,
        showEqualHousing: footerContent.showEqualHousing,
      };

      // Build branding_json with theme config and images
      const branding_json = {
        primaryColor: config.primaryColor,
        secondaryColor: config.secondaryColor,
        fontFamily: config.fontFamily,
        logoUrl,
        heroImageUrl: headshotUrl,
      };

      // Save profile data using backend's expected structure
      const profileResponse = await fetch(`${API_BASE}/api/v1/microsites/my`, {
        method: 'PUT',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          content_json,
          branding_json,
        })
      });

      if (profileResponse.ok) {
        setHasChanges(false);
        showMessage('success', 'All changes saved successfully');
        if (onSave) {
          onSave(config);
        }
      } else {
        throw new Error('Failed to save');
      }
    } catch (err) {
      console.error('Error saving:', err);
      showMessage('error', 'Failed to save changes. Please try again.');
    } finally {
      setSaving(false);
    }
  };

  // Page management
  const openPageModal = (page = null) => {
    if (page) {
      setEditingPage(page);
      setPageForm({
        title: page.title,
        slug: page.slug,
        content: page.content,
        isPublished: page.is_published !== false
      });
    } else {
      setEditingPage(null);
      setPageForm({ title: '', slug: '', content: '', isPublished: true });
    }
    setShowPageModal(true);
  };

  const closePageModal = () => {
    setShowPageModal(false);
    setEditingPage(null);
    setPageForm({ title: '', slug: '', content: '', isPublished: true });
  };

  const generateSlug = (title) => {
    return title.toLowerCase()
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/(^-|-$)/g, '');
  };

  const handlePageFormChange = (key, value) => {
    setPageForm(prev => {
      const updated = { ...prev, [key]: value };
      if (key === 'title' && !editingPage) {
        updated.slug = generateSlug(value);
      }
      return updated;
    });
  };

  const savePage = async () => {
    if (!pageForm.title.trim()) {
      showMessage('error', 'Page title is required');
      return;
    }

    try {
      const token = localStorage.getItem('token');
      const url = editingPage
        ? `${API_BASE}/api/v1/microsites/my/pages/${editingPage.id}`
        : `${API_BASE}/api/v1/microsites/my/pages`;

      const response = await fetch(url, {
        method: editingPage ? 'PUT' : 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          title: pageForm.title,
          slug: pageForm.slug || generateSlug(pageForm.title),
          content: pageForm.content,
          is_published: pageForm.isPublished
        })
      });

      if (response.ok) {
        showMessage('success', editingPage ? 'Page updated' : 'Page created');
        closePageModal();
        fetchProfileData(); // Refresh pages
      } else {
        throw new Error('Failed to save page');
      }
    } catch (err) {
      console.error('Error saving page:', err);
      showMessage('error', 'Failed to save page');
    }
  };

  const deletePage = async (pageId) => {
    if (!window.confirm('Are you sure you want to delete this page?')) return;

    try {
      const response = await fetch(`${API_BASE}/api/v1/microsites/my/pages/${pageId}`, {
        method: 'DELETE',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`,
        }
      });

      if (response.ok) {
        showMessage('success', 'Page deleted');
        fetchProfileData();
      } else {
        throw new Error('Failed to delete page');
      }
    } catch (err) {
      console.error('Error deleting page:', err);
      showMessage('error', 'Failed to delete page');
    }
  };

  // Reset to defaults
  const handleReset = () => {
    const defaults = theme?.defaultConfig || {
      primaryColor: '#2563eb',
      secondaryColor: '#1e40af',
      fontFamily: 'inter'
    };
    setConfig(defaults);
    if (onConfigChange) {
      onConfigChange(defaults);
    }
    setHasChanges(true);
  };

  // Get layout options for current theme
  const layoutOptions = theme?.layoutOptions || {};

  if (loading) {
    return (
      <div className="theme-customizer loading">
        <div className="loading-spinner"></div>
        <p>Loading your settings...</p>
      </div>
    );
  }

  return (
    <div className="theme-customizer">
      {/* Message Toast */}
      {message.text && (
        <div className={`customizer-message ${message.type}`}>
          {message.text}
        </div>
      )}

      <div className="customizer-header">
        <h3>Customize Your Microsite</h3>
        <p>Personalize your branding, content, and design</p>
      </div>

      {/* Tabs */}
      <div className="customizer-tabs">
        <button
          className={`tab-btn ${activeTab === 'branding' ? 'active' : ''}`}
          onClick={() => setActiveTab('branding')}
        >
          Branding
        </button>
        <button
          className={`tab-btn ${activeTab === 'content' ? 'active' : ''}`}
          onClick={() => setActiveTab('content')}
        >
          Content
        </button>
        <button
          className={`tab-btn ${activeTab === 'theme' ? 'active' : ''}`}
          onClick={() => setActiveTab('theme')}
        >
          Theme
        </button>
        <button
          className={`tab-btn ${activeTab === 'social' ? 'active' : ''}`}
          onClick={() => setActiveTab('social')}
        >
          Social
        </button>
        <button
          className={`tab-btn ${activeTab === 'footer' ? 'active' : ''}`}
          onClick={() => setActiveTab('footer')}
        >
          Footer
        </button>
        <button
          className={`tab-btn ${activeTab === 'pages' ? 'active' : ''}`}
          onClick={() => setActiveTab('pages')}
        >
          Pages
        </button>
      </div>

      {/* Branding Tab */}
      {activeTab === 'branding' && (
        <div className="customizer-section">
          <div className="upload-section">
            {/* Logo Upload */}
            <div className="upload-field">
              <label>Company Logo</label>
              <p className="upload-hint">Recommended: 400x100px, PNG or SVG with transparent background</p>
              <div className="upload-preview-area">
                {logoUrl ? (
                  <div className="upload-preview">
                    <img src={logoUrl} alt="Logo" className="preview-image logo-preview" />
                    <div className="preview-actions">
                      <button
                        className="change-btn"
                        onClick={() => logoInputRef.current?.click()}
                        disabled={uploadingLogo}
                      >
                        Change
                      </button>
                      <button
                        className="remove-btn"
                        onClick={handleRemoveLogo}
                      >
                        Remove
                      </button>
                    </div>
                  </div>
                ) : (
                  <div
                    className="upload-dropzone"
                    onClick={() => logoInputRef.current?.click()}
                  >
                    {uploadingLogo ? (
                      <span className="uploading">Uploading...</span>
                    ) : (
                      <>
                        <span className="upload-icon">+</span>
                        <span>Click to upload logo</span>
                      </>
                    )}
                  </div>
                )}
                <input
                  ref={logoInputRef}
                  type="file"
                  accept="image/*"
                  onChange={handleLogoUpload}
                  style={{ display: 'none' }}
                />
              </div>
            </div>

            {/* Headshot Upload */}
            <div className="upload-field">
              <label>Professional Headshot</label>
              <p className="upload-hint">Recommended: 400x400px square photo, JPG or PNG</p>
              <div className="upload-preview-area">
                {headshotUrl ? (
                  <div className="upload-preview">
                    <img src={headshotUrl} alt="Headshot" className="preview-image headshot-preview" />
                    <div className="preview-actions">
                      <button
                        className="change-btn"
                        onClick={() => headshotInputRef.current?.click()}
                        disabled={uploadingHeadshot}
                      >
                        Change
                      </button>
                      <button
                        className="remove-btn"
                        onClick={handleRemoveHeadshot}
                      >
                        Remove
                      </button>
                    </div>
                  </div>
                ) : (
                  <div
                    className="upload-dropzone headshot-dropzone"
                    onClick={() => headshotInputRef.current?.click()}
                  >
                    {uploadingHeadshot ? (
                      <span className="uploading">Uploading...</span>
                    ) : (
                      <>
                        <span className="upload-icon">+</span>
                        <span>Click to upload photo</span>
                      </>
                    )}
                  </div>
                )}
                <input
                  ref={headshotInputRef}
                  type="file"
                  accept="image/*"
                  onChange={handleHeadshotUpload}
                  style={{ display: 'none' }}
                />
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Content Tab */}
      {activeTab === 'content' && (
        <div className="customizer-section">
          <div className="content-fields">
            <div className="field-group">
              <label>Headline</label>
              <input
                type="text"
                value={profileContent.headline}
                onChange={(e) => updateProfileContent('headline', e.target.value)}
                placeholder="Your Path to Homeownership Starts Here"
                className="text-input"
              />
            </div>

            <div className="field-group">
              <label>Tagline</label>
              <input
                type="text"
                value={profileContent.tagline}
                onChange={(e) => updateProfileContent('tagline', e.target.value)}
                placeholder="Expert guidance for all your mortgage needs"
                className="text-input"
              />
            </div>

            <div className="field-group">
              <label>Bio / About Me</label>
              <textarea
                value={profileContent.bioExtended}
                onChange={(e) => updateProfileContent('bioExtended', e.target.value)}
                placeholder="Tell visitors about yourself and your experience..."
                className="textarea-input"
                rows={4}
              />
            </div>

            <div className="field-row">
              <div className="field-group half">
                <label>Years of Experience</label>
                <input
                  type="number"
                  value={profileContent.yearsExperience}
                  onChange={(e) => updateProfileContent('yearsExperience', e.target.value)}
                  placeholder="15"
                  className="text-input"
                />
              </div>

              <div className="field-group half">
                <label>Total Loans Funded</label>
                <input
                  type="number"
                  value={profileContent.totalLoansFunded}
                  onChange={(e) => updateProfileContent('totalLoansFunded', e.target.value)}
                  placeholder="500"
                  className="text-input"
                />
              </div>
            </div>

            <div className="field-row">
              <div className="field-group half">
                <label>Primary CTA Text</label>
                <input
                  type="text"
                  value={profileContent.ctaText}
                  onChange={(e) => updateProfileContent('ctaText', e.target.value)}
                  placeholder="Get Started Today"
                  className="text-input"
                />
              </div>

              <div className="field-group half">
                <label>Secondary CTA Text</label>
                <input
                  type="text"
                  value={profileContent.ctaSecondaryText}
                  onChange={(e) => updateProfileContent('ctaSecondaryText', e.target.value)}
                  placeholder="Check Your Rate"
                  className="text-input"
                />
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Theme Tab (Colors & Typography) */}
      {activeTab === 'theme' && (
        <div className="customizer-section">
          {/* Color Presets */}
          <div className="preset-section">
            <label>Color Presets</label>
            <div className="color-presets">
              {COLOR_PRESETS.map((preset, index) => (
                <button
                  key={index}
                  className={`preset-btn ${
                    config.primaryColor === preset.primary ? 'active' : ''
                  }`}
                  onClick={() => applyPreset(preset)}
                  title={preset.name}
                >
                  <span
                    className="preset-swatch"
                    style={{
                      background: `linear-gradient(135deg, ${preset.primary} 0%, ${preset.secondary} 100%)`
                    }}
                  />
                  <span className="preset-name">{preset.name}</span>
                </button>
              ))}
            </div>
          </div>

          {/* Custom Colors */}
          <div className="color-pickers">
            <div className="color-field">
              <label>Primary Color</label>
              <div className="color-input-group">
                <input
                  type="color"
                  value={config.primaryColor}
                  onChange={(e) => updateConfig('primaryColor', e.target.value)}
                  className="color-picker"
                />
                <input
                  type="text"
                  value={config.primaryColor}
                  onChange={(e) => updateConfig('primaryColor', e.target.value)}
                  className="color-text"
                  placeholder="#2563eb"
                />
              </div>
              <span className="color-hint">Used for buttons, links, and accents</span>
            </div>

            <div className="color-field">
              <label>Secondary Color</label>
              <div className="color-input-group">
                <input
                  type="color"
                  value={config.secondaryColor}
                  onChange={(e) => updateConfig('secondaryColor', e.target.value)}
                  className="color-picker"
                />
                <input
                  type="text"
                  value={config.secondaryColor}
                  onChange={(e) => updateConfig('secondaryColor', e.target.value)}
                  className="color-text"
                  placeholder="#1e40af"
                />
              </div>
              <span className="color-hint">Used for backgrounds and highlights</span>
            </div>
          </div>

          {/* Font Selector */}
          <div className="font-selector">
            <label>Font Family</label>
            <div className="font-options">
              {FONT_OPTIONS.map((font) => (
                <button
                  key={font.value}
                  className={`font-option ${config.fontFamily === font.value ? 'active' : ''}`}
                  onClick={() => updateConfig('fontFamily', font.value)}
                  style={{ fontFamily: font.family }}
                >
                  <span className="font-sample">Aa</span>
                  <span className="font-name">{font.label}</span>
                </button>
              ))}
            </div>
          </div>

          {/* Preview */}
          <div className="color-preview">
            <label>Preview</label>
            <div
              className="preview-box"
              style={{
                background: `linear-gradient(135deg, ${config.primaryColor} 0%, ${config.secondaryColor} 100%)`,
                fontFamily: FONT_OPTIONS.find(f => f.value === config.fontFamily)?.family || 'Inter'
              }}
            >
              <span className="preview-text">Your Brand Colors</span>
              <button className="preview-btn">Sample Button</button>
            </div>
          </div>
        </div>
      )}

      {/* Social Links Tab */}
      {activeTab === 'social' && (
        <div className="customizer-section">
          <div className="social-links-section">
            <p className="section-description">
              Add your social media profiles to help clients connect with you.
            </p>
            {SOCIAL_PLATFORMS.map((platform) => (
              <div key={platform.key} className="social-field">
                <label>
                  <span className="social-icon">{platform.icon}</span>
                  {platform.label}
                </label>
                <input
                  type="url"
                  value={socialLinks[platform.key]}
                  onChange={(e) => updateSocialLink(platform.key, e.target.value)}
                  placeholder={platform.placeholder}
                  className="text-input"
                />
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Footer Tab */}
      {activeTab === 'footer' && (
        <div className="customizer-section">
          <div className="footer-fields">
            <div className="field-group">
              <label>Company Name</label>
              <input
                type="text"
                value={footerContent.companyName}
                onChange={(e) => updateFooterContent('companyName', e.target.value)}
                placeholder="Your Company Name"
                className="text-input"
              />
            </div>

            <div className="field-group">
              <label>NMLS Number</label>
              <input
                type="text"
                value={footerContent.nmls}
                onChange={(e) => updateFooterContent('nmls', e.target.value)}
                placeholder="123456"
                className="text-input"
              />
            </div>

            <div className="field-group">
              <label>Disclaimer Text</label>
              <textarea
                value={footerContent.disclaimer}
                onChange={(e) => updateFooterContent('disclaimer', e.target.value)}
                placeholder="Add your legal disclaimer text here..."
                className="textarea-input"
                rows={4}
              />
            </div>

            <div className="toggle-option">
              <label className="toggle-label-wrapper">
                <input
                  type="checkbox"
                  checked={footerContent.showEqualHousing}
                  onChange={(e) => updateFooterContent('showEqualHousing', e.target.checked)}
                />
                <span className="toggle-label">Show Equal Housing Opportunity logo</span>
              </label>
            </div>
          </div>
        </div>
      )}

      {/* Pages Tab */}
      {activeTab === 'pages' && (
        <div className="customizer-section">
          <div className="pages-section">
            <div className="pages-header">
              <p className="section-description">
                Create custom pages for your microsite (About, Services, etc.)
              </p>
              <button className="add-page-btn" onClick={() => openPageModal()}>
                + Add Page
              </button>
            </div>

            {pages.length > 0 ? (
              <div className="pages-list">
                {pages.map((page) => (
                  <div key={page.id} className="page-item">
                    <div className="page-info">
                      <span className="page-title">{page.title}</span>
                      <span className="page-slug">/{page.slug}</span>
                      {!page.is_published && (
                        <span className="page-draft">Draft</span>
                      )}
                    </div>
                    <div className="page-actions">
                      <button
                        className="edit-btn"
                        onClick={() => openPageModal(page)}
                      >
                        Edit
                      </button>
                      <button
                        className="delete-btn"
                        onClick={() => deletePage(page.id)}
                      >
                        Delete
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="no-pages">
                <p>No custom pages yet. Click "Add Page" to create one.</p>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Page Modal */}
      {showPageModal && (
        <div className="page-modal-overlay" onClick={closePageModal}>
          <div className="page-modal" onClick={(e) => e.stopPropagation()}>
            <div className="page-modal-header">
              <h4>{editingPage ? 'Edit Page' : 'Add New Page'}</h4>
              <button className="modal-close" onClick={closePageModal}>x</button>
            </div>
            <div className="page-modal-body">
              <div className="field-group">
                <label>Page Title</label>
                <input
                  type="text"
                  value={pageForm.title}
                  onChange={(e) => handlePageFormChange('title', e.target.value)}
                  placeholder="About Me"
                  className="text-input"
                />
              </div>
              <div className="field-group">
                <label>URL Slug</label>
                <div className="slug-input-wrapper">
                  <span className="slug-prefix">/</span>
                  <input
                    type="text"
                    value={pageForm.slug}
                    onChange={(e) => handlePageFormChange('slug', e.target.value)}
                    placeholder="about-me"
                    className="text-input slug-input"
                  />
                </div>
              </div>
              <div className="field-group">
                <label>Content</label>
                <textarea
                  value={pageForm.content}
                  onChange={(e) => handlePageFormChange('content', e.target.value)}
                  placeholder="Write your page content here..."
                  className="textarea-input"
                  rows={8}
                />
              </div>
              <div className="toggle-option">
                <label className="toggle-label-wrapper">
                  <input
                    type="checkbox"
                    checked={pageForm.isPublished}
                    onChange={(e) => handlePageFormChange('isPublished', e.target.checked)}
                  />
                  <span className="toggle-label">Publish this page</span>
                </label>
              </div>
            </div>
            <div className="page-modal-footer">
              <button className="cancel-btn" onClick={closePageModal}>Cancel</button>
              <button className="save-btn" onClick={savePage}>
                {editingPage ? 'Update Page' : 'Create Page'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Actions */}
      <div className="customizer-actions">
        <button
          className="reset-btn"
          onClick={handleReset}
          disabled={saving}
        >
          Reset Theme
        </button>
        <button
          className="save-btn"
          onClick={handleSaveAll}
          disabled={saving}
        >
          {saving ? 'Saving...' : 'Save All Changes'}
        </button>
      </div>
    </div>
  );
};

export default MicrositeThemeCustomizer;
