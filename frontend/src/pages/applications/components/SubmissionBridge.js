import React, { useState, useEffect } from 'react';
import './SubmissionBridge.css';

const NEXT_STEPS = [
  {
    icon: '📋',
    title: 'Application Review',
    description: 'Your loan officer will review your application within 1 business day.',
  },
  {
    icon: '📄',
    title: 'Document Upload',
    description: 'Upload supporting documents through your secure portal.',
  },
  {
    icon: '📞',
    title: 'Consultation',
    description: 'Your loan officer will call to discuss your options and next steps.',
  },
];

const SubmissionBridge = ({ loName, portalUrl, companyName }) => {
  const [showSteps, setShowSteps] = useState(false);

  useEffect(() => {
    const timer = setTimeout(() => setShowSteps(true), 800);
    return () => clearTimeout(timer);
  }, []);

  return (
    <div className="submission-bridge">
      <div className="submission-bridge-content">
        <div className="submission-success-icon">
          <svg width="64" height="64" viewBox="0 0 64 64" fill="none">
            <circle cx="32" cy="32" r="30" stroke="#38a169" strokeWidth="3" fill="rgba(56, 161, 105, 0.08)" />
            <path
              d="M20 33L28 41L44 25"
              stroke="#38a169"
              strokeWidth="3.5"
              strokeLinecap="round"
              strokeLinejoin="round"
              className="checkmark-path"
            />
          </svg>
        </div>

        <h1 className="submission-bridge-title">Application Submitted</h1>
        <p className="submission-bridge-subtitle">
          Your mortgage application has been submitted successfully
          {loName && ` to ${loName}`}.
        </p>

        {showSteps && (
          <div className="submission-next-steps">
            <h2 className="next-steps-title">What happens next</h2>
            <div className="next-steps-list">
              {NEXT_STEPS.map((step, index) => (
                <div key={index} className="next-step-item" style={{ animationDelay: `${index * 150}ms` }}>
                  <span className="next-step-icon">{step.icon}</span>
                  <div className="next-step-content">
                    <strong>{step.title}</strong>
                    <p>{step.description}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {portalUrl && showSteps && (
          <div className="submission-portal-cta">
            <a href={portalUrl} className="bt-btn-primary portal-link">
              View Your Borrower Portal
            </a>
            <p className="portal-link-note">
              Track your loan progress, upload documents, and message your team.
            </p>
          </div>
        )}

        <p className="submission-email-notice">
          A confirmation email has been sent with your portal access link.
        </p>
      </div>
    </div>
  );
};

export default SubmissionBridge;
