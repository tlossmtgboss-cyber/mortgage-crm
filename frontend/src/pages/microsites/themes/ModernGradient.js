/**
 * Modern Gradient Theme
 *
 * A contemporary theme with gradient backgrounds and smooth animations.
 * Features dynamic visual effects and modern design sensibilities.
 */

import React, { useState } from 'react';
import './ModernGradient.css';

// API base URL
const API_BASE = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
  ? (process.env.REACT_APP_API_URL || 'http://localhost:8000')
  : 'https://api.perenniaai.com';

const ModernGradient = ({ user, profile, themeConfig = {} }) => {
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
    primaryColor: themeConfig.primaryColor || '#B8924A',
    secondaryColor: themeConfig.secondaryColor || '#ec4899',
    gradientDirection: themeConfig.gradientDirection || 'diagonal',
    animationStyle: themeConfig.animationStyle || 'subtle',
    ...themeConfig
  };

  // Extract profile data with fallbacks
  const loName = user?.name || user?.full_name || 'Your Mortgage Expert';
  const loEmail = user?.email || '';
  const loPhone = user?.phone || '';
  const loNmls = user?.nmls_id || user?.nmls_number || '';
  const loPhoto = profile?.heroImageUrl || user?.photo_url || user?.avatar_url;
  const headline = profile?.headline || 'Modern Mortgage Solutions';
  const tagline = profile?.tagline || 'Streamlined lending for today\'s homebuyers';
  const bioExtended = profile?.bioExtended || user?.bio || '';
  const yearsExperience = profile?.yearsExperience;
  const totalLoansFunded = profile?.totalLoansFunded;
  const testimonials = profile?.testimonials || [];
  const specialties = profile?.specialties || [];
  const ctaText = profile?.ctaText || 'Get Started';
  const calendlyUrl = profile?.calendlyUrl;
  const socialLinks = profile?.socialLinks || {};

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
          referral_source: `microsite_gradient_${user?.id}`,
          utm_source: 'microsite',
          utm_medium: 'modern_gradient',
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

  // Determine gradient based on direction
  const getGradientStyle = () => {
    const directions = {
      diagonal: '135deg',
      horizontal: '90deg',
      vertical: '180deg'
    };
    const angle = directions[config.gradientDirection] || '135deg';
    return `linear-gradient(${angle}, ${config.primaryColor} 0%, ${config.secondaryColor} 100%)`;
  };

  // Apply custom colors via CSS variables
  const customStyles = {
    '--theme-primary': config.primaryColor,
    '--theme-secondary': config.secondaryColor,
    '--theme-gradient': getGradientStyle(),
  };

  if (submitted) {
    return (
      <div className={`modern-gradient ${config.animationStyle}`} style={customStyles}>
        <div className="success-container">
          <div className="success-card">
            <div className="success-icon">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="12" cy="12" r="10" />
                <path d="M8 12l2 2 4-4" />
              </svg>
            </div>
            <h2>You're All Set!</h2>
            <p>{loName} will be in touch within 24 hours to discuss your mortgage needs.</p>
            {loPhone && (
              <a href={`tel:${loPhone}`} className="success-phone">
                Or call now: {loPhone}
              </a>
            )}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className={`modern-gradient ${config.animationStyle}`} style={customStyles}>
      {/* Navigation */}
      <nav className="gradient-nav">
        <div className="nav-container">
          <div className="nav-brand">
            {loPhoto && <img src={loPhoto} alt={loName} className="nav-avatar" />}
            <div className="nav-brand-text">
              <span className="nav-name">{loName}</span>
              {loNmls && <span className="nav-nmls">NMLS# {loNmls}</span>}
            </div>
          </div>
          <div className="nav-links">
            {loPhone && (
              <a href={`tel:${loPhone}`} className="nav-phone">{loPhone}</a>
            )}
            <a href="#contact" className="nav-cta">{ctaText}</a>
          </div>
        </div>
      </nav>

      {/* Hero Section */}
      <section className="gradient-hero">
        <div className="hero-bg">
          <div className="gradient-orb orb-1"></div>
          <div className="gradient-orb orb-2"></div>
          <div className="gradient-orb orb-3"></div>
        </div>
        <div className="hero-content">
          <div className="hero-text">
            <h1>{headline}</h1>
            <p className="hero-tagline">{tagline}</p>
            <div className="hero-cta-group">
              <a href="#contact" className="cta-primary">{ctaText}</a>
              {calendlyUrl && (
                <a href={calendlyUrl} target="_blank" rel="noopener noreferrer" className="cta-secondary">
                  Book a Call
                </a>
              )}
            </div>
            {(yearsExperience || totalLoansFunded) && (
              <div className="hero-stats">
                {yearsExperience && (
                  <div className="stat-item">
                    <span className="stat-value">{yearsExperience}+</span>
                    <span className="stat-label">Years</span>
                  </div>
                )}
                {totalLoansFunded && (
                  <div className="stat-item">
                    <span className="stat-value">{totalLoansFunded.toLocaleString()}</span>
                    <span className="stat-label">Loans</span>
                  </div>
                )}
              </div>
            )}
          </div>
          {loPhoto && (
            <div className="hero-visual">
              <div className="hero-image-wrapper">
                <img src={loPhoto} alt={loName} />
              </div>
            </div>
          )}
        </div>
      </section>

      {/* Specialties Cards */}
      {specialties.length > 0 && (
        <section className="gradient-specialties">
          <div className="specialties-container">
            <h2>What I Offer</h2>
            <div className="specialties-scroll">
              {specialties.map((specialty, index) => (
                <div key={index} className="specialty-card" style={{ '--delay': `${index * 0.1}s` }}>
                  <div className="specialty-glow"></div>
                  <span>{specialty}</span>
                </div>
              ))}
            </div>
          </div>
        </section>
      )}

      {/* About Section */}
      {bioExtended && (
        <section className="gradient-about">
          <div className="about-container">
            <div className="about-content">
              <div className="about-visual">
                {loPhoto && <img src={loPhoto} alt={loName} />}
              </div>
              <div className="about-text">
                <h2>Meet {loName}</h2>
                <p>{bioExtended}</p>
                {Object.keys(socialLinks).length > 0 && (
                  <div className="about-social">
                    {socialLinks.linkedin && (
                      <a href={socialLinks.linkedin} target="_blank" rel="noopener noreferrer">LinkedIn</a>
                    )}
                    {socialLinks.instagram && (
                      <a href={socialLinks.instagram} target="_blank" rel="noopener noreferrer">Instagram</a>
                    )}
                    {socialLinks.facebook && (
                      <a href={socialLinks.facebook} target="_blank" rel="noopener noreferrer">Facebook</a>
                    )}
                  </div>
                )}
              </div>
            </div>
          </div>
        </section>
      )}

      {/* Testimonials */}
      {testimonials.length > 0 && (
        <section className="gradient-testimonials">
          <div className="testimonials-container">
            <h2>Client Stories</h2>
            <div className="testimonials-grid">
              {testimonials.slice(0, 3).map((testimonial, index) => (
                <div key={index} className="testimonial-card" style={{ '--delay': `${index * 0.15}s` }}>
                  <div className="testimonial-stars">
                    {'★'.repeat(testimonial.rating || 5)}
                  </div>
                  <p className="testimonial-text">"{testimonial.text}"</p>
                  <div className="testimonial-author">
                    <span className="author-name">{testimonial.name}</span>
                    {testimonial.date && <span className="author-date">{testimonial.date}</span>}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>
      )}

      {/* Contact Form */}
      <section id="contact" className="gradient-contact">
        <div className="contact-container">
          <div className="contact-header">
            <h2>Ready to Get Started?</h2>
            <p>Fill out the form and let's discuss your mortgage options.</p>
          </div>

          <form onSubmit={handleSubmit} className="contact-form">
            {error && <div className="form-error">{error}</div>}

            <div className="form-grid">
              <div className="form-group">
                <input
                  type="text"
                  name="first_name"
                  value={formData.first_name}
                  onChange={handleInputChange}
                  required
                  placeholder="First Name *"
                />
              </div>
              <div className="form-group">
                <input
                  type="text"
                  name="last_name"
                  value={formData.last_name}
                  onChange={handleInputChange}
                  required
                  placeholder="Last Name *"
                />
              </div>
              <div className="form-group">
                <input
                  type="email"
                  name="email"
                  value={formData.email}
                  onChange={handleInputChange}
                  required
                  placeholder="Email *"
                />
              </div>
              <div className="form-group">
                <input
                  type="tel"
                  name="phone"
                  value={formData.phone}
                  onChange={handleInputChange}
                  placeholder="Phone"
                />
              </div>
              <div className="form-group">
                <select
                  name="loan_type"
                  value={formData.loan_type}
                  onChange={handleInputChange}
                  required
                >
                  <option value="purchase">Purchase</option>
                  <option value="refinance">Refinance</option>
                  <option value="cash_out">Cash-Out Refi</option>
                  <option value="heloc">HELOC</option>
                </select>
              </div>
              <div className="form-group">
                <select
                  name="timeline"
                  value={formData.timeline}
                  onChange={handleInputChange}
                >
                  <option value="">Timeline</option>
                  <option value="asap">ASAP</option>
                  <option value="1_month">Within 1 month</option>
                  <option value="1_3_months">1-3 months</option>
                  <option value="3_6_months">3-6 months</option>
                  <option value="just_researching">Just looking</option>
                </select>
              </div>
            </div>

            <div className="form-group full-width">
              <textarea
                name="message"
                value={formData.message}
                onChange={handleInputChange}
                placeholder="Tell me about your goals..."
                rows="3"
              />
            </div>

            <button type="submit" className="submit-btn" disabled={submitting}>
              <span>{submitting ? 'Sending...' : ctaText}</span>
              {!submitting && (
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M5 12h14M12 5l7 7-7 7" />
                </svg>
              )}
            </button>

            <p className="form-disclaimer">
              Your information is secure and confidential.
            </p>
          </form>
        </div>
      </section>

      {/* Footer */}
      <footer className="gradient-footer">
        <div className="footer-container">
          <div className="footer-info">
            <strong>{loName}</strong>
            {loNmls && <span>NMLS# {loNmls}</span>}
          </div>
          <div className="footer-contact">
            {loEmail && <a href={`mailto:${loEmail}`}>{loEmail}</a>}
            {loPhone && <a href={`tel:${loPhone}`}>{loPhone}</a>}
          </div>
          <div className="footer-legal">
            <span>Equal Housing Opportunity</span>
          </div>
        </div>
      </footer>
    </div>
  );
};

export default ModernGradient;
