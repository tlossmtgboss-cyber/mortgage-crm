import React, { useState, useEffect, useCallback } from 'react';
import { useParams, useSearchParams } from 'react-router-dom';
import './RecruitPortal.css';
import ProductionCalculator from './ProductionCalculator';
import PortalChat from './PortalChat';
import PortalScheduler from './PortalScheduler';

const API_URL = process.env.REACT_APP_API_URL || 'https://api.perenniaai.com';

// Value propositions data
const VALUE_PROPS = [
  {
    icon: '🚀',
    title: 'Cutting-Edge Technology',
    description: 'AI-powered CRM, mobile apps, and automated workflows to close more loans faster.',
  },
  {
    icon: '📈',
    title: 'Superior Lead Generation',
    description: 'High-quality leads delivered directly to you with intelligent routing and follow-up.',
  },
  {
    icon: '💰',
    title: 'Competitive Compensation',
    description: 'Industry-leading splits and bonus structures designed to maximize your earnings.',
  },
  {
    icon: '🤝',
    title: 'Dedicated Support Team',
    description: 'Expert processors, underwriters, and closers handle the details so you can focus on clients.',
  },
];

// Testimonials data
const TESTIMONIALS = [
  {
    id: 1,
    quote: "Joining Perennia was the best decision of my career. My volume increased 45% in the first year.",
    name: "Sarah Mitchell",
    title: "Senior Loan Officer",
    metric: "+45% Volume",
    avatar: null,
  },
  {
    id: 2,
    quote: "The technology and support here is unmatched. I can focus on building relationships while the team handles everything else.",
    name: "Marcus Johnson",
    title: "Branch Manager",
    metric: "98% Client Satisfaction",
    avatar: null,
  },
  {
    id: 3,
    quote: "The training and mentorship program helped me go from 2 loans a month to 8. The growth opportunity is real.",
    name: "Jennifer Chen",
    title: "Loan Officer",
    metric: "4x Production",
    avatar: null,
  },
];

// Pipeline stages
const PIPELINE_STAGES = [
  { key: 'application', label: 'Application Received' },
  { key: 'phone_screen', label: 'Phone Screen' },
  { key: 'interview', label: 'Interview' },
  { key: 'offer', label: 'Offer' },
];

const RecruitPortal = () => {
  const { slug } = useParams();
  const [searchParams] = useSearchParams();
  const token = searchParams.get('token');

  const [portalData, setPortalData] = useState(null);
  const [companyUpdates, setCompanyUpdates] = useState([]);
  const [videos, setVideos] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [activeTestimonial, setActiveTestimonial] = useState(0);
  const [calculatorExpanded, setCalculatorExpanded] = useState(false);
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
      const response = await fetch(`${API_URL}/api/v1/recruit-portal/purl/${slug}/updates?limit=6`);
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

  // Auto-rotate testimonials
  useEffect(() => {
    const interval = setInterval(() => {
      setActiveTestimonial(prev => (prev + 1) % TESTIMONIALS.length);
    }, 6000);
    return () => clearInterval(interval);
  }, []);

  // Determine current pipeline stage
  const getCurrentStage = () => {
    const status = portalData?.candidate_status || 'application';
    const stageMap = {
      'new': 0,
      'application': 0,
      'phone_screen': 1,
      'interview': 2,
      'offer': 3,
      'hired': 4,
    };
    return stageMap[status] || 0;
  };

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

  const currentStage = getCurrentStage();
  const candidateName = portalData?.candidate_name || 'there';
  const firstName = candidateName.split(' ')[0];

  return (
    <div className="recruit-portal">
      {/* Hero Section */}
      <section className="portal-hero-section">
        <div className="hero-container">
          <div className="hero-welcome">
            <h1>Welcome, {firstName}!</h1>
            <p className="hero-subtitle">Your journey to success starts here.</p>

            {/* Pipeline Progress */}
            <div className="pipeline-progress">
              <div className="progress-steps">
                {PIPELINE_STAGES.map((stage, index) => (
                  <div
                    key={stage.key}
                    className={`progress-step ${index <= currentStage ? 'completed' : ''} ${index === currentStage ? 'current' : ''}`}
                  >
                    <div className="step-indicator">
                      {index < currentStage ? '✓' : index + 1}
                    </div>
                    <span className="step-label">{stage.label}</span>
                  </div>
                ))}
              </div>
            </div>

            {portalData?.status_message && (
              <div className="status-message">
                <p>"{portalData.status_message}"</p>
              </div>
            )}
          </div>

          {/* Recruiter Card */}
          {portalData?.recruiter_name && (
            <div className="recruiter-card">
              <div className="recruiter-header">
                <div className="recruiter-photo">
                  {portalData.recruiter_photo ? (
                    <img src={portalData.recruiter_photo} alt={portalData.recruiter_name} />
                  ) : (
                    <div className="photo-placeholder">
                      {portalData.recruiter_name.split(' ').map(n => n[0]).join('')}
                    </div>
                  )}
                </div>
                <div className="recruiter-details">
                  <h4>Your Recruiter</h4>
                  <p className="recruiter-name">{portalData.recruiter_name}</p>
                  {portalData.recruiter_title && (
                    <p className="recruiter-title">{portalData.recruiter_title}</p>
                  )}
                </div>
              </div>
              <div className="recruiter-contact-info">
                {portalData.recruiter_phone && (
                  <a href={`tel:${portalData.recruiter_phone}`} className="contact-item">
                    <span className="icon">📞</span> {portalData.recruiter_phone}
                  </a>
                )}
                {portalData.recruiter_email && (
                  <a href={`mailto:${portalData.recruiter_email}`} className="contact-item">
                    <span className="icon">✉️</span> {portalData.recruiter_email}
                  </a>
                )}
              </div>
              <button
                className="schedule-call-btn"
                onClick={() => document.getElementById('schedule-section')?.scrollIntoView({ behavior: 'smooth' })}
              >
                📅 Schedule a Call
              </button>
            </div>
          )}
        </div>
      </section>

      {/* Personal Video Message */}
      {videos.length > 0 && (
        <section className="video-message-section">
          <div className="video-message-container">
            <div className="video-message-card">
              <div className="video-player-wrapper">
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
              <div className="video-sidebar">
                <div className="video-header">
                  <h3>A Personal Message for You</h3>
                  <p>Your recruiter recorded this just for you</p>
                </div>
                {videos[0].message && (
                  <div className="video-chat-wrapper">
                    <p style={{ padding: '1rem', fontStyle: 'italic' }}>"{videos[0].message}"</p>
                    <span style={{ padding: '0 1rem', color: '#64748b' }}>— {videos[0].recruiter_name}</span>
                  </div>
                )}
              </div>
            </div>
          </div>
        </section>
      )}

      {/* Quick Actions */}
      <section className="quick-actions-section">
        <div className="quick-actions-container">
          <div className="quick-actions-grid">
            <div className="quick-action-card calculator" onClick={() => setCalculatorExpanded(true)}>
              <div className="action-icon">💵</div>
              <div className="action-content">
                <h3>Calculate Your Earnings</h3>
                <p>See how much more you could make</p>
              </div>
              <span className="action-arrow">→</span>
            </div>

            <div
              className="quick-action-card schedule"
              onClick={() => document.getElementById('schedule-section')?.scrollIntoView({ behavior: 'smooth' })}
            >
              <div className="action-icon">📅</div>
              <div className="action-content">
                <h3>Schedule a Call</h3>
                <p>Book time with your recruiter</p>
              </div>
              <span className="action-arrow">→</span>
            </div>

            <div
              className="quick-action-card chat"
              onClick={() => document.getElementById('chat-section')?.scrollIntoView({ behavior: 'smooth' })}
            >
              <div className="action-icon">💬</div>
              <div className="action-content">
                <h3>Chat with AI</h3>
                <p>Get instant answers to your questions</p>
              </div>
              <span className="action-arrow">→</span>
            </div>
          </div>
        </div>
      </section>

      {/* Value Propositions */}
      <section className="value-props-section">
        <div className="value-props-container">
          <div className="section-header">
            <h2>Why Top Producers Choose Perennia</h2>
            <p>Everything you need to take your career to the next level</p>
          </div>
          <div className="value-props-grid">
            {VALUE_PROPS.map((prop, index) => (
              <div key={index} className="value-prop-card">
                <div className="prop-icon">{prop.icon}</div>
                <h3>{prop.title}</h3>
                <p>{prop.description}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Earnings Calculator */}
      <section className={`calculator-section ${calculatorExpanded ? 'expanded' : ''}`}>
        <div className="calculator-container">
          <div className="section-header">
            <h2>Calculate Your Potential Earnings</h2>
            <p>See the difference Perennia can make</p>
          </div>
          <div className="production-calculator">
            <ProductionCalculator
              slug={slug}
              calculatorConfig={portalData?.calculator_config}
            />
          </div>
          {!calculatorExpanded && (
            <button
              className="cta-button"
              onClick={() => setCalculatorExpanded(true)}
            >
              View Full Calculator
            </button>
          )}
        </div>
      </section>

      {/* Company Culture / Updates */}
      {companyUpdates.length > 0 && (
        <section className="culture-section">
          <div className="culture-container">
            <div className="section-header">
              <h2>Life at Perennia</h2>
              <p>Stories, updates, and what makes us different</p>
            </div>
            <div className="culture-grid">
              {companyUpdates.slice(0, 6).map((update, index) => (
                <div
                  key={update.id || index}
                  className={`culture-card ${index === 0 ? 'featured' : ''}`}
                >
                  {update.media_url ? (
                    <div className="culture-image">
                      <img src={update.media_url} alt={update.title} />
                    </div>
                  ) : (
                    <div className="culture-image">
                      <div className="culture-image-placeholder">🏢</div>
                    </div>
                  )}
                  <div className="culture-content">
                    <span className="culture-category">
                      {update.category}
                    </span>
                    <h3>{update.title}</h3>
                    <p>{update.content}</p>
                    {update.published_at && (
                      <span className="culture-date">
                        {new Date(update.published_at).toLocaleDateString()}
                      </span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>
      )}

      {/* Testimonials */}
      <section className="testimonials-section">
        <div className="testimonials-container">
          <div className="section-header">
            <h2>Hear from Our Team</h2>
            <p>Real stories from loan officers who made the switch</p>
          </div>
          <div className="testimonials-carousel">
            <div className="testimonials-track">
              <div className="testimonial-card">
                <p className="testimonial-quote">
                  {TESTIMONIALS[activeTestimonial].quote}
                </p>
                <div className="testimonial-author">
                  <div className="author-photo">
                    {TESTIMONIALS[activeTestimonial].avatar ? (
                      <img src={TESTIMONIALS[activeTestimonial].avatar} alt="" />
                    ) : (
                      <span className="author-photo-placeholder">{TESTIMONIALS[activeTestimonial].name.split(' ').map(n => n[0]).join('')}</span>
                    )}
                  </div>
                  <div className="author-info">
                    <h4>{TESTIMONIALS[activeTestimonial].name}</h4>
                    <p>{TESTIMONIALS[activeTestimonial].title}</p>
                    <span className="testimonial-metric">
                      {TESTIMONIALS[activeTestimonial].metric}
                    </span>
                  </div>
                </div>
              </div>
            </div>
            <div className="carousel-dots">
              {TESTIMONIALS.map((_, index) => (
                <button
                  key={index}
                  className={`carousel-dot ${index === activeTestimonial ? 'active' : ''}`}
                  onClick={() => setActiveTestimonial(index)}
                  aria-label={`View testimonial ${index + 1}`}
                />
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* Schedule Section */}
      <section id="schedule-section" className="scheduler-section">
        <div className="scheduler-container">
          <div className="section-header">
            <h2>Let's Talk About Your Future</h2>
            <p>Schedule a time that works for you</p>
          </div>
          <div className="scheduler-card">
            <PortalScheduler
              slug={slug}
              recruiterName={portalData?.recruiter_name}
            />
          </div>
        </div>
      </section>

      {/* Chat Section */}
      <section id="chat-section" className="value-props-section">
        <div className="value-props-container">
          <div className="section-header">
            <h2>Have Questions?</h2>
            <p>Chat with our AI assistant for instant answers</p>
          </div>
          <div className="inline-chat-container">
            <PortalChat
              slug={slug}
              candidateName={portalData?.candidate_name}
              inline={true}
            />
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="portal-footer">
        <div className="footer-content">
          <div className="footer-logo">
            <h4>Perennia</h4>
            <p className="footer-tagline">Empowering loan officers to achieve more.</p>
          </div>
          <div className="footer-links">
            <a href="https://perenniaai.com" target="_blank" rel="noopener noreferrer">
              About Us
            </a>
            <a href="https://perenniaai.com/careers" target="_blank" rel="noopener noreferrer">
              Careers
            </a>
            <a href="mailto:support@perenniaai.com">
              Contact
            </a>
          </div>
          <div className="footer-social">
            <a href="#" aria-label="LinkedIn">
              <svg viewBox="0 0 24 24" fill="currentColor" width="20" height="20">
                <path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433c-1.144 0-2.063-.926-2.063-2.065 0-1.138.92-2.063 2.063-2.063 1.14 0 2.064.925 2.064 2.063 0 1.139-.925 2.065-2.064 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z"/>
              </svg>
            </a>
            <a href="#" aria-label="Facebook">
              <svg viewBox="0 0 24 24" fill="currentColor" width="20" height="20">
                <path d="M24 12.073c0-6.627-5.373-12-12-12s-12 5.373-12 12c0 5.99 4.388 10.954 10.125 11.854v-8.385H7.078v-3.47h3.047V9.43c0-3.007 1.792-4.669 4.533-4.669 1.312 0 2.686.235 2.686.235v2.953H15.83c-1.491 0-1.956.925-1.956 1.874v2.25h3.328l-.532 3.47h-2.796v8.385C19.612 23.027 24 18.062 24 12.073z"/>
              </svg>
            </a>
            <a href="#" aria-label="Instagram">
              <svg viewBox="0 0 24 24" fill="currentColor" width="20" height="20">
                <path d="M12 2.163c3.204 0 3.584.012 4.85.07 3.252.148 4.771 1.691 4.919 4.919.058 1.265.069 1.645.069 4.849 0 3.205-.012 3.584-.069 4.849-.149 3.225-1.664 4.771-4.919 4.919-1.266.058-1.644.07-4.85.07-3.204 0-3.584-.012-4.849-.07-3.26-.149-4.771-1.699-4.919-4.92-.058-1.265-.07-1.644-.07-4.849 0-3.204.013-3.583.07-4.849.149-3.227 1.664-4.771 4.919-4.919 1.266-.057 1.645-.069 4.849-.069zm0-2.163c-3.259 0-3.667.014-4.947.072-4.358.2-6.78 2.618-6.98 6.98-.059 1.281-.073 1.689-.073 4.948 0 3.259.014 3.668.072 4.948.2 4.358 2.618 6.78 6.98 6.98 1.281.058 1.689.072 4.948.072 3.259 0 3.668-.014 4.948-.072 4.354-.2 6.782-2.618 6.979-6.98.059-1.28.073-1.689.073-4.948 0-3.259-.014-3.667-.072-4.947-.196-4.354-2.617-6.78-6.979-6.98-1.281-.059-1.69-.073-4.949-.073zm0 5.838c-3.403 0-6.162 2.759-6.162 6.162s2.759 6.163 6.162 6.163 6.162-2.759 6.162-6.163c0-3.403-2.759-6.162-6.162-6.162zm0 10.162c-2.209 0-4-1.79-4-4 0-2.209 1.791-4 4-4s4 1.791 4 4c0 2.21-1.791 4-4 4zm6.406-11.845c-.796 0-1.441.645-1.441 1.44s.645 1.44 1.441 1.44c.795 0 1.439-.645 1.439-1.44s-.644-1.44-1.439-1.44z"/>
              </svg>
            </a>
          </div>
        </div>
        <div className="footer-bottom">
          <p>&copy; {new Date().getFullYear()} Perennia. All rights reserved.</p>
          <p className="footer-powered">Powered by Perennia AI</p>
        </div>
      </footer>

      {/* Floating Chat Widget - for non-inline mode */}
      <PortalChat
        slug={slug}
        candidateName={portalData?.candidate_name}
        inline={false}
      />
    </div>
  );
};

export default RecruitPortal;
