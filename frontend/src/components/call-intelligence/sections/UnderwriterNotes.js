/**
 * Underwriter Notes Component
 *
 * Displays UW notes, risk flags, and suggested conditions from call analysis.
 */

import React from 'react';

const UnderwriterNotes = ({ notes, riskFlags, conditions }) => {
  const hasContent = (notes && notes.length > 0) ||
                     (riskFlags && riskFlags.length > 0) ||
                     (conditions && conditions.length > 0);

  if (!hasContent) {
    return (
      <div className="uw-notes">
        <p style={{ color: '#6b7280', textAlign: 'center', padding: '40px' }}>
          No underwriter notes or risk flags from this call.
        </p>
      </div>
    );
  }

  // Get overall assessment from notes
  const assessment = notes?.find(n => n.structured_data?.note_category === 'assessment');
  const otherNotes = notes?.filter(n => n.structured_data?.note_category !== 'assessment') || [];

  return (
    <div className="uw-notes">
      {/* Overall Risk Assessment */}
      {assessment && (
        <div style={{
          padding: '16px',
          background: getRiskBackground(assessment.structured_data?.risk_level),
          borderRadius: '8px',
          marginBottom: '20px',
          borderLeft: `4px solid ${getRiskColor(assessment.structured_data?.risk_level)}`,
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
            <h4 style={{ margin: 0, fontSize: '0.95rem', color: '#111827' }}>
              Overall Risk Assessment
            </h4>
            <span style={{
              padding: '4px 12px',
              borderRadius: '20px',
              fontSize: '0.75rem',
              fontWeight: '600',
              textTransform: 'uppercase',
              background: getRiskBadgeBackground(assessment.structured_data?.risk_level),
              color: getRiskColor(assessment.structured_data?.risk_level),
            }}>
              {assessment.structured_data?.risk_level || 'Unknown'}
            </span>
          </div>

          <p style={{ margin: 0, fontSize: '0.875rem', lineHeight: '1.6', whiteSpace: 'pre-wrap' }}>
            {assessment.content}
          </p>

          {assessment.structured_data?.recommendation && (
            <div style={{
              marginTop: '12px',
              paddingTop: '12px',
              borderTop: '1px solid rgba(0,0,0,0.1)',
              fontSize: '0.8rem',
              color: '#374151',
            }}>
              <strong>Recommendation:</strong> {assessment.structured_data.recommendation.replace(/_/g, ' ')}
            </div>
          )}
        </div>
      )}

      {/* Risk Flags */}
      {riskFlags && riskFlags.length > 0 && (
        <div className="risk-flags-section">
          <div className="section-title">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#dc2626" strokeWidth="2">
              <path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z" />
              <line x1="4" y1="22" x2="4" y2="15" />
            </svg>
            Risk Flags ({riskFlags.length})
          </div>

          {riskFlags.map((flag) => (
            <div
              key={flag.id}
              className={`risk-flag severity-${flag.structured_data?.severity || 'medium'}`}
            >
              <div className="flag-header">
                <span className="flag-title">{flag.title}</span>
                <span className={`flag-severity ${flag.structured_data?.severity || 'medium'}`}>
                  {flag.structured_data?.severity || 'medium'}
                </span>
              </div>

              <div className="flag-content">
                {flag.content}
              </div>

              {flag.structured_data?.risk_category && (
                <div style={{ marginTop: '8px', fontSize: '0.75rem' }}>
                  <span style={{
                    padding: '2px 8px',
                    background: '#f3f4f6',
                    borderRadius: '4px',
                    color: '#6b7280',
                  }}>
                    {flag.structured_data.risk_category}
                  </span>
                </div>
              )}

              {flag.structured_data?.recommended_action && (
                <div style={{
                  marginTop: '8px',
                  padding: '8px',
                  background: '#fffbeb',
                  borderRadius: '4px',
                  fontSize: '0.75rem',
                  color: '#92400e',
                }}>
                  <strong>Action:</strong> {flag.structured_data.recommended_action}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Suggested Conditions */}
      {conditions && conditions.length > 0 && (
        <div className="conditions-section" style={{ marginTop: '20px' }}>
          <div className="section-title">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#3b82f6" strokeWidth="2">
              <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
              <polyline points="22 4 12 14.01 9 11.01" />
            </svg>
            Suggested Conditions ({conditions.length})
          </div>

          {conditions.map((condition) => (
            <div
              key={condition.id}
              style={{
                background: 'white',
                border: '1px solid #e5e7eb',
                borderRadius: '8px',
                padding: '12px',
                marginBottom: '8px',
                borderLeft: '3px solid #3b82f6',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                <span style={{ fontWeight: '500', color: '#111827', fontSize: '0.875rem' }}>
                  {condition.title}
                </span>
                {condition.structured_data?.condition_type && (
                  <span style={{
                    fontSize: '0.7rem',
                    padding: '2px 8px',
                    background: '#dbeafe',
                    color: '#1e40af',
                    borderRadius: '4px',
                    textTransform: 'uppercase',
                  }}>
                    {condition.structured_data.condition_type.replace(/_/g, ' ')}
                  </span>
                )}
              </div>

              <div style={{ fontSize: '0.8rem', color: '#6b7280' }}>
                {condition.content}
              </div>

              {condition.structured_data?.reason && (
                <div style={{ marginTop: '8px', fontSize: '0.75rem', color: '#6b7280', fontStyle: 'italic' }}>
                  Reason: {condition.structured_data.reason}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Other UW Notes */}
      {otherNotes.length > 0 && (
        <div className="uw-bullets-section" style={{ marginTop: '20px' }}>
          <div className="section-title">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#6b7280" strokeWidth="2">
              <line x1="8" y1="6" x2="21" y2="6" />
              <line x1="8" y1="12" x2="21" y2="12" />
              <line x1="8" y1="18" x2="21" y2="18" />
              <line x1="3" y1="6" x2="3.01" y2="6" />
              <line x1="3" y1="12" x2="3.01" y2="12" />
              <line x1="3" y1="18" x2="3.01" y2="18" />
            </svg>
            Additional Notes ({otherNotes.length})
          </div>

          {otherNotes.map((note) => (
            <div
              key={note.id}
              style={{
                background: '#f9fafb',
                padding: '12px',
                borderRadius: '8px',
                marginBottom: '8px',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
                {note.structured_data?.note_category && (
                  <span style={{
                    fontSize: '0.7rem',
                    padding: '2px 6px',
                    background: getNoteBackground(note.structured_data.note_category),
                    color: getNoteColor(note.structured_data.note_category),
                    borderRadius: '4px',
                    textTransform: 'capitalize',
                  }}>
                    {note.structured_data.note_category}
                  </span>
                )}
              </div>
              <p style={{ margin: 0, fontSize: '0.875rem', color: '#374151' }}>
                {note.content}
              </p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

// Helper functions for styling
const getRiskColor = (level) => {
  const colors = {
    low: '#10b981',
    moderate: '#3b82f6',
    elevated: '#f59e0b',
    high: '#dc2626',
  };
  return colors[level?.toLowerCase()] || '#6b7280';
};

const getRiskBackground = (level) => {
  const backgrounds = {
    low: '#f0fdf4',
    moderate: '#eff6ff',
    elevated: '#fffbeb',
    high: '#fef2f2',
  };
  return backgrounds[level?.toLowerCase()] || '#f9fafb';
};

const getRiskBadgeBackground = (level) => {
  const backgrounds = {
    low: '#dcfce7',
    moderate: '#dbeafe',
    elevated: '#fef3c7',
    high: '#fee2e2',
  };
  return backgrounds[level?.toLowerCase()] || '#f3f4f6';
};

const getNoteColor = (category) => {
  const colors = {
    observation: '#6b7280',
    concern: '#f59e0b',
    positive: '#10b981',
    action_needed: '#3b82f6',
  };
  return colors[category] || '#6b7280';
};

const getNoteBackground = (category) => {
  const backgrounds = {
    observation: '#f3f4f6',
    concern: '#fef3c7',
    positive: '#dcfce7',
    action_needed: '#dbeafe',
  };
  return backgrounds[category] || '#f3f4f6';
};

export default UnderwriterNotes;
