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
  const [videos, setVideos] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [activeTab, setActiveTab] = useState('calculator');
  const [playingVideoId, setPlayingVideoId] = useState(null);

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

  const fetchVideos = useCallback(async () => {
    try {
      const response = await fetch(`${API_URL}/api/v1/recruiting/video/portal/${slug}/videos`);
      if (response.ok) {
        const data = await response.json();
        setVideos(data.videos || []);
      }
    } catch (err) {
      console.error('Error fetching videos:', err);
    }
  }, [slug]);

  const markVideoViewed = async (videoId) => {
    try {
      await fetch(`${API_URL}/api/v1/recruiting/video/mark-viewed/${videoId}`, {
        method: 'POST'
      });
      // Update local state to mark as viewed
      setVideos(prev => prev.map(v =>
        v.id === videoId ? { ...v, is_new: false } : v
      ));
    } catch (err) {
      console.error('Error marking video viewed:', err);
    }
  };

  useEffect(() => {
    fetchPortalData();
    fetchCompanyUpdates();
    fetchVideos();
  }, [fetchPortalData, fetchCompanyUpdates, fetchVideos]);

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
      {/* Welcome Header - Full Width */}
      <section className="portal-welcome">
        <h1>Your Path to Success Starts Here</h1>
        <p>
          We're excited to meet you! Your interview is coming up. Feel free to chat with our AI assistant if you have any questions.
        </p>
      </section>

      {/* Personal Video Message with Scheduler */}
      {videos.length > 0 && (
        <section className="personal-video-section">
          <div className="video-and-scheduler-row">
            <div className="personal-video-container">
              <div className="personal-video-header">
                <div>
                  <h3>A Personal Message for You</h3>
                  <p>Your recruiter recorded this just for you</p>
                </div>
              </div>
              <div className="personal-video-player">
                <video
                  controls
                  poster={videos[0].recruiter_photo || undefined}
                  onPlay={() => {
                    setPlayingVideoId(videos[0].id);
                    if (videos[0].is_new) {
                      markVideoViewed(videos[0].id);
                    }
                  }}
                  onEnded={() => setPlayingVideoId(null)}
                >
                  <source src={videos[0].video_url} type="video/webm" />
                  Your browser does not support video playback.
                </video>
              </div>
              {videos[0].message && (
                <div className="personal-video-message">
                  <p>"{videos[0].message}"</p>
                  <span className="video-from">— {videos[0].recruiter_name}</span>
                </div>
              )}
            </div>
            <div className="scheduler-side">
              <PortalScheduler
                slug={slug}
                recruiterName={portalData?.recruiter_name}
                compact={true}
              />
            </div>
          </div>
          {/* AI Chat below video */}
          <div className="inline-chat-section">
            <PortalChat
              slug={slug}
              candidateName={portalData?.candidate_name}
              inline={true}
            />
          </div>
        </section>
      )}

      {/* Hero Section with Recruiter Card */}
      <section className="portal-hero">
        <div className="hero-cards">
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
                {portalData.recruiter_email && (
                  <a href={`mailto:${portalData.recruiter_email}`} className="recruiter-contact">
                    {portalData.recruiter_email}
                  </a>
                )}
              </div>
            </div>
          )}
        </div>
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
          className={`tab-button ${activeTab === 'programs' ? 'active' : ''}`}
          onClick={() => setActiveTab('programs')}
        >
          Programs & Products
        </button>
        <button
          className={`tab-button ${activeTab === 'technology' ? 'active' : ''}`}
          onClick={() => setActiveTab('technology')}
        >
          Technology
        </button>
        <button
          className={`tab-button ${activeTab === 'operations' ? 'active' : ''}`}
          onClick={() => setActiveTab('operations')}
        >
          Operations
        </button>
        <button
          className={`tab-button ${activeTab === 'marketing' ? 'active' : ''}`}
          onClick={() => setActiveTab('marketing')}
        >
          Marketing
        </button>
        <button
          className={`tab-button ${activeTab === 'updates' ? 'active' : ''}`}
          onClick={() => setActiveTab('updates')}
        >
          Company News
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

        {activeTab === 'social' && (
          <SocialFeed />
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
