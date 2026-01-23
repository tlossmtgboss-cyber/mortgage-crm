/**
 * Content Marketing Hub
 *
 * Comprehensive content marketing management including:
 * - Brand Voice profiles
 * - Content Calendars
 * - Content Briefs
 * - SEO Keywords
 */

import React, { useState, useEffect, useCallback } from 'react';
import { contentMarketingAPI } from '../services/contentMarketingApi';
import './ContentMarketing.css';

// ============================================================================
// BRAND VOICE TAB
// ============================================================================

function BrandVoiceTab() {
  const [voices, setVoices] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [editingVoice, setEditingVoice] = useState(null);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);

  // Form state
  const [formData, setFormData] = useState({
    name: '',
    source_url: '',
    source_content: '',
  });
  const [analyzing, setAnalyzing] = useState(false);

  const fetchVoices = useCallback(async () => {
    try {
      setLoading(true);
      const data = await contentMarketingAPI.listBrandVoices(false);
      setVoices(data.profiles || []);
    } catch (err) {
      setError('Failed to load brand voices');
      console.error(err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchVoices();
  }, [fetchVoices]);

  const handleCreate = async (e) => {
    e.preventDefault();
    if (!formData.name.trim()) return;

    try {
      setAnalyzing(true);
      await contentMarketingAPI.createBrandVoice(formData);
      setSuccess('Brand voice created successfully');
      setShowModal(false);
      setFormData({ name: '', source_url: '', source_content: '' });
      fetchVoices();
    } catch (err) {
      setError('Failed to create brand voice');
      console.error(err);
    } finally {
      setAnalyzing(false);
    }
  };

  const handleDelete = async (voiceId) => {
    if (!window.confirm('Are you sure you want to delete this brand voice?')) return;

    try {
      await contentMarketingAPI.deleteBrandVoice(voiceId);
      setSuccess('Brand voice deleted');
      fetchVoices();
    } catch (err) {
      setError('Failed to delete brand voice');
      console.error(err);
    }
  };

  const openCreateModal = () => {
    setEditingVoice(null);
    setFormData({ name: '', source_url: '', source_content: '' });
    setShowModal(true);
  };

  useEffect(() => {
    if (success || error) {
      const timer = setTimeout(() => {
        setSuccess(null);
        setError(null);
      }, 3000);
      return () => clearTimeout(timer);
    }
  }, [success, error]);

  if (loading) {
    return (
      <div className="cm-loading">
        <div className="cm-spinner" />
        <p>Loading brand voices...</p>
      </div>
    );
  }

  return (
    <div className="cm-tab-content">
      {success && <div className="cm-alert success">{success}</div>}
      {error && <div className="cm-alert error">{error}</div>}

      <div className="cm-section-header">
        <h2>Brand Voice Profiles</h2>
        <button className="btn-primary" onClick={openCreateModal}>
          + Create Voice Profile
        </button>
      </div>

      {voices.length === 0 ? (
        <div className="cm-empty">
          <div className="cm-empty-icon">🎤</div>
          <h3>No brand voices yet</h3>
          <p>Create your first brand voice profile to ensure consistent messaging</p>
          <button className="btn-primary" onClick={openCreateModal}>
            Create Brand Voice
          </button>
        </div>
      ) : (
        <div className="cm-cards-grid">
          {voices.map((voice) => (
            <div key={voice.id} className="cm-card">
              <div className="cm-card-header">
                <h3 className="cm-card-title">{voice.name}</h3>
                <span className={`cm-card-badge ${voice.is_active ? 'active' : 'draft'}`}>
                  {voice.is_active ? 'Active' : 'Inactive'}
                </span>
              </div>

              {voice.analysis && (
                <div className="voice-tone-bars">
                  <div className="tone-bar">
                    <span className="tone-bar-label">Formal</span>
                    <div className="tone-bar-track">
                      <div
                        className="tone-bar-fill"
                        style={{ width: `${(voice.analysis.tone_analysis?.formal_casual || 0.5) * 100}%` }}
                      />
                    </div>
                  </div>
                  <div className="tone-bar">
                    <span className="tone-bar-label">Friendly</span>
                    <div className="tone-bar-track">
                      <div
                        className="tone-bar-fill"
                        style={{ width: `${(voice.analysis.tone_analysis?.authoritative_friendly || 0.5) * 100}%` }}
                      />
                    </div>
                  </div>
                  <div className="tone-bar">
                    <span className="tone-bar-label">Simple</span>
                    <div className="tone-bar-track">
                      <div
                        className="tone-bar-fill"
                        style={{ width: `${(voice.analysis.tone_analysis?.technical_simple || 0.5) * 100}%` }}
                      />
                    </div>
                  </div>
                </div>
              )}

              {voice.analysis?.brand_values && (
                <div className="voice-tags">
                  {voice.analysis.brand_values.slice(0, 3).map((value, i) => (
                    <span key={i} className="voice-tag">{value}</span>
                  ))}
                </div>
              )}

              <div className="cm-card-actions">
                <button className="btn-secondary btn-sm" onClick={() => setEditingVoice(voice)}>
                  Edit
                </button>
                <button
                  className="btn-icon btn-danger"
                  onClick={() => handleDelete(voice.id)}
                  title="Delete"
                >
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2" />
                  </svg>
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Create Modal */}
      {showModal && (
        <div className="cm-modal-overlay" onClick={() => setShowModal(false)}>
          <div className="cm-modal" onClick={(e) => e.stopPropagation()}>
            <div className="cm-modal-header">
              <h2>Create Brand Voice</h2>
              <button className="cm-modal-close" onClick={() => setShowModal(false)}>
                &times;
              </button>
            </div>

            <form onSubmit={handleCreate}>
              <div className="cm-modal-body">
                <div className="cm-form-group">
                  <label>Profile Name *</label>
                  <input
                    type="text"
                    value={formData.name}
                    onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                    placeholder="e.g., Professional & Friendly"
                    required
                  />
                </div>

                <div className="cm-form-group">
                  <label>Website URL (for analysis)</label>
                  <input
                    type="url"
                    value={formData.source_url}
                    onChange={(e) => setFormData({ ...formData, source_url: e.target.value })}
                    placeholder="https://your-website.com"
                  />
                  <p className="cm-form-hint">We'll analyze your website to extract brand voice characteristics</p>
                </div>

                <div className="cm-form-group">
                  <label>Or paste sample content</label>
                  <textarea
                    value={formData.source_content}
                    onChange={(e) => setFormData({ ...formData, source_content: e.target.value })}
                    placeholder="Paste marketing copy, blog posts, or other content that represents your brand voice..."
                    rows={5}
                  />
                </div>
              </div>

              <div className="cm-modal-footer">
                <button type="button" className="btn-secondary" onClick={() => setShowModal(false)}>
                  Cancel
                </button>
                <button type="submit" className="btn-primary" disabled={analyzing || !formData.name.trim()}>
                  {analyzing ? 'Analyzing...' : 'Create & Analyze'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

// ============================================================================
// CALENDARS TAB
// ============================================================================

function CalendarsTab() {
  const [calendars, setCalendars] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);

  // Form state
  const [formData, setFormData] = useState({
    name: '',
    description: '',
    start_date: '',
    end_date: '',
    channels: ['blog', 'linkedin'],
    posts_per_week: 3,
  });
  const [creating, setCreating] = useState(false);

  const fetchCalendars = useCallback(async () => {
    try {
      setLoading(true);
      const data = await contentMarketingAPI.listCalendars();
      setCalendars(data.calendars || []);
    } catch (err) {
      setError('Failed to load calendars');
      console.error(err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchCalendars();
  }, [fetchCalendars]);

  const handleCreate = async (e) => {
    e.preventDefault();
    if (!formData.name.trim() || !formData.start_date || !formData.end_date) return;

    try {
      setCreating(true);
      await contentMarketingAPI.createCalendar(formData);
      setSuccess('Calendar created with content briefs');
      setShowModal(false);
      setFormData({
        name: '',
        description: '',
        start_date: '',
        end_date: '',
        channels: ['blog', 'linkedin'],
        posts_per_week: 3,
      });
      fetchCalendars();
    } catch (err) {
      setError('Failed to create calendar');
      console.error(err);
    } finally {
      setCreating(false);
    }
  };

  const handleDelete = async (calendarId) => {
    if (!window.confirm('Delete this calendar and all its briefs?')) return;

    try {
      await contentMarketingAPI.deleteCalendar(calendarId, true);
      setSuccess('Calendar deleted');
      fetchCalendars();
    } catch (err) {
      setError('Failed to delete calendar');
      console.error(err);
    }
  };

  const handleStatusChange = async (calendarId, newStatus) => {
    try {
      if (newStatus === 'active') {
        await contentMarketingAPI.activateCalendar(calendarId);
      } else {
        await contentMarketingAPI.pauseCalendar(calendarId);
      }
      fetchCalendars();
    } catch (err) {
      setError('Failed to update calendar status');
      console.error(err);
    }
  };

  const formatDate = (dateStr) => {
    if (!dateStr) return '';
    return new Date(dateStr).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    });
  };

  const toggleChannel = (channel) => {
    setFormData((prev) => ({
      ...prev,
      channels: prev.channels.includes(channel)
        ? prev.channels.filter((c) => c !== channel)
        : [...prev.channels, channel],
    }));
  };

  useEffect(() => {
    if (success || error) {
      const timer = setTimeout(() => {
        setSuccess(null);
        setError(null);
      }, 3000);
      return () => clearTimeout(timer);
    }
  }, [success, error]);

  if (loading) {
    return (
      <div className="cm-loading">
        <div className="cm-spinner" />
        <p>Loading calendars...</p>
      </div>
    );
  }

  const CHANNELS = ['blog', 'linkedin', 'facebook', 'instagram', 'email', 'sms'];

  return (
    <div className="cm-tab-content">
      {success && <div className="cm-alert success">{success}</div>}
      {error && <div className="cm-alert error">{error}</div>}

      <div className="cm-section-header">
        <h2>Content Calendars</h2>
        <button className="btn-primary" onClick={() => setShowModal(true)}>
          + Create Calendar
        </button>
      </div>

      {calendars.length === 0 ? (
        <div className="cm-empty">
          <div className="cm-empty-icon">📅</div>
          <h3>No calendars yet</h3>
          <p>Create a content calendar to plan and schedule your marketing content</p>
          <button className="btn-primary" onClick={() => setShowModal(true)}>
            Create Calendar
          </button>
        </div>
      ) : (
        <div className="cm-cards-grid">
          {calendars.map((calendar) => (
            <div key={calendar.id} className="cm-card">
              <div className="cm-card-header">
                <h3 className="cm-card-title">{calendar.name}</h3>
                <span className={`cm-card-badge ${calendar.status || 'draft'}`}>
                  {calendar.status || 'Draft'}
                </span>
              </div>

              <div className="cm-card-meta">
                <span>📅 {formatDate(calendar.start_date)} - {formatDate(calendar.end_date)}</span>
              </div>

              <div className="channel-pills">
                {(calendar.channels || []).map((channel) => (
                  <span key={channel} className={`channel-pill ${channel}`}>
                    {channel}
                  </span>
                ))}
              </div>

              <div className="cm-card-meta" style={{ marginTop: 12 }}>
                <span>📝 {calendar.brief_count || 0} briefs</span>
                <span>✅ {calendar.published_count || 0} published</span>
              </div>

              <div className="cm-card-actions">
                {calendar.status === 'active' ? (
                  <button
                    className="btn-secondary btn-sm"
                    onClick={() => handleStatusChange(calendar.id, 'paused')}
                  >
                    Pause
                  </button>
                ) : (
                  <button
                    className="btn-secondary btn-sm"
                    onClick={() => handleStatusChange(calendar.id, 'active')}
                  >
                    Activate
                  </button>
                )}
                <button
                  className="btn-icon btn-danger"
                  onClick={() => handleDelete(calendar.id)}
                  title="Delete"
                >
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2" />
                  </svg>
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Create Modal */}
      {showModal && (
        <div className="cm-modal-overlay" onClick={() => setShowModal(false)}>
          <div className="cm-modal" onClick={(e) => e.stopPropagation()}>
            <div className="cm-modal-header">
              <h2>Create Content Calendar</h2>
              <button className="cm-modal-close" onClick={() => setShowModal(false)}>
                &times;
              </button>
            </div>

            <form onSubmit={handleCreate}>
              <div className="cm-modal-body">
                <div className="cm-form-group">
                  <label>Calendar Name *</label>
                  <input
                    type="text"
                    value={formData.name}
                    onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                    placeholder="e.g., Q1 2026 Content Plan"
                    required
                  />
                </div>

                <div className="cm-form-group">
                  <label>Description</label>
                  <textarea
                    value={formData.description}
                    onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                    placeholder="Brief description of this calendar's focus..."
                    rows={2}
                  />
                </div>

                <div className="cm-form-row">
                  <div className="cm-form-group">
                    <label>Start Date *</label>
                    <input
                      type="date"
                      value={formData.start_date}
                      onChange={(e) => setFormData({ ...formData, start_date: e.target.value })}
                      required
                    />
                  </div>
                  <div className="cm-form-group">
                    <label>End Date *</label>
                    <input
                      type="date"
                      value={formData.end_date}
                      onChange={(e) => setFormData({ ...formData, end_date: e.target.value })}
                      required
                    />
                  </div>
                </div>

                <div className="cm-form-group">
                  <label>Channels</label>
                  <div className="channel-pills" style={{ gap: 8 }}>
                    {CHANNELS.map((channel) => (
                      <button
                        key={channel}
                        type="button"
                        className={`channel-pill ${channel} ${formData.channels.includes(channel) ? '' : 'inactive'}`}
                        onClick={() => toggleChannel(channel)}
                        style={{
                          opacity: formData.channels.includes(channel) ? 1 : 0.4,
                          cursor: 'pointer',
                        }}
                      >
                        {channel}
                      </button>
                    ))}
                  </div>
                </div>

                <div className="cm-form-group">
                  <label>Posts per Week</label>
                  <input
                    type="number"
                    min="1"
                    max="14"
                    value={formData.posts_per_week}
                    onChange={(e) => setFormData({ ...formData, posts_per_week: parseInt(e.target.value) || 3 })}
                  />
                </div>
              </div>

              <div className="cm-modal-footer">
                <button type="button" className="btn-secondary" onClick={() => setShowModal(false)}>
                  Cancel
                </button>
                <button
                  type="submit"
                  className="btn-primary"
                  disabled={creating || !formData.name.trim() || !formData.start_date || !formData.end_date}
                >
                  {creating ? 'Creating...' : 'Create Calendar'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

// ============================================================================
// BRIEFS TAB
// ============================================================================

function BriefsTab() {
  const [briefs, setBriefs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [statusFilter, setStatusFilter] = useState('all');

  const fetchBriefs = useCallback(async () => {
    try {
      setLoading(true);
      const params = statusFilter !== 'all' ? { status: statusFilter } : {};
      const data = await contentMarketingAPI.listBriefs({ ...params, limit: 50 });
      setBriefs(data.briefs || []);
    } catch (err) {
      setError('Failed to load briefs');
      console.error(err);
    } finally {
      setLoading(false);
    }
  }, [statusFilter]);

  useEffect(() => {
    fetchBriefs();
  }, [fetchBriefs]);

  const formatDate = (dateStr) => {
    if (!dateStr) return '';
    return new Date(dateStr).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
    });
  };

  const getStatusColor = (status) => {
    const colors = {
      planned: 'draft',
      draft: 'draft',
      approved: 'active',
      scheduled: 'active',
      published: 'active',
    };
    return colors[status] || 'draft';
  };

  if (loading) {
    return (
      <div className="cm-loading">
        <div className="cm-spinner" />
        <p>Loading briefs...</p>
      </div>
    );
  }

  return (
    <div className="cm-tab-content">
      {error && <div className="cm-alert error">{error}</div>}

      <div className="cm-section-header">
        <h2>Content Briefs</h2>
        <div style={{ display: 'flex', gap: 12 }}>
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="btn-secondary"
            style={{ padding: '8px 12px' }}
          >
            <option value="all">All Status</option>
            <option value="planned">Planned</option>
            <option value="draft">Draft</option>
            <option value="approved">Approved</option>
            <option value="published">Published</option>
          </select>
        </div>
      </div>

      {briefs.length === 0 ? (
        <div className="cm-empty">
          <div className="cm-empty-icon">📝</div>
          <h3>No briefs found</h3>
          <p>Create a content calendar to automatically generate briefs</p>
        </div>
      ) : (
        <div className="cm-cards-grid">
          {briefs.map((brief) => (
            <div key={brief.id} className="cm-card">
              <div className="cm-card-header">
                <h3 className="cm-card-title">{brief.topic || 'Untitled Brief'}</h3>
                <span className={`cm-card-badge ${getStatusColor(brief.status)}`}>
                  {brief.status}
                </span>
              </div>

              <div className="cm-card-meta">
                <span>📅 {formatDate(brief.scheduled_date)}</span>
                {brief.archetype && <span>📚 {brief.archetype}</span>}
              </div>

              <div className="channel-pills">
                {(brief.channels || []).map((channel) => (
                  <span key={channel} className={`channel-pill ${channel}`}>
                    {channel}
                  </span>
                ))}
              </div>

              {brief.primary_keyword && (
                <div className="cm-card-meta" style={{ marginTop: 12 }}>
                  <span>🔑 {brief.primary_keyword}</span>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ============================================================================
// KEYWORDS TAB
// ============================================================================

function KeywordsTab() {
  const [keywords, setKeywords] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);

  // Form state
  const [formData, setFormData] = useState({
    keyword: '',
    category: '',
    search_volume: '',
    difficulty: 50,
    target_ranking: 10,
    priority: 3,
  });

  const fetchKeywords = useCallback(async () => {
    try {
      setLoading(true);
      const data = await contentMarketingAPI.listKeywords({ limit: 100 });
      setKeywords(data.keywords || []);
    } catch (err) {
      // Keywords endpoint may not exist yet
      console.error(err);
      setKeywords([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchKeywords();
  }, [fetchKeywords]);

  const handleCreate = async (e) => {
    e.preventDefault();
    if (!formData.keyword.trim()) return;

    try {
      await contentMarketingAPI.addKeyword({
        ...formData,
        search_volume: formData.search_volume ? parseInt(formData.search_volume) : null,
      });
      setSuccess('Keyword added');
      setShowModal(false);
      setFormData({
        keyword: '',
        category: '',
        search_volume: '',
        difficulty: 50,
        target_ranking: 10,
        priority: 3,
      });
      fetchKeywords();
    } catch (err) {
      setError('Failed to add keyword');
      console.error(err);
    }
  };

  const getDifficultyClass = (difficulty) => {
    if (difficulty < 30) return 'easy';
    if (difficulty < 60) return 'medium';
    return 'hard';
  };

  useEffect(() => {
    if (success || error) {
      const timer = setTimeout(() => {
        setSuccess(null);
        setError(null);
      }, 3000);
      return () => clearTimeout(timer);
    }
  }, [success, error]);

  if (loading) {
    return (
      <div className="cm-loading">
        <div className="cm-spinner" />
        <p>Loading keywords...</p>
      </div>
    );
  }

  return (
    <div className="cm-tab-content">
      {success && <div className="cm-alert success">{success}</div>}
      {error && <div className="cm-alert error">{error}</div>}

      <div className="cm-section-header">
        <h2>SEO Keywords</h2>
        <button className="btn-primary" onClick={() => setShowModal(true)}>
          + Add Keyword
        </button>
      </div>

      {keywords.length === 0 ? (
        <div className="cm-empty">
          <div className="cm-empty-icon">🔑</div>
          <h3>No keywords tracked</h3>
          <p>Add keywords to track your SEO performance and content strategy</p>
          <button className="btn-primary" onClick={() => setShowModal(true)}>
            Add Your First Keyword
          </button>
        </div>
      ) : (
        <table className="keyword-table">
          <thead>
            <tr>
              <th>Keyword</th>
              <th>Category</th>
              <th>Volume</th>
              <th>Difficulty</th>
              <th>Ranking</th>
              <th>Target</th>
              <th>Priority</th>
            </tr>
          </thead>
          <tbody>
            {keywords.map((kw) => (
              <tr key={kw.id}>
                <td><strong>{kw.keyword}</strong></td>
                <td>{kw.category || '-'}</td>
                <td>{kw.search_volume?.toLocaleString() || '-'}</td>
                <td>
                  <div className="difficulty-bar">
                    <div
                      className={`difficulty-fill ${getDifficultyClass(kw.difficulty || 0)}`}
                      style={{ width: `${kw.difficulty || 0}%` }}
                    />
                  </div>
                </td>
                <td>
                  {kw.current_ranking ? (
                    <span className={`ranking-badge ${kw.current_ranking <= 10 ? 'top-10' : kw.current_ranking <= 20 ? 'top-20' : ''}`}>
                      #{kw.current_ranking}
                    </span>
                  ) : (
                    '-'
                  )}
                </td>
                <td>#{kw.target_ranking || 10}</td>
                <td>{'⭐'.repeat(kw.priority || 3)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {/* Add Keyword Modal */}
      {showModal && (
        <div className="cm-modal-overlay" onClick={() => setShowModal(false)}>
          <div className="cm-modal" onClick={(e) => e.stopPropagation()}>
            <div className="cm-modal-header">
              <h2>Add Keyword</h2>
              <button className="cm-modal-close" onClick={() => setShowModal(false)}>
                &times;
              </button>
            </div>

            <form onSubmit={handleCreate}>
              <div className="cm-modal-body">
                <div className="cm-form-group">
                  <label>Keyword *</label>
                  <input
                    type="text"
                    value={formData.keyword}
                    onChange={(e) => setFormData({ ...formData, keyword: e.target.value })}
                    placeholder="e.g., first time home buyer"
                    required
                  />
                </div>

                <div className="cm-form-row">
                  <div className="cm-form-group">
                    <label>Category</label>
                    <select
                      value={formData.category}
                      onChange={(e) => setFormData({ ...formData, category: e.target.value })}
                    >
                      <option value="">Select...</option>
                      <option value="mortgage_types">Mortgage Types</option>
                      <option value="home_buying">Home Buying</option>
                      <option value="refinancing">Refinancing</option>
                      <option value="rates">Rates</option>
                      <option value="process">Process</option>
                      <option value="local">Local</option>
                    </select>
                  </div>
                  <div className="cm-form-group">
                    <label>Search Volume</label>
                    <input
                      type="number"
                      value={formData.search_volume}
                      onChange={(e) => setFormData({ ...formData, search_volume: e.target.value })}
                      placeholder="e.g., 5000"
                    />
                  </div>
                </div>

                <div className="cm-form-row">
                  <div className="cm-form-group">
                    <label>Difficulty (0-100)</label>
                    <input
                      type="number"
                      min="0"
                      max="100"
                      value={formData.difficulty}
                      onChange={(e) => setFormData({ ...formData, difficulty: parseInt(e.target.value) || 50 })}
                    />
                  </div>
                  <div className="cm-form-group">
                    <label>Target Ranking</label>
                    <input
                      type="number"
                      min="1"
                      max="100"
                      value={formData.target_ranking}
                      onChange={(e) => setFormData({ ...formData, target_ranking: parseInt(e.target.value) || 10 })}
                    />
                  </div>
                </div>

                <div className="cm-form-group">
                  <label>Priority (1-5)</label>
                  <input
                    type="range"
                    min="1"
                    max="5"
                    value={formData.priority}
                    onChange={(e) => setFormData({ ...formData, priority: parseInt(e.target.value) })}
                  />
                  <div style={{ textAlign: 'center', marginTop: 4 }}>
                    {'⭐'.repeat(formData.priority)}
                  </div>
                </div>
              </div>

              <div className="cm-modal-footer">
                <button type="button" className="btn-secondary" onClick={() => setShowModal(false)}>
                  Cancel
                </button>
                <button type="submit" className="btn-primary" disabled={!formData.keyword.trim()}>
                  Add Keyword
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

// ============================================================================
// MAIN COMPONENT
// ============================================================================

export default function ContentMarketing({ embedded = false }) {
  const [activeTab, setActiveTab] = useState('brand-voice');

  const TABS = [
    { id: 'brand-voice', name: 'Brand Voice', icon: '🎤' },
    { id: 'calendars', name: 'Calendars', icon: '📅' },
    { id: 'briefs', name: 'Briefs', icon: '📝' },
    { id: 'keywords', name: 'SEO Keywords', icon: '🔑' },
  ];

  const renderTab = () => {
    switch (activeTab) {
      case 'brand-voice':
        return <BrandVoiceTab />;
      case 'calendars':
        return <CalendarsTab />;
      case 'briefs':
        return <BriefsTab />;
      case 'keywords':
        return <KeywordsTab />;
      default:
        return <BrandVoiceTab />;
    }
  };

  return (
    <div className={`content-marketing ${embedded ? 'embedded' : ''}`}>
      {!embedded && (
        <div className="cm-header">
          <h1>Content Marketing</h1>
          <p>Manage your brand voice, content calendars, and SEO strategy</p>
        </div>
      )}

      <div className="cm-tabs">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            className={`cm-tab-btn ${activeTab === tab.id ? 'active' : ''}`}
            onClick={() => setActiveTab(tab.id)}
          >
            <span className="cm-tab-icon">{tab.icon}</span>
            {tab.name}
          </button>
        ))}
      </div>

      {renderTab()}
    </div>
  );
}
