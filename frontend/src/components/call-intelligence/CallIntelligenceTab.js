/**
 * Call Intelligence Tab
 *
 * Main container for the Call Intelligence feature in ClientProfile.
 * Displays call history, AI-generated summaries, tasks, documents, and UW notes.
 */

import React, { useState, useEffect, useCallback } from 'react';
import { toast } from '../../utils/toast';
import { callMonitoringAPI } from '../../services/api';
import CallTimeline from './sections/CallTimeline';
import RecordingPlayer from './sections/RecordingPlayer';
import AISummary from './sections/AISummary';
import TasksGenerated from './sections/TasksGenerated';
import DocumentRequests from './sections/DocumentRequests';
import UnderwriterNotes from './sections/UnderwriterNotes';
import ReviewApproveModal from './ReviewApproveModal';
import './CallIntelligenceTab.css';

const CallIntelligenceTab = ({ clientId, loanId, leadId }) => {
  const [calls, setCalls] = useState([]);
  const [selectedCall, setSelectedCall] = useState(null);
  const [reviewData, setReviewData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [showReviewModal, setShowReviewModal] = useState(false);
  const [activeSection, setActiveSection] = useState('summary');

  // Fetch call history for the client
  const fetchCalls = useCallback(async () => {
    try {
      setLoading(true);
      const params = loanId ? { loan_id: loanId } : {};
      const data = await callMonitoringAPI.getClientCalls(clientId, params);
      setCalls(data.calls || []);

      // Auto-select first call if available
      if (data.calls && data.calls.length > 0 && !selectedCall) {
        handleSelectCall(data.calls[0]);
      }
    } catch (error) {
      console.error('Error fetching calls:', error);
      // Don't show toast for empty state - 404 is expected for new clients
      if (error.response?.status !== 404) {
        toast.error('Failed to load call history');
      }
    } finally {
      setLoading(false);
    }
  }, [clientId, loanId, selectedCall]);

  // Fetch review data for a specific call
  const fetchReviewData = async (sessionId) => {
    try {
      const data = await callMonitoringAPI.getReviewData(sessionId);
      setReviewData(data);
    } catch (error) {
      console.error('Error fetching review data:', error);
      toast.error('Failed to load call details');
    }
  };

  // Handle call selection
  const handleSelectCall = (call) => {
    setSelectedCall(call);
    fetchReviewData(call.id);
  };

  // Handle artifact approval
  const handleApproveArtifacts = async (artifactIds) => {
    try {
      await callMonitoringAPI.approveArtifacts(selectedCall.id, artifactIds);
      toast.success('Artifacts approved successfully');
      fetchReviewData(selectedCall.id);
    } catch (error) {
      console.error('Error approving artifacts:', error);
      toast.error('Failed to approve artifacts');
    }
  };

  // Handle artifact execution
  const handleExecuteArtifacts = async () => {
    try {
      const data = await callMonitoringAPI.executeArtifacts(selectedCall.id);
      toast.success(`Executed ${data.executed_count} artifacts`);
      fetchReviewData(selectedCall.id);
    } catch (error) {
      console.error('Error executing artifacts:', error);
      toast.error('Failed to execute artifacts');
    }
  };

  // Handle review submission
  const handleSubmitReview = async (approvedArtifactIds) => {
    try {
      const data = await callMonitoringAPI.submitReview(selectedCall.id, {
        artifact_ids: approvedArtifactIds
      });
      toast.success(`Review submitted: ${data.approved_count} approved, ${data.executed_count} executed`);
      setShowReviewModal(false);
      fetchReviewData(selectedCall.id);
      fetchCalls();
    } catch (error) {
      console.error('Error submitting review:', error);
      toast.error('Failed to submit review');
    }
  };

  useEffect(() => {
    fetchCalls();
  }, [fetchCalls]);

  // Group artifacts by type
  const groupedArtifacts = reviewData?.artifacts?.reduce((acc, artifact) => {
    const type = artifact.artifact_type;
    if (!acc[type]) {
      acc[type] = [];
    }
    acc[type].push(artifact);
    return acc;
  }, {}) || {};

  // Get summary from artifacts
  const summary = groupedArtifacts.summary?.[0]?.structured_data || null;

  // Count pending approvals
  const pendingCount = reviewData?.artifacts?.filter(a => a.approval_status === 'pending').length || 0;

  if (loading && calls.length === 0) {
    return (
      <div className="call-intelligence-tab">
        <div className="ci-loading">
          <div className="spinner"></div>
          <p>Loading call history...</p>
        </div>
      </div>
    );
  }

  if (calls.length === 0) {
    return (
      <div className="call-intelligence-tab">
        <div className="ci-empty-state">
          <div className="empty-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M22 16.92v3a2 2 0 01-2.18 2 19.79 19.79 0 01-8.63-3.07 19.5 19.5 0 01-6-6 19.79 19.79 0 01-3.07-8.67A2 2 0 014.11 2h3a2 2 0 012 1.72 12.84 12.84 0 00.7 2.81 2 2 0 01-.45 2.11L8.09 9.91a16 16 0 006 6l1.27-1.27a2 2 0 012.11-.45 12.84 12.84 0 002.81.7A2 2 0 0122 16.92z" />
            </svg>
          </div>
          <h3>No Calls Yet</h3>
          <p>Call recordings and AI-generated insights will appear here once calls are processed.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="call-intelligence-tab">
      <div className="ci-header">
        <h2>Call Intelligence</h2>
        {pendingCount > 0 && (
          <button
            className="ci-review-btn"
            onClick={() => setShowReviewModal(true)}
          >
            Review & Approve ({pendingCount})
          </button>
        )}
      </div>

      <div className="ci-content">
        {/* Call Timeline - Left Panel */}
        <div className="ci-left-panel">
          <CallTimeline
            calls={calls}
            selectedCall={selectedCall}
            onSelectCall={handleSelectCall}
          />
        </div>

        {/* Main Content - Right Panel */}
        <div className="ci-right-panel">
          {selectedCall ? (
            <>
              {/* Section Navigation */}
              <div className="ci-section-nav">
                <button
                  className={activeSection === 'summary' ? 'active' : ''}
                  onClick={() => setActiveSection('summary')}
                >
                  Summary
                </button>
                <button
                  className={activeSection === 'transcript' ? 'active' : ''}
                  onClick={() => setActiveSection('transcript')}
                >
                  Transcript
                </button>
                <button
                  className={activeSection === 'tasks' ? 'active' : ''}
                  onClick={() => setActiveSection('tasks')}
                >
                  Tasks {groupedArtifacts.task?.length > 0 && `(${groupedArtifacts.task.length})`}
                </button>
                <button
                  className={activeSection === 'documents' ? 'active' : ''}
                  onClick={() => setActiveSection('documents')}
                >
                  Docs {groupedArtifacts.document_request?.length > 0 && `(${groupedArtifacts.document_request.length})`}
                </button>
                <button
                  className={activeSection === 'uw-notes' ? 'active' : ''}
                  onClick={() => setActiveSection('uw-notes')}
                >
                  UW Notes
                </button>
              </div>

              {/* Section Content */}
              <div className="ci-section-content">
                {activeSection === 'summary' && (
                  <AISummary
                    summary={summary}
                    actionItems={groupedArtifacts.action_item || []}
                    callOutcome={summary?.call_outcome}
                  />
                )}

                {activeSection === 'transcript' && (
                  <RecordingPlayer
                    transcript={reviewData?.transcript}
                    participants={reviewData?.participants || []}
                    session={selectedCall}
                  />
                )}

                {activeSection === 'tasks' && (
                  <TasksGenerated
                    tasks={groupedArtifacts.task || []}
                    actionItems={groupedArtifacts.action_item || []}
                    onApprove={handleApproveArtifacts}
                  />
                )}

                {activeSection === 'documents' && (
                  <DocumentRequests
                    requests={groupedArtifacts.document_request || []}
                    intakeFields={groupedArtifacts.intake_field || []}
                    onApprove={handleApproveArtifacts}
                  />
                )}

                {activeSection === 'uw-notes' && (
                  <UnderwriterNotes
                    notes={groupedArtifacts.uw_note || []}
                    riskFlags={groupedArtifacts.risk_flag || []}
                    conditions={groupedArtifacts.condition || []}
                  />
                )}
              </div>
            </>
          ) : (
            <div className="ci-no-selection">
              <p>Select a call from the timeline to view details</p>
            </div>
          )}
        </div>
      </div>

      {/* Review & Approve Modal */}
      {showReviewModal && reviewData && (
        <ReviewApproveModal
          artifacts={reviewData.artifacts}
          onSubmit={handleSubmitReview}
          onClose={() => setShowReviewModal(false)}
        />
      )}
    </div>
  );
};

export default CallIntelligenceTab;
