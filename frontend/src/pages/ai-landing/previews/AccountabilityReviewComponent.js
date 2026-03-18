import React from 'react';

function AccountabilityReviewComponent({ content, reviewData }) {
  const sections = content.split('\n\n').filter(s => s.trim());

  return (
    <div className="ai-message-content-new ai-special-content">
      <div className="ai-action-preview accountability-review">
        <h3>Accountability Review</h3>

        <div className="ai-review-content">
          {sections.map((section, index) => {
            if (section.includes(':') && !section.includes('\u2022')) {
              const [header, ...rest] = section.split(':');
              return (
                <div key={index} className="ai-review-section">
                  <h4>{header.trim()}</h4>
                  <p>{rest.join(':').trim()}</p>
                </div>
              );
            }

            if (section.includes('\u2022') || section.includes('-')) {
              const lines = section.split('\n');
              return (
                <div key={index} className="ai-review-section">
                  <ul>
                    {lines.map((line, i) => {
                      const cleanLine = line.replace(/^[\u2022\-]\s*/, '').trim();
                      if (cleanLine) {
                        return <li key={i}>{cleanLine}</li>;
                      }
                      return null;
                    })}
                  </ul>
                </div>
              );
            }

            return (
              <div key={index} className="ai-review-section">
                <p>{section}</p>
              </div>
            );
          })}
        </div>

        <div className="ai-review-actions">
          <div className="ai-note">
            <strong>Tip:</strong> Focus on moving leads from NEW stage to later stages, and completing pending tasks to improve your metrics.
          </div>
        </div>
      </div>
    </div>
  );
}

export default AccountabilityReviewComponent;
