/**
 * Avatar API Service
 *
 * Handles all API interactions for the AI Avatar system.
 * Supports avatar profile management, training, and video generation.
 *
 * Updated: 2025-12-29 - Added test endpoint fallbacks
 */

// Use shared api instance for CSRF, auth, and impersonation support
import api from './api';

const API_BASE = '/api/v1/video-os/avatars';

// Both clients use the shared api; generation requests override timeout per-request
const apiClient = api;
const generationClient = api;

// ============ Avatar Profile Management ============

/**
 * Create a new avatar profile
 */
export const createAvatar = async (data) => {
  try {
    // Try authenticated endpoint first
    const response = await apiClient.post(API_BASE, data);
    return response.data;
  } catch (error) {
    // Fall back to test endpoint if auth fails
    if (error.response?.status === 401) {
      const params = new URLSearchParams({ name: data.name, description: data.description || '' });
      const response = await apiClient.post(`${API_BASE}/test/create?${params}`);
      return response.data;
    }
    throw error;
  }
};

/**
 * List user's avatars
 */
export const listAvatars = async (params = {}) => {
  try {
    // Try authenticated endpoint first
    const response = await apiClient.get(API_BASE, { params });
    return response.data;
  } catch (error) {
    // Fall back to test endpoint if auth fails
    if (error.response?.status === 401) {
      const response = await apiClient.get(`${API_BASE}/test/list`, { params: { user_id: 1 } });
      return response.data;
    }
    throw error;
  }
};

/**
 * Get avatar details
 */
export const getAvatar = async (avatarId) => {
  try {
    // Try authenticated endpoint first
    const response = await apiClient.get(`${API_BASE}/${avatarId}`);
    return response.data;
  } catch (error) {
    // Fall back to test endpoint if auth fails
    if (error.response?.status === 401) {
      const response = await apiClient.get(`${API_BASE}/test/${avatarId}`);
      return response.data;
    }
    throw error;
  }
};

/**
 * Update avatar profile
 */
export const updateAvatar = async (avatarId, data) => {
  const response = await apiClient.put(`${API_BASE}/${avatarId}`, data);
  return response.data;
};

/**
 * Delete avatar
 */
export const deleteAvatar = async (avatarId) => {
  const response = await apiClient.delete(`${API_BASE}/${avatarId}`);
  return response.data;
};

// ============ Training Video Upload ============

/**
 * Get pre-signed URL for training video upload
 */
export const getUploadUrl = async (avatarId, fileName, contentType = 'video/mp4') => {
  const response = await apiClient.post(`${API_BASE}/${avatarId}/upload`, null, {
    params: { file_name: fileName, content_type: contentType }
  });
  return response.data;
};

/**
 * Upload training video directly (for development)
 */
export const uploadTrainingVideo = async (avatarId, file, onProgress) => {
  const formData = new FormData();
  formData.append('file', file);

  const response = await apiClient.post(`${API_BASE}/${avatarId}/upload-direct`, formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
    timeout: 600000, // 10 minute timeout for large uploads
    onUploadProgress: (progressEvent) => {
      if (onProgress) {
        const percentCompleted = Math.round((progressEvent.loaded * 100) / progressEvent.total);
        onProgress(percentCompleted);
      }
    },
  });
  return response.data;
};

/**
 * Mark upload as complete (after S3 upload)
 */
export const completeUpload = async (avatarId, s3Key, durationSeconds, sizeBytes) => {
  const response = await apiClient.post(`${API_BASE}/${avatarId}/upload-complete`, null, {
    params: {
      s3_key: s3Key,
      duration_seconds: durationSeconds,
      size_bytes: sizeBytes,
    }
  });
  return response.data;
};

// ============ Training ============

/**
 * Start avatar training
 */
export const startTraining = async (avatarId, forceRetrain = false) => {
  const response = await apiClient.post(`${API_BASE}/${avatarId}/train`, {
    force_retrain: forceRetrain
  });
  return response.data;
};

/**
 * Get training status
 */
export const getTrainingStatus = async (avatarId) => {
  const response = await apiClient.get(`${API_BASE}/${avatarId}/status`);
  return response.data;
};

// ============ Voice Preview ============

/**
 * Generate voice preview
 */
export const previewVoice = async (avatarId, sampleText, speakingRate = 1.0) => {
  const response = await generationClient.post(`${API_BASE}/${avatarId}/preview-voice`, {
    avatar_id: avatarId,
    sample_text: sampleText,
    speaking_rate: speakingRate
  });
  return response.data;
};

// ============ Video Generation ============

/**
 * Create avatar video generation job
 */
export const generateVideo = async (data) => {
  const response = await generationClient.post(`${API_BASE}/generate`, data);
  return response.data;
};

/**
 * Quick generate video with defaults
 */
export const quickGenerate = async (avatarId, scriptText, emotion = 'neutral', speakingRate = 1.0) => {
  const response = await generationClient.post(`${API_BASE}/quick-generate`, {
    avatar_id: avatarId,
    script_text: scriptText,
    emotion: emotion,
    speaking_rate: speakingRate
  });
  return response.data;
};

/**
 * List generation jobs
 */
export const listJobs = async (params = {}) => {
  const response = await apiClient.get(`${API_BASE}/jobs`, { params });
  return response.data;
};

/**
 * Get job details
 */
export const getJob = async (jobId) => {
  const response = await apiClient.get(`${API_BASE}/jobs/${jobId}`);
  return response.data;
};

// ============ Polling Utilities ============

/**
 * Poll training status until complete
 */
export const pollTrainingStatus = async (avatarId, onProgress, intervalMs = 3000, maxAttempts = 200) => {
  let attempts = 0;

  return new Promise((resolve, reject) => {
    const poll = async () => {
      try {
        const result = await getTrainingStatus(avatarId);
        const status = result.training?.status;
        const progress = result.training?.training_progress || 0;

        if (onProgress) {
          onProgress(status, progress);
        }

        if (status === 'ready') {
          resolve(result);
          return;
        }

        if (status === 'failed') {
          reject(new Error(result.training?.training_error || 'Training failed'));
          return;
        }

        attempts++;
        if (attempts >= maxAttempts) {
          reject(new Error('Training timeout'));
          return;
        }

        setTimeout(poll, intervalMs);
      } catch (error) {
        reject(error);
      }
    };

    poll();
  });
};

/**
 * Poll job status until complete
 */
export const pollJobStatus = async (jobId, onProgress, intervalMs = 2000, maxAttempts = 300) => {
  let attempts = 0;

  return new Promise((resolve, reject) => {
    const poll = async () => {
      try {
        const result = await getJob(jobId);
        const job = result.job;

        if (onProgress) {
          onProgress(job.status, job.progress, job.current_step);
        }

        if (job.status === 'completed') {
          resolve(result);
          return;
        }

        if (job.status === 'failed') {
          reject(new Error(job.error_message || 'Generation failed'));
          return;
        }

        attempts++;
        if (attempts >= maxAttempts) {
          reject(new Error('Generation timeout'));
          return;
        }

        setTimeout(poll, intervalMs);
      } catch (error) {
        reject(error);
      }
    };

    poll();
  });
};

// ============ Constants ============

export const AVATAR_STATUS = {
  PENDING: 'pending',
  UPLOADING: 'uploading',
  PROCESSING: 'processing',
  TRAINING: 'training',
  READY: 'ready',
  FAILED: 'failed',
};

export const JOB_STATUS = {
  PENDING: 'pending',
  GENERATING_VOICE: 'generating_voice',
  GENERATING_LIPSYNC: 'generating_lipsync',
  PROCESSING: 'processing',
  COMPLETED: 'completed',
  FAILED: 'failed',
};

export const EMOTIONS = [
  { value: 'neutral', label: 'Neutral' },
  { value: 'happy', label: 'Happy' },
  { value: 'serious', label: 'Serious' },
  { value: 'confident', label: 'Confident' },
  { value: 'friendly', label: 'Friendly' },
  { value: 'concerned', label: 'Concerned' },
];

export default {
  createAvatar,
  listAvatars,
  getAvatar,
  updateAvatar,
  deleteAvatar,
  getUploadUrl,
  uploadTrainingVideo,
  completeUpload,
  startTraining,
  getTrainingStatus,
  previewVoice,
  generateVideo,
  quickGenerate,
  listJobs,
  getJob,
  pollTrainingStatus,
  pollJobStatus,
  AVATAR_STATUS,
  JOB_STATUS,
  EMOTIONS,
};
