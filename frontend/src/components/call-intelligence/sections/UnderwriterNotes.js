/**
 * Underwriter Notes Component (Enhanced)
 *
 * Displays UW notes, risk flags, suggested conditions, and review items checklist.
 * Features:
 * - Review items checklist with completion tracking
 * - "Complete Review" button that creates PA task
 * - Progress indicator
 */

import React, { useState, useMemo } from 'react';

const UnderwriterNotes = ({
  notes,
  riskFlags,
  conditions,
  reviewItems,
  onCompleteReview,
  onMarkItemComplete,
  sessionId,
}) => {
  // Track completed items locally
  const [completedItems, setCompletedItems] = useState(new Set());
  const [isCompleting, setIsCompleting] = useState(false);
  const [reviewSummary, setReviewSummary] = useState('');

  const hasContent = (notes && notes.length > 0) ||
                     (riskFlags && riskFlags.length > 0) ||
                     (conditions && conditions.length > 0) ||
                     (reviewItems && reviewItems.length > 0);

  // Calculate progress
  const totalItems = reviewItems?.length || 0;
  const completedCount = completedItems.size;
  const progressPct = totalItems > 0 ? Math.round((completedCount / totalItems) * 100) : 0;
  const allComplete = totalItems > 0 && completedCount === totalItems;

  // Get overall assessment from notes
  const assessment = useMemo(() =>
    notes?.find(n =>
      n.structured_data?.note_category === 'assessment' ||
      n.artifact_type === 'uw_assessment'
    ), [notes]
  );

  const otherNotes = useMemo(() =>
    notes?.filter(n =>
      n.structured_data?.note_category !== 'assessment' &&
      n.artifact_type !== 'uw_assessment'
    ) || [], [notes]
  );

  const handleToggleItem = (itemId) => {
    setCompletedItems(prev => {
      const next = new Set(prev);
      if (next.has(itemId)) {
        next.delete(itemId);
      } else {
        next.add(itemId);
      }
      return next;
    });
    // Call external handler if provided
    if (onMarkItemComplete) {
      onMarkItemComplete(itemId, !completedItems.has(itemId));
    }
  };

  const handleCompleteReview = async () => {
    if (!onCompleteReview || !sessionId) return;

    setIsCompleting(true);
    try {
      const addressedItems = reviewItems
        ?.filter(item => completedItems.has(item.id))
        .map(item => item.title || item.content) || [];

      await onCompleteReview({
        sessionId,
        summary: reviewSummary || `UW Review completed. ${completedCount}/${totalItems} items addressed.`,
        items_addressed: addressedItems,
        create_pa_task: true,
      });
    } catch (err) {
      console.error('Error completing UW review:', err);
    } finally {
      setIsCompleting(false);
    }
  };

  if (!hasContent) {
    return (
      <div className="uw-notes">
        <p style={{ color: '#6b7280', textAlign: 'center', padding: '40px' }}>
          No underwriter notes or risk flags from this call.
        </p>
      </div>
    );
  }

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

      {/* Review Items Checklist */}
      {reviewItems && reviewItems.length > 0 && (
        <div className="uw-review-checklist" style={{
          background: '#fff',
          border: '2px solid #3b82f6',
          borderRadius: '12px',
          padding: '16px',
          marginBottom: '20px',
        }}>
          <div style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            marginBottom: '16px',
          }}>
            <h4 style={{ margin: 0, display: 'flex', alignItems: 'center', gap: '8px' }}>
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#3b82f6" strokeWidth="2">
                <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
                <polyline points="22 4 12 14.01 9 11.01" />
              </svg>
              Items to Address ({completedCount}/{totalItems})
            </h4>

            {/* Progress Bar */}
            <div style={{
              width: '120px',
              height: '8px',
              background: '#e5e7eb',
              borderRadius: '4px',
              overflow: 'hidden',
            }}>
              <div style={{
                width: `${progressPct}%`,
                height: '100%',
                background: allComplete ? '#22c55e' : '#3b82f6',
                transition: 'width 0.3s ease, background 0.3s ease',
              }} />
            </div>
          </div>

          <div className="review-items-checklist">
            {reviewItems.map((item, index) => {
              const itemId = item.id || `item-${index}`;
              const isComplete = completedItems.has(itemId);
              const severity = item.structured_data?.severity || item.priority || 'medium';

              return (
                <div
                  key={itemId}
                  className={`review-checklist-item ${isComplete ? 'completed' : ''}`}
                  style={{
                    display: 'flex',
                    alignItems: 'flex-start',
                    gap: '12px',
                    padding: '12px',
                    background: isComplete ? '#f0fdf4' : '#fff',
                    border: '1px solid #e5e7eb',
                    borderRadius: '8px',
                    marginBottom: '8px',
                    opacity: isComplete ? 0.75 : 1,
                    transition: 'all 0.2s ease',
                  }}
                >
                  <input
                    type="checkbox"
                    checked={isComplete}
                    onChange={() => handleToggleItem(itemId)}
                    style={{
                      width: '20px',
                      height: '20px',
                      marginTop: '2px',
                      cursor: 'pointer',
                      accentColor: '#22c55e',
                    }}
                  />

                  <div style={{ flex: 1 }}>
                    <div style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                      marginBottom: '4px',
                    }}>
                      <span style={{
                        fontWeight: '500',
                        fontSize: '0.875rem',
                        color: isComplete ? '#6b7280' : '#111827',
                        textDecoration: isComplete ? 'line-through' : 'none',
                      }}>
                        {item.title}
                      </span>
                      <span className={`severity-badge ${severity}`} style={{
                        fontSize: '0.65rem',
                        padding: '2px 8px',
                        borderRadius: '4px',
                        background: getSeverityBackground(severity),
                        color: getSeverityColor(severity),
                        textTransform: 'uppercase',
                      }}>
                        {severity}
                      </span>
                    </div>

                    <p style={{
                      margin: 0,
                      fontSize: '0.8rem',
                      color: '#6b7280',
                      textDecoration: isComplete ? 'line-through' : 'none',
                    }}>
                      {item.content || item.structured_data?.suggested_action}
                    </p>

                    {item.structured_data?.category && (
                      <span style={{
                        display: 'inline-block',
                        marginTop: '6px',
                        fontSize: '0.7rem',
                        padding: '2px 6px',
                        background: '#f3f4f6',
                        color: '#6b7280',
                        borderRadius: '4px',
                      }}>
                        {item.structured_data.category}
                      </span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>

          {/* Complete Review Section */}
          {onCompleteReview && (
            <div style={{
              marginTop: '16px',
              paddingTop: '16px',
              borderTop: '1px solid #e5e7eb',
            }}>
              <textarea
                value={reviewSummary}
                onChange={(e) => setReviewSummary(e.target.value)}
                placeholder="Add summary notes for PA (optional)..."
                style={{
                  width: '100%',
                  minHeight: '60px',
                  padding: '10px',
                  border: '1px solid #e5e7eb',
                  borderRadius: '6px',
                  fontSize: '0.875rem',
                  marginBottom: '12px',
                  resize: 'vertical',
                }}
              />

              <button
                onClick={handleCompleteReview}
                disabled={!allComplete || isCompleting}
                style={{
                  width: '100%',
                  padding: '12px 16px',
                  background: allComplete ? '#22c55e' : '#e5e7eb',
                  color: allComplete ? '#fff' : '#9ca3af',
                  border: 'none',
                  borderRadius: '8px',
                  fontSize: '0.875rem',
                  fontWeight: '600',
                  cursor: allComplete ? 'pointer' : 'not-allowed',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: '8px',
                  transition: 'all 0.2s ease',
                }}
              >
                {isCompleting ? (
                  <>
                    <span className="spinner" style={{
                      width: '16px',
                      height: '16px',
                      border: '2px solid rgba(255,255,255,0.3)',
                      borderTopColor: '#fff',
                      borderRadius: '50%',
                      animation: 'spin 0.8s linear infinite',
                    }} />
                    Completing Review...
                  </>
                ) : (
                  <>
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
                      <polyline points="22 4 12 14.01 9 11.01" />
                    </svg>
                    Complete Review & Create PA Task
                  </>
                )}
              </button>

              {!allComplete && (
                <p style={{
                  margin: '8px 0 0',
                  fontSize: '0.75rem',
                  color: '#9ca3af',
                  textAlign: 'center',
                }}>
                  Complete all {totalItems - completedCount} remaining items to enable
                </p>
              )}
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
    low: '#2D7A52',
    moderate: '#3b82f6',
    elevated: '#f59e0b',
    high: '#dc2626',
    unacceptable: '#7f1d1d',
  };
  return colors[level?.toLowerCase()] || '#6b7280';
};

const getRiskBackground = (level) => {
  const backgrounds = {
    low: '#f0fdf4',
    moderate: '#eff6ff',
    elevated: '#fffbeb',
    high: '#fef2f2',
    unacceptable: '#fef2f2',
  };
  return backgrounds[level?.toLowerCase()] || '#f9fafb';
};

const getRiskBadgeBackground = (level) => {
  const backgrounds = {
    low: '#dcfce7',
    moderate: '#dbeafe',
    elevated: '#fef3c7',
    high: '#fee2e2',
    unacceptable: '#fee2e2',
  };
  return backgrounds[level?.toLowerCase()] || '#f3f4f6';
};

const getNoteColor = (category) => {
  const colors = {
    observation: '#6b7280',
    concern: '#f59e0b',
    positive: '#2D7A52',
    action_needed: '#3b82f6',
    mitigating_factor: '#2D7A52',
  };
  return colors[category] || '#6b7280';
};

const getNoteBackground = (category) => {
  const backgrounds = {
    observation: '#f3f4f6',
    concern: '#fef3c7',
    positive: '#dcfce7',
    action_needed: '#dbeafe',
    mitigating_factor: '#dcfce7',
  };
  return backgrounds[category] || '#f3f4f6';
};

const getSeverityColor = (severity) => {
  const colors = {
    low: '#166534',
    medium: '#92400e',
    high: '#991b1b',
    critical: '#7f1d1d',
  };
  return colors[severity?.toLowerCase()] || '#6b7280';
};

const getSeverityBackground = (severity) => {
  const backgrounds = {
    low: '#dcfce7',
    medium: '#fef3c7',
    high: '#fee2e2',
    critical: '#fee2e2',
  };
  return backgrounds[severity?.toLowerCase()] || '#f3f4f6';
};

export default UnderwriterNotes;
