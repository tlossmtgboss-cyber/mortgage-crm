/**
 * VoiceProfileService.js
 * Perennia AI — Voice Profile API Client
 *
 * Handles communication between the Capacitor web app and the
 * /api/v1/voice-profile backend endpoints for Aria voice enrollment.
 */

import api from './api';

export const voiceProfileApi = {
  /**
   * Upload a single voice sample recording.
   * @param {Object} params
   * @param {string} params.promptId - Prompt identifier
   * @param {Blob} params.audioBlob - Audio blob from MediaRecorder
   * @param {string} params.category - Voice category (intro, professional, natural, numeric, emotional)
   * @returns {Promise<{sample_id: string, prompt_id: string, samples_total: number}>}
   */
  async uploadSample({ promptId, audioBlob, category }) {
    const formData = new FormData();
    formData.append('audio', audioBlob, `voice_${promptId}.webm`);
    formData.append('prompt_id', promptId);
    formData.append('category', category);

    const res = await api.post('/api/v1/voice-profile/samples', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return res.data;
  },

  /**
   * Trigger final enrollment — backend compiles all samples into a
   * speaker embedding and marks the user as voice-enrolled.
   */
  async finalizeEnrollment() {
    const res = await api.post('/api/v1/voice-profile/enroll');
    return res.data;
  },

  /**
   * Check enrollment status for the current user.
   * @returns {Promise<{status: string, samples_received: number, samples_required: number, embedding_ready: boolean, enrolled_at?: string}>}
   */
  async getStatus() {
    const res = await api.get('/api/v1/voice-profile/status');
    return res.data;
  },

  /**
   * Verify a live audio clip against stored voice profile.
   * @param {Blob} audioBlob - Audio blob to verify
   * @returns {Promise<{match: boolean, confidence: number}>}
   */
  async verifyVoice(audioBlob) {
    const formData = new FormData();
    formData.append('audio', audioBlob, 'verify_clip.webm');

    const res = await api.post('/api/v1/voice-profile/verify', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return res.data;
  },

  /**
   * Delete the voice profile for the current user (GDPR / user request).
   */
  async deleteProfile() {
    await api.delete('/api/v1/voice-profile');
  },
};
