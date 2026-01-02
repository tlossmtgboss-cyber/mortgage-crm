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
          className={`tab-button ${activeTab === 'conversation' ? 'active' : ''}`}
          onClick={() => setActiveTab('conversation')}
        >
          Conversation Log
        </button>
        <button
          className={`tab-button ${activeTab === 'social' ? 'active' : ''}`}
          onClick={() => setActiveTab('social')}
        >
          Social Media
        </button>
        <button
          className={`tab-button ${activeTab === 'videos' ? 'active' : ''}`}
          onClick={() => setActiveTab('videos')}
        >
          Video Library
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

        {activeTab === 'programs' && (
          <div className="tab-section programs-section">
            <h3>Programs & Products</h3>
            <p className="section-intro">Comprehensive loan programs to serve every client</p>
            <div className="programs-grid">
              <div className="program-card">
                <div className="program-icon">🏠</div>
                <h4>Conventional Loans</h4>
                <p>Competitive rates with flexible terms for qualified borrowers</p>
              </div>
              <div className="program-card">
                <div className="program-icon">🎖️</div>
                <h4>VA Loans</h4>
                <p>Zero down payment options for veterans and active military</p>
              </div>
              <div className="program-card">
                <div className="program-icon">🏡</div>
                <h4>FHA Loans</h4>
                <p>Low down payment options for first-time homebuyers</p>
              </div>
              <div className="program-card">
                <div className="program-icon">💎</div>
                <h4>Jumbo Loans</h4>
                <p>High-value financing for luxury properties</p>
              </div>
              <div className="program-card">
                <div className="program-icon">🔄</div>
                <h4>Non-QM Loans</h4>
                <p>Alternative documentation programs for self-employed borrowers</p>
              </div>
              <div className="program-card">
                <div className="program-icon">🌾</div>
                <h4>USDA Loans</h4>
                <p>Rural development financing with zero down payment</p>
              </div>
            </div>
          </div>
        )}

        {activeTab === 'technology' && (
          <div className="tab-section technology-section">
            <h3>Technology Stack</h3>
            <p className="section-intro">Industry-leading tools to close more loans faster</p>
            <div className="tech-features">
              <div className="tech-card">
                <div className="tech-icon">🤖</div>
                <h4>AI-Powered CRM</h4>
                <p>Intelligent lead management with automated follow-ups and smart prioritization</p>
              </div>
              <div className="tech-card">
                <div className="tech-icon">📱</div>
                <h4>Mobile App</h4>
                <p>Full-featured mobile access to manage your pipeline anywhere</p>
              </div>
              <div className="tech-card">
                <div className="tech-icon">📄</div>
                <h4>Digital Document Management</h4>
                <p>Seamless document collection with e-signatures and automated verification</p>
              </div>
              <div className="tech-card">
                <div className="tech-icon">📊</div>
                <h4>Real-Time Analytics</h4>
                <p>Dashboard insights to track performance and identify opportunities</p>
              </div>
            </div>
          </div>
        )}

        {activeTab === 'operations' && (
          <div className="tab-section operations-section">
            <h3>Operations Support</h3>
            <p className="section-intro">Dedicated teams to help you focus on selling</p>
            <div className="ops-features">
              <div className="ops-card">
                <h4>Processing Team</h4>
                <p>Experienced processors handle file management so you can focus on clients</p>
                <span className="ops-stat">Avg. 15-day close time</span>
              </div>
              <div className="ops-card">
                <h4>Underwriting Support</h4>
                <p>In-house underwriters with fast turnaround and scenario analysis</p>
                <span className="ops-stat">24-hour initial review</span>
              </div>
              <div className="ops-card">
                <h4>Closing Coordination</h4>
                <p>Dedicated closers ensure smooth transactions every time</p>
                <span className="ops-stat">98% on-time closing rate</span>
              </div>
              <div className="ops-card">
                <h4>Compliance Team</h4>
                <p>Expert compliance support to keep you protected</p>
                <span className="ops-stat">Zero audit findings</span>
              </div>
            </div>
          </div>
        )}

        {activeTab === 'marketing' && (
          <div className="tab-section marketing-section">
            <h3>Marketing Resources</h3>
            <p className="section-intro">Everything you need to build your brand and grow your business</p>
            <div className="marketing-features">
              <div className="marketing-card">
                <div className="marketing-icon">🎨</div>
                <h4>Personal Branding</h4>
                <p>Custom websites, business cards, and branded materials</p>
              </div>
              <div className="marketing-card">
                <div className="marketing-icon">📧</div>
                <h4>Email Campaigns</h4>
                <p>Pre-built drip campaigns and newsletters ready to send</p>
              </div>
              <div className="marketing-card">
                <div className="marketing-icon">📱</div>
                <h4>Social Media Content</h4>
                <p>Ready-to-post content library with graphics and videos</p>
              </div>
              <div className="marketing-card">
                <div className="marketing-icon">🎬</div>
                <h4>Video Production</h4>
                <p>Professional video creation and AI-powered content</p>
              </div>
              <div className="marketing-card">
                <div className="marketing-icon">🎯</div>
                <h4>Lead Generation</h4>
                <p>Digital advertising and lead capture landing pages</p>
              </div>
              <div className="marketing-card">
                <div className="marketing-icon">📚</div>
                <h4>Educational Content</h4>
                <p>Branded guides, calculators, and homebuyer resources</p>
              </div>
            </div>
          </div>
        )}

        {activeTab === 'social' && (
          <div className="tab-section social-profiles-section">
            <h3>My Social Profiles</h3>
            <p className="section-intro">Connect your social media accounts to showcase your professional presence</p>
            <div className="social-profiles-grid">
              <div className={`social-profile-card ${portalData?.social_profiles?.linkedin ? 'connected' : ''}`}>
                <div className="social-icon linkedin">
                  <svg viewBox="0 0 24 24" fill="currentColor">
                    <path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433c-1.144 0-2.063-.926-2.063-2.065 0-1.138.92-2.063 2.063-2.063 1.14 0 2.064.925 2.064 2.063 0 1.139-.925 2.065-2.064 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z"/>
                  </svg>
                </div>
                <h4>LinkedIn</h4>
                {portalData?.social_profiles?.linkedin ? (
                  <a href={portalData.social_profiles.linkedin} target="_blank" rel="noopener noreferrer" className="social-link">
                    View Profile
                  </a>
                ) : (
                  <button className="connect-social-btn">Connect</button>
                )}
              </div>

              <div className={`social-profile-card ${portalData?.social_profiles?.facebook ? 'connected' : ''}`}>
                <div className="social-icon facebook">
                  <svg viewBox="0 0 24 24" fill="currentColor">
                    <path d="M24 12.073c0-6.627-5.373-12-12-12s-12 5.373-12 12c0 5.99 4.388 10.954 10.125 11.854v-8.385H7.078v-3.47h3.047V9.43c0-3.007 1.792-4.669 4.533-4.669 1.312 0 2.686.235 2.686.235v2.953H15.83c-1.491 0-1.956.925-1.956 1.874v2.25h3.328l-.532 3.47h-2.796v8.385C19.612 23.027 24 18.062 24 12.073z"/>
                  </svg>
                </div>
                <h4>Facebook</h4>
                {portalData?.social_profiles?.facebook ? (
                  <a href={portalData.social_profiles.facebook} target="_blank" rel="noopener noreferrer" className="social-link">
                    View Profile
                  </a>
                ) : (
                  <button className="connect-social-btn">Connect</button>
                )}
              </div>

              <div className={`social-profile-card ${portalData?.social_profiles?.instagram ? 'connected' : ''}`}>
                <div className="social-icon instagram">
                  <svg viewBox="0 0 24 24" fill="currentColor">
                    <path d="M12 2.163c3.204 0 3.584.012 4.85.07 3.252.148 4.771 1.691 4.919 4.919.058 1.265.069 1.645.069 4.849 0 3.205-.012 3.584-.069 4.849-.149 3.225-1.664 4.771-4.919 4.919-1.266.058-1.644.07-4.85.07-3.204 0-3.584-.012-4.849-.07-3.26-.149-4.771-1.699-4.919-4.92-.058-1.265-.07-1.644-.07-4.849 0-3.204.013-3.583.07-4.849.149-3.227 1.664-4.771 4.919-4.919 1.266-.057 1.645-.069 4.849-.069zm0-2.163c-3.259 0-3.667.014-4.947.072-4.358.2-6.78 2.618-6.98 6.98-.059 1.281-.073 1.689-.073 4.948 0 3.259.014 3.668.072 4.948.2 4.358 2.618 6.78 6.98 6.98 1.281.058 1.689.072 4.948.072 3.259 0 3.668-.014 4.948-.072 4.354-.2 6.782-2.618 6.979-6.98.059-1.28.073-1.689.073-4.948 0-3.259-.014-3.667-.072-4.947-.196-4.354-2.617-6.78-6.979-6.98-1.281-.059-1.69-.073-4.949-.073zm0 5.838c-3.403 0-6.162 2.759-6.162 6.162s2.759 6.163 6.162 6.163 6.162-2.759 6.162-6.163c0-3.403-2.759-6.162-6.162-6.162zm0 10.162c-2.209 0-4-1.79-4-4 0-2.209 1.791-4 4-4s4 1.791 4 4c0 2.21-1.791 4-4 4zm6.406-11.845c-.796 0-1.441.645-1.441 1.44s.645 1.44 1.441 1.44c.795 0 1.439-.645 1.439-1.44s-.644-1.44-1.439-1.44z"/>
                  </svg>
                </div>
                <h4>Instagram</h4>
                {portalData?.social_profiles?.instagram ? (
                  <a href={portalData.social_profiles.instagram} target="_blank" rel="noopener noreferrer" className="social-link">
                    View Profile
                  </a>
                ) : (
                  <button className="connect-social-btn">Connect</button>
                )}
              </div>

              <div className={`social-profile-card ${portalData?.social_profiles?.twitter ? 'connected' : ''}`}>
                <div className="social-icon twitter">
                  <svg viewBox="0 0 24 24" fill="currentColor">
                    <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"/>
                  </svg>
                </div>
                <h4>Twitter/X</h4>
                {portalData?.social_profiles?.twitter ? (
                  <a href={portalData.social_profiles.twitter} target="_blank" rel="noopener noreferrer" className="social-link">
                    View Profile
                  </a>
                ) : (
                  <button className="connect-social-btn">Connect</button>
                )}
              </div>
            </div>

            <div className="social-info-note">
              <p>Your social profiles help us understand your professional network and how we can support your growth.</p>
            </div>
          </div>
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
      </main>

      {/* Footer */}
      <footer className="portal-footer">
        <p>&copy; {new Date().getFullYear()} Perennia. All rights reserved.</p>
        <p className="footer-tagline">Empowering loan officers to achieve more.</p>
      </footer>
    </div>
  );
};

export default RecruitPortal;
