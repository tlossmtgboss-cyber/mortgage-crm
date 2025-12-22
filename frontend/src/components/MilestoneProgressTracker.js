/**
 * MilestoneProgressTracker Component
 *
 * Visual horizontal progress tracker showing loan milestones.
 * Used in Partner Client Detail page to show current stage in the loan process.
 */

import React from 'react';
import './MilestoneProgressTracker.css';

// Define the stages in order
const STAGES = [
  { key: 'new', label: 'New Lead', shortLabel: 'New' },
  { key: 'attempted_contact', label: 'Attempted Contact', shortLabel: 'Contact' },
  { key: 'prospect', label: 'Prospect', shortLabel: 'Prospect' },
  { key: 'application', label: 'Application', shortLabel: 'App' },
  { key: 'pre_qualified', label: 'Pre-Qualified', shortLabel: 'Pre-Q' },
  { key: 'pre_approved', label: 'Pre-Approved', shortLabel: 'Pre-Appr' },
  { key: 'under_contract', label: 'Under Contract', shortLabel: 'Contract' },
  { key: 'processing', label: 'Processing', shortLabel: 'Process' },
  { key: 'clear_to_close', label: 'Clear to Close', shortLabel: 'CTC' },
  { key: 'funded', label: 'Funded', shortLabel: 'Funded' },
];

// Map various status strings to our stage keys
const STATUS_MAP = {
  // Lead stages
  'new': 'new',
  'New': 'new',
  'new_lead': 'new',
  'lead': 'new',
  'Lead': 'new',

  'attempted_contact': 'attempted_contact',
  'Attempted Contact': 'attempted_contact',
  'contacted': 'attempted_contact',

  'prospect': 'prospect',
  'Prospect': 'prospect',

  'application': 'application',
  'Application': 'application',
  'app_submitted': 'application',

  'pre_qualified': 'pre_qualified',
  'Pre-Qualified': 'pre_qualified',
  'prequalified': 'pre_qualified',
  'docs_requested': 'pre_qualified',

  'pre_approved': 'pre_approved',
  'Pre-Approved': 'pre_approved',
  'preapproved': 'pre_approved',
  'conditional_approval': 'pre_approved',

  'under_contract': 'under_contract',
  'Under Contract': 'under_contract',
  'contract': 'under_contract',

  'processing': 'processing',
  'Processing': 'processing',
  'submitted': 'processing',
  'underwriting': 'processing',

  'clear_to_close': 'clear_to_close',
  'Clear to Close': 'clear_to_close',
  'ctc': 'clear_to_close',
  'docs_out': 'clear_to_close',
  'docs_back': 'clear_to_close',

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
