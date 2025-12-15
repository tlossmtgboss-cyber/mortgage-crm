/**
 * Bold Impact Theme
 *
 * A bold, modern theme with strong call-to-actions and lead capture focus.
 * Features prominent hero section, rate calculator, testimonials, and
 * comprehensive contact form.
 */

import React, { useState } from 'react';
import './BoldImpact.css';

// API base URL
const API_BASE = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
  ? (process.env.REACT_APP_API_URL || 'http://localhost:8000')
  : 'https://mortgage-crm-production-7a9a.up.railway.app';

const BoldImpact = ({ user, profile, themeConfig = {} }) => {
  const [formData, setFormData] = useState({
    first_name: '',
    last_name: '',
    email: '',
    phone: '',
    loan_type: 'purchase',
    property_type: '',
    estimated_value: '',
    down_payment: '',
    credit_score_range: '',
    timeline: '',
    message: ''
  });
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState(null);

  // Extract config with defaults
  const config = {
    primaryColor: themeConfig.primaryColor || '#dc2626',
    secondaryColor: themeConfig.secondaryColor || '#1e3a5f',
    heroStyle: themeConfig.heroStyle || 'image',
    headerStyle: themeConfig.headerStyle || 'centered',
    showTestimonials: themeConfig.showTestimonials !== false,
    showRateCalculator: themeConfig.showRateCalculator !== false,
    ...themeConfig
  };

  // Extract profile data with fallbacks
  const loName = user?.name || user?.full_name || 'Your Trusted Mortgage Expert';
  const loEmail = user?.email || '';
  const loPhone = user?.phone || '';
  const loNmls = user?.nmls_id || user?.nmls_number || '';
  const loPhoto = profile?.heroImageUrl || user?.photo_url || user?.avatar_url;
  const headline = profile?.headline || 'Your Path to Homeownership Starts Here';
  const tagline = profile?.tagline || 'Expert guidance for all your mortgage needs';
  const bioExtended = profile?.bioExtended || user?.bio || '';
  const yearsExperience = profile?.yearsExperience;
  const totalLoansFunded = profile?.totalLoansFunded;
  const specialties = profile?.specialties || [];
  const testimonials = profile?.testimonials || [];
  const ctaText = profile?.ctaText || 'Get Started Today';
  const ctaSecondaryText = profile?.ctaSecondaryText || 'Check Your Rate';
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
          referral_source: `microsite_bold_impact_${user?.id}`,
          utm_source: 'microsite',
          utm_medium: 'bold_impact',
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
      <div className="bold-impact" style={customStyles}>
        <div className="success-message">
          <div className="success-icon">✓</div>
          <h2>Thank You!</h2>
          <p>Your information has been submitted successfully.</p>
          <p>{loName} will be in touch with you shortly.</p>
          {loPhone && (
            <p className="contact-now">
              Need immediate assistance? Call{' '}
              <a href={`tel:${loPhone}`}>{loPhone}</a>
            </p>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="bold-impact" style={customStyles}>
      {/* Navigation */}
      <nav className={`bold-impact-nav ${config.headerStyle}`}>
        <div className="nav-container">
          <div className="nav-brand">
            {loPhoto && <img src={loPhoto} alt={loName} className="nav-avatar" />}
            <div className="nav-brand-text">
              <span className="nav-name">{loName}</span>
              {loNmls && <span className="nav-nmls">NMLS# {loNmls}</span>}
            </div>
          </div>
          <div className="nav-contact">
            {loPhone && (
              <a href={`tel:${loPhone}`} className="nav-phone">
                📞 {loPhone}
              </a>
            )}
            <a href="#contact-form" className="nav-cta">{ctaText}</a>
          </div>
        </div>
      </nav>

      {/* Hero Section */}
      <section className={`bold-impact-hero ${config.heroStyle}`}>
        <div className="hero-background"></div>
        <div className="hero-content">
          <div className="hero-text">
            <h1>{headline}</h1>
            <p className="hero-tagline">{tagline}</p>
            <div className="hero-cta-group">
              <a href="#contact-form" className="hero-cta primary">{ctaText}</a>
              {config.showRateCalculator && (
                <a href="#rate-check" className="hero-cta secondary">{ctaSecondaryText}</a>
              )}
            </div>
            {(yearsExperience || totalLoansFunded) && (
              <div className="hero-stats">
                {yearsExperience && (
                  <div className="stat">
                    <span className="stat-number">{yearsExperience}+</span>
                    <span className="stat-label">Years Experience</span>
                  </div>
                )}
                {totalLoansFunded && (
                  <div className="stat">
                    <span className="stat-number">{totalLoansFunded.toLocaleString()}+</span>
                    <span className="stat-label">Loans Funded</span>
                  </div>
                )}
              </div>
            )}
          </div>
          {loPhoto && config.heroStyle === 'image' && (
            <div className="hero-image">
              <img src={loPhoto} alt={loName} />
            </div>
          )}
        </div>
      </section>

      {/* Specialties Section */}
      {specialties.length > 0 && (
        <section className="bold-impact-specialties">
          <div className="specialties-container">
            <h2>How I Can Help You</h2>
            <div className="specialties-grid">
              {specialties.map((specialty, index) => (
                <div key={index} className="specialty-card">
                  <span className="specialty-icon">✓</span>
                  <span className="specialty-text">{specialty}</span>
                </div>
              ))}
            </div>
          </div>
        </section>
      )}

      {/* About Section */}
      {bioExtended && (
        <section className="bold-impact-about">
          <div className="about-container">
            <div className="about-content">
              {loPhoto && (
                <div className="about-image">
                  <img src={loPhoto} alt={loName} />
                </div>
              )}
              <div className="about-text">
                <h2>About {loName}</h2>
                <p>{bioExtended}</p>
                {calendlyUrl && (
                  <a href={calendlyUrl} target="_blank" rel="noopener noreferrer" className="schedule-btn">
                    Schedule a Consultation
                  </a>
                )}
              </div>
            </div>
          </div>
        </section>
      )}

      {/* Testimonials Section */}
      {config.showTestimonials && testimonials.length > 0 && (
        <section className="bold-impact-testimonials">
          <div className="testimonials-container">
            <h2>What Clients Say</h2>
            <div className="testimonials-grid">
              {testimonials.slice(0, 3).map((testimonial, index) => (
                <div key={index} className="testimonial-card">
                  <div className="testimonial-rating">
                    {'★'.repeat(testimonial.rating || 5)}
                  </div>
                  <p className="testimonial-text">"{testimonial.text}"</p>
                  <div className="testimonial-author">
                    <span className="author-name">{testimonial.name}</span>
                    {testimonial.date && (
                      <span className="testimonial-date">{testimonial.date}</span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>
      )}

      {/* Contact Form Section */}
      <section id="contact-form" className="bold-impact-contact">
        <div className="contact-container">
          <div className="contact-header">
            <h2>Get Your Free Quote</h2>
            <p>Fill out the form below and {loName} will contact you within 24 hours.</p>
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
                  placeholder="John"
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
                  placeholder="Smith"
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
                  placeholder="john@example.com"
                />
              </div>
              <div className="form-group">
                <label>Phone</label>
                <input
                  type="tel"
                  name="phone"
                  value={formData.phone}
                  onChange={handleInputChange}
                  placeholder="(555) 123-4567"
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
                <label>Property Type</label>
                <select
                  name="property_type"
                  value={formData.property_type}
                  onChange={handleInputChange}
                >
                  <option value="">Select...</option>
                  <option value="single_family">Single Family</option>
                  <option value="condo">Condo</option>
                  <option value="townhouse">Townhouse</option>
                  <option value="multi_family">Multi-Family</option>
                </select>
              </div>
            </div>

            <div className="form-row">
              <div className="form-group">
                <label>Estimated Property Value</label>
                <select
                  name="estimated_value"
                  value={formData.estimated_value}
                  onChange={handleInputChange}
                >
                  <option value="">Select...</option>
                  <option value="under_200k">Under $200,000</option>
                  <option value="200k_400k">$200,000 - $400,000</option>
                  <option value="400k_600k">$400,000 - $600,000</option>
                  <option value="600k_800k">$600,000 - $800,000</option>
                  <option value="800k_1m">$800,000 - $1,000,000</option>
                  <option value="over_1m">Over $1,000,000</option>
                </select>
              </div>
              <div className="form-group">
                <label>Credit Score Range</label>
                <select
                  name="credit_score_range"
                  value={formData.credit_score_range}
                  onChange={handleInputChange}
                >
                  <option value="">Select...</option>
                  <option value="excellent">Excellent (740+)</option>
                  <option value="good">Good (700-739)</option>
                  <option value="fair">Fair (660-699)</option>
                  <option value="poor">Below 660</option>
                  <option value="unknown">Not Sure</option>
                </select>
              </div>
            </div>

            <div className="form-group full-width">
              <label>Timeline</label>
              <select
                name="timeline"
                value={formData.timeline}
                onChange={handleInputChange}
              >
                <option value="">When are you looking to move forward?</option>
                <option value="asap">ASAP</option>
                <option value="1_month">Within 1 month</option>
                <option value="1_3_months">1-3 months</option>
                <option value="3_6_months">3-6 months</option>
                <option value="6_plus_months">6+ months</option>
                <option value="just_researching">Just researching</option>
              </select>
            </div>

            <div className="form-group full-width">
              <label>Additional Message</label>
              <textarea
                name="message"
                value={formData.message}
                onChange={handleInputChange}
                placeholder="Tell us more about your situation..."
                rows="4"
              />
            </div>

            <button type="submit" className="submit-btn" disabled={submitting}>
              {submitting ? 'Submitting...' : ctaText}
            </button>

            <p className="form-disclaimer">
              By submitting this form, you agree to be contacted by {loName} regarding your mortgage inquiry.
              Your information is secure and will never be shared.
            </p>
          </form>
        </div>
      </section>

      {/* Footer */}
      <footer className="bold-impact-footer">
        <div className="footer-container">
          <div className="footer-info">
            <strong>{loName}</strong>
            {loNmls && <span>NMLS# {loNmls}</span>}
          </div>
          <div className="footer-contact">
            {loEmail && <a href={`mailto:${loEmail}`}>{loEmail}</a>}
            {loPhone && <a href={`tel:${loPhone}`}>{loPhone}</a>}
          </div>
          {Object.keys(socialLinks).length > 0 && (
            <div className="footer-social">
              {socialLinks.linkedin && (
                <a href={socialLinks.linkedin} target="_blank" rel="noopener noreferrer">LinkedIn</a>
              )}
              {socialLinks.facebook && (
                <a href={socialLinks.facebook} target="_blank" rel="noopener noreferrer">Facebook</a>
              )}
              {socialLinks.instagram && (
                <a href={socialLinks.instagram} target="_blank" rel="noopener noreferrer">Instagram</a>
              )}
            </div>
          )}
          <div className="footer-legal">
            <p>Equal Housing Opportunity</p>
          </div>
        </div>
      </footer>
    </div>
  );
};

export default BoldImpact;
