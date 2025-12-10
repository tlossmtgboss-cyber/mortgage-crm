import React, { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import './LOMicrosite.css';

const API_BASE = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
  ? (process.env.REACT_APP_API_URL || 'http://localhost:8000')
  : 'https://mortgage-crm-production-7a9a.up.railway.app';

const LOMicrosite = () => {
  const { userId, slug } = useParams();
  const [loProfile, setLoProfile] = useState(null);
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
  }, [userId, slug]);

  const fetchLoProfile = async () => {
    try {
      const identifier = slug || userId;
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
      <div className="lo-microsite-error">
        <h2>Profile Not Found</h2>
        <p>{error}</p>
      </div>
    );
  }

  const loName = loProfile?.name || `${loProfile?.first_name || ''} ${loProfile?.last_name || ''}`.trim() || 'Loan Officer';
  const loPhoto = loProfile?.photo_url || loProfile?.avatar_url || null;
  const loCompany = loProfile?.company || 'Mortgage Lending';
  const loNmls = loProfile?.nmls_id;
  const loBio = loProfile?.bio || `Hi, I'm ${loName}. I'm dedicated to helping you find the perfect mortgage solution for your needs. Whether you're buying your first home or refinancing, I'm here to guide you every step of the way.`;
  const loPhone = loProfile?.phone;
  const loEmail = loProfile?.email;

  return (
    <div className="lo-microsite">
      {/* Hero Section */}
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

      {/* About Section */}
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

      {/* Services Section */}
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

      {/* Contact Form Section */}
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
    </div>
  );
};

export default LOMicrosite;
