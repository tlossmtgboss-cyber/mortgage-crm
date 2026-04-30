import React, { useState } from 'react';
import axios from 'axios';
import './BetaApplication.css';

/**
 * BetaApplication - Landing page for beta program applications
 * Collects company info, pain points, and use cases
 */
const BetaApplication = () => {
  const [formData, setFormData] = useState({
    company_name: '',
    contact_name: '',
    email: '',
    phone: '',
    team_size: '',
    current_crm: '',
    monthly_loans: '',
    pain_points: '',
    use_cases: '',
    referral_source: ''
  });

  const [submitted, setSubmitted] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const handleChange = (e) => {
    const { name, value } = e.target;
    setFormData(prev => ({ ...prev, [name]: value }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError(null);

    try {
      await axios.post('/api/v1/beta/apply', formData);
      setSubmitted(true);
    } catch (err) {
      console.error('Beta application error:', err);
      setError('Error submitting application. Please try again or email support@perenniaai.com');
    } finally {
      setLoading(false);
    }
  };

  if (submitted) {
    return (
      <div className="beta-success-page">
        <div className="success-content">
          <div className="success-icon">✅</div>
          <h1>Application Received!</h1>
          <p className="success-subtitle">
            Thank you for your interest in Perennia AI UVIP beta.
          </p>
          <p>We'll review your application and reach out within 2 business days.</p>

          <div className="next-steps-card">
            <h3>What happens next?</h3>
            <ol>
              <li>
                <span className="step-icon">📋</span>
                <span>Our team reviews your application</span>
              </li>
              <li>
                <span className="step-icon">📞</span>
                <span>We'll schedule a 15-minute demo call</span>
              </li>
              <li>
                <span className="step-icon">🚀</span>
                <span>You get instant access to UVIP</span>
              </li>
              <li>
                <span className="step-icon">💬</span>
                <span>Weekly check-ins to gather feedback</span>
              </li>
            </ol>
          </div>

          <div className="contact-info">
            <p>
              Questions? Email{' '}
              <a href="mailto:support@perenniaai.com">support@perenniaai.com</a>
            </p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="beta-application-page">
      <div className="beta-header">
        <div className="logo">Perennia AI</div>
        <h1>Join Perennia AI UVIP Beta</h1>
        <p className="subtitle">
          Help shape the future of mortgage conversation intelligence
        </p>

        <div className="benefits">
          <div className="benefit">
            <span className="benefit-icon">🎯</span>
            <div>
              <strong>Early Access</strong>
              <p>Be first to use AI-powered video intelligence</p>
            </div>
          </div>
          <div className="benefit">
            <span className="benefit-icon">💰</span>
            <div>
              <strong>Free During Beta</strong>
              <p>No cost while you help us improve the product</p>
            </div>
          </div>
          <div className="benefit">
            <span className="benefit-icon">🤝</span>
            <div>
              <strong>Direct Influence</strong>
              <p>Your feedback shapes product development</p>
            </div>
          </div>
          <div className="benefit">
            <span className="benefit-icon">🏆</span>
            <div>
              <strong>Lifetime Discount</strong>
              <p>Special pricing when you go live</p>
            </div>
          </div>
        </div>
      </div>

      <form className="beta-form" onSubmit={handleSubmit}>
        {error && (
          <div className="error-message">
            <span>⚠️</span>
            {error}
          </div>
        )}

        <div className="form-section">
          <h2>Company Information</h2>

          <div className="form-group">
            <label htmlFor="company_name">Company Name *</label>
            <input
              type="text"
              id="company_name"
              name="company_name"
              value={formData.company_name}
              onChange={handleChange}
              required
              placeholder="Acme Mortgage"
            />
          </div>

          <div className="form-row">
            <div className="form-group">
              <label htmlFor="contact_name">Your Name *</label>
              <input
                type="text"
                id="contact_name"
                name="contact_name"
                value={formData.contact_name}
                onChange={handleChange}
                required
                placeholder="John Smith"
              />
            </div>

            <div className="form-group">
              <label htmlFor="email">Email *</label>
              <input
                type="email"
                id="email"
                name="email"
                value={formData.email}
                onChange={handleChange}
                required
                placeholder="john@acmemortgage.com"
              />
            </div>
          </div>

          <div className="form-row">
            <div className="form-group">
              <label htmlFor="phone">Phone</label>
              <input
                type="tel"
                id="phone"
                name="phone"
                value={formData.phone}
                onChange={handleChange}
                placeholder="(555) 123-4567"
              />
            </div>

            <div className="form-group">
              <label htmlFor="team_size">Team Size *</label>
              <select
                id="team_size"
                name="team_size"
                value={formData.team_size}
                onChange={handleChange}
                required
              >
                <option value="">Select...</option>
                <option value="1-5">1-5 Loan Officers</option>
                <option value="6-10">6-10 Loan Officers</option>
                <option value="11-25">11-25 Loan Officers</option>
                <option value="26-50">26-50 Loan Officers</option>
                <option value="51+">51+ Loan Officers</option>
              </select>
            </div>
          </div>

          <div className="form-row">
            <div className="form-group">
              <label htmlFor="current_crm">Current CRM</label>
              <input
                type="text"
                id="current_crm"
                name="current_crm"
                value={formData.current_crm}
                onChange={handleChange}
                placeholder="e.g., Encompass, Salesforce, Custom"
              />
            </div>

            <div className="form-group">
              <label htmlFor="monthly_loans">Monthly Loan Volume</label>
              <select
                id="monthly_loans"
                name="monthly_loans"
                value={formData.monthly_loans}
                onChange={handleChange}
              >
                <option value="">Select...</option>
                <option value="1-10">1-10 loans/month</option>
                <option value="11-25">11-25 loans/month</option>
                <option value="26-50">26-50 loans/month</option>
                <option value="51-100">51-100 loans/month</option>
                <option value="100+">100+ loans/month</option>
              </select>
            </div>
          </div>
        </div>

        <div className="form-section">
          <h2>Tell Us About Your Needs</h2>

          <div className="form-group">
            <label htmlFor="pain_points">
              What's your biggest pain point with current tools?
            </label>
            <textarea
              id="pain_points"
              name="pain_points"
              value={formData.pain_points}
              onChange={handleChange}
              rows={4}
              placeholder="e.g., Manual call notes take too long, borrowers don't read emails, no visibility into team performance..."
            />
          </div>

          <div className="form-group">
            <label htmlFor="use_cases">How would you use video intelligence?</label>
            <textarea
              id="use_cases"
              name="use_cases"
              value={formData.use_cases}
              onChange={handleChange}
              rows={4}
              placeholder="e.g., Record rate lock explanations, coach new LOs, track compliance, send video updates to borrowers..."
            />
          </div>

          <div className="form-group">
            <label htmlFor="referral_source">How did you hear about us?</label>
            <select
              id="referral_source"
              name="referral_source"
              value={formData.referral_source}
              onChange={handleChange}
            >
              <option value="">Select...</option>
              <option value="search">Google/Search</option>
              <option value="referral">Referral from colleague</option>
              <option value="social">Social media</option>
              <option value="event">Conference/Event</option>
              <option value="other">Other</option>
            </select>
          </div>
        </div>

        <button type="submit" className="submit-button" disabled={loading}>
          {loading ? (
            <>
              <span className="spinner"></span>
              Submitting...
            </>
          ) : (
            'Apply for Beta Access'
          )}
        </button>

        <p className="privacy-note">
          We'll never share your information. Beta spots are limited - apply today!
        </p>
      </form>

      <footer className="beta-footer">
        <p>
          &copy; {new Date().getFullYear()} Perennia AI. All rights reserved.
        </p>
        <div className="footer-links">
          <a href="/privacy">Privacy Policy</a>
          <a href="/terms">Terms of Service</a>
        </div>
      </footer>
    </div>
  );
};

export default BetaApplication;
