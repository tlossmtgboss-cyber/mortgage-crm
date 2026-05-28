import React from 'react';

function FeedbackModal({
  feedbackModal,
  feedbackType,
  setFeedbackType,
  feedbackText,
  setFeedbackText,
  feedbackSubmitting,
  onSubmit,
  onClose
}) {
  if (!feedbackModal.visible) return null;

  return (
    <div className="ai-feedback-modal-overlay" onClick={onClose}>
      <div className="ai-feedback-modal" onClick={e => e.stopPropagation()}>
        <div className="ai-feedback-modal-header">
          <h3>Report Issue with AI Response</h3>
          <button className="ai-feedback-modal-close" onClick={onClose}>x</button>
        </div>
        <div className="ai-feedback-modal-body">
          <div className="ai-feedback-context">
            <div className="ai-feedback-question">
              <strong>Your question:</strong>
              <p>{feedbackModal.userQuestion}</p>
            </div>
            <div className="ai-feedback-response">
              <strong>AI response:</strong>
              <p>{feedbackModal.aiResponse?.substring(0, 200)}{feedbackModal.aiResponse?.length > 200 ? '...' : ''}</p>
            </div>
          </div>

          <div className="ai-feedback-type-selector">
            <label>What was wrong with this response?</label>
            <div className="ai-feedback-type-options">
              <button
                className={`ai-feedback-type-btn ${feedbackType === 'wrong_answer' ? 'active' : ''}`}
                onClick={() => setFeedbackType('wrong_answer')}
              >
                Wrong Answer
              </button>
              <button
                className={`ai-feedback-type-btn ${feedbackType === 'incomplete' ? 'active' : ''}`}
                onClick={() => setFeedbackType('incomplete')}
              >
                Incomplete
              </button>
              <button
                className={`ai-feedback-type-btn ${feedbackType === 'outdated' ? 'active' : ''}`}
                onClick={() => setFeedbackType('outdated')}
              >
                Outdated Info
              </button>
              <button
                className={`ai-feedback-type-btn ${feedbackType === 'irrelevant' ? 'active' : ''}`}
                onClick={() => setFeedbackType('irrelevant')}
              >
                Irrelevant
              </button>
              <button
                className={`ai-feedback-type-btn ${feedbackType === 'other' ? 'active' : ''}`}
                onClick={() => setFeedbackType('other')}
              >
                Other
              </button>
            </div>
          </div>

          <div className="ai-feedback-text-input">
            <label>Additional details (optional):</label>
            <textarea
              value={feedbackText}
              onChange={e => setFeedbackText(e.target.value)}
              placeholder="What answer were you expecting? Any additional context..."
              rows={3}
            />
          </div>
        </div>
        <div className="ai-feedback-modal-footer">
          <button className="ai-feedback-cancel-btn" onClick={onClose}>Cancel</button>
          <button
            className="ai-feedback-submit-btn"
            onClick={onSubmit}
            disabled={!feedbackType || feedbackSubmitting}
          >
            {feedbackSubmitting ? 'Submitting...' : 'Submit Feedback'}
          </button>
        </div>
      </div>
    </div>
  );
}

export default FeedbackModal;
