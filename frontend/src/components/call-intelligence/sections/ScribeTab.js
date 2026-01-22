/**
 * Scribe Tab Component
 *
 * Displays the AI-generated call recap including:
 * - Detailed call recap narrative
 * - Action items with owners and deadlines
 * - Next steps with timeline
 * - Key commitments made
 */

import React from 'react';

const ScribeTab = ({ scribeRecap, actionItems, summary }) => {
  // Use scribe_recap artifact data, fall back to summary
  const recapData = scribeRecap?.structured_data || summary || {};

  if (!recapData.detailed_recap && !recapData.executive_summary && (!actionItems || actionItems.length === 0)) {
    return (
      <div className="scribe-tab">
        <div className="summary-card">
          <p style={{ color: '#6b7280', textAlign: 'center', padding: '20px' }}>
            No scribe recap available for this call.
          </p>
        </div>
      </div>
    );
  }

  const callOutcome = recapData.call_outcome;
  const borrowerSentiment = recapData.borrower_sentiment;
  const nextSteps = recapData.next_steps || [];
  const keyCommitments = recapData.key_commitments || [];

  return (
    <div className="scribe-tab">
      {/* Call Outcome & Sentiment Badges */}
      <div style={{ display: 'flex', gap: '12px', marginBottom: '16px', flexWrap: 'wrap' }}>
        {callOutcome && (
          <span className={`call-outcome-badge ${callOutcome}`}>
            {callOutcome === 'positive' && '+ '}
            {callOutcome === 'negative' && '- '}
            {callOutcome === 'needs_follow_up' && '! '}
            Call: {callOutcome.replace('_', ' ').charAt(0).toUpperCase() + callOutcome.replace('_', ' ').slice(1)}
          </span>
        )}
        {borrowerSentiment && (
          <span className={`sentiment-badge ${borrowerSentiment}`}>
            Sentiment: {borrowerSentiment.charAt(0).toUpperCase() + borrowerSentiment.slice(1)}
          </span>
        )}
      </div>

      {/* Call Recap */}
      <div className="summary-card scribe-recap">
        <h4>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
            <polyline points="14 2 14 8 20 8" />
            <line x1="16" y1="13" x2="8" y2="13" />
            <line x1="16" y1="17" x2="8" y2="17" />
          </svg>
          Call Recap
        </h4>
        <div className="recap-content">
          {recapData.detailed_recap || recapData.executive_summary || scribeRecap?.content || 'No recap available.'}
        </div>
      </div>

      {/* Action Items */}
      {actionItems && actionItems.length > 0 && (
        <div className="summary-card scribe-actions">
          <h4>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
              <polyline points="22 4 12 14.01 9 11.01" />
            </svg>
            Action Items ({actionItems.length})
          </h4>
          <div className="action-items-grid">
            {actionItems.map((item, index) => (
              <div key={item.id || index} className="action-item-card">
                <div className="action-item-header">
                  <span className="action-item-title">{item.title}</span>
                  <span className={`priority-badge ${item.structured_data?.priority || 'medium'}`}>
                    {item.structured_data?.priority || 'medium'}
                  </span>
                </div>
                <div className="action-item-body">
                  <p className="action-description">{item.content}</p>
                  <div className="action-meta">
                    {item.structured_data?.owner && (
                      <span className="action-owner">
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                          <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
                          <circle cx="12" cy="7" r="4" />
                        </svg>
                        {item.structured_data.owner}
                      </span>
                    )}
                    {item.structured_data?.deadline && (
                      <span className="action-deadline">
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                          <rect x="3" y="4" width="18" height="18" rx="2" ry="2" />
                          <line x1="16" y1="2" x2="16" y2="6" />
                          <line x1="8" y1="2" x2="8" y2="6" />
                          <line x1="3" y1="10" x2="21" y2="10" />
                        </svg>
                        {item.structured_data.deadline}
                      </span>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Next Steps */}
      {nextSteps.length > 0 && (
        <div className="summary-card scribe-next-steps">
          <h4>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <polyline points="9 18 15 12 9 6" />
            </svg>
            Next Steps
          </h4>
          <div className="next-steps-list">
            {nextSteps.map((step, index) => (
              <div key={index} className="next-step-item">
                <div className="step-number">{index + 1}</div>
                <div className="step-content">
                  <div className="step-text">{step.step}</div>
                  <div className="step-meta">
                    {step.owner && <span className="step-owner">{step.owner}</span>}
                    {step.timeline && <span className="step-timeline">{step.timeline}</span>}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Key Commitments */}
      {keyCommitments.length > 0 && (
        <div className="summary-card scribe-commitments" style={{ background: '#f0fdf4', borderLeft: '3px solid #22c55e' }}>
          <h4 style={{ color: '#166534' }}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M9 12l2 2 4-4" />
              <circle cx="12" cy="12" r="10" />
            </svg>
            Key Commitments Made
          </h4>
          <ul className="commitments-list">
            {keyCommitments.map((commitment, index) => (
              <li key={index} className="commitment-item">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#22c55e" strokeWidth="2">
                  <polyline points="20 6 9 17 4 12" />
                </svg>
                <span>{commitment}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Follow-Up Timeline */}
      {recapData.follow_up_timeline && (
        <div className="summary-card" style={{ background: '#eff6ff', borderLeft: '3px solid #3b82f6' }}>
          <h4 style={{ color: '#1e40af' }}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="10" />
              <polyline points="12 6 12 12 16 14" />
            </svg>
            Follow-Up Timeline
          </h4>
          <p style={{ fontSize: '0.875rem', color: '#1e40af', margin: 0 }}>
            {recapData.follow_up_timeline}
          </p>
        </div>
      )}
    </div>
  );
};

export default ScribeTab;
