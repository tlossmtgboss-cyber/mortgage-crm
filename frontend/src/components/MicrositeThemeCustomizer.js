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
import { sanitizeHTML } from '../utils/sanitize';
import './MicrositeThemeCustomizer.css';
import api from '../services/api';

// Preset color palettes
const COLOR_PRESETS = [
  { name: 'Classic Blue', primary: '#2563eb', secondary: '#1e40af' },
  { name: 'Bold Red', primary: '#dc2626', secondary: '#1e3a5f' },
  { name: 'Modern Purple', primary: '#B8924A', secondary: '#ec4899' },
  { name: 'Forest Green', primary: '#2D7A52', secondary: '#1F5A3A' },
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
  const [pageForm, setPageForm] = useState({
    title: '',
    slug: '',
    content: '',
    isPublished: true,
    metaTitle: '',
    metaDescription: '',
  });
  const [seoScore, setSeoScore] = useState(null);
  const contentEditableRef = useRef(null);

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

      // Fetch microsite profile (use /my-microsite endpoint)
      const { data } = await api.get('/api/v1/microsites/my-microsite');
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

      // Pages are managed separately - skip for now if endpoint doesn't exist
      try {
        const { data: pagesData } = await api.get('/api/v1/microsites/my-microsite/pages');
        setPages(pagesData.pages || pagesData || []);
      } catch (pageErr) {
        console.log('Pages endpoint not available yet');
        setPages([]);
      }
    } catch (err) {
      console.error('Error fetching profile:', err);
      showMessage('error', 'Unable to load microsite settings. Please refresh the page.');
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
      formData.append('asset_type', 'logo');

      const { data } = await api.post('/api/v1/microsites/my-microsite/upload-image', formData);
      setLogoUrl(data.url);
      showMessage('success', 'Logo uploaded successfully');
      setHasChanges(true);
    } catch (err) {
      console.error('Logo upload error:', err);
      showMessage('error', err.response?.data?.detail || err.message || 'Failed to upload logo');
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
      formData.append('asset_type', 'headshot');

      const { data } = await api.post('/api/v1/microsites/my-microsite/upload-image', formData);
      setHeadshotUrl(data.url);
      showMessage('success', 'Photo uploaded successfully');
      setHasChanges(true);
    } catch (err) {
      console.error('Headshot upload error:', err);
      showMessage('error', err.response?.data?.detail || err.message || 'Failed to upload photo');
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
      await api.put('/api/v1/microsites/my-microsite', {
        content_json,
        branding_json,
      });

      setHasChanges(false);
      showMessage('success', 'All changes saved successfully');
      if (onSave) {
        onSave(config);
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
      const bodyContent = typeof page.content === 'object' ? (page.content.body || '') : (page.content || '');
      setPageForm({
        title: page.title,
        slug: page.slug,
        content: bodyContent,
        isPublished: page.is_enabled !== false,
        metaTitle: page.meta_title || page.title || '',
        metaDescription: page.meta_description || '',
      });
    } else {
      setEditingPage(null);
      setPageForm({
        title: '',
        slug: '',
        content: '',
        isPublished: true,
        metaTitle: '',
        metaDescription: '',
      });
    }
    setSeoScore(null);
    setShowPageModal(true);
  };

  const closePageModal = () => {
    setShowPageModal(false);
    setEditingPage(null);
    setPageForm({
      title: '',
      slug: '',
      content: '',
      isPublished: true,
      metaTitle: '',
      metaDescription: '',
    });
    setSeoScore(null);
  };

  // Rich text formatting commands
  const execCommand = (command, value = null) => {
    document.execCommand(command, false, value);
    if (contentEditableRef.current) {
      handlePageFormChange('content', contentEditableRef.current.innerHTML);
    }
  };

  const insertLink = () => {
    const url = prompt('Enter URL:', 'https://');
    if (url) {
      execCommand('createLink', url);
    }
  };

  // SEO Analysis
  const analyzeSEO = () => {
    const title = pageForm.metaTitle || pageForm.title;
    const description = pageForm.metaDescription;
    const content = pageForm.content;

    let score = 0;
    const issues = [];
    const suggestions = [];

    // Title analysis (20 points max)
    if (title) {
      if (title.length >= 30 && title.length <= 60) {
        score += 20;
      } else if (title.length > 0) {
        score += 10;
        if (title.length < 30) issues.push('Title is too short (aim for 30-60 characters)');
        if (title.length > 60) issues.push('Title is too long (keep under 60 characters)');
      }
    } else {
      issues.push('Missing page title');
    }

    // Meta description (20 points max)
    if (description) {
      if (description.length >= 120 && description.length <= 160) {
        score += 20;
      } else if (description.length > 0) {
        score += 10;
        if (description.length < 120) issues.push('Meta description is too short (aim for 120-160 characters)');
        if (description.length > 160) issues.push('Meta description is too long (keep under 160 characters)');
      }
    } else {
      issues.push('Missing meta description - important for search results');
    }

    // Content analysis (30 points max)
    const plainContent = content.replace(/<[^>]*>/g, '');
    const wordCount = plainContent.split(/\s+/).filter(w => w.length > 0).length;

    if (wordCount >= 300) {
      score += 30;
    } else if (wordCount >= 150) {
      score += 20;
      suggestions.push('Add more content (300+ words recommended for SEO)');
    } else if (wordCount > 0) {
      score += 10;
      issues.push('Content is too short - aim for at least 300 words');
    } else {
      issues.push('Page has no content');
    }

    // Headings check (10 points)
    if (content.includes('<h') || content.includes('<strong>')) {
      score += 10;
    } else {
      suggestions.push('Add headings or bold text to structure content');
    }

    // Links check (10 points)
    if (content.includes('<a ')) {
      score += 10;
    } else {
      suggestions.push('Add internal or external links to improve engagement');
    }

    // AI Search Optimization (10 points)
    const hasQuestions = /\?/.test(plainContent);
    const hasLists = /<li>|<ul>|<ol>/.test(content) || /\n-\s/.test(plainContent);
    const hasStructuredContent = hasQuestions || hasLists;

    if (hasStructuredContent) {
      score += 10;
    } else {
      suggestions.push('AI Search: Add questions, lists, or structured content for better AI indexing');
    }

    setSeoScore({
      score: Math.min(score, 100),
      grade: score >= 80 ? 'A' : score >= 60 ? 'B' : score >= 40 ? 'C' : 'D',
      issues,
      suggestions,
      wordCount,
      titleLength: title?.length || 0,
      descriptionLength: description?.length || 0,
    });
  };

  const generateSlug = (title) => {
    return title.toLowerCase()
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/(^-|-$)/g, '');
  };

  // Allowed tags for the rich text page editor
  const PAGE_EDITOR_ALLOWED_TAGS = ['p', 'br', 'strong', 'em', 'b', 'i', 'u', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'ul', 'ol', 'li', 'a', 'span', 'div'];

  const handlePageFormChange = (key, value) => {
    setPageForm(prev => {
      const updated = { ...prev };
      if (key === 'content') {
        // Sanitize HTML from contentEditable before storing in state.
        // Prevents stored XSS: raw innerHTML from contentEditable can contain
        // script tags or event handlers injected via paste or browser devtools.
        // Content flows to savePage() -> API -> LOMicrosite (public page).
        updated.content = sanitizeHTML(value, { allowedTags: PAGE_EDITOR_ALLOWED_TAGS });
      } else {
        updated[key] = value;
      }
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
      // Defense-in-depth: sanitize content before sending to API even though
      // handlePageFormChange already sanitizes on input. Prevents stored XSS
      // if any code path bypasses the input handler.
      const sanitizedContent = sanitizeHTML(pageForm.content || '', {
        allowedTags: PAGE_EDITOR_ALLOWED_TAGS,
      });

      const contentData = {
        body: sanitizedContent,
        heading: pageForm.title,
      };

      const payload = editingPage ? {
        // Update payload
        title: pageForm.title,
        content: contentData,
        meta_title: pageForm.metaTitle || pageForm.title,
        meta_description: pageForm.metaDescription || '',
        is_enabled: pageForm.isPublished,
      } : {
        // Create payload - requires page_type
        page_type: 'custom',
        slug: pageForm.slug || generateSlug(pageForm.title),
        title: pageForm.title,
        content: contentData,
        meta_title: pageForm.metaTitle || pageForm.title,
        meta_description: pageForm.metaDescription || '',
        is_enabled: pageForm.isPublished,
        show_in_nav: true,
      };

      if (editingPage) {
        await api.put(`/api/v1/microsites/my-microsite/pages/${editingPage.slug}`, payload);
      } else {
        await api.post('/api/v1/microsites/my-microsite/pages', payload);
      }

      showMessage('success', editingPage ? 'Page updated' : 'Page created successfully!');
      closePageModal();
      fetchProfileData(); // Refresh pages
    } catch (err) {
      console.error('Error saving page:', err);
      showMessage('error', err.response?.data?.detail || err.message || 'Failed to save page');
    }
  };

  const deletePage = async (page) => {
    if (!window.confirm(`Are you sure you want to delete "${page.title}"?`)) return;

    try {
      await api.delete(`/api/v1/microsites/my-microsite/pages/${page.slug}`);
      showMessage('success', 'Page deleted');
      fetchProfileData();
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
                  <div key={page.id || page.slug} className="page-item">
                    <div className="page-info">
                      <span className="page-title">{page.title}</span>
                      <span className="page-slug">/{page.slug}</span>
                      {page.is_enabled === false && (
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
                        onClick={() => deletePage(page)}
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
          <div className="page-modal page-modal-large" onClick={(e) => e.stopPropagation()}>
            <div className="page-modal-header">
              <h4>{editingPage ? 'Edit Page' : 'Add New Page'}</h4>
              <button className="modal-close" onClick={closePageModal}>×</button>
            </div>
            <div className="page-modal-body">
              {/* Basic Info */}
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
                    disabled={!!editingPage}
                  />
                </div>
              </div>

              {/* Rich Text Editor */}
              <div className="field-group">
                <label>Content</label>
                <div className="rich-text-editor">
                  {/* Formatting Toolbar */}
                  <div className="editor-toolbar">
                    <button
                      type="button"
                      className="toolbar-btn"
                      onClick={() => execCommand('bold')}
                      title="Bold (Ctrl+B)"
                    >
                      <strong>B</strong>
                    </button>
                    <button
                      type="button"
                      className="toolbar-btn"
                      onClick={() => execCommand('italic')}
                      title="Italic (Ctrl+I)"
                    >
                      <em>I</em>
                    </button>
                    <button
                      type="button"
                      className="toolbar-btn"
                      onClick={() => execCommand('underline')}
                      title="Underline (Ctrl+U)"
                    >
                      <u>U</u>
                    </button>
                    <span className="toolbar-divider" />
                    <button
                      type="button"
                      className="toolbar-btn"
                      onClick={() => execCommand('formatBlock', '<h2>')}
                      title="Heading"
                    >
                      H2
                    </button>
                    <button
                      type="button"
                      className="toolbar-btn"
                      onClick={() => execCommand('formatBlock', '<h3>')}
                      title="Subheading"
                    >
                      H3
                    </button>
                    <button
                      type="button"
                      className="toolbar-btn"
                      onClick={() => execCommand('formatBlock', '<p>')}
                      title="Paragraph"
                    >
                      P
                    </button>
                    <span className="toolbar-divider" />
                    <button
                      type="button"
                      className="toolbar-btn"
                      onClick={() => execCommand('insertUnorderedList')}
                      title="Bullet List"
                    >
                      • List
                    </button>
                    <button
                      type="button"
                      className="toolbar-btn"
                      onClick={() => execCommand('insertOrderedList')}
                      title="Numbered List"
                    >
                      1. List
                    </button>
                    <span className="toolbar-divider" />
                    <button
                      type="button"
                      className="toolbar-btn"
                      onClick={insertLink}
                      title="Insert Link"
                    >
                      🔗 Link
                    </button>
                    <button
                      type="button"
                      className="toolbar-btn"
                      onClick={() => execCommand('removeFormat')}
                      title="Clear Formatting"
                    >
                      ✕ Clear
                    </button>
                  </div>

                  {/* Editable Content Area */}
                  <div
                    ref={contentEditableRef}
                    className="editor-content"
                    contentEditable
                    dangerouslySetInnerHTML={{ __html: sanitizeHTML(pageForm.content, { allowedTags: ['p', 'br', 'strong', 'em', 'b', 'i', 'u', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'ul', 'ol', 'li', 'a', 'span', 'div'] }) }}
                    onInput={(e) => handlePageFormChange('content', e.currentTarget.innerHTML)}
                    onBlur={(e) => handlePageFormChange('content', e.currentTarget.innerHTML)}
                    style={{ minHeight: '200px' }}
                  />
                </div>
              </div>

              {/* SEO Section */}
              <div className="seo-section">
                <div className="seo-header">
                  <h5>SEO Settings</h5>
                  <button
                    type="button"
                    className="analyze-seo-btn"
                    onClick={analyzeSEO}
                  >
                    🔍 Analyze SEO
                  </button>
                </div>

                {/* SEO Score Display */}
                {seoScore && (
                  <div className={`seo-score-card grade-${seoScore.grade.toLowerCase()}`}>
                    <div className="score-header">
                      <span className="score-value">{seoScore.score}/100</span>
                      <span className="score-grade">Grade: {seoScore.grade}</span>
                    </div>
                    <div className="score-stats">
                      <span>Words: {seoScore.wordCount}</span>
                      <span>Title: {seoScore.titleLength} chars</span>
                      <span>Description: {seoScore.descriptionLength} chars</span>
                    </div>
                    {seoScore.issues.length > 0 && (
                      <div className="seo-issues">
                        <strong>Issues:</strong>
                        <ul>
                          {seoScore.issues.map((issue, i) => (
                            <li key={i} className="issue-item">❌ {issue}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                    {seoScore.suggestions.length > 0 && (
                      <div className="seo-suggestions">
                        <strong>Suggestions:</strong>
                        <ul>
                          {seoScore.suggestions.map((suggestion, i) => (
                            <li key={i} className="suggestion-item">💡 {suggestion}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                )}

                <div className="field-group">
                  <label>
                    SEO Title
                    <span className="char-count">{(pageForm.metaTitle || pageForm.title || '').length}/60</span>
                  </label>
                  <input
                    type="text"
                    value={pageForm.metaTitle}
                    onChange={(e) => handlePageFormChange('metaTitle', e.target.value)}
                    placeholder={pageForm.title || 'Page title for search engines'}
                    className="text-input"
                    maxLength={70}
                  />
                </div>
                <div className="field-group">
                  <label>
                    Meta Description
                    <span className="char-count">{(pageForm.metaDescription || '').length}/160</span>
                  </label>
                  <textarea
                    value={pageForm.metaDescription}
                    onChange={(e) => handlePageFormChange('metaDescription', e.target.value)}
                    placeholder="Brief description for search results (120-160 characters ideal)"
                    className="textarea-input"
                    rows={3}
                    maxLength={200}
                  />
                </div>
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
