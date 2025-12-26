/**
 * Professional Clean Theme
 *
 * A clean, professional theme perfect for established loan officers.
 * Features a refined design with emphasis on credentials and trust.
 */

import React, { useState } from 'react';
import './ProfessionalClean.css';

// API base URL
const API_BASE = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
  ? (process.env.REACT_APP_API_URL || 'http://localhost:8000')
  : 'https://api.perenniaai.com';

const ProfessionalClean = ({ user, profile, themeConfig = {} }) => {
  const [formData, setFormData] = useState({
    first_name: '',
    last_name: '',
    email: '',
    phone: '',
    loan_type: 'purchase',
    property_type: '',
    estimated_value: '',
    credit_score_range: '',
    timeline: '',
    message: ''
  });
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState(null);

  // Extract config with defaults
  const config = {
    primaryColor: themeConfig.primaryColor || '#2563eb',
    secondaryColor: themeConfig.secondaryColor || '#1e40af',
    heroStyle: themeConfig.heroStyle || 'solid',
    headerStyle: themeConfig.headerStyle || 'left',
    ...themeConfig
  };

  // Extract profile data with fallbacks
  const loName = user?.name || user?.full_name || 'Your Mortgage Professional';
  const loEmail = user?.email || '';
  const loPhone = user?.phone || '';
  const loNmls = user?.nmls_id || user?.nmls_number || '';
  const loPhoto = profile?.heroImageUrl || user?.photo_url || user?.avatar_url;
  const headline = profile?.headline || 'Expert Mortgage Guidance You Can Trust';
  const tagline = profile?.tagline || 'Dedicated to finding the right loan solution for your unique situation';
  const bioExtended = profile?.bioExtended || user?.bio || '';
  const yearsExperience = profile?.yearsExperience;
  const totalLoansFunded = profile?.totalLoansFunded;
  const totalVolumeFunded = profile?.totalVolumeFunded;
  const certifications = profile?.certifications || [];
  const specialties = profile?.specialties || [];
  const ctaText = profile?.ctaText || 'Request Consultation';
  const calendlyUrl = profile?.calendlyUrl;
  const socialLinks = profile?.socialLinks || {};
  const companyName = user?.company || '';
  const companyLogo = user?.company_logo_url;

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
          referral_source: `microsite_professional_${user?.id}`,
          utm_source: 'microsite',
          utm_medium: 'professional_clean',
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
      <div className="professional-clean" style={customStyles}>
        <div className="success-message">
          <div className="success-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
              <polyline points="22 4 12 14.01 9 11.01" />
            </svg>
          </div>
          <h2>Thank You for Reaching Out</h2>
          <p>Your inquiry has been received. {loName} will contact you within one business day.</p>
          {loPhone && (
            <p className="contact-now">
              For immediate assistance, call <a href={`tel:${loPhone}`}>{loPhone}</a>
            </p>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="professional-clean" style={customStyles}>
      {/* Header */}
      <header className={`pro-header ${config.headerStyle}`}>
        <div className="header-container">
          <div className="header-brand">
            {companyLogo ? (
              <img src={companyLogo} alt={companyName} className="company-logo" />
            ) : companyName ? (
              <span className="company-name">{companyName}</span>
            ) : null}
            <div className="header-lo-info">
              <span className="lo-name">{loName}</span>
              {loNmls && <span className="lo-nmls">NMLS# {loNmls}</span>}
            </div>
          </div>
          <nav className="header-nav">
            <a href="#about">About</a>
            <a href="#services">Services</a>
            <a href="#contact">{ctaText}</a>
            {loPhone && (
              <a href={`tel:${loPhone}`} className="header-phone">{loPhone}</a>
            )}
          </nav>
        </div>
      </header>

      {/* Hero Section */}
      <section className={`pro-hero ${config.heroStyle}`}>
        <div className="hero-container">
          <div className="hero-content">
            <h1>{headline}</h1>
            <p className="hero-tagline">{tagline}</p>
            <div className="hero-actions">
              <a href="#contact" className="btn-primary">{ctaText}</a>
              {calendlyUrl && (
                <a href={calendlyUrl} target="_blank" rel="noopener noreferrer" className="btn-secondary">
                  Schedule a Call
                </a>
              )}
            </div>
          </div>
          {loPhoto && config.heroStyle === 'image' && (
            <div className="hero-photo">
              <img src={loPhoto} alt={loName} />
            </div>
          )}
        </div>
      </section>

      {/* Credentials Bar */}
      <section className="pro-credentials">
        <div className="credentials-container">
          {yearsExperience && (
            <div className="credential-item">
              <span className="credential-number">{yearsExperience}+</span>
              <span className="credential-label">Years Experience</span>
            </div>
          )}
          {totalLoansFunded && (
            <div className="credential-item">
              <span className="credential-number">{totalLoansFunded.toLocaleString()}</span>
              <span className="credential-label">Loans Funded</span>
            </div>
          )}
          {totalVolumeFunded && (
            <div className="credential-item">
              <span className="credential-number">${(totalVolumeFunded / 1000000).toFixed(0)}M+</span>
              <span className="credential-label">Volume Funded</span>
            </div>
          )}
          {certifications.length > 0 && (
            <div className="credential-item certifications">
              <span className="credential-label">Certifications</span>
              <span className="credential-badges">
                {certifications.slice(0, 3).map((cert, i) => (
                  <span key={i} className="cert-badge">{cert}</span>
                ))}
              </span>
            </div>
          )}
        </div>
      </section>

      {/* About Section */}
      {bioExtended && (
        <section id="about" className="pro-about">
          <div className="about-container">
            <div className="about-grid">
              {loPhoto && (
                <div className="about-photo">
                  <img src={loPhoto} alt={loName} />
                </div>
              )}
              <div className="about-content">
                <h2>About {loName}</h2>
                <p>{bioExtended}</p>
                {socialLinks && Object.keys(socialLinks).length > 0 && (
                  <div className="about-social">
                    {socialLinks.linkedin && (
                      <a href={socialLinks.linkedin} target="_blank" rel="noopener noreferrer" aria-label="LinkedIn">
                        <svg viewBox="0 0 24 24" fill="currentColor"><path d="M19 0h-14c-2.761 0-5 2.239-5 5v14c0 2.761 2.239 5 5 5h14c2.762 0 5-2.239 5-5v-14c0-2.761-2.238-5-5-5zm-11 19h-3v-11h3v11zm-1.5-12.268c-.966 0-1.75-.79-1.75-1.764s.784-1.764 1.75-1.764 1.75.79 1.75 1.764-.783 1.764-1.75 1.764zm13.5 12.268h-3v-5.604c0-3.368-4-3.113-4 0v5.604h-3v-11h3v1.765c1.396-2.586 7-2.777 7 2.476v6.759z"/></svg>
                      </a>
                    )}
                    {socialLinks.facebook && (
                      <a href={socialLinks.facebook} target="_blank" rel="noopener noreferrer" aria-label="Facebook">
                        <svg viewBox="0 0 24 24" fill="currentColor"><path d="M24 12.073c0-6.627-5.373-12-12-12s-12 5.373-12 12c0 5.99 4.388 10.954 10.125 11.854v-8.385h-3.047v-3.47h3.047v-2.642c0-3.007 1.792-4.669 4.533-4.669 1.312 0 2.686.235 2.686.235v2.953h-1.514c-1.491 0-1.956.925-1.956 1.874v2.25h3.328l-.532 3.47h-2.796v8.385c5.737-.9 10.126-5.864 10.126-11.854z"/></svg>
                      </a>
                    )}
                  </div>
                )}
              </div>
            </div>
          </div>
        </section>
      )}

      {/* Services/Specialties Section */}
      {specialties.length > 0 && (
        <section id="services" className="pro-services">
          <div className="services-container">
            <h2>Areas of Expertise</h2>
            <div className="services-grid">
              {specialties.map((specialty, index) => (
                <div key={index} className="service-card">
                  <div className="service-icon">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
                      <polyline points="22 4 12 14.01 9 11.01" />
                    </svg>
                  </div>
                  <span className="service-name">{specialty}</span>
                </div>
              ))}
            </div>
          </div>
        </section>
      )}

      {/* Contact Form Section */}
      <section id="contact" className="pro-contact">
        <div className="contact-container">
          <div className="contact-info">
            <h2>Let's Discuss Your Goals</h2>
            <p>Complete the form and {loName} will reach out to discuss your mortgage options.</p>

            <div className="contact-details">
              {loPhone && (
                <div className="contact-item">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z"></path>
                  </svg>
                  <a href={`tel:${loPhone}`}>{loPhone}</a>
                </div>
              )}
              {loEmail && (
                <div className="contact-item">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"></path>
                    <polyline points="22,6 12,13 2,6"></polyline>
                  </svg>
                  <a href={`mailto:${loEmail}`}>{loEmail}</a>
                </div>
              )}
            </div>
          </div>

          <form onSubmit={handleSubmit} className="contact-form">
            {error && <div className="form-error">{error}</div>}

            <div className="form-row">
              <div className="form-group">
                <label>First Name *</label>
                <input
                  type="text"
                  name="first_name"
                  value={formData.first_name}
                  onChange={handleInputChange}
                  required
                />
              </div>
              <div className="form-group">
                <label>Last Name *</label>
                <input
                  type="text"
                  name="last_name"
                  value={formData.last_name}
                  onChange={handleInputChange}
                  required
                />
              </div>
            </div>

            <div className="form-row">
              <div className="form-group">
                <label>Email *</label>
                <input
                  type="email"
                  name="email"
                  value={formData.email}
                  onChange={handleInputChange}
                  required
                />
              </div>
              <div className="form-group">
                <label>Phone</label>
                <input
                  type="tel"
                  name="phone"
                  value={formData.phone}
                  onChange={handleInputChange}
                />
              </div>
            </div>

            <div className="form-row">
              <div className="form-group">
                <label>Loan Purpose *</label>
                <select
                  name="loan_type"
                  value={formData.loan_type}
                  onChange={handleInputChange}
                  required
                >
                  <option value="purchase">Purchase</option>
                  <option value="refinance">Refinance</option>
                  <option value="cash_out">Cash-Out Refinance</option>
                  <option value="heloc">HELOC</option>
                </select>
              </div>
              <div className="form-group">
                <label>Timeline</label>
                <select
                  name="timeline"
                  value={formData.timeline}
                  onChange={handleInputChange}
                >
                  <option value="">When are you looking to proceed?</option>
                  <option value="asap">Immediately</option>
                  <option value="1_month">Within 30 days</option>
                  <option value="1_3_months">1-3 months</option>
                  <option value="3_6_months">3-6 months</option>
                  <option value="just_researching">Just researching</option>
                </select>
              </div>
            </div>

            <div className="form-group">
              <label>How Can I Help?</label>
              <textarea
                name="message"
                value={formData.message}
                onChange={handleInputChange}
                rows="3"
                placeholder="Tell me about your situation and goals..."
              />
            </div>

            <button type="submit" className="submit-btn" disabled={submitting}>
              {submitting ? 'Sending...' : ctaText}
            </button>

            <p className="form-disclaimer">
              Your information is secure and will only be used to contact you about your mortgage inquiry.
            </p>
          </form>
        </div>
      </section>

      {/* Footer */}
      <footer className="pro-footer">
        <div className="footer-container">
          <div className="footer-main">
            <div className="footer-brand">
              <strong>{loName}</strong>
              {loNmls && <span>NMLS# {loNmls}</span>}
              {companyName && <span>{companyName}</span>}
            </div>
            <div className="footer-contact">
              {loEmail && <a href={`mailto:${loEmail}`}>{loEmail}</a>}
              {loPhone && <a href={`tel:${loPhone}`}>{loPhone}</a>}
            </div>
          </div>
          <div className="footer-legal">
            <p>Equal Housing Lender</p>
            <p>&copy; {new Date().getFullYear()} All Rights Reserved</p>
          </div>
        </div>
      </footer>
    </div>
  );
};

export default ProfessionalClean;
