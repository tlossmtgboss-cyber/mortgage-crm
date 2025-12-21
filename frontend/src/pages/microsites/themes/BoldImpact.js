/**
 * Bold Impact Theme
 *
 * A bold, modern theme with strong call-to-actions and lead capture focus.
 * Features prominent hero section, rate calculator, testimonials, and
 * comprehensive contact form.
 */

import React from 'react';
import './BoldImpact.css';
import EmbeddedAIChat from '../../../components/EmbeddedAIChat';

const BoldImpact = ({ user, profile, themeConfig = {} }) => {

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

  // Apply custom colors via CSS variables
  const customStyles = {
    '--theme-primary': config.primaryColor,
    '--theme-secondary': config.secondaryColor,
  };

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

      {/* AI Chat Section - Claude-style embedded chat */}
      <EmbeddedAIChat
        userSlug={user?.slug}
        loName={loName}
        themeConfig={themeConfig}
      />

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
