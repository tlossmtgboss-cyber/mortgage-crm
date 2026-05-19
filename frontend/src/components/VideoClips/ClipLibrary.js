import React, { useState, useEffect, useCallback } from 'react';
import api from '../../services/api';
import ClipRecorder from './ClipRecorder';
import ClipPlayer from './ClipPlayer';
import ScheduleMeetingButton from './ScheduleMeetingButton';
import { sanitizeText } from '../../utils/sanitize';
import './ClipLibrary.css';
import { toast } from '../../utils/toast';

const ClipLibrary = () => {
  // State
  const [clips, setClips] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showRecorder, setShowRecorder] = useState(false);
  const [selectedClip, setSelectedClip] = useState(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [viewMode, setViewMode] = useState('grid'); // grid, list
  const [templates, setTemplates] = useState([]);
  const [showTemplateModal, setShowTemplateModal] = useState(false);
  const [selectedTemplate, setSelectedTemplate] = useState(null);
  const [showShareModal, setShowShareModal] = useState(null);
  const [shareSettings, setShareSettings] = useState({
    recipient_email: '',
    recipient_name: '',
    allow_download: false,
    require_email: false,
    expires_in_days: null,
    include_scheduling: true  // Schedule Smart integration
  });

  // Load clips
  const loadClips = useCallback(async () => {
    try {
      setLoading(true);
      const response = await api.get('/api/v1/clips/', {
        params: {
          status: statusFilter || undefined,
          search: searchQuery || undefined,
          limit: 100
        }
      });
      setClips(response.data.clips || []);
      setLoading(false);
    } catch (err) {
      console.error('Error loading clips:', err);
      setError('Failed to load clips');
      setLoading(false);
    }
  }, [searchQuery, statusFilter]);

  // Load templates
  const loadTemplates = async () => {
    try {
      const response = await api.get('/api/v1/clips/templates');
      setTemplates(response.data.templates || []);
    } catch (err) {
      console.error('Error loading templates:', err);
    }
  };

  useEffect(() => {
    loadClips();
    loadTemplates();
  }, [loadClips]);

  // Handle new recording from template
  const startRecordingFromTemplate = (template) => {
    setSelectedTemplate(template);
    setShowTemplateModal(false);
    setShowRecorder(true);
  };

  // Handle recording complete
  const handleRecordingComplete = (newClip) => {
    setClips(prev => [newClip, ...prev]);
    setShowRecorder(false);
    setSelectedTemplate(null);
  };

  // Handle share
  const handleShare = async (clipId) => {
    try {
      const response = await api.post(`/api/v1/clips/${clipId}/shares`, shareSettings);

      // Copy share URL to clipboard
      if (response.data.share_url) {
        navigator.clipboard.writeText(response.data.share_url);
        toast.success('Share link copied to clipboard!');
      }

      setShowShareModal(null);
      setShareSettings({
        recipient_email: '',
        recipient_name: '',
        allow_download: false,
        require_email: false,
        expires_in_days: null,
        include_scheduling: true
      });
    } catch (err) {
      console.error('Error creating share:', err);
      toast.error('Failed to create share link');
    }
  };

  // Handle delete
  const handleDelete = async (clipId) => {
    try {
      await api.delete(`/api/v1/clips/${clipId}`);
      setClips(prev => prev.filter(c => c.id !== clipId));
    } catch (err) {
      console.error('Error deleting clip:', err);
      toast.error('Failed to delete clip');
    }
  };

  // Format duration
  const formatDuration = (seconds) => {
    if (!seconds) return '0:00';
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  // Format date
  const formatDate = (dateStr) => {
    if (!dateStr) return '';
    const date = new Date(dateStr);
    return date.toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric'
    });
  };

  // Get status badge color
  const getStatusColor = (status) => {
    switch (status) {
      case 'ready': return '#2D7A52';
      case 'processing': return '#f59e0b';
      case 'uploading': return '#3b82f6';
      case 'failed': return '#ef4444';
      default: return '#6b7280';
    }
  };

  // Get template icon
  const getTemplateIcon = (icon) => {
    const icons = {
      lock: '🔒',
      document: '📄',
      star: '⭐',
      home: '🏠',
      user: '👤',
      chart: '📊',
      upload: '📤',
      search: '🔍',
      video: '🎬'
    };
    return icons[icon] || '🎬';
  };

  return (
    <div className="clip-library">
      {/* Header */}
      <div className="library-header">
        <div className="header-left">
          <h1>Video Clips</h1>
          <p className="subtitle">{clips.length} clips in your library</p>
        </div>
        <div className="header-right">
          <button className="template-btn" onClick={() => setShowTemplateModal(true)}>
            Use Template
          </button>
          <button className="create-btn" onClick={() => setShowRecorder(true)}>
            <span className="plus-icon">+</span>
            Create Clip
          </button>
        </div>
      </div>

      {/* Filters */}
      <div className="library-filters">
        <div className="search-box">
          <input
            type="text"
            placeholder="Search clips..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </div>
        <div className="filter-group">
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
          >
            <option value="">All Status</option>
            <option value="ready">Ready</option>
            <option value="processing">Processing</option>
            <option value="failed">Failed</option>
          </select>
        </div>
        <div className="view-toggle">
          <button
            className={viewMode === 'grid' ? 'active' : ''}
            onClick={() => setViewMode('grid')}
          >
            Grid
          </button>
          <button
            className={viewMode === 'list' ? 'active' : ''}
            onClick={() => setViewMode('list')}
          >
            List
          </button>
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="library-error">
          {error}
          <button onClick={() => { setError(null); loadClips(); }}>Retry</button>
        </div>
      )}

      {/* Loading */}
      {loading && (
        <div className="library-loading">
          <div className="loading-spinner"></div>
          <p>Loading clips...</p>
        </div>
      )}

      {/* Empty state */}
      {!loading && clips.length === 0 && (
        <div className="library-empty">
          <div className="empty-icon">🎬</div>
          <h2>No clips yet</h2>
          <p>Create your first video clip to send personalized messages to borrowers</p>
          <button className="create-btn" onClick={() => setShowRecorder(true)}>
            Create Your First Clip
          </button>
        </div>
      )}

      {/* Clips Grid */}
      {!loading && clips.length > 0 && (
        <div className={`clips-container ${viewMode}`}>
          {clips.map(clip => (
            <div key={clip.id} className="clip-card">
              <div
                className="clip-thumbnail"
                onClick={() => setSelectedClip(clip)}
              >
                {clip.thumbnail_path ? (
                  <img src={clip.thumbnail_path} alt={clip.title} />
                ) : (
                  <div className="thumbnail-placeholder">
                    <span>🎬</span>
                  </div>
                )}
                <div className="clip-duration">
                  {formatDuration(clip.duration_seconds)}
                </div>
                <div
                  className="clip-status"
                  style={{ backgroundColor: getStatusColor(clip.status) }}
                >
                  {clip.status}
                </div>
              </div>
              <div className="clip-info">
                <h3 className="clip-title" onClick={() => setSelectedClip(clip)}>
                  {sanitizeText(clip.title)}
                </h3>
                <div className="clip-meta">
                  <span className="clip-date">{formatDate(clip.created_at)}</span>
                  <span className="clip-views">
                    {clip.view_count} view{clip.view_count !== 1 ? 's' : ''}
                  </span>
                  {clip.average_completion_rate > 0 && (
                    <span className="clip-completion">
                      {Math.round(clip.average_completion_rate * 100)}% avg watched
                    </span>
                  )}
                </div>
                {clip.crm_entity_type && (
                  <div className="clip-linked">
                    Linked to {clip.crm_entity_type} #{clip.crm_entity_id}
                  </div>
                )}
              </div>
              <div className="clip-actions">
                <button
                  className="action-btn share"
                  onClick={() => setShowShareModal(clip)}
                  disabled={clip.status !== 'ready'}
                >
                  Share
                </button>
                <button
                  className="action-btn copy"
                  onClick={() => {
                    const url = `${window.location.origin}/watch/${clip.share_token}`;
                    navigator.clipboard.writeText(url);
                    toast.success('Link copied!');
                  }}
                  disabled={clip.status !== 'ready'}
                >
                  Copy Link
                </button>
                <ScheduleMeetingButton
                  buttonText="Schedule"
                  buttonStyle="outline"
                  buttonSize="small"
                  showIcon={false}
                  clipId={clip.id}
                  leadId={clip.crm_entity_type === 'lead' ? clip.crm_entity_id : null}
                  loanId={clip.crm_entity_type === 'loan' ? clip.crm_entity_id : null}
                />
                <button
                  className="action-btn delete"
                  onClick={() => handleDelete(clip.id)}
                >
                  Delete
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Template Modal */}
      {showTemplateModal && (
        <div className="modal-overlay" onClick={() => setShowTemplateModal(false)}>
          <div className="template-modal" onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <h2>Choose a Template</h2>
              <button className="close-btn" onClick={() => setShowTemplateModal(false)}>×</button>
            </div>
            <div className="template-grid">
              {templates.map(template => (
                <div
                  key={template.template_key}
                  className="template-card"
                  style={{ borderColor: template.color }}
                  onClick={() => startRecordingFromTemplate(template)}
                >
                  <div
                    className="template-icon"
                    style={{ backgroundColor: template.color + '20', color: template.color }}
                  >
                    {getTemplateIcon(template.icon)}
                  </div>
                  <h3>{sanitizeText(template.template_name)}</h3>
                  <p>{sanitizeText(template.description)}</p>
                  <div className="template-meta">
                    <span>{Math.ceil(template.default_duration_seconds / 60)} min</span>
                    <span>{template.usage_count || 0} uses</span>
                  </div>
                </div>
              ))}
              <div
                className="template-card blank"
                onClick={() => {
                  setShowTemplateModal(false);
                  setShowRecorder(true);
                }}
              >
                <div className="template-icon blank">+</div>
                <h3>Start from Scratch</h3>
                <p>Create a custom video without a template</p>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Share Modal */}
      {showShareModal && (
        <div className="modal-overlay" onClick={() => setShowShareModal(null)}>
          <div className="share-modal" onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <h2>Share Clip</h2>
              <button className="close-btn" onClick={() => setShowShareModal(null)}>×</button>
            </div>
            <div className="share-form">
              <div className="form-group">
                <label>Recipient Email (optional)</label>
                <input
                  type="email"
                  value={shareSettings.recipient_email}
                  onChange={e => setShareSettings(prev => ({
                    ...prev,
                    recipient_email: e.target.value
                  }))}
                  placeholder="borrower@email.com"
                />
              </div>
              <div className="form-group">
                <label>Recipient Name (optional)</label>
                <input
                  type="text"
                  value={shareSettings.recipient_name}
                  onChange={e => setShareSettings(prev => ({
                    ...prev,
                    recipient_name: e.target.value
                  }))}
                  placeholder="John Smith"
                />
              </div>
              <div className="form-options">
                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={shareSettings.allow_download}
                    onChange={e => setShareSettings(prev => ({
                      ...prev,
                      allow_download: e.target.checked
                    }))}
                  />
                  Allow download
                </label>
                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={shareSettings.require_email}
                    onChange={e => setShareSettings(prev => ({
                      ...prev,
                      require_email: e.target.checked
                    }))}
                  />
                  Require email to view
                </label>
                <label className="checkbox-label schedule-option">
                  <input
                    type="checkbox"
                    checked={shareSettings.include_scheduling}
                    onChange={e => setShareSettings(prev => ({
                      ...prev,
                      include_scheduling: e.target.checked
                    }))}
                  />
                  <span className="schedule-icon">📅</span>
                  Include "Schedule a Meeting" button
                </label>
              </div>
              <div className="form-group">
                <label>Expires after</label>
                <select
                  value={shareSettings.expires_in_days || ''}
                  onChange={e => setShareSettings(prev => ({
                    ...prev,
                    expires_in_days: e.target.value ? parseInt(e.target.value) : null
                  }))}
                >
                  <option value="">Never</option>
                  <option value="7">7 days</option>
                  <option value="30">30 days</option>
                  <option value="90">90 days</option>
                </select>
              </div>
              <button
                className="share-btn"
                onClick={() => handleShare(showShareModal.id)}
              >
                Create Share Link
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Recorder Modal */}
      {showRecorder && (
        <div className="modal-overlay">
          <ClipRecorder
            onRecordingComplete={handleRecordingComplete}
            onClose={() => {
              setShowRecorder(false);
              setSelectedTemplate(null);
            }}
            templateId={selectedTemplate?.id}
            suggestedTitle={selectedTemplate?.suggested_title || ''}
          />
        </div>
      )}

      {/* Player Modal */}
      {selectedClip && (
        <div className="modal-overlay" onClick={() => setSelectedClip(null)}>
          <div className="player-modal" onClick={e => e.stopPropagation()}>
            <ClipPlayer
              clip={selectedClip}
              onClose={() => setSelectedClip(null)}
            />
          </div>
        </div>
      )}
    </div>
  );
};

export default ClipLibrary;
