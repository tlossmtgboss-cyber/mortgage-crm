import React, { useState, useEffect, useCallback } from 'react';
import { useParams, useSearchParams } from 'react-router-dom';
import './RecruitPortal.css';
import PortalScheduler from './PortalScheduler';

const API_URL = process.env.REACT_APP_API_URL || 'https://api.perenniaai.com';

// Tab content data
const TAB_CONTENT = {
  culture: {
    title: 'Our Culture',
    subtitle: 'What makes Perennia different',
    sections: [
      {
        icon: '🎯',
        title: 'Mission-Driven',
        description: 'We believe in empowering loan officers to build sustainable, thriving careers. Our success is measured by your success.',
      },
      {
        icon: '🤝',
        title: 'Collaborative Environment',
        description: 'No competition between LOs. We share best practices, celebrate wins together, and support each other through challenges.',
      },
      {
        icon: '⚡',
        title: 'Innovation First',
        description: 'We invest heavily in technology and tools that make your job easier, not harder. AI-powered workflows, automated follow-ups, and smart lead routing.',
      },
      {
        icon: '🌱',
        title: 'Growth Mindset',
        description: 'Continuous learning opportunities, mentorship programs, and clear paths to leadership for those who want to grow.',
      },
    ],
  },
  people: {
    title: 'The People',
    subtitle: 'Meet the team behind your success',
    sections: [
      {
        icon: '👥',
        title: 'Leadership Team',
        description: 'Experienced mortgage professionals with 50+ combined years in the industry. They\'ve been where you are and know what it takes to succeed.',
      },
      {
        icon: '🛠️',
        title: 'Operations Support',
        description: 'Dedicated processors, underwriters, and closers who handle the heavy lifting so you can focus on what you do best - building relationships.',
      },
      {
        icon: '📊',
        title: 'Marketing & Technology',
        description: 'In-house marketing team and tech specialists who create campaigns, build tools, and ensure you always have an edge.',
      },
      {
        icon: '🎓',
        title: 'Training & Development',
        description: 'Full-time coaches and trainers who work with you to refine your skills, improve your pitch, and grow your business.',
      },
    ],
  },
  programs: {
    title: 'Our Programs',
    subtitle: 'Everything you need to succeed',
    sections: [
      {
        icon: '📱',
        title: 'Lead Generation Program',
        description: 'Exclusive leads delivered directly to your pipeline. We invest in marketing so you can focus on converting.',
      },
      {
        icon: '💰',
        title: 'Competitive Compensation',
        description: 'Industry-leading splits, bonus structures, and incentives. The more you produce, the more you earn.',
      },
      {
        icon: '🖥️',
        title: 'Technology Suite',
        description: 'AI-powered CRM, mobile apps, automated workflows, e-signatures, and integrations with all major systems.',
      },
      {
        icon: '📈',
        title: 'Business Development',
        description: 'Co-marketing opportunities, realtor partnerships, builder relationships, and referral programs to grow your network.',
      },
    ],
  },
  onboarding: {
    title: 'The Onboarding Process',
    subtitle: 'Your journey to success starts here',
    sections: [
      {
        icon: '1️⃣',
        title: 'Week 1: Foundation',
        description: 'Complete licensing transfers, system setup, and orientation. Meet your support team and understand our culture.',
      },
      {
        icon: '2️⃣',
        title: 'Week 2: Training',
        description: 'Deep dive into our technology, processes, and best practices. Shadow top producers and learn what makes them successful.',
      },
      {
        icon: '3️⃣',
        title: 'Week 3: Launch',
        description: 'Start taking leads, work with your coach on your first deals, and begin building your pipeline with full support.',
      },
      {
        icon: '4️⃣',
        title: 'Ongoing Support',
        description: 'Weekly check-ins, monthly training sessions, and 24/7 access to your support team. We\'re invested in your long-term success.',
      },
    ],
  },
};

const TABS = [
  { key: 'culture', label: 'Culture' },
  { key: 'people', label: 'The People' },
  { key: 'programs', label: 'Programs' },
  { key: 'onboarding', label: 'The Onboarding Process' },
];

const RecruitPortal = () => {
  const { slug } = useParams();
  const [searchParams] = useSearchParams();
  const token = searchParams.get('token');

  const [portalData, setPortalData] = useState(null);
  const [videos, setVideos] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [activeTab, setActiveTab] = useState('culture');
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

  const fetchVideos = useCallback(async () => {
    try {
      if (!token) return;
      const response = await fetch(`${API_URL}/api/v1/recruiting/video/portal/${slug}/videos?token=${encodeURIComponent(token)}`);
      if (response.ok) {
        const data = await response.json();
        setVideos(data.videos || []);
      }
    } catch (err) {
      console.error('Error fetching videos:', err);
    }
  }, [slug, token]);

  const markVideoViewed = async (videoId) => {
    try {
      await fetch(`${API_URL}/api/v1/recruiting/video/mark-viewed/${videoId}`, {
        method: 'POST'
      });
      setVideos(prev => prev.map(v =>
        v.id === videoId ? { ...v, is_new: false } : v
      ));
    } catch (err) {
      console.error('Error marking video viewed:', err);
    }
  };

  useEffect(() => {
    fetchPortalData();
    fetchVideos();
  }, [fetchPortalData, fetchVideos]);

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
        <div className="error-icon">⚠️</div>
        <h2>Portal Access Error</h2>
        <p>{error}</p>
        <p>Please check your link or contact the recruiter.</p>
      </div>
    );
  }

  const candidateName = portalData?.candidate_name || 'there';
  const firstName = candidateName.split(' ')[0];
  const activeContent = TAB_CONTENT[activeTab];

  return (
    <div className="recruit-portal">
      {/* Hero Section - Compact */}
      <section className="portal-hero-section compact">
        <div className="hero-container">
          {/* Company Logo */}
          <div className="company-logo-section">
            {portalData?.company_logo ? (
              <img src={portalData.company_logo} alt={portalData.company_name || 'Company'} className="company-logo" />
            ) : (
              <h2 className="company-name-text">{portalData?.company_name || 'Perennia'}</h2>
            )}
          </div>

          <div className="hero-welcome">
            <h1>Welcome, {firstName}!</h1>
            <p className="hero-subtitle">Discover your future at {portalData?.company_name || 'Perennia'}</p>
          </div>
        </div>
      </section>

      {/* Video + Scheduler Side by Side - Compact */}
      <section className="video-scheduler-section">
        <div className="video-scheduler-container">
          {/* Video Column */}
          <div className="video-column-compact">
            {videos.length > 0 ? (
              <div className="video-card-compact">
                <div className="video-wrapper">
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
                <div className="video-caption">
                  <span className="video-badge">Personal Message</span>
                  <p>{videos[0].message || `A message from ${videos[0].recruiter_name}`}</p>
                </div>
              </div>
            ) : (
              <div className="video-card-compact placeholder">
                <div className="video-placeholder-content">
                  <span className="placeholder-icon">🎬</span>
                  <p>Video message coming soon</p>
                </div>
              </div>
            )}
          </div>

          {/* Scheduler Column - Compact */}
          <div className="scheduler-column-compact">
            <div className="scheduler-card-compact">
              <div className="scheduler-body-compact">
                <PortalScheduler
                  slug={slug}
                  recruiterName={portalData?.recruiter_name}
                  compact={true}
                />
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Tab Navigation */}
      <section className="tabs-section">
        <div className="tabs-container">
          <nav className="tabs-nav">
            {TABS.map(tab => (
              <button
                key={tab.key}
                className={`tab-button ${activeTab === tab.key ? 'active' : ''}`}
                onClick={() => setActiveTab(tab.key)}
              >
                {tab.label}
              </button>
            ))}
          </nav>
        </div>
      </section>

      {/* Tab Content */}
      <section className="tab-content-section">
        <div className="tab-content-container">
          <div className="tab-header">
            <h2>{activeContent.title}</h2>
            <p>{activeContent.subtitle}</p>
          </div>
          <div className="tab-cards-grid">
            {activeContent.sections.map((section, index) => (
              <div key={index} className="tab-card">
                <div className="tab-card-icon">{section.icon}</div>
                <h3>{section.title}</h3>
                <p>{section.description}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA Section */}
      <section className="cta-section">
        <div className="cta-container">
          <h2>Ready to Take the Next Step?</h2>
          <p>Schedule a call with {portalData?.recruiter_name || 'your recruiter'} to learn more</p>
          <button
            className="cta-button"
            onClick={() => window.scrollTo({ top: 0, behavior: 'smooth' })}
          >
            Schedule Your Call
          </button>
        </div>
      </section>

      {/* Footer */}
      <footer className="portal-footer">
        <div className="footer-content">
          <div className="footer-logo">
            <h4>Perennia</h4>
            <p className="footer-tagline">Empowering loan officers to achieve more.</p>
          </div>
        </div>
        <div className="footer-bottom">
          <p>&copy; {new Date().getFullYear()} Perennia. All rights reserved.</p>
        </div>
      </footer>
    </div>
  );
};

export default RecruitPortal;
