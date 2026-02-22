/**
 * MicrositeWizard - Step-by-Step Theme Builder
 *
 * Guides users through creating their perfect microsite:
 * 1. Theme Selection - Choose from available themes
 * 2. Brand Colors - Customize colors and fonts
 * 3. Profile Setup - Photo, headline, bio
 * 4. Credentials - Experience, certifications, stats
 * 5. Testimonials - Add client reviews
 * 6. Contact Info - Social links, booking, contact preferences
 * 7. Preview & Publish - Review and go live
 */

import React, { useState, useEffect, useCallback } from 'react';
import './MicrositeWizard.css';
import { toast } from '../../utils/toast';

// API base URL
const API_BASE = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
  ? (process.env.REACT_APP_API_URL || 'http://localhost:8000')
  : 'https://api.perenniaai.com';

// Step definitions
const STEPS = [
  { id: 1, name: 'Theme', icon: '🎨', title: 'Choose Your Theme' },
  { id: 2, name: 'Brand', icon: '🖌️', title: 'Brand Colors & Fonts' },
  { id: 3, name: 'Profile', icon: '👤', title: 'Your Profile' },
  { id: 4, name: 'Credentials', icon: '🏆', title: 'Credentials & Stats' },
  { id: 5, name: 'Testimonials', icon: '⭐', title: 'Client Testimonials' },
  { id: 6, name: 'Contact', icon: '📞', title: 'Contact & Social' },
  { id: 7, name: 'Publish', icon: '🚀', title: 'Preview & Publish' },
];

// Available themes
const THEMES = [
  {
    id: 'bold-impact',
    name: 'Bold Impact',
    description: 'Stand out with bold colors and strong calls-to-action. Perfect for high-volume producers.',
    category: 'bold',
    preview: '/images/themes/bold-impact-preview.jpg',
    features: ['Hero Image', 'Rate Calculator', 'Testimonials', 'Contact Form'],
    recommended: true,
  },
  {
    id: 'professional-clean',
    name: 'Professional Clean',
    description: 'A clean, trustworthy design that conveys expertise and reliability.',
    category: 'professional',
    preview: '/images/themes/professional-clean-preview.jpg',
    features: ['Credentials Display', 'About Section', 'Contact Form'],
  },
  {
    id: 'modern-gradient',
    name: 'Modern Gradient',
    description: 'Contemporary design with smooth gradients and modern aesthetics.',
    category: 'modern',
    preview: '/images/themes/modern-gradient-preview.jpg',
    features: ['Gradient Hero', 'Testimonials', 'Social Links'],
  },
  {
    id: 'minimal-focus',
    name: 'Minimal Focus',
    description: 'Simple and focused design that puts your message front and center.',
    category: 'minimal',
    preview: '/images/themes/minimal-focus-preview.jpg',
    features: ['Clean Layout', 'Fast Loading', 'Mobile First'],
  },
];

// Color presets
const COLOR_PRESETS = [
  { name: 'Classic Blue', primary: '#2563eb', secondary: '#1e40af' },
  { name: 'Bold Red', primary: '#dc2626', secondary: '#1e3a5f' },
  { name: 'Forest Green', primary: '#059669', secondary: '#047857' },
  { name: 'Royal Purple', primary: '#7c3aed', secondary: '#5b21b6' },
  { name: 'Warm Orange', primary: '#ea580c', secondary: '#c2410c' },
  { name: 'Elegant Gold', primary: '#ca8a04', secondary: '#854d0e' },
  { name: 'Ocean Teal', primary: '#0891b2', secondary: '#0e7490' },
  { name: 'Slate Gray', primary: '#475569', secondary: '#334155' },
];

// Font options
const FONT_OPTIONS = [
  { value: 'inter', label: 'Inter', family: "'Inter', sans-serif" },
  { value: 'poppins', label: 'Poppins', family: "'Poppins', sans-serif" },
  { value: 'roboto', label: 'Roboto', family: "'Roboto', sans-serif" },
  { value: 'montserrat', label: 'Montserrat', family: "'Montserrat', sans-serif" },
  { value: 'open-sans', label: 'Open Sans', family: "'Open Sans', sans-serif" },
  { value: 'playfair', label: 'Playfair Display', family: "'Playfair Display', serif" },
];

const MicrositeWizard = () => {
  const [currentStep, setCurrentStep] = useState(1);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  // Wizard data state
  const [wizardData, setWizardData] = useState({
    // Step 1: Theme
    selectedTheme: 'bold-impact',

    // Step 2: Brand
    primaryColor: '#2563eb',
    secondaryColor: '#1e40af',
    fontFamily: 'inter',

    // Step 3: Profile
    headline: '',
    tagline: '',
    bioExtended: '',
    heroImageUrl: '',
    photoFile: null,

    // Step 4: Credentials
    yearsExperience: '',
    totalLoansFunded: '',
    totalVolumeFunded: '',
    specialties: [],
    certifications: [],

    // Step 5: Testimonials
    testimonials: [],

    // Step 6: Contact
    calendlyUrl: '',
    showPhone: true,
    showEmail: true,
    contactFormEnabled: true,
    socialLinks: {
      linkedin: '',
      facebook: '',
      instagram: '',
      twitter: '',
      youtube: '',
    },
    ctaText: 'Get Started Today',
    ctaSecondaryText: 'Check Your Rate',

    // Meta
    metaTitle: '',
    metaDescription: '',
  });

  // Load existing microsite data
  useEffect(() => {
    loadExistingData();
  }, []);

  const loadExistingData = async () => {
    try {
      const token = localStorage.getItem('token');
      if (!token) {
        setLoading(false);
        return;
      }

      const response = await fetch(`${API_BASE}/api/v1/microsites/my-microsite`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });

      if (response.ok) {
        const data = await response.json();
        // Map API data to wizard state
        setWizardData(prev => ({
          ...prev,
          selectedTheme: data.theme?.slug || prev.selectedTheme,
          primaryColor: data.themeConfig?.primaryColor || prev.primaryColor,
          secondaryColor: data.themeConfig?.secondaryColor || prev.secondaryColor,
          fontFamily: data.themeConfig?.fontFamily || prev.fontFamily,
          headline: data.profile?.headline || prev.headline,
          tagline: data.profile?.tagline || prev.tagline,
          bioExtended: data.profile?.bioExtended || prev.bioExtended,
          heroImageUrl: data.profile?.heroImageUrl || prev.heroImageUrl,
          yearsExperience: data.profile?.yearsExperience || prev.yearsExperience,
          totalLoansFunded: data.profile?.totalLoansFunded || prev.totalLoansFunded,
          totalVolumeFunded: data.profile?.totalVolumeFunded || prev.totalVolumeFunded,
          specialties: data.profile?.specialties || prev.specialties,
          certifications: data.profile?.certifications || prev.certifications,
          testimonials: data.profile?.testimonials || prev.testimonials,
          calendlyUrl: data.profile?.calendlyUrl || prev.calendlyUrl,
          showPhone: data.profile?.showPhone ?? prev.showPhone,
          showEmail: data.profile?.showEmail ?? prev.showEmail,
          contactFormEnabled: data.profile?.contactFormEnabled ?? prev.contactFormEnabled,
          socialLinks: data.profile?.socialLinks || prev.socialLinks,
          ctaText: data.profile?.ctaText || prev.ctaText,
          ctaSecondaryText: data.profile?.ctaSecondaryText || prev.ctaSecondaryText,
          metaTitle: data.metaTitle || prev.metaTitle,
          metaDescription: data.metaDescription || prev.metaDescription,
        }));
      }
    } catch (err) {
      console.error('Error loading microsite data:', err);
    } finally {
      setLoading(false);
    }
  };

  // Update wizard data
  const updateData = useCallback((updates) => {
    setWizardData(prev => ({ ...prev, ...updates }));
  }, []);

  // Save current step data
  const saveStepData = async () => {
    setSaving(true);
    setError(null);

    try {
      const token = localStorage.getItem('token');

      // Build the payload based on current data
      const payload = {
        theme_slug: wizardData.selectedTheme,
        theme_config: {
          primaryColor: wizardData.primaryColor,
          secondaryColor: wizardData.secondaryColor,
          fontFamily: wizardData.fontFamily,
        },
        profile: {
          headline: wizardData.headline,
          tagline: wizardData.tagline,
          bio_extended: wizardData.bioExtended,
          hero_image_url: wizardData.heroImageUrl,
          years_experience: wizardData.yearsExperience ? parseInt(wizardData.yearsExperience) : null,
          total_loans_funded: wizardData.totalLoansFunded ? parseInt(wizardData.totalLoansFunded) : null,
          total_volume_funded: wizardData.totalVolumeFunded ? parseFloat(wizardData.totalVolumeFunded) : null,
          specialties: wizardData.specialties,
          certifications: wizardData.certifications,
          testimonials: wizardData.testimonials,
          calendly_url: wizardData.calendlyUrl,
          show_phone: wizardData.showPhone,
          show_email: wizardData.showEmail,
          contact_form_enabled: wizardData.contactFormEnabled,
          social_links: wizardData.socialLinks,
          cta_text: wizardData.ctaText,
          cta_secondary_text: wizardData.ctaSecondaryText,
        },
        meta_title: wizardData.metaTitle,
        meta_description: wizardData.metaDescription,
      };

      const response = await fetch(`${API_BASE}/api/v1/microsites/my-microsite`, {
        method: 'PUT',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(payload),
      });

      if (!response.ok) {
        throw new Error('Failed to save');
      }

      return true;
    } catch (err) {
      console.error('Error saving:', err);
      setError('Failed to save changes. Please try again.');
      return false;
    } finally {
      setSaving(false);
    }
  };

  // Navigation
  const goToStep = async (step) => {
    if (step > currentStep) {
      // Save before moving forward
      const saved = await saveStepData();
      if (!saved) return;
    }
    setCurrentStep(step);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const nextStep = () => {
    if (currentStep < STEPS.length) {
      goToStep(currentStep + 1);
    }
  };

  const prevStep = () => {
    if (currentStep > 1) {
      setCurrentStep(currentStep - 1);
      window.scrollTo({ top: 0, behavior: 'smooth' });
    }
  };

  // Publish microsite
  const publishMicrosite = async () => {
    setSaving(true);
    setError(null);

    try {
      const token = localStorage.getItem('token');

      // First save all data
      await saveStepData();

      // Then publish
      const response = await fetch(`${API_BASE}/api/v1/microsites/my-microsite/publish`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` },
      });

      if (response.ok) {
        toast.success('Your microsite is now live!');
      } else {
        throw new Error('Failed to publish');
      }
    } catch (err) {
      console.error('Error publishing:', err);
      setError('Failed to publish. Please try again.');
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="wizard-loading">
        <div className="wizard-spinner" />
        <p>Loading your microsite...</p>
      </div>
    );
  }

  return (
    <div className="microsite-wizard">
      {/* Header */}
      <div className="wizard-header">
        <h1>Build Your Professional Microsite</h1>
        <p>Complete each step to create your personalized loan officer website</p>
      </div>

      {/* Progress Steps */}
      <div className="wizard-progress">
        {STEPS.map((step) => (
          <div
            key={step.id}
            className={`progress-step ${currentStep === step.id ? 'active' : ''} ${currentStep > step.id ? 'completed' : ''}`}
            onClick={() => goToStep(step.id)}
          >
            <div className="step-indicator">
              {currentStep > step.id ? '✓' : step.icon}
            </div>
            <span className="step-name">{step.name}</span>
          </div>
        ))}
      </div>

      {/* Step Content */}
      <div className="wizard-content">
        <div className="step-header">
          <span className="step-number">Step {currentStep} of {STEPS.length}</span>
          <h2>{STEPS[currentStep - 1].title}</h2>
        </div>

        {error && (
          <div className="wizard-error">
            {error}
          </div>
        )}

        {/* Step 1: Theme Selection */}
        {currentStep === 1 && (
          <StepThemeSelection
            selectedTheme={wizardData.selectedTheme}
            onSelect={(theme) => updateData({ selectedTheme: theme })}
          />
        )}

        {/* Step 2: Brand Colors */}
        {currentStep === 2 && (
          <StepBrandColors
            data={wizardData}
            onUpdate={updateData}
          />
        )}

        {/* Step 3: Profile */}
        {currentStep === 3 && (
          <StepProfile
            data={wizardData}
            onUpdate={updateData}
          />
        )}

        {/* Step 4: Credentials */}
        {currentStep === 4 && (
          <StepCredentials
            data={wizardData}
            onUpdate={updateData}
          />
        )}

        {/* Step 5: Testimonials */}
        {currentStep === 5 && (
          <StepTestimonials
            testimonials={wizardData.testimonials}
            onUpdate={(testimonials) => updateData({ testimonials })}
          />
        )}

        {/* Step 6: Contact */}
        {currentStep === 6 && (
          <StepContact
            data={wizardData}
            onUpdate={updateData}
          />
        )}

        {/* Step 7: Preview & Publish */}
        {currentStep === 7 && (
          <StepPublish
            data={wizardData}
            onPublish={publishMicrosite}
            saving={saving}
          />
        )}
      </div>

      {/* Navigation Buttons */}
      <div className="wizard-navigation">
        <button
          className="nav-btn prev"
          onClick={prevStep}
          disabled={currentStep === 1 || saving}
        >
          ← Previous
        </button>

        <div className="nav-center">
          <button
            className="nav-btn save"
            onClick={saveStepData}
            disabled={saving}
          >
            {saving ? 'Saving...' : 'Save Progress'}
          </button>
        </div>

        {currentStep < STEPS.length ? (
          <button
            className="nav-btn next"
            onClick={nextStep}
            disabled={saving}
          >
            {saving ? 'Saving...' : 'Next →'}
          </button>
        ) : (
          <button
            className="nav-btn publish"
            onClick={publishMicrosite}
            disabled={saving}
          >
            {saving ? 'Publishing...' : 'Publish Site 🚀'}
          </button>
        )}
      </div>
    </div>
  );
};

// =============================================================================
// STEP COMPONENTS
// =============================================================================

// Step 1: Theme Selection
const StepThemeSelection = ({ selectedTheme, onSelect }) => (
  <div className="step-theme-selection">
    <p className="step-description">
      Choose a theme that matches your personal brand. You can customize colors and content in the next steps.
    </p>

    <div className="theme-grid">
      {THEMES.map((theme) => (
        <div
          key={theme.id}
          className={`theme-card ${selectedTheme === theme.id ? 'selected' : ''} ${theme.recommended ? 'recommended' : ''}`}
          onClick={() => onSelect(theme.id)}
        >
          {theme.recommended && <span className="recommended-badge">Recommended</span>}

          <div className="theme-preview">
            <div className="theme-placeholder" style={{ background: theme.id === 'bold-impact' ? '#dc2626' : theme.id === 'professional-clean' ? '#2563eb' : theme.id === 'modern-gradient' ? 'linear-gradient(135deg, #7c3aed, #ec4899)' : '#475569' }}>
              <span>{theme.name.charAt(0)}</span>
            </div>
          </div>

          <div className="theme-info">
            <h3>{theme.name}</h3>
            <p>{theme.description}</p>

            <div className="theme-features">
              {theme.features.map((feature, i) => (
                <span key={i} className="feature-tag">{feature}</span>
              ))}
            </div>
          </div>

          <div className="theme-select-indicator">
            {selectedTheme === theme.id ? '✓ Selected' : 'Select Theme'}
          </div>
        </div>
      ))}
    </div>
  </div>
);

// Step 2: Brand Colors & Fonts
const StepBrandColors = ({ data, onUpdate }) => (
  <div className="step-brand-colors">
    <p className="step-description">
      Customize your colors and fonts to match your brand identity.
    </p>

    {/* Color Presets */}
    <div className="form-section">
      <label className="section-label">Quick Color Presets</label>
      <div className="color-presets">
        {COLOR_PRESETS.map((preset, i) => (
          <button
            key={i}
            className={`preset-btn ${data.primaryColor === preset.primary ? 'active' : ''}`}
            onClick={() => onUpdate({ primaryColor: preset.primary, secondaryColor: preset.secondary })}
            title={preset.name}
          >
            <span
              className="preset-swatch"
              style={{ background: `linear-gradient(135deg, ${preset.primary}, ${preset.secondary})` }}
            />
            <span className="preset-name">{preset.name}</span>
          </button>
        ))}
      </div>
    </div>

    {/* Custom Colors */}
    <div className="form-section">
      <label className="section-label">Custom Colors</label>
      <div className="color-pickers">
        <div className="color-field">
          <label>Primary Color</label>
          <div className="color-input">
            <input
              type="color"
              value={data.primaryColor}
              onChange={(e) => onUpdate({ primaryColor: e.target.value })}
            />
            <input
              type="text"
              value={data.primaryColor}
              onChange={(e) => onUpdate({ primaryColor: e.target.value })}
              placeholder="#2563eb"
            />
          </div>
          <span className="color-hint">Buttons, links, accents</span>
        </div>

        <div className="color-field">
          <label>Secondary Color</label>
          <div className="color-input">
            <input
              type="color"
              value={data.secondaryColor}
              onChange={(e) => onUpdate({ secondaryColor: e.target.value })}
            />
            <input
              type="text"
              value={data.secondaryColor}
              onChange={(e) => onUpdate({ secondaryColor: e.target.value })}
              placeholder="#1e40af"
            />
          </div>
          <span className="color-hint">Backgrounds, highlights</span>
        </div>
      </div>
    </div>

    {/* Color Preview */}
    <div className="form-section">
      <label className="section-label">Preview</label>
      <div
        className="color-preview-box"
        style={{ background: `linear-gradient(135deg, ${data.primaryColor}, ${data.secondaryColor})` }}
      >
        <span className="preview-text">Your Brand Colors</span>
        <button className="preview-button" style={{ background: data.primaryColor }}>
          Sample Button
        </button>
      </div>
    </div>

    {/* Font Selection */}
    <div className="form-section">
      <label className="section-label">Font Family</label>
      <div className="font-options">
        {FONT_OPTIONS.map((font) => (
          <button
            key={font.value}
            className={`font-btn ${data.fontFamily === font.value ? 'active' : ''}`}
            onClick={() => onUpdate({ fontFamily: font.value })}
            style={{ fontFamily: font.family }}
          >
            <span className="font-sample">Aa</span>
            <span className="font-name">{font.label}</span>
          </button>
        ))}
      </div>
    </div>
  </div>
);

// Step 3: Profile Setup
const StepProfile = ({ data, onUpdate }) => {
  const [generatingBio, setGeneratingBio] = useState(false);

  const handlePhotoUpload = async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    // For now, create a preview URL
    // In production, this would upload to your storage
    const previewUrl = URL.createObjectURL(file);
    onUpdate({ heroImageUrl: previewUrl, photoFile: file });
  };

  const generateBioWithAI = async () => {
    setGeneratingBio(true);
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(`${API_BASE}/api/v1/ai/generate-bio`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          name: data.displayName || '',
          headline: data.headline || '',
          tagline: data.tagline || '',
          specialties: data.specialties || [],
          yearsExperience: data.yearsExperience || '',
          certifications: data.certifications || []
        })
      });

      if (response.ok) {
        const result = await response.json();
        if (result.bio) {
          onUpdate({ bioExtended: result.bio });
        }
      } else {
        console.error('Failed to generate bio');
      }
    } catch (error) {
      console.error('Error generating bio:', error);
    } finally {
      setGeneratingBio(false);
    }
  };

  return (
    <div className="step-profile">
      <p className="step-description">
        Set up your professional profile that visitors will see first.
      </p>

      {/* Photo Upload */}
      <div className="form-section">
        <label className="section-label">Profile Photo</label>
        <div className="photo-upload">
          <div className="photo-preview">
            {data.heroImageUrl ? (
              <img src={data.heroImageUrl} alt="Profile" />
            ) : (
              <div className="photo-placeholder">
                <span>👤</span>
                <p>Add Photo</p>
              </div>
            )}
          </div>
          <div className="photo-actions">
            <label className="upload-btn">
              Upload Photo
              <input
                type="file"
                accept="image/*"
                onChange={handlePhotoUpload}
                hidden
              />
            </label>
            <p className="photo-hint">Recommended: 400x400px, professional headshot</p>
          </div>
        </div>
      </div>

      {/* Headline */}
      <div className="form-section">
        <label className="section-label">Headline</label>
        <input
          type="text"
          className="form-input"
          value={data.headline}
          onChange={(e) => onUpdate({ headline: e.target.value })}
          placeholder="Your Trusted Mortgage Expert"
          maxLength={200}
        />
        <span className="input-hint">A compelling headline that grabs attention</span>
      </div>

      {/* Tagline */}
      <div className="form-section">
        <label className="section-label">Tagline</label>
        <input
          type="text"
          className="form-input"
          value={data.tagline}
          onChange={(e) => onUpdate({ tagline: e.target.value })}
          placeholder="Making homeownership dreams a reality since 2010"
          maxLength={300}
        />
        <span className="input-hint">A brief statement about what you do</span>
      </div>

      {/* Bio */}
      <div className="form-section">
        <div className="section-header-with-action">
          <label className="section-label">About You</label>
          <button
            type="button"
            className="ai-generate-btn"
            onClick={generateBioWithAI}
            disabled={generatingBio}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              padding: '6px 12px',
              fontSize: '13px',
              background: 'linear-gradient(135deg, #8b5cf6, #6366f1)',
              color: 'white',
              border: 'none',
              borderRadius: '6px',
              cursor: generatingBio ? 'wait' : 'pointer',
              opacity: generatingBio ? 0.7 : 1
            }}
          >
            {generatingBio ? (
              <>⏳ Generating...</>
            ) : (
              <>✨ Generate with AI</>
            )}
          </button>
        </div>
        <textarea
          className="form-textarea"
          value={data.bioExtended}
          onChange={(e) => onUpdate({ bioExtended: e.target.value })}
          placeholder="Tell your story. What makes you different? Why should clients choose you? Share your passion for helping families achieve homeownership..."
          rows={6}
        />
        <span className="input-hint">Share your story and what makes you unique</span>
      </div>
    </div>
  );
};

// Step 4: Credentials & Stats
const StepCredentials = ({ data, onUpdate }) => {
  const [newSpecialty, setNewSpecialty] = useState('');
  const [newCertification, setNewCertification] = useState('');

  const addSpecialty = () => {
    if (newSpecialty.trim()) {
      onUpdate({ specialties: [...data.specialties, newSpecialty.trim()] });
      setNewSpecialty('');
    }
  };

  const removeSpecialty = (index) => {
    onUpdate({ specialties: data.specialties.filter((_, i) => i !== index) });
  };

  const addCertification = () => {
    if (newCertification.trim()) {
      onUpdate({ certifications: [...data.certifications, newCertification.trim()] });
      setNewCertification('');
    }
  };

  const removeCertification = (index) => {
    onUpdate({ certifications: data.certifications.filter((_, i) => i !== index) });
  };

  return (
    <div className="step-credentials">
      <p className="step-description">
        Showcase your experience and build trust with potential clients.
      </p>

      {/* Stats */}
      <div className="form-section">
        <label className="section-label">Your Numbers</label>
        <div className="stats-grid">
          <div className="stat-field">
            <label>Years of Experience</label>
            <input
              type="number"
              className="form-input"
              value={data.yearsExperience}
              onChange={(e) => onUpdate({ yearsExperience: e.target.value })}
              placeholder="15"
              min="0"
            />
          </div>
          <div className="stat-field">
            <label>Loans Funded</label>
            <input
              type="number"
              className="form-input"
              value={data.totalLoansFunded}
              onChange={(e) => onUpdate({ totalLoansFunded: e.target.value })}
              placeholder="500"
              min="0"
            />
          </div>
          <div className="stat-field">
            <label>Volume Funded ($)</label>
            <input
              type="number"
              className="form-input"
              value={data.totalVolumeFunded}
              onChange={(e) => onUpdate({ totalVolumeFunded: e.target.value })}
              placeholder="150000000"
              min="0"
            />
            <span className="input-hint">Total dollar volume</span>
          </div>
        </div>
      </div>

      {/* Specialties */}
      <div className="form-section">
        <label className="section-label">Specialties</label>
        <div className="tag-input">
          <input
            type="text"
            className="form-input"
            value={newSpecialty}
            onChange={(e) => setNewSpecialty(e.target.value)}
            onKeyPress={(e) => e.key === 'Enter' && (e.preventDefault(), addSpecialty())}
            placeholder="e.g., First-Time Buyers, VA Loans, Jumbo..."
          />
          <button className="add-btn" onClick={addSpecialty}>Add</button>
        </div>
        <div className="tags-list">
          {data.specialties.map((item, i) => (
            <span key={i} className="tag">
              {item}
              <button onClick={() => removeSpecialty(i)}>×</button>
            </span>
          ))}
        </div>
      </div>

      {/* Certifications */}
      <div className="form-section">
        <label className="section-label">Certifications & Licenses</label>
        <div className="tag-input">
          <input
            type="text"
            className="form-input"
            value={newCertification}
            onChange={(e) => setNewCertification(e.target.value)}
            onKeyPress={(e) => e.key === 'Enter' && (e.preventDefault(), addCertification())}
            placeholder="e.g., CMPS, FHA Direct Endorsed..."
          />
          <button className="add-btn" onClick={addCertification}>Add</button>
        </div>
        <div className="tags-list">
          {data.certifications.map((item, i) => (
            <span key={i} className="tag certification">
              {item}
              <button onClick={() => removeCertification(i)}>×</button>
            </span>
          ))}
        </div>
      </div>
    </div>
  );
};

// Step 5: Testimonials
const StepTestimonials = ({ testimonials, onUpdate }) => {
  const [editingIndex, setEditingIndex] = useState(null);
  const [testimonialForm, setTestimonialForm] = useState({
    name: '',
    text: '',
    rating: 5,
    location: '',
  });

  const addTestimonial = () => {
    if (testimonialForm.name && testimonialForm.text) {
      const newTestimonials = [...testimonials, { ...testimonialForm, date: new Date().toISOString() }];
      onUpdate(newTestimonials);
      setTestimonialForm({ name: '', text: '', rating: 5, location: '' });
    }
  };

  const updateTestimonial = () => {
    if (editingIndex !== null) {
      const newTestimonials = [...testimonials];
      newTestimonials[editingIndex] = testimonialForm;
      onUpdate(newTestimonials);
      setEditingIndex(null);
      setTestimonialForm({ name: '', text: '', rating: 5, location: '' });
    }
  };

  const editTestimonial = (index) => {
    setEditingIndex(index);
    setTestimonialForm(testimonials[index]);
  };

  const removeTestimonial = (index) => {
    onUpdate(testimonials.filter((_, i) => i !== index));
  };

  return (
    <div className="step-testimonials">
      <p className="step-description">
        Add testimonials from satisfied clients to build trust and credibility.
      </p>

      {/* Testimonial Form */}
      <div className="testimonial-form">
        <div className="form-row">
          <div className="form-field">
            <label>Client Name</label>
            <input
              type="text"
              className="form-input"
              value={testimonialForm.name}
              onChange={(e) => setTestimonialForm(prev => ({ ...prev, name: e.target.value }))}
              placeholder="John D."
            />
          </div>
          <div className="form-field">
            <label>Location (optional)</label>
            <input
              type="text"
              className="form-input"
              value={testimonialForm.location}
              onChange={(e) => setTestimonialForm(prev => ({ ...prev, location: e.target.value }))}
              placeholder="Los Angeles, CA"
            />
          </div>
        </div>

        <div className="form-field">
          <label>Rating</label>
          <div className="rating-selector">
            {[1, 2, 3, 4, 5].map((star) => (
              <button
                key={star}
                className={`star-btn ${testimonialForm.rating >= star ? 'active' : ''}`}
                onClick={() => setTestimonialForm(prev => ({ ...prev, rating: star }))}
              >
                ⭐
              </button>
            ))}
          </div>
        </div>

        <div className="form-field">
          <label>Testimonial</label>
          <textarea
            className="form-textarea"
            value={testimonialForm.text}
            onChange={(e) => setTestimonialForm(prev => ({ ...prev, text: e.target.value }))}
            placeholder="Share what the client said about their experience..."
            rows={3}
          />
        </div>

        <button
          className="add-testimonial-btn"
          onClick={editingIndex !== null ? updateTestimonial : addTestimonial}
        >
          {editingIndex !== null ? 'Update Testimonial' : 'Add Testimonial'}
        </button>
      </div>

      {/* Testimonials List */}
      {testimonials.length > 0 && (
        <div className="testimonials-list">
          <h4>Your Testimonials ({testimonials.length})</h4>
          {testimonials.map((t, i) => (
            <div key={i} className="testimonial-card">
              <div className="testimonial-header">
                <span className="testimonial-name">{t.name}</span>
                {t.location && <span className="testimonial-location">{t.location}</span>}
                <span className="testimonial-rating">{'⭐'.repeat(t.rating)}</span>
              </div>
              <p className="testimonial-text">"{t.text}"</p>
              <div className="testimonial-actions">
                <button onClick={() => editTestimonial(i)}>Edit</button>
                <button onClick={() => removeTestimonial(i)}>Remove</button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

// Step 6: Contact & Social
const StepContact = ({ data, onUpdate }) => (
  <div className="step-contact">
    <p className="step-description">
      Set up how visitors can reach you and connect with you on social media.
    </p>

    {/* Contact Preferences */}
    <div className="form-section">
      <label className="section-label">Contact Options</label>
      <div className="toggle-options">
        <label className="toggle-option">
          <input
            type="checkbox"
            checked={data.showPhone}
            onChange={(e) => onUpdate({ showPhone: e.target.checked })}
          />
          <span className="toggle-label">Show Phone Number</span>
        </label>
        <label className="toggle-option">
          <input
            type="checkbox"
            checked={data.showEmail}
            onChange={(e) => onUpdate({ showEmail: e.target.checked })}
          />
          <span className="toggle-label">Show Email Address</span>
        </label>
        <label className="toggle-option">
          <input
            type="checkbox"
            checked={data.contactFormEnabled}
            onChange={(e) => onUpdate({ contactFormEnabled: e.target.checked })}
          />
          <span className="toggle-label">Enable Contact Form</span>
        </label>
      </div>
    </div>

    {/* Calendly */}
    <div className="form-section">
      <label className="section-label">Booking Link</label>
      <input
        type="url"
        className="form-input"
        value={data.calendlyUrl}
        onChange={(e) => onUpdate({ calendlyUrl: e.target.value })}
        placeholder="https://calendly.com/your-link"
      />
      <span className="input-hint">Calendly, Cal.com, or other booking service URL</span>
    </div>

    {/* Social Links */}
    <div className="form-section">
      <label className="section-label">Social Media Links</label>
      <div className="social-inputs">
        <div className="social-field">
          <span className="social-icon">💼</span>
          <input
            type="url"
            className="form-input"
            value={data.socialLinks.linkedin}
            onChange={(e) => onUpdate({ socialLinks: { ...data.socialLinks, linkedin: e.target.value } })}
            placeholder="LinkedIn URL"
          />
        </div>
        <div className="social-field">
          <span className="social-icon">📘</span>
          <input
            type="url"
            className="form-input"
            value={data.socialLinks.facebook}
            onChange={(e) => onUpdate({ socialLinks: { ...data.socialLinks, facebook: e.target.value } })}
            placeholder="Facebook URL"
          />
        </div>
        <div className="social-field">
          <span className="social-icon">📸</span>
          <input
            type="url"
            className="form-input"
            value={data.socialLinks.instagram}
            onChange={(e) => onUpdate({ socialLinks: { ...data.socialLinks, instagram: e.target.value } })}
            placeholder="Instagram URL"
          />
        </div>
        <div className="social-field">
          <span className="social-icon">🐦</span>
          <input
            type="url"
            className="form-input"
            value={data.socialLinks.twitter}
            onChange={(e) => onUpdate({ socialLinks: { ...data.socialLinks, twitter: e.target.value } })}
            placeholder="Twitter/X URL"
          />
        </div>
        <div className="social-field">
          <span className="social-icon">🎬</span>
          <input
            type="url"
            className="form-input"
            value={data.socialLinks.youtube}
            onChange={(e) => onUpdate({ socialLinks: { ...data.socialLinks, youtube: e.target.value } })}
            placeholder="YouTube URL"
          />
        </div>
      </div>
    </div>

    {/* CTA Text */}
    <div className="form-section">
      <label className="section-label">Call-to-Action Buttons</label>
      <div className="cta-inputs">
        <div className="form-field">
          <label>Primary CTA</label>
          <input
            type="text"
            className="form-input"
            value={data.ctaText}
            onChange={(e) => onUpdate({ ctaText: e.target.value })}
            placeholder="Get Started Today"
          />
        </div>
        <div className="form-field">
          <label>Secondary CTA</label>
          <input
            type="text"
            className="form-input"
            value={data.ctaSecondaryText}
            onChange={(e) => onUpdate({ ctaSecondaryText: e.target.value })}
            placeholder="Check Your Rate"
          />
        </div>
      </div>
    </div>
  </div>
);

// Step 7: Preview & Publish
const StepPublish = ({ data, onPublish, saving }) => {
  const selectedTheme = THEMES.find(t => t.id === data.selectedTheme);

  return (
    <div className="step-publish">
      <p className="step-description">
        Review your microsite and publish when ready!
      </p>

      {/* Summary */}
      <div className="publish-summary">
        <div className="summary-section">
          <h4>Theme</h4>
          <div className="summary-item">
            <span className="summary-label">Selected:</span>
            <span className="summary-value">{selectedTheme?.name || 'None'}</span>
          </div>
        </div>

        <div className="summary-section">
          <h4>Brand</h4>
          <div className="summary-item">
            <span className="summary-label">Colors:</span>
            <div className="color-badges">
              <span className="color-badge" style={{ background: data.primaryColor }} />
              <span className="color-badge" style={{ background: data.secondaryColor }} />
            </div>
          </div>
        </div>

        <div className="summary-section">
          <h4>Profile</h4>
          <div className="summary-item">
            <span className="summary-label">Headline:</span>
            <span className="summary-value">{data.headline || 'Not set'}</span>
          </div>
          <div className="summary-item">
            <span className="summary-label">Photo:</span>
            <span className="summary-value">{data.heroImageUrl ? '✓ Uploaded' : 'Not set'}</span>
          </div>
        </div>

        <div className="summary-section">
          <h4>Credentials</h4>
          <div className="summary-item">
            <span className="summary-label">Experience:</span>
            <span className="summary-value">{data.yearsExperience ? `${data.yearsExperience} years` : 'Not set'}</span>
          </div>
          <div className="summary-item">
            <span className="summary-label">Specialties:</span>
            <span className="summary-value">{data.specialties.length || 0} added</span>
          </div>
        </div>

        <div className="summary-section">
          <h4>Social Proof</h4>
          <div className="summary-item">
            <span className="summary-label">Testimonials:</span>
            <span className="summary-value">{data.testimonials.length || 0} added</span>
          </div>
        </div>

        <div className="summary-section">
          <h4>Contact</h4>
          <div className="summary-item">
            <span className="summary-label">Booking Link:</span>
            <span className="summary-value">{data.calendlyUrl ? '✓ Set' : 'Not set'}</span>
          </div>
          <div className="summary-item">
            <span className="summary-label">Social Links:</span>
            <span className="summary-value">
              {Object.values(data.socialLinks).filter(Boolean).length} connected
            </span>
          </div>
        </div>
      </div>

      {/* Preview Button */}
      <div className="preview-section">
        <h4>Preview Your Site</h4>
        <p>See how your microsite will look before publishing.</p>
        <button
          className="preview-btn"
          onClick={() => window.open(`/microsite/preview`, '_blank')}
        >
          Open Preview →
        </button>
      </div>

      {/* Publish Section */}
      <div className="publish-section">
        <h4>Ready to Go Live?</h4>
        <p>Your microsite will be accessible at your unique URL.</p>
        <button
          className="publish-btn"
          onClick={onPublish}
          disabled={saving}
        >
          {saving ? 'Publishing...' : 'Publish My Microsite 🚀'}
        </button>
      </div>
    </div>
  );
};

export default MicrositeWizard;
