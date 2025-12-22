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

  // Generate content
  const handleGenerate = async () => {
    if (!generateForm.topic.trim()) {
      setError('Please enter a topic');
      return;
    }

    setLoading(true);
    setError(null);
    setGeneratedContent(null);

    try {
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

      setGeneratedContent({
        id: result.id,
        title: result.title,
        slug: result.slug,
        blog_md: result.blog_md,
        blog_html: result.blog_html,
        social: result.social,
        compliance: result.compliance,
        similarity: result.similarity,
        metadata: result.metadata,
      });

      setSuccess('Content generated successfully!');
      setTimeout(() => setSuccess(null), 3000);

      // Refresh content list
      const contentRes = await blogAPI.getContentList({ limit: 20 });
      setContentList(contentRes.items || []);

    } catch (err) {
      console.error('Blog generation error:', err);
      let errorMessage = 'Generation failed. Please try again.';
      if (err.code === 'ECONNABORTED' || err.message?.includes('timeout')) {
        errorMessage = 'Request timed out. The AI generation is taking too long. Please try again.';
      } else if (err.response?.data?.detail) {
        errorMessage = err.response.data.detail;
      } else if (err.message) {
        errorMessage = err.message;
      }
      setError(errorMessage);
    }
    setLoading(false);
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
        <div className="alert alert-warning" style={{ backgroundColor: '#fef3cd', borderColor: '#ffc107', color: '#856404', marginBottom: '1rem', padding: '12px 16px', borderRadius: '6px', display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span style={{ fontSize: '18px' }}>⚠️</span>
          <span>
            <strong>AI Service Not Configured:</strong> {serviceStatus.message}
          </span>
        </div>
      )}

      {/* Alerts */}
      {error && (
        <div className="alert alert-error">
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
                            let successCount = 0;
                            const totalCount = topicsToGenerate.length;

                            let lastError = null;
                            for (let i = 0; i < topicsToGenerate.length; i++) {
                              const topic = topicsToGenerate[i];
                              // Update progress message
                              setSuccess(`Generating post ${i + 1} of ${totalCount}: "${topic.topic.substring(0, 40)}..."`);

                              try {
                                await blogAPI.generateContent({
                                  topic: topic.topic,
                                  archetype: topic.archetype,
                                  keyword: topic.keyword,
                                  generate_social: generateForm.generateSocial,
                                  platforms: generateForm.platforms,
                                });
                                successCount++;
                              } catch (err) {
                                console.error(`Failed to generate: ${topic.topic}`, err);
                                lastError = err;
                                // Continue with next topic even if one fails
                              }
                            }

                            setLoading(false);
                            if (successCount > 0) {
                              setSuccess(`Successfully generated ${successCount} of ${totalCount} blog post${successCount > 1 ? 's' : ''}!`);
                              setSelectedTopics([]);
                              // Refresh content list
                              try {
                                const contentRes = await blogAPI.getContentList({ limit: 20 });
                                setContentList(contentRes.items || []);
                              } catch (e) {}
                            } else {
                              setSuccess(null);
                              // Show detailed error message
                              let errorMessage = 'Failed to generate content. Please try again.';
                              if (lastError?.response?.data?.detail) {
                                errorMessage = lastError.response.data.detail;
                              } else if (lastError?.message) {
                                errorMessage = lastError.message;
                              }
                              setError(errorMessage);
                            }
                          }}
                          disabled={loading}
                        >
                          {loading ? 'Generating...' : `Generate ${selectedTopics.length} Post${selectedTopics.length > 1 ? 's' : ''}`}
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

            {/* Generated Content Preview */}
            {generatedContent && (
              <div className="generated-preview">
                <h3>Generated Content</h3>
                <ContentEditor
                  content={generatedContent}
                  onChange={setGeneratedContent}
                  onSave={async (content) => {
                    try {
                      await blogAPI.updateContent(content.id, {
                        title: content.title,
                        blog_md: content.blog_md,
                        social_json: content.social,
                      });
                      setSuccess('Content saved!');
                    } catch (err) {
                      setError('Failed to save content');
                    }
                  }}
                />

                {/* Compliance Check Results */}
                {generatedContent.compliance && (
                  <div className={`compliance-result ${generatedContent.compliance.is_compliant ? 'compliant' : 'not-compliant'}`}>
                    <h4>Compliance Check</h4>
                    <p>
                      {generatedContent.compliance.is_compliant
                        ? 'Content is compliant'
                        : `${generatedContent.compliance.issues?.length || 0} issues found`}
                    </p>
                    {generatedContent.compliance.issues?.map((issue, i) => (
                      <div key={i} className="issue-item">
                        <span className="issue-type">{issue.type}</span>
                        <span className="issue-message">{issue.message}</span>
                      </div>
                    ))}
                  </div>
                )}

                {/* Similarity Check Results */}
                {generatedContent.similarity && (
                  <div className={`similarity-result ${generatedContent.similarity.is_unique ? 'unique' : 'not-unique'}`}>
                    <h4>Uniqueness Score</h4>
                    <div className="score-bar">
                      <div
                        className="score-fill"
                        style={{ width: `${(generatedContent.similarity.uniqueness_score || 0) * 100}%` }}
                      ></div>
                    </div>
                    <p>{Math.round((generatedContent.similarity.uniqueness_score || 0) * 100)}% unique</p>
                  </div>
                )}
              </div>
            )}
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
    </div>
  );
};

export default AIDailyBlog;
