/**
 * MilestoneProgressTracker Component
 *
 * Visual horizontal progress tracker showing loan milestones.
 * Used in Partner Client Detail page to show current stage in the loan process.
 */

import React from 'react';
import './MilestoneProgressTracker.css';

// Define the key stages in order (simplified for clarity)
const STAGES = [
  { key: 'new', label: 'New Lead', shortLabel: 'Lead' },
  { key: 'application', label: 'Application', shortLabel: 'Application' },
  { key: 'pre_approved', label: 'Pre-Approved', shortLabel: 'Pre-Approved' },
  { key: 'under_contract', label: 'Under Contract', shortLabel: 'Contract' },
  { key: 'processing', label: 'Processing', shortLabel: 'Processing' },
  { key: 'clear_to_close', label: 'Clear to Close', shortLabel: 'CTC' },
  { key: 'funded', label: 'Funded', shortLabel: 'Funded' },
];

// Map various status strings to our stage keys
const STATUS_MAP = {
  // Lead stages - all map to 'new'
  'new': 'new',
  'New': 'new',
  'new_lead': 'new',
  'lead': 'new',
  'Lead': 'new',
  'attempted_contact': 'new',
  'Attempted Contact': 'new',
  'contacted': 'new',
  'prospect': 'new',
  'Prospect': 'new',

  // Application stage
  'application': 'application',
  'Application': 'application',
  'app_submitted': 'application',
  'pre_qualified': 'application',
  'Pre-Qualified': 'application',
  'prequalified': 'application',
  'docs_requested': 'application',

  // Pre-Approved stage
  'pre_approved': 'pre_approved',
  'Pre-Approved': 'pre_approved',
  'preapproved': 'pre_approved',
  'conditional_approval': 'pre_approved',

  // Under Contract
  'under_contract': 'under_contract',
  'Under Contract': 'under_contract',
  'contract': 'under_contract',

  // Processing
  'processing': 'processing',
  'Processing': 'processing',
  'submitted': 'processing',
  'underwriting': 'processing',

  // Clear to Close
  'clear_to_close': 'clear_to_close',
  'Clear to Close': 'clear_to_close',
  'ctc': 'clear_to_close',
  'docs_out': 'clear_to_close',
  'docs_back': 'clear_to_close',

  // Funded
  'funded': 'funded',
  'Funded': 'funded',
  'closed': 'funded',
  'Completed': 'funded',
};

const MilestoneProgressTracker = ({ currentStatus, completedMilestones = [] }) => {
  // Normalize the current status
  const normalizedStatus = STATUS_MAP[currentStatus] || 'new';
  const currentIndex = STAGES.findIndex(s => s.key === normalizedStatus);

  // Determine which stages are completed
  const getStageStatus = (stageKey, index) => {
    // If this stage is in completedMilestones, it's complete
    if (completedMilestones.includes(stageKey)) {
      return 'completed';
    }

    // If before current index, it's completed
    if (index < currentIndex) {
      return 'completed';
    }

    // If at current index, it's current
    if (index === currentIndex) {
      return 'current';
    }

    // Otherwise, it's upcoming
    return 'upcoming';
  };

  return (
    <div className="milestone-progress-tracker">
      <div className="progress-bar-container">
        {/* Progress fill */}
        <div
          className="progress-bar-fill"
          style={{
            width: `${Math.max(0, (currentIndex / (STAGES.length - 1)) * 100)}%`
          }}
        />

        {/* Stage indicators */}
        <div className="progress-stages">
          {STAGES.map((stage, index) => {
            const status = getStageStatus(stage.key, index);

            return (
              <div
                key={stage.key}
                className={`progress-stage ${status}`}
                title={stage.label}
              >
                <div className="stage-indicator">
                  {status === 'completed' ? (
                    <svg viewBox="0 0 24 24" fill="currentColor" className="check-icon">
                      <path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41L9 16.17z"/>
                    </svg>
                  ) : status === 'current' ? (
                    <div className="current-dot" />
                  ) : (
                    <div className="empty-dot" />
                  )}
                </div>
                <span className="stage-label">{stage.shortLabel}</span>
              </div>
            );
          })}
        </div>
      </div>

      {/* Current stage highlight */}
      <div className="current-stage-info">
        <span className="current-label">Current Stage:</span>
        <span className="current-value">
          {STAGES[currentIndex]?.label || currentStatus}
        </span>
      </div>
    </div>
  );
};

export default MilestoneProgressTracker;
