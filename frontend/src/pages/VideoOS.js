import React, { useState, useEffect, useCallback } from 'react';
import VideoRecorder from '../components/video/VideoRecorder';
import './VideoOS.css';
import { toast } from '../utils/toast';

const API_BASE_URL = (window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1')
  ? 'https://api.perenniaai.com'
  : 'http://localhost:8000';

const VideoOS = () => {
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('dashboard');
  const [videos, setVideos] = useState([]);
  const [stats, setStats] = useState({
    totalVideos: 0,
    totalViews: 0,
    avgWatchTime: 0,
    engagementRate: 0
  });
  const [showRecorder, setShowRecorder] = useState(false);
  const [selectedVideo, setSelectedVideo] = useState(null);
  const [templates, setTemplates] = useState([]);
  const [selectedTemplate, setSelectedTemplate] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);

  // Video templates for common scenarios
  const defaultTemplates = [
    {
      id: 'welcome',
      name: 'Welcome Message',
      description: 'Introduce yourself to new leads',
      script: "Hi [Name], thank you for reaching out about your home financing needs. I'm [Your Name], and I'm excited to help you navigate the mortgage process. I wanted to personally introduce myself and let you know I'm here to answer any questions you have. Let's schedule a quick call to discuss your goals!",
      duration: '30-60 seconds',
      icon: '👋'
    },
    {
      id: 'application_received',
      name: 'Application Received',
      description: 'Confirm receipt of loan application',
      script: "Hi [Name], great news! I've received your loan application and everything looks good. I wanted to give you a quick update on next steps: First, I'll review all the documents you submitted. Then, we'll move into the processing phase where we verify everything. You should hear back from me within 24-48 hours with any questions or updates. Thanks for choosing to work with me!",
      duration: '45-60 seconds',
      icon: '📋'
    },
    {
      id: 'document_request',
      name: 'Document Request',
      description: 'Request additional documents',
      script: "Hi [Name], hope you're doing well! I'm reviewing your file and need a couple more documents to keep things moving. Specifically, I need: [List documents]. You can upload these directly to your client portal, or just reply to my email with the attachments. Let me know if you have any questions about what I'm looking for!",
      duration: '30-45 seconds',
      icon: '📄'
    },
    {
      id: 'rate_lock',
      name: 'Rate Lock Confirmation',
      description: 'Confirm rate has been locked',
      script: "Hi [Name], exciting news! I've locked in your interest rate at [Rate]% for [Term] days. This means your rate is protected from any market fluctuations while we work through the rest of the process. Your estimated monthly payment is [Amount]. I'll keep you updated on our progress toward closing!",
      duration: '30-45 seconds',
      icon: '🔒'
    },
    {
      id: 'clear_to_close',
      name: 'Clear to Close',
      description: 'Celebrate reaching CTC milestone',
      script: "Hi [Name], I'm thrilled to share some fantastic news - you are officially CLEAR TO CLOSE! This means the underwriter has approved everything and we're in the final stretch. Your closing is scheduled for [Date]. I'll be reaching out to walk you through what to bring and what to expect. Congratulations on reaching this milestone!",
      duration: '45-60 seconds',
      icon: '🎉'
    },
    {
      id: 'closing_prep',
      name: 'Closing Preparation',
      description: 'Explain what to expect at closing',
      script: "Hi [Name], your closing is coming up on [Date] and I wanted to make sure you're prepared. Here's what to bring: A valid photo ID, a cashier's check for [Amount] made out to [Title Company], and any documents we discussed. The closing should take about an hour. I'll be available by phone if any questions come up. You're almost to the finish line!",
      duration: '45-60 seconds',
      icon: '📝'
    },
    {
      id: 'thank_you',
      name: 'Thank You / Referral Request',
      description: 'Thank client and ask for referrals',
      script: "Hi [Name], congratulations on your new home! I wanted to personally thank you for trusting me with one of the biggest financial decisions of your life. It was a pleasure working with you. If you know anyone else looking to buy, refinance, or who has questions about real estate, I'd love to help them too. Feel free to pass along my information. Best wishes in your new home!",
      duration: '30-45 seconds',
      icon: '🙏'
    },
    {
      id: 'market_update',
      name: 'Market Update',
      description: 'Share rate or market news',
      script: "Hi, I wanted to share a quick market update. Interest rates have [increased/decreased] recently, and I wanted to let you know what this means for your home buying power. If you've been waiting to make a move, now might be a great time to chat. I'm here to help you understand your options and find the best path forward. Let's connect!",
      duration: '30-45 seconds',
      icon: '📈'
    }
  ];

  useEffect(() => {
    loadVideoData();
    setTemplates(defaultTemplates);
  }, []);

  const loadVideoData = async () => {
    setLoading(true);
    try {
      const token = localStorage.getItem('token');

      // Fetch video library
      const videosResponse = await fetch(`${API_BASE_URL}/api/v1/video-os/library`, {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });

      if (videosResponse.ok) {
        const videosData = await videosResponse.json();
        setVideos(videosData.videos || []);
        setStats({
          totalVideos: videosData.total || 0,
          totalViews: videosData.totalViews || 0,
          avgWatchTime: videosData.avgWatchTime || 0,
          engagementRate: videosData.engagementRate || 0
        });
      } else {
        // Use demo data if API not available
        setVideos(getDemoVideos());
        setStats({
          totalVideos: 12,
          totalViews: 248,
          avgWatchTime: 45,
          engagementRate: 78
        });
      }
    } catch (error) {
      console.error('Error loading video data:', error);
      // Use demo data on error
      setVideos(getDemoVideos());
      setStats({
        totalVideos: 12,
        totalViews: 248,
        avgWatchTime: 45,
        engagementRate: 78
      });
    } finally {
      setLoading(false);
    }
  };

  const getDemoVideos = () => [
    {
      id: 1,
      title: 'Welcome - John Smith',
      type: 'welcome',
      duration: 42,
      views: 3,
      createdAt: new Date(Date.now() - 2 * 24 * 60 * 60 * 1000).toISOString(),
      thumbnail: null,
      recipient: 'John Smith',
      status: 'sent'
    },
    {
      id: 2,
      title: 'Rate Lock Confirmation',
      type: 'rate_lock',
      duration: 38,
      views: 2,
      createdAt: new Date(Date.now() - 3 * 24 * 60 * 60 * 1000).toISOString(),
      thumbnail: null,
      recipient: 'Sarah Johnson',
      status: 'viewed'
    },
    {
      id: 3,
      title: 'Document Request',
      type: 'document_request',
      duration: 55,
      views: 1,
      createdAt: new Date(Date.now() - 5 * 24 * 60 * 60 * 1000).toISOString(),
      thumbnail: null,
      recipient: 'Mike Chen',
      status: 'sent'
    },
    {
      id: 4,
      title: 'Clear to Close!',
      type: 'clear_to_close',
      duration: 48,
      views: 4,
      createdAt: new Date(Date.now() - 7 * 24 * 60 * 60 * 1000).toISOString(),
      thumbnail: null,
      recipient: 'Emily Davis',
      status: 'viewed'
    }
  ];

  const handleRecordingComplete = useCallback(async (blob, duration) => {
    setUploading(true);
    setUploadProgress(0);

    try {
      const token = localStorage.getItem('token');

      // Step 1: Get presigned upload URL
      setUploadProgress(10);
      const uploadUrlResponse = await fetch(`${API_BASE_URL}/api/v1/video-os/library/upload-url`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({
          content_type: 'video/webm',
          filename: `video_${Date.now()}.webm`,
          template: selectedTemplate?.id || null
        })
      });

      if (!uploadUrlResponse.ok) {
        throw new Error('Failed to get upload URL');
      }

      const { upload_url, video_id } = await uploadUrlResponse.json();
      setUploadProgress(30);

      // Step 2: Upload video to S3
      const uploadResponse = await fetch(upload_url, {
        method: 'PUT',
        headers: {
          'Content-Type': 'video/webm'
        },
        body: blob
      });

      if (!uploadResponse.ok) {
        throw new Error('Failed to upload video');
      }

      setUploadProgress(70);

      // Step 3: Complete upload
      const completeResponse = await fetch(`${API_BASE_URL}/api/v1/video-os/library/complete`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({
          video_id,
          duration_seconds: duration,
          title: selectedTemplate?.name || 'Custom Video',
          template_id: selectedTemplate?.id || null
        })
      });

      if (completeResponse.ok) {
        setUploadProgress(100);
        // Refresh video list
        await loadVideoData();
      }

    } catch (error) {
      console.error('Upload error:', error);
      toast.error('Failed to upload video. Please try again.');
    } finally {
      setUploading(false);
      setShowRecorder(false);
      setSelectedTemplate(null);
    }
  }, [selectedTemplate]);

  const handleStartRecording = (template = null) => {
    setSelectedTemplate(template);
    setShowRecorder(true);
  };

  const formatDuration = (seconds) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  const formatDate = (dateString) => {
    const date = new Date(dateString);
    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
  };

  const getStatusBadge = (status) => {
    switch (status) {
      case 'viewed':
        return <span className="status-badge viewed">Viewed</span>;
      case 'sent':
        return <span className="status-badge sent">Sent</span>;
      case 'draft':
        return <span className="status-badge draft">Draft</span>;
      default:
        return null;
    }
  };

  if (loading) {
    return (
      <div className="video-os loading">
        <div className="loading-spinner"></div>
        <p>Loading Video OS...</p>
      </div>
    );
  }

  return (
    <div className="video-os">
      {/* Header */}
      <div className="video-header">
        <div className="header-left">
          <h1>Video OS</h1>
          <p className="header-subtitle">Create personalized video messages for your clients</p>
        </div>
        <div className="header-right">
          <button className="btn-primary" onClick={() => handleStartRecording()}>
            <span className="btn-icon">🎬</span>
            Record New Video
          </button>
        </div>
      </div>

      {/* Quick Stats */}
      <div className="video-stats">
        <div className="stat-card">
          <div className="stat-icon">🎥</div>
          <div className="stat-content">
            <div className="stat-value">{stats.totalVideos}</div>
            <div className="stat-label">Total Videos</div>
          </div>
        </div>
        <div className="stat-card">
          <div className="stat-icon">👁️</div>
          <div className="stat-content">
            <div className="stat-value">{stats.totalViews}</div>
            <div className="stat-label">Total Views</div>
          </div>
        </div>
        <div className="stat-card">
          <div className="stat-icon">⏱️</div>
          <div className="stat-content">
            <div className="stat-value">{stats.avgWatchTime}s</div>
            <div className="stat-label">Avg Watch Time</div>
          </div>
        </div>
        <div className="stat-card">
          <div className="stat-icon">📊</div>
          <div className="stat-content">
            <div className="stat-value">{stats.engagementRate}%</div>
            <div className="stat-label">Engagement Rate</div>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="video-tabs">
        <button
          className={`tab ${activeTab === 'dashboard' ? 'active' : ''}`}
          onClick={() => setActiveTab('dashboard')}
        >
          Dashboard
        </button>
        <button
          className={`tab ${activeTab === 'library' ? 'active' : ''}`}
          onClick={() => setActiveTab('library')}
        >
          Video Library
        </button>
        <button
          className={`tab ${activeTab === 'templates' ? 'active' : ''}`}
          onClick={() => setActiveTab('templates')}
        >
          Templates
        </button>
        <button
          className={`tab ${activeTab === 'analytics' ? 'active' : ''}`}
          onClick={() => setActiveTab('analytics')}
        >
          Analytics
        </button>
      </div>

      {/* Tab Content */}
      <div className="tab-content">
        {/* Dashboard Tab */}
        {activeTab === 'dashboard' && (
          <div className="dashboard-tab">
            <div className="dashboard-grid">
              {/* Quick Actions */}
              <div className="dashboard-section quick-actions-section">
                <h2>Quick Actions</h2>
                <div className="quick-actions-grid">
                  <button className="quick-action" onClick={() => handleStartRecording()}>
                    <span className="action-icon">🎬</span>
                    <span className="action-label">Record Video</span>
                  </button>
                  <button className="quick-action" onClick={() => setActiveTab('templates')}>
                    <span className="action-icon">📝</span>
                    <span className="action-label">Use Template</span>
                  </button>
                  <button className="quick-action" onClick={() => setActiveTab('library')}>
                    <span className="action-icon">📚</span>
                    <span className="action-label">View Library</span>
                  </button>
                  <button className="quick-action" onClick={() => setActiveTab('analytics')}>
                    <span className="action-icon">📈</span>
                    <span className="action-label">View Analytics</span>
                  </button>
                </div>
              </div>

              {/* Recent Videos */}
              <div className="dashboard-section recent-videos-section">
                <h2>Recent Videos</h2>
                {videos.length > 0 ? (
                  <div className="recent-videos-list">
                    {videos.slice(0, 5).map((video) => (
                      <div key={video.id} className="recent-video-item">
                        <div className="video-thumbnail">
                          <div className="thumbnail-placeholder">🎥</div>
                          <span className="video-duration">{formatDuration(video.duration)}</span>
                        </div>
                        <div className="video-info">
                          <h4>{video.title}</h4>
                          <p className="video-meta">
                            <span>To: {video.recipient}</span>
                            <span className="separator">•</span>
                            <span>{formatDate(video.createdAt)}</span>
                          </p>
                        </div>
                        <div className="video-stats-mini">
                          <span className="views-count">
                            <span className="view-icon">👁️</span> {video.views}
                          </span>
                          {getStatusBadge(video.status)}
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="empty-state">
                    <p>No videos yet. Record your first video to get started!</p>
                    <button className="btn-secondary" onClick={() => handleStartRecording()}>
                      Record Video
                    </button>
                  </div>
                )}
              </div>

              {/* Popular Templates */}
              <div className="dashboard-section templates-preview-section">
                <h2>Popular Templates</h2>
                <div className="templates-preview-grid">
                  {templates.slice(0, 4).map((template) => (
                    <button
                      key={template.id}
                      className="template-preview-card"
                      onClick={() => handleStartRecording(template)}
                    >
                      <span className="template-icon">{template.icon}</span>
                      <span className="template-name">{template.name}</span>
                    </button>
                  ))}
                </div>
              </div>

              {/* Tips */}
              <div className="dashboard-section tips-section">
                <h2>Video Tips</h2>
                <div className="tips-list">
                  <div className="tip-item">
                    <span className="tip-icon">💡</span>
                    <p>Keep videos under 60 seconds for maximum engagement</p>
                  </div>
                  <div className="tip-item">
                    <span className="tip-icon">🎯</span>
                    <p>Personalize each video by using your client's name</p>
                  </div>
                  <div className="tip-item">
                    <span className="tip-icon">😊</span>
                    <p>Smile and make eye contact with the camera</p>
                  </div>
                  <div className="tip-item">
                    <span className="tip-icon">🔊</span>
                    <p>Record in a quiet space with good lighting</p>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Library Tab */}
        {activeTab === 'library' && (
          <div className="library-tab">
            <div className="library-header">
              <h2>Video Library</h2>
              <div className="library-filters">
                <select className="filter-select">
                  <option value="all">All Videos</option>
                  <option value="welcome">Welcome</option>
                  <option value="rate_lock">Rate Lock</option>
                  <option value="document_request">Document Request</option>
                  <option value="clear_to_close">Clear to Close</option>
                  <option value="custom">Custom</option>
                </select>
                <select className="filter-select">
                  <option value="recent">Most Recent</option>
                  <option value="views">Most Viewed</option>
                  <option value="oldest">Oldest</option>
                </select>
              </div>
            </div>

            {videos.length > 0 ? (
              <div className="video-grid">
                {videos.map((video) => (
                  <div key={video.id} className="video-card" onClick={() => setSelectedVideo(video)}>
                    <div className="video-card-thumbnail">
                      <div className="thumbnail-placeholder">🎥</div>
                      <span className="video-duration">{formatDuration(video.duration)}</span>
                      <button className="play-overlay">▶</button>
                    </div>
                    <div className="video-card-content">
                      <h3>{video.title}</h3>
                      <p className="video-recipient">To: {video.recipient}</p>
                      <div className="video-card-footer">
                        <span className="video-date">{formatDate(video.createdAt)}</span>
                        <span className="video-views">
                          <span className="view-icon">👁️</span> {video.views} views
                        </span>
                      </div>
                      {getStatusBadge(video.status)}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="empty-state-large">
                <div className="empty-icon">🎬</div>
                <h3>No Videos Yet</h3>
                <p>Start creating personalized video messages for your clients.</p>
                <button className="btn-primary" onClick={() => handleStartRecording()}>
                  Record Your First Video
                </button>
              </div>
            )}
          </div>
        )}

        {/* Templates Tab */}
        {activeTab === 'templates' && (
          <div className="templates-tab">
            <div className="templates-header">
              <h2>Video Templates</h2>
              <p>Choose a template to guide your video message</p>
            </div>

            <div className="templates-grid">
              {templates.map((template) => (
                <div key={template.id} className="template-card">
                  <div className="template-header">
                    <span className="template-icon-large">{template.icon}</span>
                    <div className="template-title-section">
                      <h3>{template.name}</h3>
                      <p className="template-description">{template.description}</p>
                    </div>
                  </div>

                  <div className="template-script">
                    <label>Suggested Script:</label>
                    <p>{template.script}</p>
                  </div>

                  <div className="template-footer">
                    <span className="template-duration">
                      <span className="duration-icon">⏱️</span>
                      {template.duration}
                    </span>
                    <button
                      className="btn-use-template"
                      onClick={() => handleStartRecording(template)}
                    >
                      Use Template
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Analytics Tab */}
        {activeTab === 'analytics' && (
          <div className="analytics-tab">
            <div className="analytics-header">
              <h2>Video Analytics</h2>
              <div className="date-range-selector">
                <select className="filter-select">
                  <option value="7">Last 7 Days</option>
                  <option value="30">Last 30 Days</option>
                  <option value="90">Last 90 Days</option>
                  <option value="all">All Time</option>
                </select>
              </div>
            </div>

            <div className="analytics-grid">
              {/* Overview Cards */}
              <div className="analytics-overview">
                <div className="analytics-card">
                  <h3>Videos Created</h3>
                  <div className="analytics-value">{stats.totalVideos}</div>
                  <div className="analytics-trend positive">+3 this week</div>
                </div>
                <div className="analytics-card">
                  <h3>Total Views</h3>
                  <div className="analytics-value">{stats.totalViews}</div>
                  <div className="analytics-trend positive">+28 this week</div>
                </div>
                <div className="analytics-card">
                  <h3>View Rate</h3>
                  <div className="analytics-value">{stats.engagementRate}%</div>
                  <div className="analytics-trend positive">+5% vs last week</div>
                </div>
                <div className="analytics-card">
                  <h3>Avg Watch Time</h3>
                  <div className="analytics-value">{stats.avgWatchTime}s</div>
                  <div className="analytics-trend neutral">No change</div>
                </div>
              </div>

              {/* Top Performing Videos */}
              <div className="analytics-section">
                <h3>Top Performing Videos</h3>
                <div className="top-videos-table">
                  <table>
                    <thead>
                      <tr>
                        <th>Video</th>
                        <th>Recipient</th>
                        <th>Views</th>
                        <th>Watch Time</th>
                        <th>Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {videos.sort((a, b) => b.views - a.views).slice(0, 5).map((video) => (
                        <tr key={video.id}>
                          <td className="video-title-cell">
                            <span className="video-icon">🎥</span>
                            {video.title}
                          </td>
                          <td>{video.recipient}</td>
                          <td>{video.views}</td>
                          <td>{formatDuration(video.duration)}</td>
                          <td>{getStatusBadge(video.status)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              {/* Performance by Template */}
              <div className="analytics-section">
                <h3>Performance by Template</h3>
                <div className="template-performance">
                  {[
                    { name: 'Welcome Message', count: 5, views: 15, rate: 85 },
                    { name: 'Clear to Close', count: 3, views: 12, rate: 92 },
                    { name: 'Rate Lock', count: 2, views: 6, rate: 75 },
                    { name: 'Document Request', count: 2, views: 4, rate: 67 }
                  ].map((template, index) => (
                    <div key={index} className="template-stat-row">
                      <div className="template-stat-name">{template.name}</div>
                      <div className="template-stat-bar">
                        <div
                          className="template-stat-fill"
                          style={{ width: `${template.rate}%` }}
                        />
                      </div>
                      <div className="template-stat-value">{template.rate}% viewed</div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Video Recorder Modal */}
      {showRecorder && (
        <div className="recorder-modal-overlay" onClick={() => setShowRecorder(false)}>
          <div className="recorder-modal" onClick={(e) => e.stopPropagation()}>
            <div className="recorder-modal-header">
              <h2>
                {selectedTemplate ? `Record: ${selectedTemplate.name}` : 'Record New Video'}
              </h2>
              <button className="close-btn" onClick={() => setShowRecorder(false)}>×</button>
            </div>

            {selectedTemplate && (
              <div className="template-script-prompt">
                <label>Script Guide:</label>
                <p>{selectedTemplate.script}</p>
              </div>
            )}

            {uploading ? (
              <div className="upload-progress">
                <div className="upload-spinner"></div>
                <p>Uploading video... {uploadProgress}%</p>
                <div className="progress-bar">
                  <div className="progress-fill" style={{ width: `${uploadProgress}%` }} />
                </div>
              </div>
            ) : (
              <VideoRecorder
                onRecordingComplete={handleRecordingComplete}
                onCancel={() => setShowRecorder(false)}
                maxDuration={120}
                showPreview={true}
              />
            )}
          </div>
        </div>
      )}

      {/* Video Preview Modal */}
      {selectedVideo && (
        <div className="video-preview-modal-overlay" onClick={() => setSelectedVideo(null)}>
          <div className="video-preview-modal" onClick={(e) => e.stopPropagation()}>
            <div className="preview-modal-header">
              <h2>{selectedVideo.title}</h2>
              <button className="close-btn" onClick={() => setSelectedVideo(null)}>×</button>
            </div>
            <div className="preview-modal-content">
              <div className="video-player-placeholder">
                <div className="placeholder-icon">🎥</div>
                <p>Video playback coming soon</p>
              </div>
              <div className="video-details">
                <div className="detail-row">
                  <span className="detail-label">Recipient:</span>
                  <span className="detail-value">{selectedVideo.recipient}</span>
                </div>
                <div className="detail-row">
                  <span className="detail-label">Duration:</span>
                  <span className="detail-value">{formatDuration(selectedVideo.duration)}</span>
                </div>
                <div className="detail-row">
                  <span className="detail-label">Created:</span>
                  <span className="detail-value">{formatDate(selectedVideo.createdAt)}</span>
                </div>
                <div className="detail-row">
                  <span className="detail-label">Views:</span>
                  <span className="detail-value">{selectedVideo.views}</span>
                </div>
                <div className="detail-row">
                  <span className="detail-label">Status:</span>
                  {getStatusBadge(selectedVideo.status)}
                </div>
              </div>
              <div className="preview-modal-actions">
                <button className="btn-secondary">Copy Link</button>
                <button className="btn-secondary">Resend</button>
                <button className="btn-danger">Delete</button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default VideoOS;
