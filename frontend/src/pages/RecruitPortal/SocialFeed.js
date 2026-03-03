import React, { useState, useEffect, useCallback } from 'react';
import './SocialFeed.css';

const API_URL = process.env.REACT_APP_API_URL || 'https://api.perenniaai.com';

const SocialFeed = ({ slug }) => {
  const [posts, setPosts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const platformIcons = {
    facebook: '📘',
    linkedin: '🔗',
    instagram: '📷',
    twitter: '🐦'
  };

  const platformColors = {
    facebook: '#1877f2',
    linkedin: '#0077b5',
    instagram: '#e4405f',
    twitter: '#1da1f2'
  };

  const fetchPosts = useCallback(async () => {
    try {
      setLoading(true);
      if (!slug) return;
      const response = await fetch(`${API_URL}/api/v1/recruit-social/public/feed?slug=${encodeURIComponent(slug)}&limit=10`);
      if (response.ok) {
        const data = await response.json();
        setPosts(data.posts || []);
      } else {
        setError('Unable to load social feed');
      }
    } catch (err) {
      console.error('Error fetching social feed:', err);
      setError('Unable to load social feed');
    } finally {
      setLoading(false);
    }
  }, [slug]);

  useEffect(() => {
    fetchPosts();
  }, [fetchPosts]);

  const formatDate = (dateString) => {
    if (!dateString) return '';
    const date = new Date(dateString);
    const now = new Date();
    const diffMs = now - date;
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMins / 60);
    const diffDays = Math.floor(diffHours / 24);

    if (diffMins < 60) {
      return `${diffMins}m ago`;
    } else if (diffHours < 24) {
      return `${diffHours}h ago`;
    } else if (diffDays < 7) {
      return `${diffDays}d ago`;
    } else {
      return date.toLocaleDateString();
    }
  };

  if (loading) {
    return (
      <div className="social-feed-loading">
        <div className="feed-spinner"></div>
        <p>Loading social updates...</p>
      </div>
    );
  }

  if (error || posts.length === 0) {
    return (
      <div className="social-feed-empty">
        <span className="empty-icon">📱</span>
        <h4>Stay Connected</h4>
        <p>Follow us on social media for the latest updates!</p>
        <div className="social-links">
          <a href="https://linkedin.com/company/perennia" target="_blank" rel="noopener noreferrer" className="social-link linkedin">
            <span>🔗</span> LinkedIn
          </a>
          <a href="https://facebook.com/perennia" target="_blank" rel="noopener noreferrer" className="social-link facebook">
            <span>📘</span> Facebook
          </a>
          <a href="https://instagram.com/perennia" target="_blank" rel="noopener noreferrer" className="social-link instagram">
            <span>📷</span> Instagram
          </a>
        </div>
      </div>
    );
  }

  return (
    <div className="social-feed">
      <div className="feed-header">
        <h3>Our Latest Posts</h3>
        <span className="live-indicator">
          <span className="live-dot"></span> Live Feed
        </span>
      </div>

      <div className="feed-grid">
        {posts.map((post) => (
          <div key={post.id} className="feed-card">
            <div className="card-header">
              <div className="platform-badges">
                {post.platforms.map((platform, idx) => (
                  <span
                    key={idx}
                    className="platform-badge"
                    style={{ backgroundColor: platformColors[platform.trim()] || '#6b7280' }}
                  >
                    {platformIcons[platform.trim()] || '📱'} {platform.trim()}
                  </span>
                ))}
              </div>
              <span className="post-time">{formatDate(post.posted_at)}</span>
            </div>

            {post.image_url && (
              <div className="card-image">
                <img src={post.image_url} alt="Post" loading="lazy" />
              </div>
            )}

            <div className="card-content">
              <p>{post.content}</p>
            </div>

            {post.engagement && Object.keys(post.engagement).length > 0 && (
              <div className="card-engagement">
                {post.engagement.likes > 0 && (
                  <span className="engagement-stat">👍 {post.engagement.likes}</span>
                )}
                {post.engagement.comments > 0 && (
                  <span className="engagement-stat">💬 {post.engagement.comments}</span>
                )}
                {post.engagement.shares > 0 && (
                  <span className="engagement-stat">↗️ {post.engagement.shares}</span>
                )}
              </div>
            )}
          </div>
        ))}
      </div>

      <div className="feed-footer">
        <p>Want to see more? Follow us on social media!</p>
      </div>
    </div>
  );
};

export default SocialFeed;
