import React, { useState, useEffect } from 'react';
import { useParams, useSearchParams } from 'react-router-dom';
import './LOMicrosite.css';
import MortgageAIChat from '../../components/MortgageAIChat';

const API_BASE = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
  ? (process.env.REACT_APP_API_URL || 'http://localhost:8000')
  : 'https://mortgage-crm-production-7a9a.up.railway.app';

const LOMicrosite = () => {
  const { userId, slug, pageSlug } = useParams();
  const [searchParams] = useSearchParams();
  const [loProfile, setLoProfile] = useState(null);
  const [themeData, setThemeData] = useState(null);
  const [pages, setPages] = useState([]);
  const [activePage, setActivePage] = useState(pageSlug || 'home');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [formData, setFormData] = useState({
    first_name: '',
    last_name: '',
    email: '',
    phone: '',
    property_type: '',
    loan_type: 'purchase',
    estimated_value: '',
    down_payment: '',
    credit_score_range: '',
    timeline: '',
    message: ''
  });
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);

  useEffect(() => {
    fetchLoProfile();
    fetchThemeData();
    fetchPages();
  }, [userId, slug]);

  // Update active page when URL changes
  useEffect(() => {
    if (pageSlug) {
      setActivePage(pageSlug);
    }
  }, [pageSlug]);

  const fetchLoProfile = async () => {
    try {
      const identifier = slug || userId;

      // If no identifier provided, show helpful error
      if (!identifier) {
        setError('No loan officer specified. Please use a valid microsite URL like /lo/john-smith');
        setLoading(false);
        return;
      }

      const response = await fetch(`${API_BASE}/api/v1/public/loan-officer/${identifier}`);
      if (response.ok) {
        const data = await response.json();
        setLoProfile(data);
      } else {
        setError('Loan officer profile not found');
      }
    } catch (err) {
      console.error('Error fetching LO profile:', err);
      setError('Unable to load profile');
    } finally {
      setLoading(false);
    }
  };

  const fetchThemeData = async () => {
    try {
      const identifier = slug || userId;
      if (!identifier) return;

      const response = await fetch(`${API_BASE}/api/v1/public/themes/render/${identifier}`);
      if (response.ok) {
        const data = await response.json();
        setThemeData(data);
        // Apply theme colors as CSS variables
        if (data.themeConfig) {
          const root = document.documentElement;
          if (data.themeConfig.primaryColor) root.style.setProperty('--lo-primary', data.themeConfig.primaryColor);
          if (data.themeConfig.secondaryColor) root.style.setProperty('--lo-secondary', data.themeConfig.secondaryColor);
          if (data.themeConfig.accentColor) root.style.setProperty('--lo-accent', data.themeConfig.accentColor);
          if (data.themeConfig.backgroundColor) root.style.setProperty('--lo-background', data.themeConfig.backgroundColor);
          if (data.themeConfig.textColor) root.style.setProperty('--lo-text', data.themeConfig.textColor);
        }
      }
    } catch (err) {
      console.error('Error fetching theme data:', err);
    }
  };

  const fetchPages = async () => {
    try {
      const identifier = slug || userId;
      if (!identifier) return;

      const response = await fetch(`${API_BASE}/api/v1/public/themes/render/${identifier}/pages`);
      if (response.ok) {
        const data = await response.json();
        setPages(data.pages || []);
      }
    } catch (err) {
      console.error('Error fetching pages:', err);
    }
  };

  const handleInputChange = (e) => {
    const { name, value } = e.target;
    setFormData(prev => ({ ...prev, [name]: value }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSubmitting(true);

    try {
      const response = await fetch(`${API_BASE}/api/v1/public/leads`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...formData,
          source: 'microsite',
          loan_officer_id: loProfile?.id,
          referral_source: `lo_microsite_${loProfile?.id}`,
          utm_source: 'microsite',
          utm_medium: 'lo_page',
          utm_campaign: loProfile?.slug || loProfile?.id
        })
      });

      if (response.ok) {
        setSubmitted(true);
      } else {
        throw new Error('Failed to submit');
      }
    } catch (err) {
      console.error('Error submitting lead:', err);
      alert('There was an error submitting your request. Please try again.');
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return (
      <div className="lo-microsite-loading">
        <div className="loading-spinner"></div>
        <p>Loading...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="lo-microsite-error" style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        minHeight: '100vh',
        padding: '40px',
        textAlign: 'center',
        background: 'linear-gradient(135deg, #f5f7fa 0%, #e4e8ec 100%)'
      }}>
        <div style={{
          background: 'white',
          padding: '60px',
          borderRadius: '16px',
          boxShadow: '0 10px 40px rgba(0,0,0,0.1)',
          maxWidth: '500px'
        }}>
          <div style={{ fontSize: '64px', marginBottom: '20px' }}>🏠</div>
          <h2 style={{ fontSize: '28px', color: '#374151', marginBottom: '16px' }}>Profile Not Found</h2>
          <p style={{ color: '#6b7280', fontSize: '16px', lineHeight: '1.6' }}>{error}</p>
          <p style={{ color: '#9ca3af', fontSize: '14px', marginTop: '24px' }}>
            Looking for a loan officer? Contact your mortgage company for the correct link.
          </p>
        </div>
      </div>
    );
  }

  const loName = loProfile?.name || themeData?.user?.name || `${loProfile?.first_name || ''} ${loProfile?.last_name || ''}`.trim() || 'Loan Officer';
  const loPhoto = loProfile?.photo_url || loProfile?.avatar_url || themeData?.user?.photo_url || null;
  const loCompany = loProfile?.company || themeData?.user?.company || 'Mortgage Lending';
  const loNmls = loProfile?.nmls_id || themeData?.user?.nmls_id;
  const loBio = loProfile?.bio || themeData?.user?.bio || themeData?.profile?.bioExtended || `Hi, I'm ${loName}. I'm dedicated to helping you find the perfect mortgage solution for your needs. Whether you're buying your first home or refinancing, I'm here to guide you every step of the way.`;
  const loPhone = loProfile?.phone || themeData?.user?.phone;
  const loEmail = loProfile?.email || themeData?.user?.email;

  // Navigation items - only show pages that should be in nav
  const navPages = pages.filter(p => p.showInNav);
  const hasPages = navPages.length > 0;

  // Get current page content
  const currentPage = pages.find(p => p.slug === activePage);

  // Handle page navigation
  const navigateToPage = (pageSlug) => {
    setActivePage(pageSlug);
    // Update URL without full page reload
    const identifier = slug || userId;
    if (pageSlug === 'home') {
      window.history.pushState({}, '', `/lo/${identifier}`);
    } else {
      window.history.pushState({}, '', `/lo/${identifier}/${pageSlug}`);
    }
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  // Render page-specific content
  const renderPageContent = () => {
    if (!currentPage) return null;

    const content = currentPage.content || {};

    switch (currentPage.pageType) {
      case 'about':
        return (
          <section className="lo-page-content about-page">
            <div className="container">
              <h2>{currentPage.title}</h2>
              {content.sections?.map((section, idx) => (
                <div key={idx} className={`about-section ${section.type}`}>
                  {section.type === 'bio' && (
                    <>
                      <h3>{section.heading}</h3>
                      <p>{section.text || loBio}</p>
                    </>
                  )}
                  {section.type === 'experience' && (
                    <>
                      <h3>{section.heading}</h3>
                      <div className="experience-stats">
                        {section.yearsExperience && (
                          <div className="stat-card">
                            <span className="stat-value">{section.yearsExperience}+</span>
                            <span className="stat-label">Years Experience</span>
                          </div>
                        )}
                        {section.loansFunded && (
                          <div className="stat-card">
                            <span className="stat-value">{section.loansFunded.toLocaleString()}</span>
                            <span className="stat-label">Loans Funded</span>
                          </div>
                        )}
                        {section.volumeFunded && (
                          <div className="stat-card">
                            <span className="stat-value">${(section.volumeFunded / 1000000).toFixed(0)}M+</span>
                            <span className="stat-label">Volume Funded</span>
                          </div>
                        )}
                      </div>
                    </>
                  )}
                  {section.type === 'certifications' && section.items?.length > 0 && (
                    <>
                      <h3>{section.heading}</h3>
                      <ul className="certifications-list">
                        {section.items.map((cert, i) => (
                          <li key={i}>{cert}</li>
                        ))}
                      </ul>
                    </>
                  )}
                </div>
              ))}
            </div>
          </section>
        );

      case 'services':
        return (
          <section className="lo-page-content services-page">
            <div className="container">
              <div className="services-header">
                <h2>{content.headline || currentPage.title}</h2>
                {content.subheadline && <p className="section-subtitle">{content.subheadline}</p>}
              </div>
              <div className="services-grid">
                {content.programs?.map((program, idx) => (
                  <div key={idx} className="service-card">
                    <div className="service-icon">
                      {program.icon === 'home' && (
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                          <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>
                          <polyline points="9 22 9 12 15 12 15 22"/>
                        </svg>
                      )}
                      {program.icon === 'shield' && (
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                          <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
                        </svg>
                      )}
                      {program.icon === 'star' && (
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                          <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>
                        </svg>
                      )}
                      {program.icon === 'tree' && (
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                          <path d="M12 22v-7"/>
                          <path d="M9 22h6"/>
                          <path d="M12 15l-6-6h3l-4-5h5l-3-3 8 8h-3l5 6z"/>
                        </svg>
                      )}
                      {program.icon === 'building' && (
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                          <rect x="4" y="2" width="16" height="20" rx="2" ry="2"/>
                          <path d="M9 22v-4h6v4"/>
                          <path d="M8 6h.01M16 6h.01M12 6h.01M8 10h.01M16 10h.01M12 10h.01M8 14h.01M16 14h.01M12 14h.01"/>
                        </svg>
                      )}
                      {program.icon === 'refresh' && (
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                          <polyline points="23 4 23 10 17 10"/>
                          <polyline points="1 20 1 14 7 14"/>
                          <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>
                        </svg>
                      )}
                      {!['home', 'shield', 'star', 'tree', 'building', 'refresh'].includes(program.icon) && (
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                          <line x1="12" y1="1" x2="12" y2="23"/>
                          <path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/>
                        </svg>
                      )}
                    </div>
                    <h3>{program.name}</h3>
                    <p className="service-description">{program.description}</p>
                    {program.features && program.features.length > 0 && (
                      <ul className="service-features">
                        {program.features.map((feature, fidx) => (
                          <li key={fidx}>
                            <svg viewBox="0 0 24 24" fill="currentColor">
                              <path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"/>
                            </svg>
                            {feature}
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                ))}
              </div>
              {content.cta && (
                <div className="services-cta">
                  <h3>{content.cta.headline}</h3>
                  <p>{content.cta.text}</p>
                  <a href="#contact" className="btn-primary" onClick={(e) => { e.preventDefault(); setActivePage('home'); setTimeout(() => document.getElementById('contact')?.scrollIntoView({ behavior: 'smooth' }), 100); }}>
                    {content.cta.buttonText || 'Get Started'}
                  </a>
                </div>
              )}
            </div>
          </section>
        );

      case 'testimonials':
        return (
          <section className="lo-page-content testimonials-page">
            <div className="container">
              <h2>{content.heading || currentPage.title}</h2>
              {content.description && <p className="section-subtitle">{content.description}</p>}
              {content.testimonials?.length > 0 ? (
                <div className="testimonials-grid">
                  {content.testimonials.map((testimonial, idx) => (
                    <div key={idx} className="testimonial-card">
                      <div className="testimonial-quote">"</div>
                      <p className="testimonial-text">{testimonial.text}</p>
                      <div className="testimonial-author">
                        <strong>{testimonial.name}</strong>
                        {testimonial.location && <span>{testimonial.location}</span>}
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="no-content">Client testimonials coming soon!</p>
              )}
            </div>
          </section>
        );

      case 'blog':
        return (
          <section className="lo-page-content blog-page">
            <div className="container">
              <h2>{content.heading || currentPage.title}</h2>
              {content.description && <p className="section-subtitle">{content.description}</p>}
              {content.posts?.length > 0 ? (
                <div className="blog-grid">
                  {content.posts.map((post, idx) => (
                    <div key={idx} className="blog-card">
                      {post.image && <img src={post.image} alt={post.title} />}
                      <div className="blog-content">
                        <h3>{post.title}</h3>
                        <p>{post.excerpt}</p>
                        {post.date && <span className="blog-date">{post.date}</span>}
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="no-content">Blog posts coming soon! Check back for mortgage tips and market updates.</p>
              )}
            </div>
          </section>
        );

      default:
        return (
          <section className="lo-page-content custom-page">
            <div className="container">
              <h2>{currentPage.title}</h2>
              {content.text && <div dangerouslySetInnerHTML={{ __html: content.text }} />}
            </div>
          </section>
        );
    }
  };

  return (
    <div className="lo-microsite" style={themeData?.themeConfig ? {
      '--lo-primary': themeData.themeConfig.primaryColor || '#c9a227',
      '--lo-secondary': themeData.themeConfig.secondaryColor || '#1f2937',
      '--lo-accent': themeData.themeConfig.accentColor || '#059669',
      '--lo-background': themeData.themeConfig.backgroundColor || '#ffffff',
      '--lo-text': themeData.themeConfig.textColor || '#1a1a1a'
    } : {}}>

      {/* Navigation Bar - shown when pages exist */}
      {hasPages && (
        <nav className="lo-nav">
          <div className="container">
            <div className="nav-brand" onClick={() => navigateToPage('home')}>
              {loName}
            </div>
            <ul className="nav-links">
              <li>
                <button
                  className={activePage === 'home' ? 'active' : ''}
                  onClick={() => navigateToPage('home')}
                >
                  Home
                </button>
              </li>
              {navPages.map(page => (
                <li key={page.id}>
                  <button
                    className={activePage === page.slug ? 'active' : ''}
                    onClick={() => navigateToPage(page.slug)}
                  >
                    {page.title}
                  </button>
                </li>
              ))}
            </ul>
            <a href="#contact-form" className="nav-cta">Get Started</a>
          </div>
        </nav>
      )}

      {/* Hero Section - only on home page */}
      {activePage === 'home' && (
        <header className="lo-hero">
        <div className="lo-hero-content">
          <div className="lo-hero-profile">
            {loPhoto ? (
              <img src={loPhoto} alt={loName} className="lo-avatar" />
            ) : (
              <div className="lo-avatar-placeholder">
                {loName.charAt(0).toUpperCase()}
              </div>
            )}
            <div className="lo-hero-info">
              <h1>{loName}</h1>
              <p className="lo-title">Loan Officer</p>
              <p className="lo-company">{loCompany}</p>
              {loNmls && <p className="lo-nmls">NMLS# {loNmls}</p>}
            </div>
          </div>
          <div className="lo-hero-cta">
            <a href="#contact-form" className="btn-primary">Get Started</a>
            {loPhone && <a href={`tel:${loPhone}`} className="btn-secondary">Call Now</a>}
          </div>
        </div>
      </header>
      )}

      {/* Render page content for non-home pages */}
      {activePage !== 'home' && renderPageContent()}

      {/* About Section - only on home page */}
      {activePage === 'home' && (
      <section className="lo-about">
        <div className="container">
          <h2>About Me</h2>
          <p>{loBio}</p>
          <div className="lo-contact-info">
            {loPhone && (
              <div className="contact-item">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z"/>
                </svg>
                <a href={`tel:${loPhone}`}>{loPhone}</a>
              </div>
            )}
            {loEmail && (
              <div className="contact-item">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/>
                  <polyline points="22,6 12,13 2,6"/>
                </svg>
                <a href={`mailto:${loEmail}`}>{loEmail}</a>
              </div>
            )}
          </div>
        </div>
      </section>
      )}

      {/* Services Section - only on home page */}
      {activePage === 'home' && (
      <section className="lo-services">
        <div className="container">
          <h2>Services I Offer</h2>
          <div className="services-grid">
            <div className="service-card">
              <div className="service-icon">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>
                  <polyline points="9 22 9 12 15 12 15 22"/>
                </svg>
              </div>
              <h3>Home Purchase</h3>
              <p>First-time buyer or upgrading? I'll help you find the perfect loan.</p>
            </div>
            <div className="service-card">
              <div className="service-icon">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/>
                </svg>
              </div>
              <h3>Refinancing</h3>
              <p>Lower your rate or tap into equity. Let's explore your options.</p>
            </div>
            <div className="service-card">
              <div className="service-icon">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <rect x="1" y="4" width="22" height="16" rx="2" ry="2"/>
                  <line x1="1" y1="10" x2="23" y2="10"/>
                </svg>
              </div>
              <h3>Pre-Approval</h3>
              <p>Get pre-approved and shop with confidence.</p>
            </div>
            <div className="service-card">
              <div className="service-icon">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <circle cx="12" cy="12" r="10"/>
                  <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/>
                  <line x1="12" y1="17" x2="12.01" y2="17"/>
                </svg>
              </div>
              <h3>Expert Guidance</h3>
              <p>Answers to all your mortgage questions.</p>
            </div>
          </div>
        </div>
      </section>
      )}

      {/* Contact Form Section - always shown */}
      <section className="lo-contact" id="contact-form">
        <div className="container">
          <h2>Let's Get Started</h2>
          <p className="section-subtitle">Fill out the form below and I'll be in touch within 24 hours.</p>

          {submitted ? (
            <div className="success-message">
              <div className="success-icon">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3">
                  <path d="M5 13l4 4L19 7"/>
                </svg>
              </div>
              <h3>Thank You!</h3>
              <p>Your request has been submitted. {loName} will be in touch with you shortly.</p>
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="lead-capture-form">
              <div className="form-row">
                <div className="form-group">
                  <label htmlFor="first_name">First Name *</label>
                  <input
                    type="text"
                    id="first_name"
                    name="first_name"
                    value={formData.first_name}
                    onChange={handleInputChange}
                    required
                  />
                </div>
                <div className="form-group">
                  <label htmlFor="last_name">Last Name *</label>
                  <input
                    type="text"
                    id="last_name"
                    name="last_name"
                    value={formData.last_name}
                    onChange={handleInputChange}
                    required
                  />
                </div>
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label htmlFor="email">Email *</label>
                  <input
                    type="email"
                    id="email"
                    name="email"
                    value={formData.email}
                    onChange={handleInputChange}
                    required
                  />
                </div>
                <div className="form-group">
                  <label htmlFor="phone">Phone *</label>
                  <input
                    type="tel"
                    id="phone"
                    name="phone"
                    value={formData.phone}
                    onChange={handleInputChange}
                    required
                  />
                </div>
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label htmlFor="loan_type">I'm Looking To</label>
                  <select
                    id="loan_type"
                    name="loan_type"
                    value={formData.loan_type}
                    onChange={handleInputChange}
                  >
                    <option value="purchase">Purchase a Home</option>
                    <option value="refinance">Refinance</option>
                    <option value="cash_out">Cash-Out Refinance</option>
                    <option value="preapproval">Get Pre-Approved</option>
                  </select>
                </div>
                <div className="form-group">
                  <label htmlFor="timeline">Timeline</label>
                  <select
                    id="timeline"
                    name="timeline"
                    value={formData.timeline}
                    onChange={handleInputChange}
                  >
                    <option value="">Select...</option>
                    <option value="asap">ASAP</option>
                    <option value="1-3_months">1-3 Months</option>
                    <option value="3-6_months">3-6 Months</option>
                    <option value="6+_months">6+ Months</option>
                    <option value="just_exploring">Just Exploring</option>
                  </select>
                </div>
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label htmlFor="estimated_value">Estimated Property Value</label>
                  <select
                    id="estimated_value"
                    name="estimated_value"
                    value={formData.estimated_value}
                    onChange={handleInputChange}
                  >
                    <option value="">Select...</option>
                    <option value="under_200k">Under $200,000</option>
                    <option value="200k-400k">$200,000 - $400,000</option>
                    <option value="400k-600k">$400,000 - $600,000</option>
                    <option value="600k-800k">$600,000 - $800,000</option>
                    <option value="800k-1m">$800,000 - $1M</option>
                    <option value="over_1m">Over $1M</option>
                  </select>
                </div>
                <div className="form-group">
                  <label htmlFor="credit_score_range">Estimated Credit Score</label>
                  <select
                    id="credit_score_range"
                    name="credit_score_range"
                    value={formData.credit_score_range}
                    onChange={handleInputChange}
                  >
                    <option value="">Select...</option>
                    <option value="excellent">Excellent (740+)</option>
                    <option value="good">Good (700-739)</option>
                    <option value="fair">Fair (660-699)</option>
                    <option value="below_660">Below 660</option>
                    <option value="not_sure">Not Sure</option>
                  </select>
                </div>
              </div>

              <div className="form-group full-width">
                <label htmlFor="message">Additional Information</label>
                <textarea
                  id="message"
                  name="message"
                  value={formData.message}
                  onChange={handleInputChange}
                  rows="4"
                  placeholder="Tell me about your situation or any questions you have..."
                />
              </div>

              <button type="submit" className="btn-submit" disabled={submitting}>
                {submitting ? 'Submitting...' : 'Get My Free Quote'}
              </button>

              <p className="form-disclaimer">
                By submitting this form, you agree to be contacted about mortgage options.
                Your information is secure and will never be shared.
              </p>
            </form>
          )}
        </div>
      </section>

      {/* Footer */}
      <footer className="lo-footer">
        <div className="container">
          <p>&copy; {new Date().getFullYear()} {loName} | {loCompany}</p>
          {loNmls && <p>NMLS# {loNmls}</p>}
          <p className="footer-disclaimer">
            Equal Housing Lender. This is not a commitment to lend.
          </p>
        </div>
      </footer>

      {/* AI Mortgage Chat Assistant */}
      <MortgageAIChat
        userSlug={slug || userId}
        themeConfig={themeData?.themeConfig}
      />
    </div>
  );
};

export default LOMicrosite;
