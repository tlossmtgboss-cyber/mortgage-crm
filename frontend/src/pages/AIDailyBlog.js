/**
 * AI Daily Blog + PDF Content Factory
 *
 * Full-featured content generation dashboard:
 * - Upload PDFs and mine topics
 * - Configure voice profiles with sliders
 * - Generate blog posts and social content
 * - Manage content calendar
 * - Track performance analytics
 */
import React, { useState, useEffect, useCallback } from 'react';
import { blogAPI } from '../services/blogApi';
import './AIDailyBlog.css';

// ============ Voice Profile Sliders Component ============
const VoiceProfileSliders = ({ sliders, onChange }) => {
  const sliderConfig = [
    { key: 'professional_casual', leftLabel: 'Professional', rightLabel: 'Casual' },
    { key: 'bold_conservative', leftLabel: 'Bold', rightLabel: 'Conservative' },
    { key: 'detailed_concise', leftLabel: 'Detailed', rightLabel: 'Concise' },
    { key: 'formal_friendly', leftLabel: 'Formal', rightLabel: 'Friendly' },
    { key: 'technical_simple', leftLabel: 'Technical', rightLabel: 'Simple' },
  ];

  return (
    <div className="voice-sliders">
      {sliderConfig.map(({ key, leftLabel, rightLabel }) => (
        <div key={key} className="slider-row">
          <span className="slider-label left">{leftLabel}</span>
          <input
            type="range"
            min="0"
            max="100"
            value={sliders[key] || 50}
            onChange={(e) => onChange({ ...sliders, [key]: parseInt(e.target.value) })}
            className="voice-slider"
          />
          <span className="slider-label right">{rightLabel}</span>
        </div>
      ))}
    </div>
  );
};

// ============ Voice Profile Toggles Component ============
const VoiceProfileToggles = ({ toggles, onChange }) => {
  const toggleConfig = [
    { key: 'use_emojis', label: 'Use Emojis' },
    { key: 'use_hashtags', label: 'Use Hashtags' },
    { key: 'use_questions', label: 'Rhetorical Questions' },
    { key: 'use_statistics', label: 'Include Statistics' },
    { key: 'use_stories', label: 'Use Stories/Examples' },
  ];

  return (
    <div className="voice-toggles">
      {toggleConfig.map(({ key, label }) => (
        <label key={key} className="toggle-item">
          <input
            type="checkbox"
            checked={toggles[key] || false}
            onChange={(e) => onChange({ ...toggles, [key]: e.target.checked })}
          />
          <span className="toggle-label">{label}</span>
        </label>
      ))}
    </div>
  );
};

// ============ Batch Review Modal Component ============
const BatchReviewModal = ({ posts, onApprove, onDiscard, onApproveAll, onDiscardAll, onClose, onEdit }) => {
  const [currentIndex, setCurrentIndex] = useState(0);
  const [activePreview, setActivePreview] = useState('blog');
  const [editedPosts, setEditedPosts] = useState(posts.map(p => ({ ...p })));

  const currentPost = editedPosts[currentIndex];
  const approvedCount = editedPosts.filter(p => p._approved).length;
  const discardedCount = editedPosts.filter(p => p._discarded).length;
  const pendingCount = editedPosts.filter(p => !p._approved && !p._discarded).length;

  const updateCurrentPost = (updates) => {
    const newPosts = [...editedPosts];
    newPosts[currentIndex] = { ...newPosts[currentIndex], ...updates };
    setEditedPosts(newPosts);
  };

  const handleApprove = (index) => {
    const newPosts = [...editedPosts];
    newPosts[index] = { ...newPosts[index], _approved: true, _discarded: false };
    setEditedPosts(newPosts);
    // Move to next pending post
    const nextPending = newPosts.findIndex((p, i) => i > index && !p._approved && !p._discarded);
    if (nextPending !== -1) {
      setCurrentIndex(nextPending);
    }
  };

  const handleDiscard = (index) => {
    const newPosts = [...editedPosts];
    newPosts[index] = { ...newPosts[index], _approved: false, _discarded: true };
    setEditedPosts(newPosts);
    // Move to next pending post
    const nextPending = newPosts.findIndex((p, i) => i > index && !p._approved && !p._discarded);
    if (nextPending !== -1) {
      setCurrentIndex(nextPending);
    }
  };

  const handleApproveAll = () => {
    const approved = editedPosts.filter(p => !p._discarded).map(p => ({ ...p, _approved: true }));
    onApproveAll(approved);
  };

  const handleSaveApproved = () => {
    const approved = editedPosts.filter(p => p._approved);
    onApproveAll(approved);
  };

  return (
    <div className="modal-overlay batch-review-overlay" onClick={onClose}>
      <div className="modal batch-review-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header batch-review-header">
          <h3>Review Generated Posts ({editedPosts.length})</h3>
          <div className="review-stats">
            <span className="stat approved">{approvedCount} Approved</span>
            <span className="stat discarded">{discardedCount} Discarded</span>
            <span className="stat pending">{pendingCount} Pending</span>
          </div>
          <button className="close-btn" onClick={onClose}>×</button>
        </div>

        <div className="batch-review-body">
          {/* Post Navigation Sidebar */}
          <div className="review-sidebar">
            <h4>Posts</h4>
            <div className="post-list">
              {editedPosts.map((post, index) => (
                <div
                  key={index}
                  className={`post-item ${currentIndex === index ? 'active' : ''} ${post._approved ? 'approved' : ''} ${post._discarded ? 'discarded' : ''}`}
                  onClick={() => setCurrentIndex(index)}
                >
                  <span className="post-number">#{index + 1}</span>
                  <span className="post-title">{post.title?.substring(0, 30) || 'Untitled'}...</span>
                  <span className={`status-dot ${post._approved ? 'approved' : post._discarded ? 'discarded' : 'pending'}`}></span>
                </div>
              ))}
            </div>
            <div className="sidebar-actions">
              <button className="btn-approve-all" onClick={handleApproveAll}>
                Approve All
              </button>
              <button className="btn-discard-all" onClick={onDiscardAll}>
                Discard All
              </button>
            </div>
          </div>

          {/* Post Preview/Edit */}
          <div className="review-content">
            {currentPost && (
              <>
                <div className="review-content-header">
                  <input
                    type="text"
                    className="title-input"
                    value={currentPost.title || ''}
                    onChange={(e) => updateCurrentPost({ title: e.target.value })}
                    placeholder="Enter title..."
                  />
                </div>

                <div className="editor-tabs">
                  <button
                    className={`tab ${activePreview === 'blog' ? 'active' : ''}`}
                    onClick={() => setActivePreview('blog')}
                  >
                    Blog Post
                  </button>
                  <button
                    className={`tab ${activePreview === 'linkedin' ? 'active' : ''}`}
                    onClick={() => setActivePreview('linkedin')}
                  >
                    LinkedIn
                  </button>
                  <button
                    className={`tab ${activePreview === 'facebook' ? 'active' : ''}`}
                    onClick={() => setActivePreview('facebook')}
                  >
                    Facebook
                  </button>
                  <button
                    className={`tab ${activePreview === 'instagram' ? 'active' : ''}`}
                    onClick={() => setActivePreview('instagram')}
                  >
                    Instagram
                  </button>
                </div>

                <div className="editor-content">
                  {activePreview === 'blog' ? (
                    <textarea
                      className="blog-editor"
                      value={currentPost.blog_md || ''}
                      onChange={(e) => updateCurrentPost({ blog_md: e.target.value })}
                      placeholder="Blog content in Markdown..."
                    />
                  ) : (
                    <textarea
                      className="social-editor"
                      value={currentPost.social?.[activePreview] || ''}
                      onChange={(e) => updateCurrentPost({
                        social: { ...currentPost.social, [activePreview]: e.target.value }
                      })}
                      placeholder={`${activePreview} post content...`}
                    />
                  )}
                </div>

                {/* Compliance and Uniqueness Info */}
                <div className="review-meta">
                  {currentPost.compliance && (
                    <div className={`compliance-badge ${currentPost.compliance.is_compliant ? 'compliant' : 'not-compliant'}`}>
                      {currentPost.compliance.is_compliant ? '✓ Compliant' : `⚠ ${currentPost.compliance.issues?.length || 0} Issues`}
                    </div>
                  )}
                  {currentPost.uniqueness_score !== undefined && (
                    <div className="uniqueness-badge">
                      Uniqueness: {Math.round((currentPost.uniqueness_score || 0) * 100)}%
                    </div>
                  )}
                </div>

                {/* Post Actions */}
                <div className="review-actions">
                  <button
                    className={`btn-discard ${currentPost._discarded ? 'active' : ''}`}
                    onClick={() => handleDiscard(currentIndex)}
                    disabled={currentPost._approved}
                  >
                    {currentPost._discarded ? '✗ Discarded' : 'Discard'}
                  </button>
                  <button
                    className={`btn-approve ${currentPost._approved ? 'active' : ''}`}
                    onClick={() => handleApprove(currentIndex)}
                    disabled={currentPost._discarded}
                  >
                    {currentPost._approved ? '✓ Approved' : 'Approve'}
                  </button>
                </div>

                {/* Navigation */}
                <div className="review-navigation">
                  <button
                    className="btn-prev"
                    onClick={() => setCurrentIndex(Math.max(0, currentIndex - 1))}
                    disabled={currentIndex === 0}
                  >
                    ← Previous
                  </button>
                  <span className="nav-indicator">{currentIndex + 1} of {editedPosts.length}</span>
                  <button
                    className="btn-next"
                    onClick={() => setCurrentIndex(Math.min(editedPosts.length - 1, currentIndex + 1))}
                    disabled={currentIndex === editedPosts.length - 1}
                  >
                    Next →
                  </button>
                </div>
              </>
            )}
          </div>
        </div>

        <div className="modal-footer batch-review-footer">
          <button className="btn-cancel" onClick={onClose}>
            Cancel
          </button>
          <button
            className="btn-save-approved"
            onClick={handleSaveApproved}
            disabled={approvedCount === 0}
          >
            Save {approvedCount} Approved Post{approvedCount !== 1 ? 's' : ''}
          </button>
        </div>
      </div>
    </div>
  );
};

// ============ Content Editor Component ============
const ContentEditor = ({ content, onChange, onSave }) => {
  const [activePreview, setActivePreview] = useState('blog');

  return (
    <div className="content-editor">
      <div className="editor-header">
        <input
          type="text"
          className="title-input"
          value={content.title || ''}
          onChange={(e) => onChange({ ...content, title: e.target.value })}
          placeholder="Enter title..."
        />
      </div>

      <div className="editor-tabs">
        <button
          className={`tab ${activePreview === 'blog' ? 'active' : ''}`}
          onClick={() => setActivePreview('blog')}
        >
          Blog Post
        </button>
        <button
          className={`tab ${activePreview === 'linkedin' ? 'active' : ''}`}
          onClick={() => setActivePreview('linkedin')}
        >
          LinkedIn
        </button>
        <button
          className={`tab ${activePreview === 'facebook' ? 'active' : ''}`}
          onClick={() => setActivePreview('facebook')}
        >
          Facebook
        </button>
        <button
          className={`tab ${activePreview === 'instagram' ? 'active' : ''}`}
          onClick={() => setActivePreview('instagram')}
        >
          Instagram
        </button>
      </div>

      <div className="editor-content">
        {activePreview === 'blog' ? (
          <textarea
            className="blog-editor"
            value={content.blog_md || ''}
            onChange={(e) => onChange({ ...content, blog_md: e.target.value })}
            placeholder="Write your blog post in Markdown..."
          />
        ) : (
          <textarea
            className="social-editor"
            value={content.social?.[activePreview] || ''}
            onChange={(e) => onChange({
              ...content,
              social: { ...content.social, [activePreview]: e.target.value }
            })}
            placeholder={`Write your ${activePreview} post...`}
          />
        )}
      </div>

      <div className="editor-footer">
        <button className="btn-primary" onClick={() => onSave(content)}>
          Save Changes
        </button>
      </div>
    </div>
  );
};

// ============ Main Component ============
const AIDailyBlog = () => {
  // State
  const [activeTab, setActiveTab] = useState('generate');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);

  // Data
  const [voiceProfiles, setVoiceProfiles] = useState([]);
  const [complianceProfiles, setComplianceProfiles] = useState([]);
  const [sourceDocuments, setSourceDocuments] = useState([]);
  const [contentList, setContentList] = useState([]);
  const [topicQueue, setTopicQueue] = useState([]);
  const [analytics, setAnalytics] = useState(null);
  const [trendingTopics, setTrendingTopics] = useState([]);
  const [selectedTopics, setSelectedTopics] = useState([]);
  const [trendingDate, setTrendingDate] = useState('');
  const [serviceStatus, setServiceStatus] = useState(null);

  // Generation form state
  const [generateForm, setGenerateForm] = useState({
    topic: '',
    archetype: 'informative',
    keyword: '',
    sourceDocumentId: '',
    voiceProfileId: '',
    complianceProfileId: '',
    generateSocial: true,
    platforms: ['linkedin', 'facebook', 'instagram'],
  });

  // Generated content state
  const [generatedContent, setGeneratedContent] = useState(null);

  // Batch review state
  const [pendingReviewPosts, setPendingReviewPosts] = useState([]);
  const [showBatchReview, setShowBatchReview] = useState(false);
  const [generationProgress, setGenerationProgress] = useState({ current: 0, total: 0, topic: '' });

  // Voice profile modal state
  const [showVoiceModal, setShowVoiceModal] = useState(false);
  const [voiceModalData, setVoiceModalData] = useState({
    name: '',
    sliders_json: {},
    toggles_json: {},
  });

  // Document upload state
  const [uploadFile, setUploadFile] = useState(null);
  const [uploadTitle, setUploadTitle] = useState('');
  const [uploadAuthor, setUploadAuthor] = useState('');
  const [rightsAttestation, setRightsAttestation] = useState(false);

  // Load data on mount
  useEffect(() => {
    loadInitialData();
  }, []);

  const loadInitialData = async () => {
    setLoading(true);
    try {
      // Check service status first
      try {
        const statusRes = await blogAPI.getStatus();
        setServiceStatus(statusRes);
        if (!statusRes.llm_service_enabled) {
          setError('AI service not configured. Please contact your administrator to set up API keys.');
        }
      } catch (statusErr) {
        console.error('Failed to check service status:', statusErr);
      }

      // Load trending topics first - this is the main feature
      const trendingRes = await blogAPI.getTrendingTopics();
      setTrendingTopics(trendingRes.topics || []);
      setTrendingDate(trendingRes.date || '');

      // Try to load other data but don't fail if they error
      try {
        const [voiceRes, complianceRes, docsRes, contentRes, topicsRes] = await Promise.all([
          blogAPI.getVoiceProfiles().catch(() => ({ profiles: [] })),
          blogAPI.getComplianceProfiles().catch(() => ({ profiles: [] })),
          blogAPI.getSourceDocuments().catch(() => ({ documents: [] })),
          blogAPI.getContentList({ limit: 20 }).catch(() => ({ items: [] })),
          blogAPI.getTopics(null, false).catch(() => ({ topics: [] })),
        ]);

        setVoiceProfiles(voiceRes.profiles || []);
        setComplianceProfiles(complianceRes.profiles || []);
        setSourceDocuments(docsRes.documents || []);
        setContentList(contentRes.items || []);
        setTopicQueue(topicsRes.topics || []);
      } catch (innerErr) {
        console.log('Some data failed to load:', innerErr);
      }
    } catch (err) {
      console.error('Failed to load initial data:', err);
      let errorMessage = 'Failed to load data. Please refresh the page.';
      if (err.code === 'ECONNABORTED' || err.message?.includes('timeout')) {
        errorMessage = 'Connection timed out. Please check your internet connection and refresh.';
      } else if (err.response?.status === 404) {
        errorMessage = 'Blog API not found. Please contact support.';
      } else if (err.message?.includes('Network Error') || err.code === 'ERR_NETWORK') {
        errorMessage = 'Cannot connect to server. This may be due to a deployment in progress. Please wait 2-3 minutes and refresh the page.';
      } else if (err.message) {
        errorMessage = `Failed to load: ${err.message}`;
      }
      setError(errorMessage);
    }
    setLoading(false);
  };

  // Generate content - uses same review flow as batch generation for consistency
  const handleGenerate = async () => {
    if (!generateForm.topic.trim()) {
      setError('Please enter a topic');
      return;
    }

    setLoading(true);
    setError(null);
    setGeneratedContent(null);
    setGenerationProgress({ current: 1, total: 1, topic: generateForm.topic });

    try {
      // Check service status before generating
      try {
        const statusCheck = await blogAPI.getStatus();
        if (!statusCheck.llm_service_enabled) {
          setError('AI service is not configured. The ANTHROPIC_API_KEY environment variable needs to be set in Railway. Please contact your administrator.');
          setLoading(false);
          setGenerationProgress({ current: 0, total: 0, topic: '' });
          return;
        }
      } catch (statusErr) {
        console.error('Status check failed:', statusErr);
        // Continue anyway - the generate call will fail with a better error
      }

      const result = await blogAPI.generateContent({
        topic: generateForm.topic,
        archetype: generateForm.archetype,
        keyword: generateForm.keyword,
        source_document_id: generateForm.sourceDocumentId || null,
        voice_profile_id: generateForm.voiceProfileId || null,
        compliance_profile_id: generateForm.complianceProfileId || null,
        generate_social: generateForm.generateSocial,
        platforms: generateForm.platforms,
      });

      // Use same review flow as batch generation for consistent UX
      const generatedPost = {
        id: result.id,
        title: result.title,
        slug: result.slug,
        blog_md: result.blog_md,
        blog_html: result.blog_html,
        social: result.social,
        compliance: result.compliance,
        similarity: result.similarity,
        uniqueness_score: result.similarity?.uniqueness_score,
        metadata: result.metadata,
        _topic: generateForm.topic,
        _approved: false,
        _discarded: false,
      };

      // Show batch review modal (works for 1 or multiple posts)
      setPendingReviewPosts([generatedPost]);
      setShowBatchReview(true);
      setGenerateForm({ ...generateForm, topic: '' }); // Clear topic input

    } catch (err) {
      console.error('Blog generation error:', err);
      let errorMessage = 'Generation failed. Please try again.';

      if (err.code === 'ECONNABORTED' || err.message?.includes('timeout')) {
        errorMessage = 'Request timed out. The AI generation is taking too long. Please try again.';
      } else if (err.message?.includes('Network Error') || err.code === 'ERR_NETWORK') {
        errorMessage = 'Cannot connect to the server. Please check:\n1. Your internet connection\n2. The backend service is running on Railway\n3. Try refreshing the page in a few minutes';
      } else if (err.response?.status === 503) {
        errorMessage = 'AI service is not available. The ANTHROPIC_API_KEY environment variable needs to be configured in Railway.';
      } else if (err.response?.status === 500) {
        errorMessage = 'Server error during generation. Please check Railway logs for details.';
      } else if (err.response?.data?.detail) {
        errorMessage = err.response.data.detail;
      } else if (err.message) {
        errorMessage = err.message;
      }
      setError(errorMessage);
    }
    setLoading(false);
    setGenerationProgress({ current: 0, total: 0, topic: '' });
  };

  // Upload document
  const handleUploadDocument = async () => {
    if (!uploadFile || !uploadTitle.trim()) {
      setError('Please select a file and enter a title');
      return;
    }

    if (!rightsAttestation) {
      setError('Please confirm you have rights to use this content');
      return;
    }

    setLoading(true);
    setError(null);

    try {
      await blogAPI.uploadSourceDocument(uploadFile, uploadTitle, uploadAuthor, rightsAttestation);
      setSuccess('Document uploaded and processing...');
      setTimeout(() => setSuccess(null), 3000);

      // Reset form
      setUploadFile(null);
      setUploadTitle('');
      setUploadAuthor('');
      setRightsAttestation(false);

      // Refresh documents
      const docsRes = await blogAPI.getSourceDocuments();
      setSourceDocuments(docsRes.documents || []);

    } catch (err) {
      setError(err.response?.data?.detail || 'Upload failed. Please try again.');
    }
    setLoading(false);
  };

  // Mine topics from document
  const handleMineTopics = async (docId) => {
    setLoading(true);
    setError(null);

    try {
      const result = await blogAPI.mineTopics(docId, 10);
      setSuccess(`Mined ${result.mined_count} topic ideas!`);
      setTimeout(() => setSuccess(null), 3000);

      // Refresh topics
      const topicsRes = await blogAPI.getTopics(null, false);
      setTopicQueue(topicsRes.topics || []);

    } catch (err) {
      setError('Failed to mine topics. Please try again.');
    }
    setLoading(false);
  };

  // Use topic from queue
  const handleUseTopic = (topic) => {
    setGenerateForm({
      ...generateForm,
      topic: topic.topic,
      archetype: topic.archetype || 'informative',
      keyword: topic.keyword || '',
    });
    setActiveTab('generate');
  };

  // Save voice profile
  const handleSaveVoiceProfile = async () => {
    if (!voiceModalData.name.trim()) {
      setError('Please enter a profile name');
      return;
    }

    setLoading(true);
    try {
      await blogAPI.createVoiceProfile(voiceModalData);
      setSuccess('Voice profile created!');
      setShowVoiceModal(false);
      setVoiceModalData({ name: '', sliders_json: {}, toggles_json: {} });

      const voiceRes = await blogAPI.getVoiceProfiles();
      setVoiceProfiles(voiceRes.profiles || []);
    } catch (err) {
      setError('Failed to save voice profile');
    }
    setLoading(false);
  };

  // Load analytics
  const loadAnalytics = async () => {
    try {
      const analyticsRes = await blogAPI.getAnalyticsOverview(30);
      setAnalytics(analyticsRes);
    } catch (err) {
      console.error('Failed to load analytics:', err);
    }
  };

  useEffect(() => {
    if (activeTab === 'analytics') {
      loadAnalytics();
    }
  }, [activeTab]);

  // Archetype options
  const archetypes = [
    { value: 'informative', label: 'Informative', desc: 'Educational, fact-based content' },
    { value: 'story', label: 'Story', desc: 'Narrative-driven with case studies' },
    { value: 'data_driven', label: 'Data-Driven', desc: 'Statistics and market data focused' },
    { value: 'how_to', label: 'How-To', desc: 'Step-by-step guides' },
    { value: 'myth_busting', label: 'Myth-Busting', desc: 'Debunking misconceptions' },
  ];

  return (
    <div className="ai-daily-blog">
      {/* Header */}
      <div className="blog-header">
        <h1>AI Daily Blog</h1>
        <p className="subtitle">Content Factory powered by AI</p>
      </div>

      {/* Service Status Warning */}
      {serviceStatus && !serviceStatus.llm_service_enabled && (
        <div className="alert alert-warning" style={{ backgroundColor: '#fef3cd', border: '2px solid #ffc107', color: '#856404', marginBottom: '1rem', padding: '16px 20px', borderRadius: '8px' }}>
          <div style={{ display: 'flex', alignItems: 'flex-start', gap: '12px' }}>
            <span style={{ fontSize: '24px' }}>⚠️</span>
            <div>
              <strong style={{ fontSize: '16px', display: 'block', marginBottom: '8px' }}>AI Content Generation Not Available</strong>
              <p style={{ margin: '0 0 12px 0' }}>The AI service needs to be configured before you can generate blog posts.</p>
              <div style={{ backgroundColor: '#fff8e6', padding: '12px', borderRadius: '4px', fontSize: '13px' }}>
                <strong>To fix this (Administrator):</strong>
                <ol style={{ margin: '8px 0 0 0', paddingLeft: '20px' }}>
                  <li>Go to your <a href="https://railway.app" target="_blank" rel="noopener noreferrer" style={{ color: '#0066cc' }}>Railway dashboard</a></li>
                  <li>Select your mortgage-crm service</li>
                  <li>Go to Variables tab</li>
                  <li>Add: <code style={{ backgroundColor: '#f0f0f0', padding: '2px 6px', borderRadius: '3px' }}>ANTHROPIC_API_KEY</code> with your Anthropic API key</li>
                  <li>Redeploy the service</li>
                </ol>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Alerts */}
      {error && (
        <div className="alert alert-error" style={{ whiteSpace: 'pre-line' }}>
          {error}
          <button onClick={() => setError(null)}>×</button>
        </div>
      )}
      {success && (
        <div className="alert alert-success">
          {success}
          <button onClick={() => setSuccess(null)}>×</button>
        </div>
      )}

      {/* Navigation Tabs */}
      <div className="blog-tabs">
        <button
          className={`tab-btn ${activeTab === 'generate' ? 'active' : ''}`}
          onClick={() => setActiveTab('generate')}
        >
          Generate Content
        </button>
        <button
          className={`tab-btn ${activeTab === 'documents' ? 'active' : ''}`}
          onClick={() => setActiveTab('documents')}
        >
          Source Documents
        </button>
        <button
          className={`tab-btn ${activeTab === 'topics' ? 'active' : ''}`}
          onClick={() => setActiveTab('topics')}
        >
          Topic Queue ({topicQueue.length})
        </button>
        <button
          className={`tab-btn ${activeTab === 'content' ? 'active' : ''}`}
          onClick={() => setActiveTab('content')}
        >
          Content Library
        </button>
        <button
          className={`tab-btn ${activeTab === 'voices' ? 'active' : ''}`}
          onClick={() => setActiveTab('voices')}
        >
          Voice Profiles
        </button>
        <button
          className={`tab-btn ${activeTab === 'analytics' ? 'active' : ''}`}
          onClick={() => setActiveTab('analytics')}
        >
          Analytics
        </button>
      </div>

      {/* Tab Content */}
      <div className="blog-content">
        {loading && (
          <div className="loading-overlay">
            <div className="spinner"></div>
            <p>Processing...</p>
          </div>
        )}

        {/* Generate Tab */}
        {activeTab === 'generate' && (
          <div className="generate-tab">
            <div className="generate-form">
              {/* Trending Topics Section */}
              <div className="form-section trending-section">
                <div className="trending-header">
                  <h3>Top 10 Trending Mortgage Topics</h3>
                  <span className="trending-date">Based on searches from {trendingDate || 'yesterday'}</span>
                </div>

                {trendingTopics.length > 0 ? (
                  <>
                    <div className="trending-actions">
                      <button
                        className={`btn-select-all ${selectedTopics.length === trendingTopics.length ? 'all-selected' : ''}`}
                        onClick={() => {
                          if (selectedTopics.length === trendingTopics.length) {
                            setSelectedTopics([]);
                          } else {
                            setSelectedTopics(trendingTopics.map(t => t.rank));
                          }
                        }}
                      >
                        {selectedTopics.length === trendingTopics.length ? (
                          <>☑ Deselect All</>
                        ) : (
                          <>☐ Select All {trendingTopics.length}</>
                        )}
                      </button>
                      {selectedTopics.length > 0 && selectedTopics.length < trendingTopics.length && (
                        <span className="selected-count">{selectedTopics.length} of {trendingTopics.length} selected</span>
                      )}
                    </div>

                    <div className="trending-topics-list">
                      {trendingTopics.map((topic) => (
                        <div
                          key={topic.rank}
                          className={`trending-topic-item ${selectedTopics.includes(topic.rank) ? 'selected' : ''}`}
                          onClick={() => {
                            if (selectedTopics.includes(topic.rank)) {
                              setSelectedTopics(selectedTopics.filter(r => r !== topic.rank));
                            } else {
                              setSelectedTopics([...selectedTopics, topic.rank]);
                            }
                          }}
                        >
                          <div className="topic-rank">#{topic.rank}</div>
                          <div className="topic-content">
                            <div className="topic-title">{topic.topic}</div>
                            <div className="topic-meta">
                              <span className="topic-keyword">{topic.keyword}</span>
                              <span className={`topic-trend trend-${topic.trend}`}>
                                {topic.trend === 'up' ? '↑' : topic.trend === 'down' ? '↓' : '→'} {topic.trend}
                              </span>
                              <span className="topic-volume">{topic.search_volume?.toLocaleString()} searches</span>
                            </div>
                          </div>
                          <div className="topic-checkbox">
                            <input
                              type="checkbox"
                              checked={selectedTopics.includes(topic.rank)}
                              onChange={() => {}}
                            />
                          </div>
                        </div>
                      ))}
                    </div>

                    {selectedTopics.length > 0 && (
                      <div className="generate-selected-section">
                        <button
                          className="btn-generate-selected"
                          onClick={async () => {
                            const topicsToGenerate = trendingTopics.filter(t => selectedTopics.includes(t.rank));
                            setLoading(true);
                            setError(null);
                            setSuccess(null);

                            // Check service status before batch generation
                            try {
                              const statusCheck = await blogAPI.getStatus();
                              if (!statusCheck.llm_service_enabled) {
                                setError('AI service is not configured. The ANTHROPIC_API_KEY environment variable needs to be set in Railway. Please contact your administrator.');
                                setLoading(false);
                                return;
                              }
                            } catch (statusErr) {
                              console.error('Status check failed:', statusErr);
                              // Continue anyway - the generate call will fail with a better error
                            }

                            const totalCount = topicsToGenerate.length;
                            const generatedPosts = [];

                            let lastError = null;
                            for (let i = 0; i < topicsToGenerate.length; i++) {
                              const topic = topicsToGenerate[i];
                              // Update progress message
                              setGenerationProgress({ current: i + 1, total: totalCount, topic: topic.topic });
                              setSuccess(`Generating post ${i + 1} of ${totalCount}: "${topic.topic.substring(0, 40)}..."`);

                              try {
                                const result = await blogAPI.generateContent({
                                  topic: topic.topic,
                                  archetype: topic.archetype || 'informative',
                                  keyword: topic.keyword,
                                  generate_social: generateForm.generateSocial,
                                  platforms: generateForm.platforms,
                                });
                                // Store generated post for review
                                generatedPosts.push({
                                  id: result.id,
                                  title: result.title,
                                  slug: result.slug,
                                  blog_md: result.blog_md,
                                  blog_html: result.blog_html,
                                  social: result.social,
                                  compliance: result.compliance,
                                  similarity: result.similarity,
                                  uniqueness_score: result.similarity?.uniqueness_score,
                                  metadata: result.metadata,
                                  _topic: topic.topic,
                                  _approved: false,
                                  _discarded: false,
                                });
                              } catch (err) {
                                console.error(`Failed to generate: ${topic.topic}`, err);
                                lastError = err;
                                // Continue with next topic even if one fails
                              }
                            }

                            setLoading(false);
                            setGenerationProgress({ current: 0, total: 0, topic: '' });

                            if (generatedPosts.length > 0) {
                              // Show batch review modal
                              setPendingReviewPosts(generatedPosts);
                              setShowBatchReview(true);
                              setSuccess(null);
                              setSelectedTopics([]);
                            } else {
                              setSuccess(null);
                              // Show detailed error message
                              let errorMessage = 'Failed to generate content. Please try again.';
                              if (lastError?.message?.includes('Network Error') || lastError?.code === 'ERR_NETWORK') {
                                errorMessage = 'Cannot connect to the server. Please check your internet connection and try again.';
                              } else if (lastError?.response?.status === 503) {
                                errorMessage = 'AI service is not available. The ANTHROPIC_API_KEY environment variable needs to be configured in Railway.';
                              } else if (lastError?.response?.data?.detail) {
                                errorMessage = lastError.response.data.detail;
                              } else if (lastError?.message) {
                                errorMessage = lastError.message;
                              }
                              setError(errorMessage);
                            }
                          }}
                          disabled={loading}
                        >
                          {loading && generationProgress.total > 0
                            ? `Generating ${generationProgress.current}/${generationProgress.total}...`
                            : loading
                            ? 'Generating...'
                            : `Generate ${selectedTopics.length} Post${selectedTopics.length > 1 ? 's' : ''}`}
                        </button>
                        {selectedTopics.length > 3 && !loading && (
                          <span className="generation-warning">Generating multiple posts may take several minutes</span>
                        )}
                      </div>
                    )}
                  </>
                ) : (
                  <div className="no-topics">Loading trending topics...</div>
                )}
              </div>

              <div className="divider-or">
                <span>or enter a custom topic</span>
              </div>

              <div className="form-section">
                <h3>Custom Topic</h3>
                <input
                  type="text"
                  className="topic-input"
                  value={generateForm.topic}
                  onChange={(e) => setGenerateForm({ ...generateForm, topic: e.target.value })}
                  placeholder="Enter your topic or headline..."
                />
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label>Content Type</label>
                  <select
                    value={generateForm.archetype}
                    onChange={(e) => setGenerateForm({ ...generateForm, archetype: e.target.value })}
                  >
                    {archetypes.map(a => (
                      <option key={a.value} value={a.value}>{a.label}</option>
                    ))}
                  </select>
                  <span className="hint">
                    {archetypes.find(a => a.value === generateForm.archetype)?.desc}
                  </span>
                </div>

                <div className="form-group">
                  <label>Target Keyword (SEO)</label>
                  <input
                    type="text"
                    value={generateForm.keyword}
                    onChange={(e) => setGenerateForm({ ...generateForm, keyword: e.target.value })}
                    placeholder="e.g., first-time homebuyer"
                  />
                </div>
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label>Source Document</label>
                  <select
                    value={generateForm.sourceDocumentId}
                    onChange={(e) => setGenerateForm({ ...generateForm, sourceDocumentId: e.target.value })}
                  >
                    <option value="">None - Generate from scratch</option>
                    {sourceDocuments.filter(d => d.processed).map(d => (
                      <option key={d.id} value={d.id}>{d.title}</option>
                    ))}
                  </select>
                </div>

                <div className="form-group">
                  <label>Voice Profile</label>
                  <select
                    value={generateForm.voiceProfileId}
                    onChange={(e) => setGenerateForm({ ...generateForm, voiceProfileId: e.target.value })}
                  >
                    <option value="">Default Voice</option>
                    {voiceProfiles.map(v => (
                      <option key={v.id} value={v.id}>{v.name}</option>
                    ))}
                  </select>
                </div>

                <div className="form-group">
                  <label>Compliance Profile</label>
                  <select
                    value={generateForm.complianceProfileId}
                    onChange={(e) => setGenerateForm({ ...generateForm, complianceProfileId: e.target.value })}
                  >
                    <option value="">Default Compliance</option>
                    {complianceProfiles.map(c => (
                      <option key={c.id} value={c.id}>{c.name}</option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="form-section">
                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={generateForm.generateSocial}
                    onChange={(e) => setGenerateForm({ ...generateForm, generateSocial: e.target.checked })}
                  />
                  Generate social media posts
                </label>
              </div>

              <button
                className="btn-generate"
                onClick={handleGenerate}
                disabled={loading || !generateForm.topic.trim()}
              >
                {loading ? 'Generating...' : 'Generate Content'}
              </button>
            </div>

            {/* Note: Generated content is now shown in the Batch Review Modal for consistent UX */}
          </div>
        )}

        {/* Documents Tab */}
        {activeTab === 'documents' && (
          <div className="documents-tab">
            <div className="upload-section">
              <h3>Upload Source Document</h3>
              <p className="hint">Upload PDFs, guides, and training materials to mine for content ideas.</p>

              <div className="upload-form">
                <div className="form-group">
                  <label>Document Title</label>
                  <input
                    type="text"
                    value={uploadTitle}
                    onChange={(e) => setUploadTitle(e.target.value)}
                    placeholder="e.g., First-Time Homebuyer Guide"
                  />
                </div>

                <div className="form-group">
                  <label>Author (optional)</label>
                  <input
                    type="text"
                    value={uploadAuthor}
                    onChange={(e) => setUploadAuthor(e.target.value)}
                    placeholder="e.g., John Smith"
                  />
                </div>

                <div className="form-group">
                  <label>PDF File</label>
                  <input
                    type="file"
                    accept=".pdf"
                    onChange={(e) => setUploadFile(e.target.files[0])}
                  />
                </div>

                <label className="checkbox-label attestation">
                  <input
                    type="checkbox"
                    checked={rightsAttestation}
                    onChange={(e) => setRightsAttestation(e.target.checked)}
                  />
                  I confirm I have rights to use this content for blog generation
                </label>

                <button
                  className="btn-upload"
                  onClick={handleUploadDocument}
                  disabled={loading || !uploadFile || !uploadTitle.trim() || !rightsAttestation}
                >
                  Upload Document
                </button>
              </div>
            </div>

            <div className="documents-list">
              <h3>Your Documents</h3>
              {sourceDocuments.length === 0 ? (
                <p className="empty-state">No documents uploaded yet</p>
              ) : (
                <div className="document-grid">
                  {sourceDocuments.map(doc => (
                    <div key={doc.id} className={`document-card ${doc.processed ? 'processed' : 'processing'}`}>
                      <div className="doc-icon">PDF</div>
                      <div className="doc-info">
                        <h4>{doc.title}</h4>
                        <p>{doc.page_count} pages • {Math.round(doc.file_size / 1024)} KB</p>
                        {doc.processed ? (
                          <span className="status-badge success">Processed</span>
                        ) : doc.processing_error ? (
                          <span className="status-badge error">Error: {doc.processing_error}</span>
                        ) : (
                          <span className="status-badge pending">Processing...</span>
                        )}
                        {doc.topic_count > 0 && (
                          <p className="topic-count">{doc.topic_count} topics extracted</p>
                        )}
                      </div>
                      {doc.processed && (
                        <button
                          className="btn-mine"
                          onClick={() => handleMineTopics(doc.id)}
                        >
                          Mine Topics
                        </button>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}

        {/* Topics Tab */}
        {activeTab === 'topics' && (
          <div className="topics-tab">
            <h3>Topic Queue</h3>
            <p className="hint">Topics mined from your source documents. Click to use in generation.</p>

            {topicQueue.length === 0 ? (
              <p className="empty-state">No topics in queue. Upload documents and mine topics to get started.</p>
            ) : (
              <div className="topic-list">
                {topicQueue.map(topic => (
                  <div key={topic.id} className="topic-card">
                    <div className="topic-priority">Priority: {topic.priority}/10</div>
                    <h4>{topic.topic}</h4>
                    {topic.angle && <p className="topic-angle">{topic.angle}</p>}
                    <div className="topic-meta">
                      <span className="archetype-badge">{topic.archetype}</span>
                      {topic.keyword && <span className="keyword-badge">{topic.keyword}</span>}
                    </div>
                    <button
                      className="btn-use-topic"
                      onClick={() => handleUseTopic(topic)}
                    >
                      Use This Topic
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Content Library Tab */}
        {activeTab === 'content' && (
          <div className="content-tab">
            <h3>Content Library</h3>

            {contentList.length === 0 ? (
              <p className="empty-state">No content generated yet. Start by generating your first post!</p>
            ) : (
              <div className="content-list">
                {contentList.map(item => (
                  <div key={item.id} className="content-card">
                    <div className="content-status">
                      <span className={`status-badge ${item.status}`}>{item.status}</span>
                    </div>
                    <h4>{item.title || 'Untitled'}</h4>
                    <div className="content-meta">
                      <span className="archetype-badge">{item.archetype}</span>
                      <span className="date">
                        {new Date(item.created_at).toLocaleDateString()}
                      </span>
                      {item.uniqueness_score && (
                        <span className="uniqueness">
                          {Math.round(item.uniqueness_score * 100)}% unique
                        </span>
                      )}
                    </div>
                    {item.scheduled_at && (
                      <p className="scheduled">
                        Scheduled: {new Date(item.scheduled_at).toLocaleString()}
                      </p>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Voice Profiles Tab */}
        {activeTab === 'voices' && (
          <div className="voices-tab">
            <div className="voices-header">
              <h3>Voice Profiles</h3>
              <button
                className="btn-new-voice"
                onClick={() => setShowVoiceModal(true)}
              >
                + New Voice Profile
              </button>
            </div>

            {voiceProfiles.length === 0 ? (
              <p className="empty-state">No voice profiles created yet.</p>
            ) : (
              <div className="voice-grid">
                {voiceProfiles.map(profile => (
                  <div key={profile.id} className="voice-card">
                    <h4>{profile.name}</h4>
                    <div className="voice-preview">
                      {Object.entries(profile.sliders_json || {}).slice(0, 3).map(([key, value]) => (
                        <div key={key} className="slider-preview">
                          <span>{key.replace('_', ' → ')}</span>
                          <div className="mini-slider">
                            <div className="mini-fill" style={{ width: `${value}%` }}></div>
                          </div>
                        </div>
                      ))}
                    </div>
                    <div className="voice-toggles-preview">
                      {Object.entries(profile.toggles_json || {})
                        .filter(([_, v]) => v)
                        .map(([key]) => (
                          <span key={key} className="toggle-badge">{key.replace('use_', '')}</span>
                        ))}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Analytics Tab */}
        {activeTab === 'analytics' && (
          <div className="analytics-tab">
            <h3>Content Analytics</h3>

            {analytics ? (
              <div className="analytics-grid">
                <div className="analytics-card">
                  <h4>Content by Status</h4>
                  {Object.entries(analytics.content_by_status || {}).map(([status, count]) => (
                    <div key={status} className="stat-row">
                      <span className="stat-label">{status}</span>
                      <span className="stat-value">{count}</span>
                    </div>
                  ))}
                </div>

                <div className="analytics-card">
                  <h4>Content by Type</h4>
                  {Object.entries(analytics.content_by_archetype || {}).map(([type, count]) => (
                    <div key={type} className="stat-row">
                      <span className="stat-label">{type}</span>
                      <span className="stat-value">{count}</span>
                    </div>
                  ))}
                </div>

                <div className="analytics-card">
                  <h4>Performance (30 days)</h4>
                  <div className="stat-row">
                    <span className="stat-label">Views</span>
                    <span className="stat-value">{analytics.performance?.total_views || 0}</span>
                  </div>
                  <div className="stat-row">
                    <span className="stat-label">Likes</span>
                    <span className="stat-value">{analytics.performance?.total_likes || 0}</span>
                  </div>
                  <div className="stat-row">
                    <span className="stat-label">Comments</span>
                    <span className="stat-value">{analytics.performance?.total_comments || 0}</span>
                  </div>
                  <div className="stat-row">
                    <span className="stat-label">Shares</span>
                    <span className="stat-value">{analytics.performance?.total_shares || 0}</span>
                  </div>
                  <div className="stat-row">
                    <span className="stat-label">Clicks</span>
                    <span className="stat-value">{analytics.performance?.total_clicks || 0}</span>
                  </div>
                </div>
              </div>
            ) : (
              <p className="loading-text">Loading analytics...</p>
            )}
          </div>
        )}
      </div>

      {/* Voice Profile Modal */}
      {showVoiceModal && (
        <div className="modal-overlay" onClick={() => setShowVoiceModal(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3>Create Voice Profile</h3>
              <button className="close-btn" onClick={() => setShowVoiceModal(false)}>×</button>
            </div>
            <div className="modal-body">
              <div className="form-group">
                <label>Profile Name</label>
                <input
                  type="text"
                  value={voiceModalData.name}
                  onChange={(e) => setVoiceModalData({ ...voiceModalData, name: e.target.value })}
                  placeholder="e.g., Professional Authority"
                />
              </div>

              <h4>Tone Sliders</h4>
              <VoiceProfileSliders
                sliders={voiceModalData.sliders_json}
                onChange={(sliders) => setVoiceModalData({ ...voiceModalData, sliders_json: sliders })}
              />

              <h4>Content Options</h4>
              <VoiceProfileToggles
                toggles={voiceModalData.toggles_json}
                onChange={(toggles) => setVoiceModalData({ ...voiceModalData, toggles_json: toggles })}
              />
            </div>
            <div className="modal-footer">
              <button className="btn-cancel" onClick={() => setShowVoiceModal(false)}>
                Cancel
              </button>
              <button className="btn-save" onClick={handleSaveVoiceProfile}>
                Save Profile
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Batch Review Modal */}
      {showBatchReview && pendingReviewPosts.length > 0 && (
        <BatchReviewModal
          posts={pendingReviewPosts}
          onApprove={async (post, index) => {
            // Individual approve - mark in state
            const newPosts = [...pendingReviewPosts];
            newPosts[index] = { ...post, _approved: true };
            setPendingReviewPosts(newPosts);
          }}
          onDiscard={async (post, index) => {
            // Individual discard - delete from DB and mark in state
            try {
              await blogAPI.deleteContent(post.id);
            } catch (err) {
              console.error('Failed to delete discarded post:', err);
            }
            const newPosts = [...pendingReviewPosts];
            newPosts[index] = { ...post, _discarded: true };
            setPendingReviewPosts(newPosts);
          }}
          onApproveAll={async (approvedPosts) => {
            // Save approved posts (update any edits) and delete discarded
            setLoading(true);
            try {
              // Update approved posts with any edits
              for (const post of approvedPosts) {
                if (post._approved) {
                  await blogAPI.updateContent(post.id, {
                    title: post.title,
                    blog_md: post.blog_md,
                    social_json: post.social,
                  });
                }
              }

              // Delete discarded posts
              const discardedPosts = pendingReviewPosts.filter(p => p._discarded);
              for (const post of discardedPosts) {
                try {
                  await blogAPI.deleteContent(post.id);
                } catch (err) {
                  console.error('Failed to delete discarded post:', err);
                }
              }

              // Refresh content list
              const contentRes = await blogAPI.getContentList({ limit: 20 });
              setContentList(contentRes.items || []);

              const savedCount = approvedPosts.filter(p => p._approved).length;
              setSuccess(`Saved ${savedCount} blog post${savedCount !== 1 ? 's' : ''}!`);
              setTimeout(() => setSuccess(null), 3000);
            } catch (err) {
              setError('Failed to save posts. Please try again.');
            }
            setLoading(false);
            setShowBatchReview(false);
            setPendingReviewPosts([]);
          }}
          onDiscardAll={async () => {
            // Delete all generated posts
            setLoading(true);
            try {
              for (const post of pendingReviewPosts) {
                try {
                  await blogAPI.deleteContent(post.id);
                } catch (err) {
                  console.error('Failed to delete post:', err);
                }
              }
              setSuccess('All posts discarded');
              setTimeout(() => setSuccess(null), 3000);
            } catch (err) {
              setError('Failed to discard posts');
            }
            setLoading(false);
            setShowBatchReview(false);
            setPendingReviewPosts([]);
          }}
          onClose={() => {
            // Cancel - ask user what to do with generated posts
            if (window.confirm('Close without saving? Generated posts will remain as drafts in your content library.')) {
              setShowBatchReview(false);
              setPendingReviewPosts([]);
              // Refresh content list to show the drafts
              blogAPI.getContentList({ limit: 20 }).then(res => {
                setContentList(res.items || []);
              }).catch(() => {});
            }
          }}
          onEdit={(post, index) => {
            const newPosts = [...pendingReviewPosts];
            newPosts[index] = post;
            setPendingReviewPosts(newPosts);
          }}
        />
      )}
    </div>
  );
};

export default AIDailyBlog;
