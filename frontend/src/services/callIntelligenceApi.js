// ─────────────────────────────────────────────────────────────
// CALL INTELLIGENCE API SERVICE
// src/services/callIntelligenceApi.js
// ─────────────────────────────────────────────────────────────

import api, { API_BASE_URL } from './api';

/**
 * Derive WebSocket base URL from the API base URL.
 * Replaces https:// with wss:// and http:// with ws://.
 */
function getWsBase() {
  return API_BASE_URL
    .replace('https://', 'wss://')
    .replace('http://', 'ws://');
}

export const CallIntelligenceApi = {

  // ── Initiate an outbound call with all 4 agents activated ──
  // Called when LO taps "Call Intelligence" + dials a borrower
  async startCall(params) {
    try {
      const response = await api.post('/api/call-intelligence/start', params);
      return response.data;
    } catch (error) {
      console.error('[CallIntelligenceApi] startCall error:', error);
      const errMsg = error.response?.data?.detail || error.message || 'Failed to start call';
      throw new Error(errMsg);
    }
    // Backend actions:
    //   1. Telnyx: initiate outbound call -> get call_sid
    //   2. Create CallSession row in DB
    //   3. Spin up LangGraph graph with 4 agent nodes
    //   4. Open Deepgram/Whisper stream on call audio
    //   5. Return session_id + call_sid
  },

  // ── End call and trigger post-call processing ─────────────
  async endCall(sessionId) {
    try {
      await api.post(`/api/call-intelligence/${sessionId}/end`);
    } catch (error) {
      console.error('[CallIntelligenceApi] endCall error:', error);
      const errMsg = error.response?.data?.detail || error.message || 'Failed to end call';
      throw new Error(errMsg);
    }
    // Backend actions:
    //   1. Telnyx: hang up call
    //   2. Finalize transcript
    //   3. Jr. LO: save application draft to DB
    //   4. Note Taker: save full transcript + summary
    //   5. Auditor: finalize all flags, tasks, doc requests
    //   6. Receptionist: confirm all calendar events
  },

  // ── Get active session for this LO ───────────────────────
  async getActiveSession(loUserId) {
    try {
      const response = await api.get('/api/call-intelligence/active', {
        params: { lo_user_id: loUserId },
      });
      return response.data ?? null;
    } catch (error) {
      console.error('[CallIntelligenceApi] getActiveSession error:', error);
      return null;
    }
  },

  // ── Get call history ──────────────────────────────────────
  async getCallHistory(loUserId, limit = 10) {
    try {
      const response = await api.get('/api/call-intelligence/history', {
        params: { lo_user_id: loUserId, limit },
      });
      return response.data;
    } catch (error) {
      console.error('[CallIntelligenceApi] getCallHistory error:', error);
      return [];
    }
  },

  // ── Get full post-call summary ────────────────────────────
  async getCallSummary(sessionId) {
    try {
      const response = await api.get(`/api/call-intelligence/${sessionId}/summary`);
      return response.data;
    } catch (error) {
      console.error('[CallIntelligenceApi] getCallSummary error:', error);
      const errMsg = error.response?.data?.detail || error.message || 'Failed to get summary';
      throw new Error(errMsg);
    }
  },

  // ── Manually approve a document request ──────────────────
  async approveDocumentRequest(sessionId, requestId) {
    try {
      await api.post(`/api/call-intelligence/${sessionId}/doc-requests/${requestId}/approve`);
    } catch (error) {
      console.error('[CallIntelligenceApi] approveDocumentRequest error:', error);
      const errMsg = error.response?.data?.detail || error.message || 'Failed to approve document request';
      throw new Error(errMsg);
    }
  },

  // ── Dismiss an audit flag ─────────────────────────────────
  async dismissFlag(sessionId, flagId) {
    try {
      await api.patch(`/api/call-intelligence/${sessionId}/flags/${flagId}`, {
        resolved: true,
      });
    } catch (error) {
      console.error('[CallIntelligenceApi] dismissFlag error:', error);
      const errMsg = error.response?.data?.detail || error.message || 'Failed to dismiss flag';
      throw new Error(errMsg);
    }
  },

  // ── Save loan application fields to the CRM ──────────────
  async saveApplicationDraft(sessionId, fields) {
    try {
      const response = await api.post(
        `/api/call-intelligence/${sessionId}/application`,
        fields,
      );
      return response.data;
    } catch (error) {
      console.error('[CallIntelligenceApi] saveApplicationDraft error:', error);
      const errMsg = error.response?.data?.detail || error.message || 'Failed to save application draft';
      throw new Error(errMsg);
    }
  },

  // ── WebSocket URL for live agent updates ──────────────────
  // Format: wss://api.perenniaai.com/ws/call-intelligence/{session_id}
  getWebSocketUrl(sessionId) {
    return `${getWsBase()}/ws/call-intelligence/${sessionId}`;
  },

  // ── WebSocket URL to watch for a new incoming active call ─
  getActiveCallWatcherUrl(loUserId) {
    return `${getWsBase()}/ws/call-intelligence/watch?lo_user_id=${loUserId}`;
  },
};
