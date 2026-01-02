/**
 * Vidyard API Client
 *
 * Client for Vidyard AI Avatar video generation.
 * Supports:
 * - Avatar management (list, create, get, delete)
 * - Video generation from scripts
 * - Video status tracking
 */

import axios from 'axios';

const API_BASE = process.env.REACT_APP_API_URL || 'https://api.perenniaai.com';

// Create axios instance with auth
const api = axios.create({
  baseURL: `${API_BASE}/api/v1/vidyard`,
  timeout: 60000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Add auth token to requests
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Longer timeout for video generation
const generationApi = axios.create({
  baseURL: `${API_BASE}/api/v1/vidyard`,
  timeout: 300000, // 5 minutes
  headers: {
    'Content-Type': 'application/json',
  },
});

generationApi.interceptors.request.use((config) => {
  const token = localStorage.getItem('token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// =============================================================================
// Constants
// =============================================================================

export const VIDYARD_STATUS = {
  PENDING: 'pending',
  PROCESSING: 'processing',
  READY: 'ready',
  FAILED: 'failed',
};

export const VIDYARD_VIDEO_STATUS = {
  QUEUED: 'queued',
  PROCESSING: 'processing',
  COMPLETED: 'completed',
  FAILED: 'failed',
};

export const VIDYARD_LANGUAGES = [
  { code: 'en', name: 'English' },
  { code: 'es', name: 'Spanish' },
  { code: 'fr', name: 'French' },
  { code: 'de', name: 'German' },
  { code: 'it', name: 'Italian' },
  { code: 'pt', name: 'Portuguese' },
  { code: 'ja', name: 'Japanese' },
  { code: 'zh', name: 'Chinese' },
  { code: 'ko', name: 'Korean' },
  { code: 'ar', name: 'Arabic' },
  { code: 'hi', name: 'Hindi' },
  { code: 'nl', name: 'Dutch' },
  { code: 'pl', name: 'Polish' },
  { code: 'sv', name: 'Swedish' },
  { code: 'tr', name: 'Turkish' },
];

export const MAX_SCRIPT_LENGTH = 1000;

// =============================================================================
// Health Check
// =============================================================================

export const checkHealth = async () => {
  const response = await api.get('/health');
  return response.data;
};

// =============================================================================
// Avatar Management
// =============================================================================

export const listAvatars = async () => {
  const response = await api.get('/avatars');
  return response.data;
};

export const getAvatar = async (avatarId) => {
  const response = await api.get(`/avatars/${avatarId}`);
  return response.data;
};

export const createAvatar = async (data) => {
  const response = await api.post('/avatars', data);
  return response.data;
};

export const deleteAvatar = async (avatarId) => {
  const response = await api.delete(`/avatars/${avatarId}`);
  return response.data;
};

// =============================================================================
// Video Generation
// =============================================================================

export const generateVideo = async (data) => {
  const response = await generationApi.post('/videos/generate', data);
  return response.data;
};

export const getVideoStatus = async (jobId) => {
  const response = await api.get(`/videos/${jobId}/status`);
  return response.data;
};

export const listVideos = async (params = {}) => {
  const response = await api.get('/videos', { params });
  return response.data;
};

export const getVideo = async (videoId) => {
  const response = await api.get(`/videos/${videoId}`);
  return response.data;
};

// =============================================================================
// Script Validation
// =============================================================================

export const validateScript = async (script) => {
  const response = await api.post('/scripts/validate', { script });
  return response.data;
};

export const getLanguages = async () => {
  const response = await api.get('/languages');
  return response.data;
};

// =============================================================================
// Polling Helpers
// =============================================================================

export const pollVideoStatus = async (
  jobId,
  onProgress,
  interval = 5000,
  timeout = 600000 // 10 minutes
) => {
  const startTime = Date.now();

  return new Promise((resolve, reject) => {
    const poll = async () => {
      try {
        const status = await getVideoStatus(jobId);

        if (onProgress) {
          onProgress(status.status, status.progress || 0, status);
        }

        if (status.status === VIDYARD_VIDEO_STATUS.COMPLETED) {
          resolve(status);
          return;
        }

        if (status.status === VIDYARD_VIDEO_STATUS.FAILED) {
          reject(new Error(status.error || 'Video generation failed'));
          return;
        }

        if (Date.now() - startTime > timeout) {
          reject(new Error('Video generation timed out'));
          return;
        }

        setTimeout(poll, interval);
      } catch (error) {
        reject(error);
      }
    };

    poll();
  });
};

// =============================================================================
// Upload Helper (for standard video upload)
// =============================================================================

export const uploadVideo = async (data) => {
  const response = await api.post('/videos/upload', data);
  return response.data;
};

// =============================================================================
// Default Export
// =============================================================================

const vidyardApi = {
  // Health
  checkHealth,

  // Avatars
  listAvatars,
  getAvatar,
  createAvatar,
  deleteAvatar,

  // Video Generation
  generateVideo,
  getVideoStatus,
  listVideos,
  getVideo,
  pollVideoStatus,

  // Utilities
  validateScript,
  getLanguages,
  uploadVideo,

  // Constants
  VIDYARD_STATUS,
  VIDYARD_VIDEO_STATUS,
  VIDYARD_LANGUAGES,
  MAX_SCRIPT_LENGTH,
};

export default vidyardApi;
