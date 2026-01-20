/**
 * AI Summary Component
 *
 * Displays the AI-generated call summary including:
 * - Executive summary
 * - Key points
 * - Action items
 * - Call outcome
 */

import React from 'react';

const AISummary = ({ summary, actionItems, callOutcome }) => {
  if (!summary && (!actionItems || actionItems.length === 0)) {
    return (
      <div className="ai-summary">
        <div className="summary-card">
          <p style={{ color: '#6b7280', textAlign: 'center', padding: '20px' }}>
            No summary available for this call.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="ai-summary">
      {/* Call Outcome Badge */}
      {callOutcome && (
        <div style={{ marginBottom: '16px' }}>
          <span className={`call-outcome-badge ${callOutcome}`}>
            {callOutcome === 'positive' && '+ '}
            {callOutcome === 'negative' && '- '}
            Call Outcome: {callOutcome.charAt(0).toUpperCase() + callOutcome.slice(1)}
          </span>
        </div>
      )}

      {/* Executive Summary */}
      {summary?.executive_summary && (
        <div className="summary-card">
          <h4>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
              <polyline points="14 2 14 8 20 8" />
              <line x1="16" y1="13" x2="8" y2="13" />
              <line x1="16" y1="17" x2="8" y2="17" />
              <polyline points="10 9 9 9 8 9" />
            </svg>
            Executive Summary
          </h4>
          <p className="executive-summary">{summary.executive_summary}</p>
        </div>
      )}

      {/* Key Points */}
      {summary?.key_points && summary.key_points.length > 0 && (
        <div className="summary-card">
          <h4>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <line x1="8" y1="6" x2="21" y2="6" />
              <line x1="8" y1="12" x2="21" y2="12" />
              <line x1="8" y1="18" x2="21" y2="18" />
              <line x1="3" y1="6" x2="3.01" y2="6" />
              <line x1="3" y1="12" x2="3.01" y2="12" />
              <line x1="3" y1="18" x2="3.01" y2="18" />
            </svg>
            Key Points
          </h4>
          <ul className="key-points-list">
            {summary.key_points.map((point, index) => (
              <li key={index}>{point}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Action Items */}
      {actionItems && actionItems.length > 0 && (
        <div className="summary-card">
          <h4>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
              <polyline points="22 4 12 14.01 9 11.01" />
            </svg>
            Action Items ({actionItems.length})
          </h4>
          <div className="action-items-list">
            {actionItems.map((item) => (
              <div key={item.id} className="action-item">
                <div className="item-header">
                  <span className="item-title">{item.title}</span>
                  {item.structured_data?.owner && (
                    <span className="item-owner">{item.structured_data.owner}</span>
                  )}
                </div>
                <div className="item-content">{item.content}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Detailed Summary */}
      {summary?.detailed_summary && (
        <div className="summary-card">
          <h4>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
            </svg>
            Detailed Summary
          </h4>
          <p style={{ fontSize: '0.875rem', lineHeight: '1.7', color: '#374151' }}>
            {summary.detailed_summary}
          </p>
        </div>
      )}

      {/* Next Steps */}
      {summary?.next_call_recommended && summary?.next_call_topic && (
        <div className="summary-card" style={{ background: '#eff6ff', borderLeft: '3px solid #3b82f6' }}>
          <h4 style={{ color: '#1e40af' }}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="10" />
              <polyline points="12 6 12 12 16 14" />
            </svg>
            Next Call Recommended
          </h4>
          <p style={{ fontSize: '0.875rem', color: '#1e40af', margin: 0 }}>
            Topic: {summary.next_call_topic}
          </p>
        </div>
      )}
    </div>
  );
};

export default AISummary;
