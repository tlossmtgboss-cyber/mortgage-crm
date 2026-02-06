/**
 * Call Intelligence Tab (Enhanced)
 *
 * Main container for the Call Intelligence feature in ClientProfile.
 * Displays call history, AI-generated summaries, tasks, documents, and UW notes.
 *
 * New tabs:
 * - Scribe: Call recap, action items, next steps
 * - JR LO: 5 C's analysis, documents requested
 * - Underwriter: Review items checklist, PA task creation
 * - Notes: Chronological stacked notes across all calls
 */

import React, { useState, useEffect, useCallback } from 'react';
import { toast } from '../../utils/toast';
import { callMonitoringAPI } from '../../services/api';
import CallTimeline from './sections/CallTimeline';
import RecordingPlayer from './sections/RecordingPlayer';
import AISummary from './sections/AISummary';
import ScribeTab from './sections/ScribeTab';
import JRLOTab from './sections/JRLOTab';
import TasksGenerated from './sections/TasksGenerated';
import DocumentRequests from './sections/DocumentRequests';
import UnderwriterNotes from './sections/UnderwriterNotes';
import CalculatorResults from './sections/CalculatorResults';
import MarketingTab from './sections/MarketingTab';
import SchedulingTab from './sections/SchedulingTab';
import StackedNotes from './sections/StackedNotes';
import ExtractionsSection from './sections/ExtractionsSection';
import ReviewApproveModal from './ReviewApproveModal';
import ShareCalculatorModal from './ShareCalculatorModal';
import './CallIntelligenceTab.css';

const CallIntelligenceTab = ({ clientId, loanId, leadId }) => {
  const [calls, setCalls] = useState([]);
  const [selectedCall, setSelectedCall] = useState(null);
  const [reviewData, setReviewData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [showReviewModal, setShowReviewModal] = useState(false);
  const [activeSection, setActiveSection] = useState('scribe');
  const [shareModalArtifact, setShareModalArtifact] = useState(null);

  // Stacked notes state
  const [stackedNotes, setStackedNotes] = useState([]);
  const [loadingNotes, setLoadingNotes] = useState(false);

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

  // Fetch stacked notes for the client
  const fetchStackedNotes = useCallback(async () => {
    if (!clientId) return;
    try {
      setLoadingNotes(true);
      const data = await callMonitoringAPI.getStackedNotes(clientId);
      setStackedNotes(data.notes || []);
    } catch (error) {
      console.error('Error fetching stacked notes:', error);
    } finally {
      setLoadingNotes(false);
    }
  }, [clientId]);

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

  // Handle artifact rejection
  const handleRejectArtifacts = async (artifactIds, reason) => {
    try {
      await callMonitoringAPI.rejectArtifacts(selectedCall.id, artifactIds, reason);
      toast.success('Artifacts rejected');
      fetchReviewData(selectedCall.id);
    } catch (error) {
      console.error('Error rejecting artifacts:', error);
      toast.error('Failed to reject artifacts');
    }
  };

  // Handle share calculator result
  const handleShareCalculator = (artifact) => {
    setShareModalArtifact(artifact);
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

  // Handle UW review completion with PA task creation
  const handleCompleteUWReview = async ({ sessionId, summary, items_addressed, create_pa_task }) => {
    try {
      const data = await callMonitoringAPI.completeUWReview(sessionId, {
        summary,
        items_addressed,
        create_pa_task,
      });
      toast.success(data.pa_task_created
        ? 'UW review completed and PA task created!'
        : 'UW review completed!'
      );
      fetchReviewData(sessionId);
    } catch (error) {
      console.error('Error completing UW review:', error);
      toast.error('Failed to complete UW review');
    }
  };

  // Handle creating review task from JR LO or UW
  const handleCreateReviewTask = async (taskData) => {
    try {
      const data = await callMonitoringAPI.createReviewTask(selectedCall.id, taskData);
      toast.success(`Review task created: ${data.task_id}`);
    } catch (error) {
      console.error('Error creating review task:', error);
      toast.error('Failed to create review task');
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

  // Fetch stacked notes when notes tab is active
  useEffect(() => {
    if (activeSection === 'notes') {
      fetchStackedNotes();
    }
  }, [activeSection, fetchStackedNotes]);

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

  // Get scribe recap
  const scribeRecap = groupedArtifacts.scribe_recap?.[0] || null;

  // Get 5 C's artifacts
  const fiveCAnalysis = [
    ...(groupedArtifacts.five_c_credit || []),
    ...(groupedArtifacts.five_c_collateral || []),
    ...(groupedArtifacts.five_c_capacity || []),
    ...(groupedArtifacts.five_c_characteristics || []),
    ...(groupedArtifacts.five_c_cash || []),
  ];

  // Get UW review items
  const uwReviewItems = groupedArtifacts.uw_review_item || [];

  // Get Marketing Agent artifacts
  const storyNotes = groupedArtifacts.borrower_story_note || [];
  const storyThemes = groupedArtifacts.story_theme || [];
  const borrowerQuotes = groupedArtifacts.borrower_quote || [];
  const contentIdeas = groupedArtifacts.content_idea || [];
  const marketingMilestones = groupedArtifacts.marketing_milestone || [];

  // Get Receptionist Agent artifacts (scheduling)
  const scheduledAppointments = groupedArtifacts.scheduled_appointment || [];
  const followUpCalls = groupedArtifacts.follow_up_call || [];
  const calendarActions = groupedArtifacts.calendar_action || [];
  const meetingSummaries = groupedArtifacts.meeting_summary || [];

  // Get Call Intelligence extraction artifacts
  const extractedIdentity = groupedArtifacts.extracted_identity?.[0]?.structured_data || {};
  const extractedProperty = groupedArtifacts.extracted_property?.[0]?.structured_data || {};
  const extractedEmployment = groupedArtifacts.extracted_employment?.[0]?.structured_data || {};
  const extractedFinancial = groupedArtifacts.extracted_financial?.[0]?.structured_data || {};
  const extractedCompliance = groupedArtifacts.extracted_compliance?.[0]?.structured_data || {};
  const extractedIntent = groupedArtifacts.extracted_intent?.[0]?.structured_data || {};
  const callOutcomeData = groupedArtifacts.call_outcome?.[0]?.structured_data || null;

  // Combine extractions
  const extractions = {
    identity: extractedIdentity,
    property: extractedProperty,
    employment: extractedEmployment,
    financial: extractedFinancial,
    compliance: extractedCompliance,
    intent: extractedIntent,
  };

  const hasExtractions = Object.values(extractions).some(e => Object.keys(e).length > 0) || callOutcomeData;

  // Count pending approvals
  const pendingCount = reviewData?.artifacts?.filter(a => a.approval_status === 'pending').length || 0;

  // Calculate tab counts
  const taskCount = (groupedArtifacts.task?.length || 0);
  const docCount = (groupedArtifacts.document_request?.length || 0);
  const calcCount = (groupedArtifacts.calculator_result?.length || 0);
  const uwItemCount = uwReviewItems.length;
  const fiveCCount = fiveCAnalysis.length;
  const marketingCount = storyNotes.length + storyThemes.length + borrowerQuotes.length +
    contentIdeas.length + marketingMilestones.length;
  const schedulingCount = scheduledAppointments.length + followUpCalls.length + calendarActions.length;
  const extractionCount = Object.values(extractions).filter(e => Object.keys(e).length > 0).length +
    (callOutcomeData ? 1 : 0);

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
                  className={activeSection === 'scribe' ? 'active' : ''}
                  onClick={() => setActiveSection('scribe')}
                >
                  Scribe
                </button>
                <button
                  className={activeSection === 'extractions' ? 'active' : ''}
                  onClick={() => setActiveSection('extractions')}
                >
                  Data {extractionCount > 0 && `(${extractionCount})`}
                </button>
                <button
                  className={activeSection === 'jrlo' ? 'active' : ''}
                  onClick={() => setActiveSection('jrlo')}
                >
                  JR LO {fiveCCount > 0 && `(${fiveCCount})`}
                </button>
                <button
                  className={activeSection === 'uw-notes' ? 'active' : ''}
                  onClick={() => setActiveSection('uw-notes')}
                >
                  UW {uwItemCount > 0 && `(${uwItemCount})`}
                </button>
                <button
                  className={activeSection === 'documents' ? 'active' : ''}
                  onClick={() => setActiveSection('documents')}
                >
                  Docs {docCount > 0 && `(${docCount})`}
                </button>
                <button
                  className={activeSection === 'calculators' ? 'active' : ''}
                  onClick={() => setActiveSection('calculators')}
                >
                  Calcs {calcCount > 0 && `(${calcCount})`}
                </button>
                <button
                  className={activeSection === 'marketing' ? 'active' : ''}
                  onClick={() => setActiveSection('marketing')}
                >
                  Story {marketingCount > 0 && `(${marketingCount})`}
                </button>
                <button
                  className={activeSection === 'scheduling' ? 'active' : ''}
                  onClick={() => setActiveSection('scheduling')}
                >
                  Schedule {schedulingCount > 0 && `(${schedulingCount})`}
                </button>
                <button
                  className={activeSection === 'transcript' ? 'active' : ''}
                  onClick={() => setActiveSection('transcript')}
                >
                  Transcript
                </button>
                <button
                  className={activeSection === 'notes' ? 'active' : ''}
                  onClick={() => setActiveSection('notes')}
                >
                  Notes
                </button>
              </div>

              {/* Section Content */}
              <div className="ci-section-content">
                {activeSection === 'scribe' && (
                  <ScribeTab
                    scribeRecap={scribeRecap}
                    actionItems={groupedArtifacts.action_item || []}
                    summary={summary}
                  />
                )}

                {activeSection === 'extractions' && (
                  <ExtractionsSection
                    extractions={extractions}
                    callOutcome={callOutcomeData}
                    sessionId={selectedCall?.id}
                  />
                )}

                {activeSection === 'jrlo' && (
                  <JRLOTab
                    fiveCAnalysis={fiveCAnalysis}
                    documentRequests={groupedArtifacts.document_request || []}
                    reviewTasks={groupedArtifacts.task?.filter(t => t.structured_data?.source === 'jrlo_5c_analysis') || []}
                    onCreateTask={handleCreateReviewTask}
                  />
                )}

                {activeSection === 'uw-notes' && (
                  <UnderwriterNotes
                    notes={[
                      ...(groupedArtifacts.uw_note || []),
                      ...(groupedArtifacts.uw_assessment || []),
                    ]}
                    riskFlags={groupedArtifacts.risk_flag || []}
                    conditions={groupedArtifacts.condition || []}
                    reviewItems={uwReviewItems}
                    sessionId={selectedCall?.id}
                    onCompleteReview={handleCompleteUWReview}
                  />
                )}

                {activeSection === 'documents' && (
                  <DocumentRequests
                    requests={groupedArtifacts.document_request || []}
                    intakeFields={groupedArtifacts.intake_field || []}
                    onApprove={handleApproveArtifacts}
                  />
                )}

                {activeSection === 'calculators' && (
                  <CalculatorResults
                    calculatorResults={groupedArtifacts.calculator_result || []}
                    recommendations={groupedArtifacts.calculator_recommendation || []}
                    onShare={handleShareCalculator}
                    onApprove={handleApproveArtifacts}
                    onReject={handleRejectArtifacts}
                  />
                )}

                {activeSection === 'marketing' && (
                  <MarketingTab
                    storyNotes={storyNotes}
                    storyThemes={storyThemes}
                    borrowerQuotes={borrowerQuotes}
                    contentIdeas={contentIdeas}
                    milestones={marketingMilestones}
                    borrowerName={reviewData?.session?.borrower_name || ''}
                  />
                )}

                {activeSection === 'scheduling' && (
                  <SchedulingTab
                    appointments={scheduledAppointments}
                    followUpCalls={followUpCalls}
                    calendarActions={calendarActions}
                    meetingSummaries={meetingSummaries}
                    onApproveAppointment={handleApproveArtifacts}
                    onRejectAppointment={handleRejectArtifacts}
                  />
                )}

                {activeSection === 'transcript' && (
                  <RecordingPlayer
                    transcript={reviewData?.transcript}
                    participants={reviewData?.participants || []}
                    session={selectedCall}
                  />
                )}

                {activeSection === 'notes' && (
                  <StackedNotes
                    clientId={clientId}
                    notes={stackedNotes}
                    loading={loadingNotes}
                    onRefresh={fetchStackedNotes}
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

      {/* Share Calculator Modal */}
      {shareModalArtifact && (
        <ShareCalculatorModal
          artifact={shareModalArtifact}
          onClose={() => setShareModalArtifact(null)}
        />
      )}
    </div>
  );
};

export default CallIntelligenceTab;
