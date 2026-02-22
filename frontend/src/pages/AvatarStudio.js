/**
 * Avatar Studio - AI Video Avatar Management
 *
 * Create and manage AI avatars for automated video generation:
 * - Upload training videos
 * - Monitor training progress
 * - Generate videos from scripts
 * - Preview voice and manage settings
 */
import React, { useState, useEffect, useCallback, useRef } from 'react';
import avatarApi, { AVATAR_STATUS, JOB_STATUS, EMOTIONS } from '../services/avatarApi';
import vidyardApi, { VIDYARD_STATUS, VIDYARD_VIDEO_STATUS, VIDYARD_LANGUAGES } from '../services/vidyardApi';
import './AvatarStudio.css';
import { toast } from '../utils/toast';

// Provider options
const PROVIDERS = {
  LOCAL: 'local',
  VIDYARD: 'vidyard',
};

const PROVIDER_INFO = {
  [PROVIDERS.LOCAL]: {
    name: 'Local ML Services',
    description: 'Self-hosted XTTS + Wav2Lip (requires GPU)',
    features: ['Full control', 'No API limits', 'Requires GPU server'],
  },
  [PROVIDERS.VIDYARD]: {
    name: 'Vidyard',
    description: 'Cloud-based AI Avatar generation',
    features: ['No GPU needed', '25+ languages', '~10 min/min video', 'Requires API key'],
  },
};

// ============ Status Badge Component ============
const StatusBadge = ({ status }) => {
  const statusConfig = {
    pending: { label: 'Pending', color: '#6b7280' },
    uploading: { label: 'Uploading', color: '#3b82f6' },
    processing: { label: 'Processing', color: '#f59e0b' },
    training: { label: 'Training', color: '#8b5cf6' },
    ready: { label: 'Ready', color: '#10b981' },
    failed: { label: 'Failed', color: '#ef4444' },
    generating_voice: { label: 'Generating Voice', color: '#8b5cf6' },
    generating_lipsync: { label: 'Generating Lip Sync', color: '#3b82f6' },
    completed: { label: 'Completed', color: '#10b981' },
  };

  const config = statusConfig[status] || { label: status, color: '#6b7280' };

  return (
    <span className="status-badge" style={{ backgroundColor: config.color }}>
      {config.label}
    </span>
  );
};

// ============ Progress Bar Component ============
const ProgressBar = ({ progress, label }) => (
  <div className="progress-container">
    {label && <span className="progress-label">{label}</span>}
    <div className="progress-bar">
      <div className="progress-fill" style={{ width: `${progress}%` }} />
    </div>
    <span className="progress-text">{progress}%</span>
  </div>
);

// ============ Provider Selector Component ============
const ProviderSelector = ({ provider, onSelect, providerStatus }) => (
  <div className="provider-selector">
    <label>Video Generation Provider</label>
    <div className="provider-options">
      {Object.entries(PROVIDER_INFO).map(([key, info]) => (
        <div
          key={key}
          className={`provider-option ${provider === key ? 'selected' : ''} ${
            providerStatus[key] === 'healthy' ? 'available' : 'unavailable'
          }`}
          onClick={() => onSelect(key)}
        >
          <div className="provider-header">
            <span className="provider-name">{info.name}</span>
            <span className={`provider-status ${providerStatus[key] || 'unknown'}`}>
              {providerStatus[key] === 'healthy' ? 'Connected' :
               providerStatus[key] === 'not_configured' ? 'Not Configured' :
               providerStatus[key] || 'Unknown'}
            </span>
          </div>
          <p className="provider-description">{info.description}</p>
          <ul className="provider-features">
            {info.features.map((f, i) => (
              <li key={i}>{f}</li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  </div>
);

// ============ Vidyard Video Generator Component ============
const VidyardVideoGenerator = ({ onJobCreated }) => {
  const [avatars, setAvatars] = useState([]);
  const [selectedAvatarId, setSelectedAvatarId] = useState('');
  const [script, setScript] = useState('');
  const [language, setLanguage] = useState('en');
  const [title, setTitle] = useState('');
  const [generating, setGenerating] = useState(false);
  const [validation, setValidation] = useState(null);
  const [jobStatus, setJobStatus] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadVidyardAvatars();
  }, []);

  useEffect(() => {
    // Validate script as user types
    if (script.length > 0) {
      vidyardApi.validateScript(script).then(setValidation).catch(console.error);
    } else {
      setValidation(null);
    }
  }, [script]);

  const loadVidyardAvatars = async () => {
    try {
      const result = await vidyardApi.listAvatars();
      setAvatars(result.avatars || []);
      if (result.avatars?.length > 0) {
        setSelectedAvatarId(result.avatars[0].id);
      }
    } catch (error) {
      console.error('Failed to load Vidyard avatars:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleGenerate = async () => {
    if (!selectedAvatarId || !script.trim()) return;

    setGenerating(true);
    setJobStatus({ status: 'queued', progress: 0 });

    try {
      const result = await vidyardApi.generateVideo({
        avatar_id: selectedAvatarId,
        script: script.trim(),
        language,
        title: title || undefined,
      });

      if (result.error) {
        toast.error('Generation failed: ' + result.message);
        setGenerating(false);
        return;
      }

      // Poll for completion
      await vidyardApi.pollVideoStatus(
        result.job_id,
        (status, progress, data) => {
          setJobStatus({ status, progress, ...data });
        }
      );

      toast.success('Video generated successfully!');
      if (onJobCreated) onJobCreated();
    } catch (error) {
      console.error('Generation failed:', error);
      toast.error('Generation failed: ' + error.message);
    } finally {
      setGenerating(false);
      setJobStatus(null);
    }
  };

  if (loading) {
    return <div className="vidyard-generator loading">Loading Vidyard avatars...</div>;
  }

  return (
    <div className="vidyard-generator">
      <h3>Generate Video with Vidyard</h3>

      <div className="generator-form">
        <div className="form-group">
          <label>Select Avatar</label>
          <select
            value={selectedAvatarId}
            onChange={(e) => setSelectedAvatarId(e.target.value)}
          >
            {avatars.length === 0 ? (
              <option value="">No avatars available</option>
            ) : (
              avatars.map((avatar) => (
                <option key={avatar.id} value={avatar.id}>
                  {avatar.name} {avatar.type === 'stock' ? '(Stock)' : ''}
                </option>
              ))
            )}
          </select>
        </div>

        <div className="form-group">
          <label>
            Script
            <span className="char-count">
              {script.length} / {vidyardApi.MAX_SCRIPT_LENGTH}
            </span>
          </label>
          <textarea
            value={script}
            onChange={(e) => setScript(e.target.value)}
            rows={6}
            placeholder="Enter your script (max 1000 characters, ~1 minute video)..."
            maxLength={vidyardApi.MAX_SCRIPT_LENGTH}
          />
          {validation && (
            <div className="validation-feedback">
              {validation.warnings?.map((w, i) => (
                <p key={i} className="warning">{w}</p>
              ))}
              {validation.issues?.map((issue, i) => (
                <p key={i} className="error">{issue}</p>
              ))}
              {validation.valid && (
                <p className="info">
                  Estimated duration: ~{validation.estimated_duration_seconds}s
                </p>
              )}
            </div>
          )}
        </div>

        <div className="form-row">
          <div className="form-group">
            <label>Language</label>
            <select value={language} onChange={(e) => setLanguage(e.target.value)}>
              {VIDYARD_LANGUAGES.map((lang) => (
                <option key={lang.code} value={lang.code}>
                  {lang.name}
                </option>
              ))}
            </select>
          </div>

          <div className="form-group">
            <label>Video Title (optional)</label>
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="My AI Video"
            />
          </div>
        </div>

        <button
          onClick={handleGenerate}
          className="primary generate-btn"
          disabled={generating || !script.trim() || !selectedAvatarId || (validation && !validation.valid)}
        >
          {generating ? 'Generating...' : 'Generate Video'}
        </button>

        <p className="generation-note">
          Video generation takes approximately 10 minutes per minute of video.
        </p>
      </div>

      {jobStatus && (
        <div className="job-progress">
          <ProgressBar progress={jobStatus.progress || 0} label={jobStatus.status} />
          {jobStatus.video_url && (
            <a href={jobStatus.video_url} target="_blank" rel="noopener noreferrer" className="download-btn">
              Download Video
            </a>
          )}
        </div>
      )}
    </div>
  );
};

// ============ Avatar Card Component ============
const AvatarCard = ({ avatar, onSelect, onDelete, selected }) => (
  <div
    className={`avatar-card ${selected ? 'selected' : ''}`}
    onClick={() => onSelect(avatar)}
  >
    <div className="avatar-image">
      {avatar.reference_image_url ? (
        <img src={avatar.reference_image_url} alt={avatar.name} />
      ) : (
        <div className="avatar-placeholder">
          <span>{avatar.name.charAt(0).toUpperCase()}</span>
        </div>
      )}
    </div>
    <div className="avatar-info">
      <h3>{avatar.name}</h3>
      <StatusBadge status={avatar.status} />
      <p className="avatar-stats">
        {avatar.total_videos_generated} videos generated
      </p>
    </div>
    <button
      className="delete-btn"
      onClick={(e) => {
        e.stopPropagation();
        onDelete(avatar.id);
      }}
    >
      Delete
    </button>
  </div>
);

// ============ Create Avatar Modal ============
const CreateAvatarModal = ({ onClose, onCreate }) => {
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!name.trim()) return;

    setLoading(true);
    try {
      await onCreate({ name, description });
      onClose();
    } catch (error) {
      console.error('Failed to create avatar:', error);
      toast.error('Failed to create avatar: ' + (error.response?.data?.detail || error.message));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()}>
        <h2>Create New Avatar</h2>
        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label>Avatar Name</label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g., Professional Tim"
              required
            />
          </div>
          <div className="form-group">
            <label>Description (optional)</label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Describe this avatar's purpose..."
              rows={3}
            />
          </div>
          <div className="modal-actions">
            <button type="button" onClick={onClose} disabled={loading}>
              Cancel
            </button>
            <button type="submit" className="primary" disabled={loading || !name.trim()}>
              {loading ? 'Creating...' : 'Create Avatar'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

// ============ Video Upload Component ============
const VideoUpload = ({ avatar, onUploadComplete }) => {
  const [file, setFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [dragActive, setDragActive] = useState(false);
  const inputRef = useRef(null);

  const handleDrag = (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setDragActive(true);
    } else if (e.type === 'dragleave') {
      setDragActive(false);
    }
  };

  const handleDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);

    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleFile(e.dataTransfer.files[0]);
    }
  };

  const handleFile = (selectedFile) => {
    // Validate file type
    const validTypes = ['video/mp4', 'video/quicktime', 'video/webm'];
    if (!validTypes.includes(selectedFile.type)) {
      toast.error('Please upload a valid video file (MP4, MOV, or WebM)');
      return;
    }

    // Validate file size (max 500MB)
    if (selectedFile.size > 500 * 1024 * 1024) {
      toast.error('File size must be less than 500MB');
      return;
    }

    setFile(selectedFile);
  };

  const handleUpload = async () => {
    if (!file) return;

    setUploading(true);
    setProgress(0);

    try {
      await avatarApi.uploadTrainingVideo(avatar.id, file, setProgress);
      onUploadComplete();
    } catch (error) {
      console.error('Upload failed:', error);
      toast.error('Upload failed: ' + (error.response?.data?.detail || error.message));
    } finally {
      setUploading(false);
      setFile(null);
    }
  };

  return (
    <div className="video-upload">
      <div
        className={`upload-zone ${dragActive ? 'drag-active' : ''}`}
        onDragEnter={handleDrag}
        onDragLeave={handleDrag}
        onDragOver={handleDrag}
        onDrop={handleDrop}
        onClick={() => inputRef.current?.click()}
      >
        <input
          ref={inputRef}
          type="file"
          accept="video/mp4,video/quicktime,video/webm"
          onChange={(e) => e.target.files[0] && handleFile(e.target.files[0])}
          style={{ display: 'none' }}
        />

        {file ? (
          <div className="file-preview">
            <p>{file.name}</p>
            <p className="file-size">{(file.size / (1024 * 1024)).toFixed(1)} MB</p>
          </div>
        ) : (
          <>
            <div className="upload-icon">+</div>
            <p>Drag and drop your training video here</p>
            <p className="upload-hint">or click to browse</p>
            <p className="upload-requirements">
              MP4, MOV, or WebM - 2-5 minutes of you speaking clearly
            </p>
          </>
        )}
      </div>

      {file && (
        <div className="upload-actions">
          <button onClick={() => setFile(null)} disabled={uploading}>
            Cancel
          </button>
          <button onClick={handleUpload} className="primary" disabled={uploading}>
            {uploading ? 'Uploading...' : 'Upload Video'}
          </button>
        </div>
      )}

      {uploading && <ProgressBar progress={progress} label="Uploading" />}
    </div>
  );
};

// ============ Training Panel Component ============
const TrainingPanel = ({ avatar, onTrainingComplete }) => {
  const [training, setTraining] = useState(false);
  const [progress, setProgress] = useState(0);
  const [status, setStatus] = useState(avatar.status);
  const [error, setError] = useState(null);

  useEffect(() => {
    // If already training, start polling
    if (avatar.status === 'training' || avatar.status === 'processing') {
      pollTraining();
    }
  }, [avatar.id]);

  const startTraining = async () => {
    setTraining(true);
    setError(null);

    try {
      await avatarApi.startTraining(avatar.id);
      pollTraining();
    } catch (error) {
      console.error('Failed to start training:', error);
      setError(error.response?.data?.detail || error.message);
      setTraining(false);
    }
  };

  const pollTraining = async () => {
    try {
      await avatarApi.pollTrainingStatus(
        avatar.id,
        (newStatus, newProgress) => {
          setStatus(newStatus);
          setProgress(newProgress);
        }
      );
      setTraining(false);
      onTrainingComplete();
    } catch (error) {
      setError(error.message);
      setTraining(false);
    }
  };

  const isTraining = training || status === 'training' || status === 'processing';

  return (
    <div className="training-panel">
      <h3>Training Status</h3>

      {status === 'ready' ? (
        <div className="training-complete">
          <span className="success-icon">Ready</span>
          <p>Avatar is trained and ready for video generation!</p>
          <button onClick={startTraining} className="secondary">
            Retrain Avatar
          </button>
        </div>
      ) : isTraining ? (
        <div className="training-progress">
          <ProgressBar progress={progress} label="Training" />
          <p className="training-status">
            {status === 'processing' ? 'Processing video...' : 'Training voice model...'}
          </p>
        </div>
      ) : status === 'failed' ? (
        <div className="training-failed">
          <p className="error-message">{error || 'Training failed'}</p>
          <button onClick={startTraining} className="primary">
            Retry Training
          </button>
        </div>
      ) : (
        <div className="training-ready">
          <p>Ready to start training. Make sure you've uploaded a training video.</p>
          <button
            onClick={startTraining}
            className="primary"
            disabled={!avatar.training_video_url}
          >
            Start Training
          </button>
        </div>
      )}
    </div>
  );
};

// ============ Voice Preview Component ============
const VoicePreview = ({ avatar }) => {
  const [sampleText, setSampleText] = useState(
    "Hello, I'm your AI avatar. I can speak any text you give me with realistic lip synchronization."
  );
  const [speakingRate, setSpeakingRate] = useState(1.0);
  const [generating, setGenerating] = useState(false);
  const [audioUrl, setAudioUrl] = useState(null);

  const generatePreview = async () => {
    setGenerating(true);
    try {
      const result = await avatarApi.previewVoice(avatar.id, sampleText, speakingRate);
      setAudioUrl(result.preview?.audio_url);
    } catch (error) {
      console.error('Preview failed:', error);
      toast.error('Failed to generate preview: ' + (error.response?.data?.detail || error.message));
    } finally {
      setGenerating(false);
    }
  };

  if (avatar.status !== 'ready') {
    return (
      <div className="voice-preview disabled">
        <h3>Voice Preview</h3>
        <p>Train your avatar first to preview the voice.</p>
      </div>
    );
  }

  return (
    <div className="voice-preview">
      <h3>Voice Preview</h3>
      <div className="preview-controls">
        <div className="form-group">
          <label>Sample Text</label>
          <textarea
            value={sampleText}
            onChange={(e) => setSampleText(e.target.value)}
            rows={3}
            placeholder="Enter text to preview..."
          />
        </div>
        <div className="form-group">
          <label>Speaking Rate: {speakingRate.toFixed(1)}x</label>
          <input
            type="range"
            min="0.5"
            max="2"
            step="0.1"
            value={speakingRate}
            onChange={(e) => setSpeakingRate(parseFloat(e.target.value))}
          />
        </div>
        <button
          onClick={generatePreview}
          className="primary"
          disabled={generating || !sampleText.trim()}
        >
          {generating ? 'Generating...' : 'Generate Preview'}
        </button>
      </div>

      {audioUrl && (
        <div className="audio-player">
          <audio controls src={audioUrl} />
        </div>
      )}
    </div>
  );
};

// ============ Video Generator Component ============
const VideoGenerator = ({ avatar, onJobCreated }) => {
  const [script, setScript] = useState('');
  const [emotion, setEmotion] = useState('neutral');
  const [speakingRate, setSpeakingRate] = useState(1.0);
  const [generating, setGenerating] = useState(false);
  const [activeJob, setActiveJob] = useState(null);
  const [jobProgress, setJobProgress] = useState(0);
  const [jobStatus, setJobStatus] = useState('');

  const generateVideo = async () => {
    if (!script.trim()) return;

    setGenerating(true);
    setActiveJob(null);

    try {
      const result = await avatarApi.quickGenerate(avatar.id, script, emotion, speakingRate);
      const jobId = result.job_id;
      setActiveJob(jobId);

      // Poll for completion
      await avatarApi.pollJobStatus(jobId, (status, progress, step) => {
        setJobStatus(status);
        setJobProgress(progress);
      });

      // Job completed
      if (onJobCreated) onJobCreated();
      toast.success('Video generated successfully!');
    } catch (error) {
      console.error('Generation failed:', error);
      toast.error('Generation failed: ' + error.message);
    } finally {
      setGenerating(false);
      setActiveJob(null);
    }
  };

  const wordCount = script.trim().split(/\s+/).filter(Boolean).length;
  const estimatedDuration = Math.ceil((wordCount / 150) * 60 / speakingRate);

  if (avatar.status !== 'ready') {
    return (
      <div className="video-generator disabled">
        <h3>Generate Video</h3>
        <p>Train your avatar first to generate videos.</p>
      </div>
    );
  }

  return (
    <div className="video-generator">
      <h3>Generate Video</h3>

      <div className="generator-form">
        <div className="form-group">
          <label>Script</label>
          <textarea
            value={script}
            onChange={(e) => setScript(e.target.value)}
            rows={6}
            placeholder="Enter the script for your avatar to speak..."
          />
          <p className="word-count">
            {wordCount} words - ~{estimatedDuration}s video
          </p>
        </div>

        <div className="form-row">
          <div className="form-group">
            <label>Emotion</label>
            <select value={emotion} onChange={(e) => setEmotion(e.target.value)}>
              {EMOTIONS.map((e) => (
                <option key={e.value} value={e.value}>
                  {e.label}
                </option>
              ))}
            </select>
          </div>

          <div className="form-group">
            <label>Speaking Rate: {speakingRate.toFixed(1)}x</label>
            <input
              type="range"
              min="0.5"
              max="2"
              step="0.1"
              value={speakingRate}
              onChange={(e) => setSpeakingRate(parseFloat(e.target.value))}
            />
          </div>
        </div>

        <button
          onClick={generateVideo}
          className="primary generate-btn"
          disabled={generating || !script.trim()}
        >
          {generating ? 'Generating...' : 'Generate Video'}
        </button>
      </div>

      {activeJob && (
        <div className="job-progress">
          <ProgressBar progress={jobProgress} label={jobStatus} />
        </div>
      )}
    </div>
  );
};

// ============ Recent Jobs List ============
const RecentJobs = ({ avatarId }) => {
  const [jobs, setJobs] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadJobs();
  }, [avatarId]);

  const loadJobs = async () => {
    try {
      const result = await avatarApi.listJobs({ avatar_id: avatarId, page_size: 10 });
      setJobs(result.jobs || []);
    } catch (error) {
      console.error('Failed to load jobs:', error);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return <div className="recent-jobs loading">Loading jobs...</div>;
  }

  if (jobs.length === 0) {
    return (
      <div className="recent-jobs empty">
        <p>No videos generated yet.</p>
      </div>
    );
  }

  return (
    <div className="recent-jobs">
      <h3>Recent Videos</h3>
      <div className="jobs-list">
        {jobs.map((job) => (
          <div key={job.job_id} className="job-item">
            <div className="job-info">
              <StatusBadge status={job.status} />
              <p className="job-script">{job.script_text.substring(0, 50)}...</p>
              <span className="job-date">
                {new Date(job.created_at).toLocaleDateString()}
              </span>
            </div>
            {job.video_url && (
              <a href={job.video_url} target="_blank" rel="noopener noreferrer" className="download-btn">
                Download
              </a>
            )}
          </div>
        ))}
      </div>
    </div>
  );
};

// ============ Main Avatar Studio Component ============
const AvatarStudio = () => {
  const [avatars, setAvatars] = useState([]);
  const [selectedAvatar, setSelectedAvatar] = useState(null);
  const [loading, setLoading] = useState(true);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [activeTab, setActiveTab] = useState('upload');
  const [provider, setProvider] = useState(PROVIDERS.VIDYARD); // Default to Vidyard since local ML not available
  const [providerStatus, setProviderStatus] = useState({});

  useEffect(() => {
    loadAvatars();
    checkProviderStatus();
  }, []);

  const checkProviderStatus = async () => {
    const status = {};

    // Check local ML services
    try {
      const response = await fetch('http://localhost:5501/health');
      status[PROVIDERS.LOCAL] = response.ok ? 'healthy' : 'unavailable';
    } catch {
      status[PROVIDERS.LOCAL] = 'unavailable';
    }

    // Check Vidyard
    try {
      const result = await vidyardApi.checkHealth();
      status[PROVIDERS.VIDYARD] = result.status;
    } catch {
      status[PROVIDERS.VIDYARD] = 'error';
    }

    setProviderStatus(status);

    // Auto-select available provider
    if (status[PROVIDERS.VIDYARD] === 'healthy') {
      setProvider(PROVIDERS.VIDYARD);
    } else if (status[PROVIDERS.LOCAL] === 'healthy') {
      setProvider(PROVIDERS.LOCAL);
    }
  };

  const loadAvatars = async () => {
    try {
      const result = await avatarApi.listAvatars();
      setAvatars(result.avatars || []);
      if (result.avatars?.length > 0 && !selectedAvatar) {
        // Auto-select first avatar
        const first = result.avatars[0];
        const full = await avatarApi.getAvatar(first.id);
        setSelectedAvatar(full.avatar);
      }
    } catch (error) {
      console.error('Failed to load avatars:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleSelectAvatar = async (avatar) => {
    try {
      const result = await avatarApi.getAvatar(avatar.id);
      setSelectedAvatar(result.avatar);
    } catch (error) {
      console.error('Failed to load avatar details:', error);
    }
  };

  const handleCreateAvatar = async (data) => {
    const result = await avatarApi.createAvatar(data);
    await loadAvatars();
    setSelectedAvatar(result.avatar);
  };

  const handleDeleteAvatar = async (avatarId) => {
    if (!window.confirm('Are you sure you want to delete this avatar?')) return;

    try {
      await avatarApi.deleteAvatar(avatarId);
      if (selectedAvatar?.id === avatarId) {
        setSelectedAvatar(null);
      }
      await loadAvatars();
    } catch (error) {
      console.error('Failed to delete avatar:', error);
      toast.error('Failed to delete avatar');
    }
  };

  const refreshAvatar = async () => {
    if (selectedAvatar) {
      const result = await avatarApi.getAvatar(selectedAvatar.id);
      setSelectedAvatar(result.avatar);
      await loadAvatars();
    }
  };

  if (loading) {
    return (
      <div className="avatar-studio loading">
        <div className="loading-spinner">Loading Avatar Studio...</div>
      </div>
    );
  }

  return (
    <div className="avatar-studio">
      <div className="studio-header">
        <h1>Avatar Studio</h1>
        <p>Create AI avatars from your videos and generate content automatically</p>
        <ProviderSelector
          provider={provider}
          onSelect={setProvider}
          providerStatus={providerStatus}
        />
      </div>

      {/* Vidyard Mode */}
      {provider === PROVIDERS.VIDYARD && (
        <div className="vidyard-mode">
          <VidyardVideoGenerator onJobCreated={() => {}} />
        </div>
      )}

      {/* Local ML Mode */}
      {provider === PROVIDERS.LOCAL && (
      <div className="studio-layout">
        {/* Sidebar - Avatar List */}
        <div className="studio-sidebar">
          <div className="sidebar-header">
            <h2>My Avatars</h2>
            <button className="create-btn" onClick={() => setShowCreateModal(true)}>
              + New
            </button>
          </div>

          <div className="avatar-list">
            {avatars.length === 0 ? (
              <div className="empty-state">
                <p>No avatars yet</p>
                <button onClick={() => setShowCreateModal(true)}>
                  Create Your First Avatar
                </button>
              </div>
            ) : (
              avatars.map((avatar) => (
                <AvatarCard
                  key={avatar.id}
                  avatar={avatar}
                  onSelect={handleSelectAvatar}
                  onDelete={handleDeleteAvatar}
                  selected={selectedAvatar?.id === avatar.id}
                />
              ))
            )}
          </div>
        </div>

        {/* Main Content */}
        <div className="studio-main">
          {selectedAvatar ? (
            <>
              <div className="avatar-header">
                <div className="avatar-title">
                  <h2>{selectedAvatar.name}</h2>
                  <StatusBadge status={selectedAvatar.status} />
                </div>
                {selectedAvatar.description && (
                  <p className="avatar-description">{selectedAvatar.description}</p>
                )}
              </div>

              <div className="tabs">
                <button
                  className={activeTab === 'upload' ? 'active' : ''}
                  onClick={() => setActiveTab('upload')}
                >
                  Training
                </button>
                <button
                  className={activeTab === 'generate' ? 'active' : ''}
                  onClick={() => setActiveTab('generate')}
                  disabled={selectedAvatar.status !== 'ready'}
                >
                  Generate
                </button>
                <button
                  className={activeTab === 'preview' ? 'active' : ''}
                  onClick={() => setActiveTab('preview')}
                  disabled={selectedAvatar.status !== 'ready'}
                >
                  Preview
                </button>
                <button
                  className={activeTab === 'history' ? 'active' : ''}
                  onClick={() => setActiveTab('history')}
                >
                  History
                </button>
              </div>

              <div className="tab-content">
                {activeTab === 'upload' && (
                  <div className="upload-tab">
                    {!selectedAvatar.training_video_url ? (
                      <VideoUpload
                        avatar={selectedAvatar}
                        onUploadComplete={refreshAvatar}
                      />
                    ) : (
                      <div className="video-uploaded">
                        <p>Training video uploaded</p>
                        <TrainingPanel
                          avatar={selectedAvatar}
                          onTrainingComplete={refreshAvatar}
                        />
                      </div>
                    )}
                  </div>
                )}

                {activeTab === 'generate' && (
                  <VideoGenerator
                    avatar={selectedAvatar}
                    onJobCreated={refreshAvatar}
                  />
                )}

                {activeTab === 'preview' && (
                  <VoicePreview avatar={selectedAvatar} />
                )}

                {activeTab === 'history' && (
                  <RecentJobs avatarId={selectedAvatar.id} />
                )}
              </div>
            </>
          ) : (
            <div className="no-selection">
              <h2>Welcome to Avatar Studio</h2>
              <p>Select an avatar from the sidebar or create a new one to get started.</p>
              <button className="primary" onClick={() => setShowCreateModal(true)}>
                Create Your First Avatar
              </button>
            </div>
          )}
        </div>
      </div>
      )}

      {showCreateModal && (
        <CreateAvatarModal
          onClose={() => setShowCreateModal(false)}
          onCreate={handleCreateAvatar}
        />
      )}
    </div>
  );
};

export default AvatarStudio;
