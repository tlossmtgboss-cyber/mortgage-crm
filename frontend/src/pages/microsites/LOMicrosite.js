/**
 * LOMicrosite - Loan Officer Personal Microsite
 * Clean home page with hero section only
 */
import React, { useState, useEffect } from 'react';
import { useParams, useSearchParams } from 'react-router-dom';
import { sanitizeHTML } from '../../utils/sanitize';
import './LOMicrosite.css';
import MortgageAIChat from '../../components/MortgageAIChat';

const API_BASE = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
  ? (process.env.REACT_APP_API_URL || 'http://localhost:8000')
  : 'https://api.perenniaai.com';

const LOMicrosite = () => {
  const { userId, slug, pageSlug } = useParams();
  const [searchParams] = useSearchParams();
  const [loProfile, setLoProfile] = useState(null);
  const [themeData, setThemeData] = useState(null);
  const [pages, setPages] = useState([]);
  const [activePage, setActivePage] = useState(pageSlug || 'home');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

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
  const loPhoto = themeData?.themeConfig?.heroImageUrl || loProfile?.photo_url || loProfile?.avatar_url || themeData?.user?.photo_url || null;
  const loLogo = themeData?.themeConfig?.logoUrl || null;
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
              <div className="testimonials-header">
                <h2>{content.headline || currentPage.title}</h2>
                {content.subheadline && <p className="section-subtitle">{content.subheadline}</p>}
              </div>

              {/* Stats Section */}
              {content.stats && (
                <div className="testimonials-stats">
                  {content.stats.totalClients && (
                    <div className="stat-item">
                      <span className="stat-value">{content.stats.totalClients}</span>
                      <span className="stat-label">Happy Clients</span>
                    </div>
                  )}
                  {content.stats.avgRating && (
                    <div className="stat-item">
                      <span className="stat-value">{content.stats.avgRating}</span>
                      <span className="stat-label">Average Rating</span>
                    </div>
                  )}
                  {content.stats.yearsExperience && (
                    <div className="stat-item">
                      <span className="stat-value">{content.stats.yearsExperience}</span>
                      <span className="stat-label">Years Experience</span>
                    </div>
                  )}
                </div>
              )}

              {content.testimonials?.length > 0 ? (
                <div className="testimonials-grid">
                  {content.testimonials.map((testimonial, idx) => (
                    <div key={idx} className="testimonial-card">
                      <div className="testimonial-rating">
                        {[...Array(testimonial.rating || 5)].map((_, i) => (
                          <svg key={i} viewBox="0 0 24 24" fill="currentColor" className="star-icon">
                            <path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"/>
                          </svg>
                        ))}
                      </div>
                      <p className="testimonial-text">"{testimonial.text}"</p>
                      <div className="testimonial-author">
                        <strong>{testimonial.name}</strong>
                        <div className="author-details">
                          {testimonial.type && <span className="testimonial-type">{testimonial.type}</span>}
                          {testimonial.location && <span className="testimonial-location">{testimonial.location}</span>}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="no-content">Client testimonials coming soon!</p>
              )}

              {content.cta && (
                <div className="testimonials-cta">
                  <h3>{content.cta.headline}</h3>
                  <p>{content.cta.text}</p>
                  <button onClick={() => navigateToPage('home')} className="btn-primary">
                    {content.cta.buttonText || 'Get Started'}
                  </button>
                </div>
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
              {content.text && <div dangerouslySetInnerHTML={{ __html: sanitizeHTML(content.text, { allowedTags: ['p', 'br', 'strong', 'em', 'b', 'i', 'u', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'ul', 'ol', 'li', 'a', 'span', 'div'] }) }} />}
            </div>
          </section>
        );
    }
  };

  return (
    <div className="lo-microsite" style={themeData?.themeConfig ? {
      '--lo-primary': themeData.themeConfig.primaryColor || '#c9a227',
      '--lo-secondary': themeData.themeConfig.secondaryColor || '#1f2937',
      '--lo-accent': themeData.themeConfig.accentColor || '#2D7A52',
      '--lo-background': themeData.themeConfig.backgroundColor || '#ffffff',
      '--lo-text': themeData.themeConfig.textColor || '#1a1a1a'
    } : {}}>

      {/* Navigation Bar - shown when pages exist */}
      {hasPages && (
        <nav className="lo-nav">
          <div className="container">
            <div className="nav-brand" onClick={() => navigateToPage('home')}>
              {loLogo ? (
                <img src={loLogo} alt={loName} className="nav-logo" />
              ) : (
                loName
              )}
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
            <button onClick={() => { setActivePage('services'); window.history.pushState({}, '', `/lo/${slug || userId}/services`); }} className="btn-primary">View Loan Programs</button>
            {loPhone && <a href={`tel:${loPhone}`} className="btn-secondary">Call Now</a>}
          </div>
        </div>
      </header>
      )}

      {/* Render page content for non-home pages */}
      {activePage !== 'home' && renderPageContent()}

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
