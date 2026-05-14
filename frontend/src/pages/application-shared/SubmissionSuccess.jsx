import React from 'react';

/**
 * Submission success lightbox overlay with animated checkmark.
 * Shown after successful application submission, before redirect.
 * Shared between Purchase and Refinance applications.
 */
const SubmissionSuccess = ({ show, applicationType = 'mortgage' }) => {
  if (!show) return null;

  return (
    <div className="submission-success-overlay">
      <div className="submission-success-lightbox">
        <div className="success-checkmark">
          <svg viewBox="0 0 52 52" className="checkmark-svg">
            <circle className="checkmark-circle" cx="26" cy="26" r="25" fill="none"/>
            <path className="checkmark-check" fill="none" d="M14.1 27.2l7.1 7.2 16.7-16.8"/>
          </svg>
        </div>
        <h2>Application Submitted!</h2>
        <p>Your {applicationType} application has been successfully submitted.</p>
        <p className="redirect-message">You will be redirected to your client portal...</p>
      </div>
    </div>
  );
};

export default SubmissionSuccess;
