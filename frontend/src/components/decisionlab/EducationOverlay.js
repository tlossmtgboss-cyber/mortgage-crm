import React, { useState, useEffect } from 'react';
import './EducationOverlay.css';

function EducationOverlay({ overlay, onClose }) {
  const [isVisible, setIsVisible] = useState(false);
  const [showExample, setShowExample] = useState(false);

  useEffect(() => {
    // Animate in
    setTimeout(() => setIsVisible(true), 50);
  }, []);

  const handleClose = () => {
    setIsVisible(false);
    setTimeout(onClose, 300);
  };

  // Parse content sections if available
  const sections = overlay.content_sections || [];
  const hasExample = overlay.example || sections.some(s => s.type === 'example');
  const hasTip = overlay.tip || sections.some(s => s.type === 'tip');
  const hasFormula = overlay.formula || sections.some(s => s.type === 'formula');

  return (
    <div className={`education-overlay-backdrop ${isVisible ? 'visible' : ''}`}>
      <div className={`education-overlay ${isVisible ? 'visible' : ''}`}>
        {/* Header */}
        <div className="overlay-header">
          <div className="overlay-badge">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
            </svg>
            <span>Learn</span>
          </div>
          <button className="close-button" onClick={handleClose}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Content */}
        <div className="overlay-content">
          <h2 className="overlay-title">{overlay.title}</h2>

          {/* Main Content */}
          <div className="overlay-body">
            {overlay.content && (
              <p className="overlay-text">{overlay.content}</p>
            )}

            {/* Rendered sections */}
            {sections.map((section, index) => (
              <div key={index} className={`content-section ${section.type}`}>
                {section.type === 'text' && (
                  <p>{section.content}</p>
                )}
                {section.type === 'heading' && (
                  <h3>{section.content}</h3>
                )}
                {section.type === 'list' && (
                  <ul>
                    {section.items?.map((item, i) => (
                      <li key={i}>{item}</li>
                    ))}
                  </ul>
                )}
              </div>
            ))}
          </div>

          {/* Formula (if applicable) */}
          {hasFormula && (
            <div className="overlay-formula">
              <div className="formula-label">Formula</div>
              <div className="formula-content">
                {overlay.formula || sections.find(s => s.type === 'formula')?.content}
              </div>
            </div>
          )}

          {/* Example */}
          {hasExample && (
            <div className="overlay-example">
              <button
                className="example-toggle"
                onClick={() => setShowExample(!showExample)}
              >
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
                </svg>
                {showExample ? 'Hide Example' : 'See an Example'}
                <svg className={`chevron ${showExample ? 'open' : ''}`} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M19 9l-7 7-7-7" />
                </svg>
              </button>
              {showExample && (
                <div className="example-content">
                  {overlay.example || sections.find(s => s.type === 'example')?.content}
                </div>
              )}
            </div>
          )}

          {/* Tip */}
          {hasTip && (
            <div className="overlay-tip">
              <div className="tip-icon">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
              </div>
              <div className="tip-content">
                <strong>Pro Tip:</strong> {overlay.tip || sections.find(s => s.type === 'tip')?.content}
              </div>
            </div>
          )}

          {/* Key Takeaway */}
          {overlay.key_takeaway && (
            <div className="overlay-takeaway">
              <div className="takeaway-header">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M5 3v4M3 5h4M6 17v4m-2-2h4m5-16l2.286 6.857L21 12l-5.714 2.143L13 21l-2.286-6.857L5 12l5.714-2.143L13 3z" />
                </svg>
                <span>Key Takeaway</span>
              </div>
              <p>{overlay.key_takeaway}</p>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="overlay-footer">
          <button className="got-it-button" onClick={handleClose}>
            Got it, continue
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M13 7l5 5m0 0l-5 5m5-5H6" />
            </svg>
          </button>
        </div>
      </div>
    </div>
  );
}

export default EducationOverlay;
