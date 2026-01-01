import React, { useState, useEffect, useCallback } from 'react';
import { useParams, useSearchParams } from 'react-router-dom';
import './RecruitPortal.css';
import ProductionCalculator from './ProductionCalculator';
import PortalChat from './PortalChat';
import PortalScheduler from './PortalScheduler';

const API_URL = process.env.REACT_APP_API_URL || 'https://api.perenniaai.com';

const RecruitPortal = () => {
  const { slug } = useParams();
  const [searchParams] = useSearchParams();
  const token = searchParams.get('token');

  const [portalData, setPortalData] = useState(null);
  const [companyUpdates, setCompanyUpdates] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [activeTab, setActiveTab] = useState('calculator');

  const fetchPortalData = useCallback(async () => {
    try {
      setLoading(true);
      const url = token
        ? `${API_URL}/api/v1/recruit-portal/purl/${slug}?token=${token}`
        : `${API_URL}/api/v1/recruit-portal/purl/${slug}`;

      const response = await fetch(url);
      if (!response.ok) {
        throw new Error('Portal not found');
      }
      const data = await response.json();
      setPortalData(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [slug, token]);

  const fetchCompanyUpdates = useCallback(async () => {
    try {
      const response = await fetch(`${API_URL}/api/v1/recruit-portal/purl/${slug}/updates?limit=10`);
      if (response.ok) {
        const data = await response.json();
        setCompanyUpdates(data.updates || []);
      }
    } catch (err) {
      console.error('Error fetching company updates:', err);
    }
  }, [slug]);

  useEffect(() => {
    fetchPortalData();
    fetchCompanyUpdates();
  }, [fetchPortalData, fetchCompanyUpdates]);

  if (loading) {
    return (
      <div className="recruit-portal-loading">
        <div className="loading-spinner"></div>
        <p>Loading your personalized portal...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="recruit-portal-error">
        <h2>Portal Access Error</h2>
        <p>{error}</p>
        <p>Please check your link or contact the recruiter.</p>
      </div>
    );
  }

  return (
    <div className="recruit-portal">
      {/* Header */}
      <header className="portal-header">
        <div className="portal-logo">
          <h1>Perennia</h1>
          <span className="tagline">{portalData?.company_tagline || 'Join the team that helps you succeed'}</span>
        </div>
        <div className="portal-user">
          <span className="user-name">Welcome, {portalData?.candidate_name || 'Candidate'}</span>
          {portalData?.candidate_status && (
            <span className={`status-badge status-${portalData.candidate_status}`}>
              {portalData.candidate_status.replace('_', ' ')}
            </span>
          )}
        </div>
      </header>

      {/* Hero Section */}
      <section className="portal-hero">
        <div className="hero-content">
          <h2>Your Path to Success Starts Here</h2>
          <p>
            {portalData?.next_steps ||
              'We believe in empowering loan officers with the best technology, leads, and support. See how joining our team can transform your business.'}
          </p>
        </div>
        {portalData?.recruiter_name && (
          <div className="recruiter-card">
            <div className="recruiter-photo">
              {portalData.recruiter_photo ? (
                <img src={portalData.recruiter_photo} alt={portalData.recruiter_name} />
              ) : (
                <div className="photo-placeholder">
                  {portalData.recruiter_name.split(' ').map(n => n[0]).join('')}
                </div>
              )}
            </div>
            <div className="recruiter-info">
              <h4>Your Recruiter</h4>
              <p className="recruiter-name">{portalData.recruiter_name}</p>
              {portalData.recruiter_phone && (
                <a href={`tel:${portalData.recruiter_phone}`} className="recruiter-contact">
                  {portalData.recruiter_phone}
                </a>
              )}
              {portalData.recruiter_email && (
                <a href={`mailto:${portalData.recruiter_email}`} className="recruiter-contact">
                  {portalData.recruiter_email}
                </a>
              )}
            </div>
          </div>
        )}
      </section>

      {/* Tab Navigation */}
      <nav className="portal-tabs">
        <button
          className={`tab-button ${activeTab === 'calculator' ? 'active' : ''}`}
          onClick={() => setActiveTab('calculator')}
        >
          Production Calculator
        </button>
        <button
          className={`tab-button ${activeTab === 'updates' ? 'active' : ''}`}
          onClick={() => setActiveTab('updates')}
        >
          Company News
        </button>
        <button
          className={`tab-button ${activeTab === 'schedule' ? 'active' : ''}`}
          onClick={() => setActiveTab('schedule')}
        >
          Schedule a Call
        </button>
      </nav>

      {/* Tab Content */}
      <main className="portal-content">
        {activeTab === 'calculator' && (
          <ProductionCalculator
            slug={slug}
            calculatorConfig={portalData?.calculator_config}
          />
        )}

        {activeTab === 'updates' && (
          <div className="updates-section">
            <h3>Latest from Perennia</h3>
            {companyUpdates.length > 0 ? (
              <div className="updates-grid">
                {companyUpdates.map((update, index) => (
                  <div key={update.id || index} className={`update-card ${update.is_featured ? 'featured' : ''}`}>
                    {update.media_url && (
                      <div className="update-media">
                        <img src={update.media_url} alt={update.title} />
                      </div>
                    )}
                    <div className="update-content">
                      <span className={`update-category category-${update.category}`}>
                        {update.category}
                      </span>
                      <h4>{update.title}</h4>
                      <p>{update.content}</p>
                      {update.published_at && (
                        <span className="update-date">
                          {new Date(update.published_at).toLocaleDateString()}
                        </span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="no-updates">
                <p>Check back soon for updates!</p>
              </div>
            )}
          </div>
        )}

        {activeTab === 'schedule' && (
          <PortalScheduler
            slug={slug}
            recruiterName={portalData?.recruiter_name}
          />
        )}
      </main>

      {/* AI Chat Widget */}
      <PortalChat
        slug={slug}
        candidateName={portalData?.candidate_name}
      />

      {/* Footer */}
      <footer className="portal-footer">
        <p>&copy; {new Date().getFullYear()} Perennia. All rights reserved.</p>
        <p className="footer-tagline">Empowering loan officers to achieve more.</p>
      </footer>
    </div>
  );
};

export default RecruitPortal;
