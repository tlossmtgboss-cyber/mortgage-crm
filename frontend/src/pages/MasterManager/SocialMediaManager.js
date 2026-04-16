import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { usePermissions } from '../../contexts/PermissionContext';
import './SocialMediaManager.css';
import { getToken } from '../../utils/tokenStore';

const API_URL = process.env.REACT_APP_API_URL || 'https://api.perenniaai.com';

const SocialMediaManager = () => {
  const navigate = useNavigate();
  const { userRole, hasAnyPermission, isAdmin } = usePermissions();
  const canAccessSocial = isAdmin || hasAnyPermission(['marketing.manage', 'social.manage', 'admin.manage']) || userRole === 'admin' || userRole === 'management';
  const [connections, setConnections] = useState({
    facebook: { connected: false, configured: false },
    linkedin: { connected: false, configured: false },
    instagram: { connected: false, configured: false }
  });
  const [posts, setPosts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [posting, setPosting] = useState(false);
  const [showComposer, setShowComposer] = useState(false);
  const [newPost, setNewPost] = useState({
    content: '',
    platforms: [],
    image_url: '',
    scheduled_time: ''
  });
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  const token = getToken();

  const fetchConnections = useCallback(async () => {
    try {
      const response = await fetch(`${API_URL}/api/v1/recruit-social/connections`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (response.ok) {
        const data = await response.json();
        setConnections(data);
      }
    } catch (err) {
      console.error('Error fetching connections:', err);
    }
  }, [token]);

  const fetchPosts = useCallback(async () => {
    try {
      const response = await fetch(`${API_URL}/api/v1/recruit-social/posts?limit=20`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (response.ok) {
        const data = await response.json();
        setPosts(data.posts || []);
      }
    } catch (err) {
      console.error('Error fetching posts:', err);
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    fetchConnections();
    fetchPosts();
  }, [fetchConnections, fetchPosts]);

  const handlePlatformToggle = (platform) => {
    setNewPost(prev => ({
      ...prev,
      platforms: prev.platforms.includes(platform)
        ? prev.platforms.filter(p => p !== platform)
        : [...prev.platforms, platform]
    }));
  };

  const handleCreatePost = async (e) => {
    e.preventDefault();
    if (!newPost.content.trim()) {
      setError('Post content is required');
      return;
    }
    if (newPost.platforms.length === 0) {
      setError('Select at least one platform');
      return;
    }

    setPosting(true);
    setError('');
    setSuccess('');

    try {
      const response = await fetch(`${API_URL}/api/v1/recruit-social/posts`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          content: newPost.content,
          platforms: newPost.platforms,
          image_url: newPost.image_url || null,
          scheduled_time: newPost.scheduled_time || null
        })
      });

      if (response.ok) {
        const result = await response.json();
        setSuccess('Post created successfully!');
        setNewPost({ content: '', platforms: [], image_url: '', scheduled_time: '' });
        setShowComposer(false);
        fetchPosts();
        console.log('Post result:', result);
      } else {
        const errData = await response.json();
        setError(errData.detail || 'Failed to create post');
      }
    } catch (err) {
      setError('Network error creating post');
    } finally {
      setPosting(false);
    }
  };

  const handleConnect = async (platform) => {
    // Get OAuth URL
    const redirectUri = `${window.location.origin}/settings/social-callback`;
    try {
      const response = await fetch(
        `${API_URL}/api/v1/recruit-social/oauth/${platform}/url?redirect_uri=${encodeURIComponent(redirectUri)}`,
        { headers: { 'Authorization': `Bearer ${token}` } }
      );
      if (response.ok) {
        const data = await response.json();
        // Open OAuth popup
        window.open(data.oauth_url, '_blank', 'width=600,height=700');
      }
    } catch (err) {
      setError(`Failed to get ${platform} OAuth URL`);
    }
  };

  const platformIcons = {
    facebook: '📘',
    linkedin: '🔗',
    instagram: '📷'
  };

  const platformColors = {
    facebook: '#1877f2',
    linkedin: '#0077b5',
    instagram: '#e4405f'
  };

  if (loading) {
    return (
      <div className="social-manager-loading">
        <div className="spinner"></div>
        <p>Loading social media manager...</p>
      </div>
    );
  }

  if (!canAccessSocial) {
    return (
      <div className="social-media-manager">
        <div className="access-denied" style={{ textAlign: 'center', padding: '60px 20px' }}>
          <h2>Access Denied</h2>
          <p>You don't have permission to access Social Media Manager.</p>
          <button className="btn-primary" onClick={() => navigate('/dashboard')}>
            Return to Dashboard
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="social-media-manager">
      {/* Header */}
      <div className="social-header">
        <div className="header-content">
          <h1>Social Media Manager</h1>
          <p>Create recruiting posts across LinkedIn, Facebook, and Instagram</p>
        </div>
        <button
          className="compose-button"
          onClick={() => setShowComposer(!showComposer)}
        >
          {showComposer ? 'Cancel' : '+ Create Post'}
        </button>
      </div>

      {/* Alerts */}
      {error && (
        <div className="alert alert-error">
          <span>{error}</span>
          <button onClick={() => setError('')}>×</button>
        </div>
      )}
      {success && (
        <div className="alert alert-success">
          <span>{success}</span>
          <button onClick={() => setSuccess('')}>×</button>
        </div>
      )}

      {/* Connection Status */}
      <div className="connections-section">
        <h2>Connected Platforms</h2>
        <div className="connections-grid">
          {Object.entries(connections).map(([platform, status]) => (
            <div
              key={platform}
              className={`connection-card ${status.connected ? 'connected' : ''}`}
              style={{ '--platform-color': platformColors[platform] }}
            >
              <div className="connection-icon">{platformIcons[platform]}</div>
              <div className="connection-info">
                <h3>{platform.charAt(0).toUpperCase() + platform.slice(1)}</h3>
                <span className={`connection-status ${status.connected ? 'active' : ''}`}>
                  {status.connected ? 'Connected' : status.configured ? 'Not connected' : 'Not configured'}
                </span>
              </div>
              {!status.connected && status.configured && (
                <button
                  className="connect-button"
                  onClick={() => handleConnect(platform)}
                >
                  Connect
                </button>
              )}
              {status.connected && (
                <span className="connected-badge">✓</span>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Post Composer */}
      {showComposer && (
        <div className="composer-section">
          <h2>Create New Post</h2>
          <form onSubmit={handleCreatePost} className="composer-form">
            <div className="platform-selector">
              <label>Select Platforms:</label>
              <div className="platform-buttons">
                {Object.keys(connections).map(platform => (
                  <button
                    key={platform}
                    type="button"
                    className={`platform-button ${newPost.platforms.includes(platform) ? 'selected' : ''}`}
                    style={{
                      '--platform-color': platformColors[platform],
                      opacity: connections[platform].connected ? 1 : 0.5
                    }}
                    onClick={() => handlePlatformToggle(platform)}
                    disabled={!connections[platform].connected}
                  >
                    {platformIcons[platform]} {platform.charAt(0).toUpperCase() + platform.slice(1)}
                  </button>
                ))}
              </div>
            </div>

            <div className="form-group">
              <label>Post Content:</label>
              <textarea
                value={newPost.content}
                onChange={(e) => setNewPost({ ...newPost, content: e.target.value })}
                placeholder="Write your recruiting post here...

Example:
🚀 We're hiring! Looking for talented loan officers who want to take their career to the next level.

✅ Cutting-edge technology
✅ Superior leads
✅ Unmatched support

Ready to grow? Let's talk! 💼

#Hiring #MortgageJobs #LoanOfficer #Recruiting"
                rows={8}
                maxLength={2000}
              />
              <span className="char-count">{newPost.content.length}/2000</span>
            </div>

            <div className="form-group">
              <label>Image URL (optional):</label>
              <input
                type="url"
                value={newPost.image_url}
                onChange={(e) => setNewPost({ ...newPost, image_url: e.target.value })}
                placeholder="https://example.com/image.jpg"
              />
              {newPost.image_url && (
                <div className="image-preview">
                  <img src={newPost.image_url} alt="Preview" onError={(e) => e.target.style.display = 'none'} />
                </div>
              )}
            </div>

            <div className="form-group">
              <label>Schedule Post (optional):</label>
              <input
                type="datetime-local"
                value={newPost.scheduled_time}
                onChange={(e) => setNewPost({ ...newPost, scheduled_time: e.target.value })}
                min={new Date().toISOString().slice(0, 16)}
              />
            </div>

            <div className="form-actions">
              <button
                type="button"
                className="cancel-button"
                onClick={() => setShowComposer(false)}
              >
                Cancel
              </button>
              <button
                type="submit"
                className="post-button"
                disabled={posting || newPost.platforms.length === 0 || !newPost.content.trim()}
              >
                {posting ? 'Posting...' : newPost.scheduled_time ? 'Schedule Post' : 'Post Now'}
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Recent Posts */}
      <div className="posts-section">
        <h2>Recent Posts</h2>
        {posts.length === 0 ? (
          <div className="empty-posts">
            <span className="empty-icon">📝</span>
            <p>No posts yet. Create your first recruiting post!</p>
          </div>
        ) : (
          <div className="posts-list">
            {posts.map(post => (
              <div key={post.id} className="post-card">
                <div className="post-header">
                  <div className="post-platforms">
                    {(post.platforms || '').split(',').map(p => (
                      <span
                        key={p}
                        className="platform-tag"
                        style={{ backgroundColor: platformColors[p.trim()] }}
                      >
                        {platformIcons[p.trim()]} {p.trim()}
                      </span>
                    ))}
                  </div>
                  <span className={`post-status status-${post.status}`}>
                    {post.status}
                  </span>
                </div>
                <div className="post-content">
                  <p>{post.content}</p>
                  {post.image_url && (
                    <img src={post.image_url} alt="Post" className="post-image" />
                  )}
                </div>
                <div className="post-footer">
                  <span className="post-date">
                    {post.scheduled_at
                      ? `Scheduled: ${new Date(post.scheduled_at).toLocaleString()}`
                      : post.posted_at
                        ? `Posted: ${new Date(post.posted_at).toLocaleString()}`
                        : `Created: ${new Date(post.created_at).toLocaleString()}`
                    }
                  </span>
                  {post.engagement_data && Object.keys(post.engagement_data).length > 0 && (
                    <div className="post-engagement">
                      <span>👍 {post.engagement_data.likes || 0}</span>
                      <span>💬 {post.engagement_data.comments || 0}</span>
                      <span>↗️ {post.engagement_data.shares || 0}</span>
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Post Templates */}
      <div className="templates-section">
        <h2>Quick Templates</h2>
        <div className="templates-grid">
          <div
            className="template-card"
            onClick={() => setNewPost({
              ...newPost,
              content: `🚀 We're expanding our team!

Looking for motivated loan officers who want to:
✅ Close more loans
✅ Earn more commission
✅ Work with cutting-edge technology

DM me or apply now! Link in bio.

#Hiring #MortgageJobs #LoanOfficer #JoinOurTeam`
            })}
          >
            <span className="template-icon">🚀</span>
            <h4>We're Hiring</h4>
            <p>General recruiting announcement</p>
          </div>

          <div
            className="template-card"
            onClick={() => setNewPost({
              ...newPost,
              content: `🎉 Celebrating another record-breaking month!

Our loan officers averaged 15% more closed deals this quarter. Here's what makes the difference:

📊 AI-powered lead qualification
🎯 Superior marketing support
💼 Industry-leading comp plan

Want to be part of a winning team? Let's connect!

#MortgageSuccess #TeamWin #LoanOfficerLife`
            })}
          >
            <span className="template-icon">🎉</span>
            <h4>Success Story</h4>
            <p>Celebrate team wins</p>
          </div>

          <div
            className="template-card"
            onClick={() => setNewPost({
              ...newPost,
              content: `💡 Why do top producers choose us?

1️⃣ Technology that actually helps you close
2️⃣ Leads that are pre-qualified and ready
3️⃣ Training that never stops
4️⃣ A culture that celebrates wins

Curious? DM me for a confidential conversation.

#MortgageIndustry #CareerGrowth #LoanOfficer`
            })}
          >
            <span className="template-icon">💡</span>
            <h4>Why Join Us</h4>
            <p>Company value proposition</p>
          </div>

          <div
            className="template-card"
            onClick={() => setNewPost({
              ...newPost,
              content: `📈 Market Update for Loan Officers:

Rates are moving, and so should your career!

We're actively recruiting LOs who want:
• Better leads
• Better tech
• Better support

If you're ready for a change, let's talk. Your next chapter starts with one conversation.

#MortgageRates #LoanOfficerOpportunity`
            })}
          >
            <span className="template-icon">📈</span>
            <h4>Market Update</h4>
            <p>Rate/market-based recruiting</p>
          </div>
        </div>
      </div>
    </div>
  );
};

export default SocialMediaManager;
