/**
 * Bold Impact Theme
 *
 * A bold, modern theme with strong call-to-actions and lead capture focus.
 * Features prominent hero section, rate calculator, testimonials, and
 * comprehensive contact form.
 */

import React, { useState, useEffect } from 'react';
import './BoldImpact.css';
import EmbeddedAIChat from '../../../components/EmbeddedAIChat';

const BoldImpact = ({ user, profile, themeConfig = {} }) => {
  const [showLoginModal, setShowLoginModal] = useState(false);
  const [showSchedulerModal, setShowSchedulerModal] = useState(false);
  const [showCompareModal, setShowCompareModal] = useState(false);
  const [showRefinanceModal, setShowRefinanceModal] = useState(false);
  const [showPurchaseModal, setShowPurchaseModal] = useState(false);
  const [showCalculatorModal, setShowCalculatorModal] = useState(false);

  // Listen for messages from embedded iframes (application submissions)
  useEffect(() => {
    // Only accept postMessages from trusted origins
    const ALLOWED_ORIGINS = [
      window.location.origin,
      'https://app.perenniaai.com',
      'https://api.perenniaai.com',
    ];

    const handleMessage = (event) => {
      if (!ALLOWED_ORIGINS.includes(event.origin)) return;

      if (event.data?.type === 'APPLICATION_SUBMITTED') {
        // Close all modals when application is submitted
        setShowRefinanceModal(false);
        setShowPurchaseModal(false);
        setShowCompareModal(false);

        // Open the portal URL in a new tab if provided — validate URL safety
        if (event.data.portalUrl) {
          try {
            const url = new URL(event.data.portalUrl);
            if (['https:', 'http:'].includes(url.protocol)) {
              window.open(event.data.portalUrl, '_blank');
            }
          } catch {
            // Invalid URL — ignore
          }
        }
      }
    };

    window.addEventListener('message', handleMessage);
    return () => window.removeEventListener('message', handleMessage);
  }, []);

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
            <button
              className="nav-calculator-btn"
              onClick={() => setShowCalculatorModal(true)}
            >
              Calculator
            </button>
            <button
              className="nav-login-btn"
              onClick={() => setShowLoginModal(true)}
            >
              Log In
            </button>
          </div>
        </div>
      </nav>

      {/* Login Modal */}
      {showLoginModal && (
        <div className="login-modal-overlay" onClick={() => setShowLoginModal(false)}>
          <div className="login-modal" onClick={(e) => e.stopPropagation()}>
            <button className="login-modal-close" onClick={() => setShowLoginModal(false)}>
              ×
            </button>
            <h3 className="login-modal-title">Select Your Portal</h3>
            <div className="login-modal-options">
              <a href="/login" className="login-option loan-officer">
                <span className="login-option-title">Loan Officer</span>
                <span className="login-option-desc">Access the CRM dashboard</span>
              </a>
              <a href="/apply/login" className="login-option client">
                <span className="login-option-title">Client</span>
                <span className="login-option-desc">View your loan status</span>
              </a>
              <a href="/realtor-portal" className="login-option partner">
                <span className="login-option-title">Partner</span>
                <span className="login-option-desc">Realtor & referral partners</span>
              </a>
            </div>
          </div>
        </div>
      )}

      {/* Scheduler Modal - Public Booking Calendar */}
      {showSchedulerModal && (
        <div className="embedded-modal-overlay" onClick={() => setShowSchedulerModal(false)}>
          <div className="embedded-modal scheduler-modal-size" onClick={(e) => e.stopPropagation()}>
            <button className="embedded-modal-close" onClick={() => setShowSchedulerModal(false)}>
              ×
            </button>
            <iframe
              src={`/book/${user?.slug || 'tim-loss'}?embedded=true`}
              title="Schedule Appointment"
              className="embedded-modal-iframe"
            />
          </div>
        </div>
      )}

      {/* Compare Estimates Modal */}
      {showCompareModal && (
        <div className="embedded-modal-overlay" onClick={() => setShowCompareModal(false)}>
          <div className="embedded-modal" onClick={(e) => e.stopPropagation()}>
            <button className="embedded-modal-close" onClick={() => setShowCompareModal(false)}>
              ×
            </button>
            <iframe
              src="/estimate-comparison?embedded=true"
              title="Compare Loan Estimates"
              className="embedded-modal-iframe"
            />
          </div>
        </div>
      )}

      {/* Refinance Modal */}
      {showRefinanceModal && (
        <div className="embedded-modal-overlay" onClick={() => setShowRefinanceModal(false)}>
          <div className="embedded-modal" onClick={(e) => e.stopPropagation()}>
            <button className="embedded-modal-close" onClick={() => setShowRefinanceModal(false)}>
              ×
            </button>
            <iframe
              src="/apply/refinance?embedded=true"
              title="Refinance Application"
              className="embedded-modal-iframe"
            />
          </div>
        </div>
      )}

      {/* Purchase Modal */}
      {showPurchaseModal && (
        <div className="embedded-modal-overlay" onClick={() => setShowPurchaseModal(false)}>
          <div className="embedded-modal" onClick={(e) => e.stopPropagation()}>
            <button className="embedded-modal-close" onClick={() => setShowPurchaseModal(false)}>
              ×
            </button>
            <iframe
              src="/apply/purchase?embedded=true&fresh=true"
              title="Purchase Application"
              className="embedded-modal-iframe"
            />
          </div>
        </div>
      )}

      {/* Calculator Modal */}
      {showCalculatorModal && (
        <div className="embedded-modal-overlay" onClick={() => setShowCalculatorModal(false)}>
          <div className="embedded-modal calculator-modal" onClick={(e) => e.stopPropagation()}>
            <button className="embedded-modal-close" onClick={() => setShowCalculatorModal(false)}>
              ×
            </button>
            <iframe
              src="https://lendtelligent.replit.app/embed?partnerId=bbf8c77c-1add-4922-bb7a-f3779b6e8d06"
              title="Mortgage Calculator"
              className="embedded-modal-iframe calculator-iframe"
              scrolling="yes"
              frameBorder="0"
              allowFullScreen
            />
          </div>
        </div>
      )}

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
            <p className="sidebar-card-text">Have questions? Schedule a time for me to call you.</p>
            <button
              className="sidebar-card-btn schedule-btn-action"
              onClick={() => setShowSchedulerModal(true)}
            >
              Schedule with {loName.split(' ')[0]}
            </button>
          </div>

          {/* Compare Estimates Card */}
          <div className="sidebar-card">
            <p className="sidebar-card-text">Shopping for a home loan? Upload your estimates and I'll compare them for you.</p>
            <button
              className="sidebar-card-btn compare-btn"
              onClick={() => setShowCompareModal(true)}
            >
              Compare Loan Estimates
            </button>
          </div>

          {/* Refinance Card */}
          <div className="sidebar-card">
            <p className="sidebar-card-text">Lower your rate or tap into your home's equity.</p>
            <button
              className="sidebar-card-btn refinance-btn"
              onClick={() => setShowRefinanceModal(true)}
            >
              Refinance Your Home
            </button>
          </div>

          {/* Purchase Application Card */}
          <div className="sidebar-card">
            <p className="sidebar-card-text">Become a bulletproof buyer with a fully underwritten pre-approval.</p>
            <button
              className="sidebar-card-btn purchase-btn"
              onClick={() => setShowPurchaseModal(true)}
            >
              Get Pre-Approved
            </button>
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
