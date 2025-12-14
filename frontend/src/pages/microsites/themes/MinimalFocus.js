/**
 * Minimal Focus Theme
 *
 * A minimalist theme that puts the focus on your message and lead capture.
 * Clean design with maximum whitespace and typography-first approach.
 */

import React, { useState } from 'react';
import './MinimalFocus.css';

// API base URL
const API_BASE = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
  ? (process.env.REACT_APP_API_URL || 'http://localhost:8000')
  : 'https://mortgage-crm-production-7a9a.up.railway.app';

const MinimalFocus = ({ user, profile, themeConfig = {} }) => {
  const [formData, setFormData] = useState({
    first_name: '',
    last_name: '',
    email: '',
    phone: '',
    loan_type: 'purchase',
    message: ''
  });
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState(null);

  // Extract config with defaults
  const config = {
    primaryColor: themeConfig.primaryColor || '#18181b',
    secondaryColor: themeConfig.secondaryColor || '#71717a',
    layout: themeConfig.layout || 'centered',
    ...themeConfig
  };

  // Extract profile data with fallbacks
  const loName = user?.name || user?.full_name || 'Mortgage Expert';
  const loEmail = user?.email || '';
  const loPhone = user?.phone || '';
  const loNmls = user?.nmls_id || user?.nmls_number || '';
  const loPhoto = profile?.heroImageUrl || user?.photo_url || user?.avatar_url;
  const headline = profile?.headline || 'Simple. Honest. Mortgage Advice.';
  const tagline = profile?.tagline || 'Navigating your path to homeownership with clarity and care.';
  const bioExtended = profile?.bioExtended || user?.bio || '';
  const yearsExperience = profile?.yearsExperience;
  const ctaText = profile?.ctaText || 'Get in Touch';
  const calendlyUrl = profile?.calendlyUrl;

  const handleInputChange = (e) => {
    const { name, value } = e.target;
    setFormData(prev => ({ ...prev, [name]: value }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    setError(null);

    try {
      const response = await fetch(`${API_BASE}/api/v1/public/leads`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...formData,
          source: 'microsite',
          loan_officer_id: user?.id,
          referral_source: `microsite_minimal_${user?.id}`,
          utm_source: 'microsite',
          utm_medium: 'minimal_focus',
          utm_campaign: user?.slug || user?.id
        })
      });

      if (response.ok) {
        setSubmitted(true);
      } else {
        throw new Error('Failed to submit');
      }
    } catch (err) {
      console.error('Error submitting lead:', err);
      setError('There was an error submitting your request. Please try again.');
    } finally {
      setSubmitting(false);
    }
  };

  // Apply custom colors via CSS variables
  const customStyles = {
    '--theme-primary': config.primaryColor,
    '--theme-secondary': config.secondaryColor,
  };

  if (submitted) {
    return (
      <div className={`minimal-focus ${config.layout}`} style={customStyles}>
        <div className="minimal-success">
          <div className="success-content">
            <span className="success-mark">Done</span>
            <h2>Message Received</h2>
            <p>I'll reach out within one business day.</p>
            {loPhone && (
              <p className="success-phone">
                Prefer to talk now?<br />
                <a href={`tel:${loPhone}`}>{loPhone}</a>
              </p>
            )}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className={`minimal-focus ${config.layout}`} style={customStyles}>
      {/* Header */}
      <header className="minimal-header">
        <div className="header-content">
          <span className="header-name">{loName}</span>
          {loNmls && <span className="header-nmls">NMLS# {loNmls}</span>}
        </div>
        {loPhone && (
          <a href={`tel:${loPhone}`} className="header-phone">{loPhone}</a>
        )}
      </header>

      {/* Main Content */}
      <main className="minimal-main">
        {config.layout === 'split' ? (
          <div className="split-layout">
            <div className="split-left">
              <div className="hero-section">
                <h1>{headline}</h1>
                <p className="hero-tagline">{tagline}</p>

                {yearsExperience && (
                  <p className="hero-experience">{yearsExperience} years of experience</p>
                )}

                {bioExtended && (
                  <div className="about-section">
                    <p>{bioExtended}</p>
                  </div>
                )}

                {calendlyUrl && (
                  <a href={calendlyUrl} target="_blank" rel="noopener noreferrer" className="schedule-link">
                    Or schedule a call
                  </a>
                )}
              </div>
            </div>

            <div className="split-right">
              {loPhoto && (
                <div className="photo-section">
                  <img src={loPhoto} alt={loName} />
                </div>
              )}

              <form onSubmit={handleSubmit} className="contact-form">
                {error && <div className="form-error">{error}</div>}

                <div className="form-fields">
                  <input
                    type="text"
                    name="first_name"
                    value={formData.first_name}
                    onChange={handleInputChange}
                    required
                    placeholder="First name"
                  />
                  <input
                    type="text"
                    name="last_name"
                    value={formData.last_name}
                    onChange={handleInputChange}
                    required
                    placeholder="Last name"
                  />
                  <input
                    type="email"
                    name="email"
                    value={formData.email}
                    onChange={handleInputChange}
                    required
                    placeholder="Email"
                  />
                  <input
                    type="tel"
                    name="phone"
                    value={formData.phone}
                    onChange={handleInputChange}
                    placeholder="Phone (optional)"
                  />
                  <select
                    name="loan_type"
                    value={formData.loan_type}
                    onChange={handleInputChange}
                  >
                    <option value="purchase">Purchase</option>
                    <option value="refinance">Refinance</option>
                    <option value="cash_out">Cash-out refinance</option>
                    <option value="heloc">HELOC</option>
                    <option value="other">Other</option>
                  </select>
                  <textarea
                    name="message"
                    value={formData.message}
                    onChange={handleInputChange}
                    placeholder="How can I help?"
                    rows="3"
                  />
                </div>

                <button type="submit" disabled={submitting}>
                  {submitting ? 'Sending...' : ctaText}
                </button>
              </form>
            </div>
          </div>
        ) : (
          /* Centered Layout */
          <div className="centered-layout">
            {loPhoto && (
              <div className="profile-photo">
                <img src={loPhoto} alt={loName} />
              </div>
            )}

            <div className="hero-section">
              <h1>{headline}</h1>
              <p className="hero-tagline">{tagline}</p>
            </div>

            {bioExtended && (
              <div className="about-section">
                <p>{bioExtended}</p>
              </div>
            )}

            <form onSubmit={handleSubmit} className="contact-form">
              {error && <div className="form-error">{error}</div>}

              <div className="form-fields">
                <div className="form-row">
                  <input
                    type="text"
                    name="first_name"
                    value={formData.first_name}
                    onChange={handleInputChange}
                    required
                    placeholder="First name"
                  />
                  <input
                    type="text"
                    name="last_name"
                    value={formData.last_name}
                    onChange={handleInputChange}
                    required
                    placeholder="Last name"
                  />
                </div>
                <input
                  type="email"
                  name="email"
                  value={formData.email}
                  onChange={handleInputChange}
                  required
                  placeholder="Email"
                />
                <input
                  type="tel"
                  name="phone"
                  value={formData.phone}
                  onChange={handleInputChange}
                  placeholder="Phone (optional)"
                />
                <select
                  name="loan_type"
                  value={formData.loan_type}
                  onChange={handleInputChange}
                >
                  <option value="purchase">I'm looking to purchase</option>
                  <option value="refinance">I want to refinance</option>
                  <option value="cash_out">Cash-out refinance</option>
                  <option value="heloc">HELOC</option>
                  <option value="other">Something else</option>
                </select>
                <textarea
                  name="message"
                  value={formData.message}
                  onChange={handleInputChange}
                  placeholder="Tell me about your situation..."
                  rows="3"
                />
              </div>

              <button type="submit" disabled={submitting}>
                {submitting ? 'Sending...' : ctaText}
              </button>

              <p className="form-note">
                Your information stays private.
              </p>
            </form>

            {calendlyUrl && (
              <div className="alternate-action">
                <span>Prefer to talk?</span>
                <a href={calendlyUrl} target="_blank" rel="noopener noreferrer">
                  Schedule a call
                </a>
              </div>
            )}
          </div>
        )}
      </main>

      {/* Footer */}
      <footer className="minimal-footer">
        <div className="footer-content">
          <span>{loName}</span>
          {loNmls && <span>NMLS# {loNmls}</span>}
          {loEmail && <a href={`mailto:${loEmail}`}>{loEmail}</a>}
        </div>
        <span className="footer-legal">Equal Housing Opportunity</span>
      </footer>
    </div>
  );
};

export default MinimalFocus;
