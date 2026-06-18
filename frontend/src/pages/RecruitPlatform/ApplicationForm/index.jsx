import React, { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import './ApplicationForm.css';

const API_BASE = import.meta.env.VITE_API_URL || 'https://api.perenniaai.com';

const EXPERIENCE_OPTIONS = ['0-1 years', '2-5 years', '5-10 years', '10+ years'];
const PRODUCTION_OPTIONS = ['Under $10M', '$10-30M', '$30-75M', '$75M+', 'N/A'];
const SOURCE_OPTIONS = ['LinkedIn', 'Indeed', 'Referral', 'Social Media', 'Company Website', 'Other'];

export default function ApplicationForm() {
  const { orgSlug } = useParams();
  const [org, setOrg] = useState(null);
  const [orgLoading, setOrgLoading] = useState(true);
  const [orgNotFound, setOrgNotFound] = useState(false);

  const [form, setForm] = useState({
    first_name: '', last_name: '', email: '', phone: '',
    nmls_number: '', current_employer: '', years_experience: '', annual_production: '',
    linkedin_url: '', resume_url: '', message: '', source: '',
  });
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [duplicate, setDuplicate] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    fetch(`${API_BASE}/api/v1/recruit-platform/apply/${orgSlug}`)
      .then(r => {
        if (r.status === 404) { setOrgNotFound(true); return null; }
        return r.json();
      })
      .then(data => { if (data) setOrg(data); })
      .catch(() => setOrgNotFound(true))
      .finally(() => setOrgLoading(false));
  }, [orgSlug]);

  const set = (field) => (e) => setForm(f => ({ ...f, [field]: e.target.value }));

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    setError('');
    try {
      const res = await fetch(`${API_BASE}/api/v1/recruit-platform/apply/${orgSlug}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(form),
      });
      if (res.status === 409) { setDuplicate(true); return; }
      if (!res.ok) throw new Error('Something went wrong');
      setSubmitted(true);
    } catch {
      setError('Something went wrong. Please try again.');
    } finally {
      setSubmitting(false);
    }
  };

  if (orgLoading) {
    return <div className="af-loading">Loading...</div>;
  }

  if (orgNotFound) {
    return (
      <div className="af-page">
        <div className="af-container">
          <div className="af-inactive">
            <div className="af-inactive-icon">📋</div>
            <h2>This job posting is no longer active.</h2>
            <p>The position has been filled or the posting has been removed.</p>
          </div>
        </div>
      </div>
    );
  }

  if (submitted) {
    return (
      <div className="af-page">
        <div className="af-container">
          <div className="af-success">
            <div className="af-success-icon">✅</div>
            <h2>Application received!</h2>
            <p>We'll review your application and be in touch within 3-5 business days.</p>
          </div>
        </div>
      </div>
    );
  }

  if (duplicate) {
    return (
      <div className="af-page">
        <div className="af-container">
          <div className="af-success">
            <div className="af-success-icon">👋</div>
            <h2>Already on file</h2>
            <p>We already have an application on file with this email address. We'll be in touch!</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="af-page">
      <div className="af-container">
        {/* Org header */}
        <div className="af-org-header">
          <div className="af-org-logo">
            <svg width="32" height="32" viewBox="0 0 32 32" fill="none">
              <path d="M8 22V12a2 2 0 012-2h12a2 2 0 012 2v10" stroke="white" strokeWidth="2" strokeLinecap="round"/>
              <path d="M5 22h22" stroke="white" strokeWidth="2" strokeLinecap="round"/>
              <path d="M13 10V7a2 2 0 012-2h2a2 2 0 012 2v3" stroke="white" strokeWidth="2" strokeLinecap="round"/>
              <rect x="13" y="15" width="6" height="4" rx="1" stroke="white" strokeWidth="1.5"/>
            </svg>
          </div>
          <h1 className="af-org-name">{org?.name || 'Join Our Team'}</h1>
          {org?.description && <p className="af-org-tagline">{org.description}</p>}
        </div>

        <div className="af-card">
          <h2 className="af-card-title">Apply Now</h2>

          {error && <div className="af-error">{error}</div>}

          <form onSubmit={handleSubmit}>
            {/* Personal */}
            <div className="af-section">
              <div className="af-section-title">Personal Information</div>
              <div className="af-grid">
                <div className="af-field">
                  <label className="af-label">First Name *</label>
                  <input className="af-input" type="text" required value={form.first_name} onChange={set('first_name')} placeholder="Jane" />
                </div>
                <div className="af-field">
                  <label className="af-label">Last Name *</label>
                  <input className="af-input" type="text" required value={form.last_name} onChange={set('last_name')} placeholder="Doe" />
                </div>
                <div className="af-field">
                  <label className="af-label">Email *</label>
                  <input className="af-input" type="email" required value={form.email} onChange={set('email')} placeholder="jane@example.com" />
                </div>
                <div className="af-field">
                  <label className="af-label">Phone *</label>
                  <input className="af-input" type="tel" required value={form.phone} onChange={set('phone')} placeholder="(555) 555-5555" />
                </div>
              </div>
            </div>

            {/* Professional */}
            <div className="af-section">
              <div className="af-section-title">Professional Background</div>
              <div className="af-grid">
                <div className="af-field">
                  <label className="af-label">
                    NMLS Number
                    <span className="af-optional">(optional)</span>
                    <span className="af-tooltip" data-tip="Your NMLS ID if you are a licensed mortgage professional">?</span>
                  </label>
                  <input className="af-input" type="text" value={form.nmls_number} onChange={set('nmls_number')} placeholder="e.g. 1234567" />
                </div>
                <div className="af-field">
                  <label className="af-label">Current Employer</label>
                  <input className="af-input" type="text" value={form.current_employer} onChange={set('current_employer')} placeholder="Company name" />
                </div>
                <div className="af-field">
                  <label className="af-label">Years of Experience *</label>
                  <select className="af-select" required value={form.years_experience} onChange={set('years_experience')}>
                    <option value="">Select...</option>
                    {EXPERIENCE_OPTIONS.map(o => <option key={o} value={o}>{o}</option>)}
                  </select>
                </div>
                <div className="af-field">
                  <label className="af-label">Annual Production Volume</label>
                  <select className="af-select" value={form.annual_production} onChange={set('annual_production')}>
                    <option value="">Select...</option>
                    {PRODUCTION_OPTIONS.map(o => <option key={o} value={o}>{o}</option>)}
                  </select>
                </div>
              </div>
            </div>

            {/* Links */}
            <div className="af-section">
              <div className="af-section-title">Links</div>
              <div className="af-grid">
                <div className="af-field">
                  <label className="af-label">LinkedIn URL <span className="af-optional">(optional)</span></label>
                  <input className="af-input" type="url" value={form.linkedin_url} onChange={set('linkedin_url')} placeholder="https://linkedin.com/in/..." />
                </div>
                <div className="af-field">
                  <label className="af-label">Resume URL <span className="af-optional">(optional)</span></label>
                  <input className="af-input" type="url" value={form.resume_url} onChange={set('resume_url')} placeholder="Link to Google Drive, Dropbox, etc." />
                </div>
              </div>
            </div>

            {/* Message */}
            <div className="af-section">
              <div className="af-section-title">Additional Info</div>
              <div className="af-grid">
                <div className="af-field full">
                  <label className="af-label">Anything you'd like us to know? <span className="af-optional">(optional)</span></label>
                  <textarea className="af-textarea" value={form.message} onChange={set('message')} placeholder="Tell us about yourself, your goals, or why you're interested..." />
                </div>
                <div className="af-field full">
                  <label className="af-label">How did you hear about us? *</label>
                  <select className="af-select" required value={form.source} onChange={set('source')}>
                    <option value="">Select...</option>
                    {SOURCE_OPTIONS.map(o => <option key={o} value={o}>{o}</option>)}
                  </select>
                </div>
              </div>
            </div>

            <div className="af-submit-row">
              <button type="submit" disabled={submitting} className="af-submit-btn">
                {submitting ? 'Submitting...' : 'Submit Application'}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}
