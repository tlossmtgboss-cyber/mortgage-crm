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
  const logoUrl = profile?.logoUrl || themeConfig?.logoUrl;
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
            {logoUrl ? (
              <img src={logoUrl} alt={loName} className="nav-logo" />
            ) : (
              <>
                {loPhoto && <img src={loPhoto} alt={loName} className="nav-avatar" />}
                <div className="nav-brand-text">
                  <span className="nav-name">{loName}</span>
                  {loNmls && <span className="nav-nmls">NMLS# {loNmls}</span>}
                </div>
              </>
            )}
          </div>
          <div className="nav-contact">
            {loPhone && (
              <a href={`tel:${loPhone}`} className="nav-phone">
                📞 {loPhone}
              </a>
            )}
            <div className="nav-cta-group">
              <a href="/apply/purchase" className="nav-cta primary">{ctaText}</a>
              <a href="/apply/refinance" className="nav-cta secondary">Refinance</a>
            </div>
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

      {/* Main Content with AI Chat and Sidebar */}
      <div className="bold-impact-main-content">
        {/* AI Chat Section - Claude-style embedded chat */}
        <div className="bold-impact-chat-container">
          <EmbeddedAIChat
            userSlug={user?.slug}
            loName={loName}
            themeConfig={themeConfig}
          />
        </div>

        {/* Right Sidebar with Action Cards */}
        <aside className="bold-impact-sidebar">
          {/* Schedule Appointment Card */}
          <div className="sidebar-card">
            <div className="sidebar-card-icon schedule-icon">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <rect x="3" y="4" width="18" height="18" rx="2" ry="2"/>
                <line x1="16" y1="2" x2="16" y2="6"/>
                <line x1="8" y1="2" x2="8" y2="6"/>
                <line x1="3" y1="10" x2="21" y2="10"/>
              </svg>
            </div>
            <p className="sidebar-card-text">Have questions? Schedule a call with me.</p>
            <a href={calendlyUrl || `/schedule/${user?.slug || ''}`} className="sidebar-card-btn schedule-btn-action">
              Schedule with {loName.split(' ')[0]}
            </a>
          </div>

          {/* Compare Estimates Card */}
          <div className="sidebar-card">
            <div className="sidebar-card-icon compare-icon">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/>
                <rect x="8" y="2" width="8" height="4" rx="1" ry="1"/>
                <path d="M9 14l2 2 4-4"/>
              </svg>
            </div>
            <p className="sidebar-card-text">Shopping for a home loan? Upload your estimates and I'll compare them for you.</p>
            <a href="/estimate-comparison" className="sidebar-card-btn compare-btn">
              Compare Loan Estimates
            </a>
          </div>

          {/* Refinance Card */}
          <div className="sidebar-card">
            <div className="sidebar-card-icon refinance-icon">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>
                <polyline points="9 22 9 12 15 12 15 22"/>
              </svg>
            </div>
            <p className="sidebar-card-text">Lower your rate or tap into your home's equity.</p>
            <a href="/apply/refinance" className="sidebar-card-btn refinance-btn">
              Refinance Your Home
            </a>
          </div>

          {/* Purchase Application Card */}
          <div className="sidebar-card">
            <div className="sidebar-card-icon purchase-icon">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/>
                <polyline points="22 4 12 14.01 9 11.01"/>
              </svg>
            </div>
            <p className="sidebar-card-text">Become a bulletproof buyer with a fully underwritten pre-approval.</p>
            <a href="/apply/purchase" className="sidebar-card-btn purchase-btn">
              Get Pre-Approved
            </a>
          </div>
        </aside>
      </div>

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
