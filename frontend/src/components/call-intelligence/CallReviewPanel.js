/**
 * Call Review Panel Component
 *
 * Full review interface for a selected call showing:
 * - Call header with key info
 * - Transcript
 * - AI Summary
 * - Generated artifacts (tasks, docs, action items)
 * - Approval/rejection actions
 * - Convert to application button
 */

import React, { useState } from 'react';
import AISummary from './sections/AISummary';
import TasksGenerated from './sections/TasksGenerated';
import DocumentRequests from './sections/DocumentRequests';
import UnderwriterNotes from './sections/UnderwriterNotes';
import CalculatorResults from './sections/CalculatorResults';
import RecordingPlayer from './sections/RecordingPlayer';

const CallReviewPanel = ({
  session,
  reviewData,
  onApprove,
  onReject,
  onExecute,
  onComplete,
  onConvertToApp,
  onClose,
  isReadOnly = false,
}) => {
  const [activeSection, setActiveSection] = useState('summary');
  const [selectedArtifacts, setSelectedArtifacts] = useState([]);

  // Format duration
  const formatDuration = (seconds) => {
    if (!seconds) return '--';
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  // Format date
  const formatDate = (dateStr) => {
    if (!dateStr) return '';
    const date = new Date(dateStr);
    return date.toLocaleString([], {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

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

  // Count pending artifacts
  const pendingArtifacts = reviewData?.artifacts?.filter(
    a => a.approval_status === 'pending'
  ) || [];
  const pendingCount = pendingArtifacts.length;

  // Toggle artifact selection
  const toggleArtifact = (id) => {
    setSelectedArtifacts(prev =>
      prev.includes(id)
        ? prev.filter(x => x !== id)
        : [...prev, id]
    );
  };

  // Select all pending
  const selectAllPending = () => {
    setSelectedArtifacts(pendingArtifacts.map(a => a.id));
  };

  // Handle bulk approve
  const handleBulkApprove = () => {
    if (selectedArtifacts.length > 0) {
      onApprove(selectedArtifacts);
      setSelectedArtifacts([]);
    }
  };

  // Handle bulk reject
  const handleBulkReject = () => {
    if (selectedArtifacts.length > 0) {
      onReject(selectedArtifacts);
      setSelectedArtifacts([]);
    }
  };

  // Section navigation
  const sections = [
    { id: 'summary', label: 'Summary' },
    { id: 'transcript', label: 'Transcript' },
    { id: 'tasks', label: 'Tasks', count: groupedArtifacts.task?.length || 0 },
    { id: 'documents', label: 'Docs', count: groupedArtifacts.document_request?.length || 0 },
    { id: 'calculators', label: 'Calcs', count: groupedArtifacts.calculator_result?.length || 0 },
    { id: 'uw-notes', label: 'UW Notes', count: groupedArtifacts.uw_note?.length || 0 },
  ];

  return (
    <div className="call-review-panel">
      {/* Header */}
      <div className="crp-header">
        <div className="crp-header-main">
          <div className="crp-caller-info">
            <h2>{session.metadata?.caller_name || 'Call Review'}</h2>
            <div className="crp-meta">
              <span>{formatDate(session.started_at)}</span>
              <span className="divider">|</span>
              <span>{formatDuration(session.duration_seconds)}</span>
              <span className="divider">|</span>
              <span className="capture-mode">{session.capture_mode?.replace('_', ' ')}</span>
            </div>
          </div>
          <button className="crp-close-btn" onClick={onClose}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>

        {/* Contact Info */}
        {(session.metadata?.phone || session.metadata?.email) && (
          <div className="crp-contact">
            {session.metadata?.phone && (
              <span className="contact-item">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="14" height="14">
                  <path d="M22 16.92v3a2 2 0 01-2.18 2 19.79 19.79 0 01-8.63-3.07 19.5 19.5 0 01-6-6 19.79 19.79 0 01-3.07-8.67A2 2 0 014.11 2h3a2 2 0 012 1.72 12.84 12.84 0 00.7 2.81 2 2 0 01-.45 2.11L8.09 9.91a16 16 0 006 6l1.27-1.27a2 2 0 012.11-.45 12.84 12.84 0 002.81.7A2 2 0 0122 16.92z" />
                </svg>
                {session.metadata.phone}
              </span>
            )}
            {session.metadata?.email && (
              <span className="contact-item">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="14" height="14">
                  <path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z" />
                  <polyline points="22,6 12,13 2,6" />
                </svg>
                {session.metadata.email}
              </span>
            )}
          </div>
        )}

        {/* Loan Purpose / Context */}
        {session.metadata?.loan_purpose && (
          <div className="crp-purpose">
            <span className="purpose-label">Purpose:</span>
            <span className="purpose-value">{session.metadata.loan_purpose}</span>
            {session.metadata?.loan_amount && (
              <>
                <span className="purpose-label">Amount:</span>
                <span className="purpose-value">
                  ${Number(session.metadata.loan_amount).toLocaleString()}
                </span>
              </>
            )}
          </div>
        )}
      </div>

      {/* Section Navigation */}
      <div className="crp-section-nav">
        {sections.map(section => (
          <button
            key={section.id}
            className={activeSection === section.id ? 'active' : ''}
            onClick={() => setActiveSection(section.id)}
          >
            {section.label}
            {section.count > 0 && (
              <span className="section-count">{section.count}</span>
            )}
          </button>
        ))}
      </div>

      {/* Section Content */}
      <div className="crp-content">
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
            session={session}
          />
        )}

        {activeSection === 'tasks' && (
          <TasksGenerated
            tasks={groupedArtifacts.task || []}
            actionItems={groupedArtifacts.action_item || []}
            onApprove={!isReadOnly ? onApprove : undefined}
          />
        )}

        {activeSection === 'documents' && (
          <DocumentRequests
            requests={groupedArtifacts.document_request || []}
            intakeFields={groupedArtifacts.intake_field || []}
            onApprove={!isReadOnly ? onApprove : undefined}
          />
        )}

        {activeSection === 'calculators' && (
          <CalculatorResults
            calculatorResults={groupedArtifacts.calculator_result || []}
            recommendations={groupedArtifacts.calculator_recommendation || []}
            onApprove={!isReadOnly ? onApprove : undefined}
            onReject={!isReadOnly ? onReject : undefined}
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

      {/* Action Bar */}
      {!isReadOnly && (
        <div className="crp-actions">
          <div className="crp-actions-left">
            {pendingCount > 0 && (
              <>
                <button
                  className="crp-select-all-btn"
                  onClick={selectAllPending}
                >
                  Select All ({pendingCount})
                </button>
                {selectedArtifacts.length > 0 && (
                  <>
                    <button
                      className="crp-approve-btn"
                      onClick={handleBulkApprove}
                    >
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="16" height="16">
                        <polyline points="20 6 9 17 4 12" />
                      </svg>
                      Approve ({selectedArtifacts.length})
                    </button>
                    <button
                      className="crp-reject-btn"
                      onClick={handleBulkReject}
                    >
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="16" height="16">
                        <line x1="18" y1="6" x2="6" y2="18" />
                        <line x1="6" y1="6" x2="18" y2="18" />
                      </svg>
                      Reject
                    </button>
                  </>
                )}
              </>
            )}
          </div>
          <div className="crp-actions-right">
            <button
              className="crp-convert-btn"
              onClick={onConvertToApp}
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="16" height="16">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                <polyline points="14 2 14 8 20 8" />
                <line x1="12" y1="18" x2="12" y2="12" />
                <line x1="9" y1="15" x2="15" y2="15" />
              </svg>
              Convert to Application
            </button>
            {onComplete && (
              <button
                className="crp-complete-btn"
                onClick={onComplete}
              >
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="16" height="16">
                  <path d="M22 11.08V12a10 10 0 11-5.93-9.14" />
                  <polyline points="22 4 12 14.01 9 11.01" />
                </svg>
                Complete Review
              </button>
            )}
          </div>
        </div>
      )}

      {/* Read-only Action Bar */}
      {isReadOnly && (
        <div className="crp-actions">
          <div className="crp-actions-left">
            <span className="crp-readonly-label">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="14" height="14">
                <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
                <path d="M7 11V7a5 5 0 0110 0v4" />
              </svg>
              Read-only view
            </span>
          </div>
          <div className="crp-actions-right">
            <button
              className="crp-convert-btn"
              onClick={onConvertToApp}
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="16" height="16">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                <polyline points="14 2 14 8 20 8" />
                <line x1="12" y1="18" x2="12" y2="12" />
                <line x1="9" y1="15" x2="15" y2="15" />
              </svg>
              Convert to Application
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

export default CallReviewPanel;
