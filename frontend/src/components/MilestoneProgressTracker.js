/**
 * MilestoneProgressTracker Component
 *
 * Visual horizontal progress tracker showing loan milestones.
 * Used in Partner Client Detail page to show current stage in the loan process.
 */

import React from 'react';
import './MilestoneProgressTracker.css';

// Define the key stages in order (main pipeline progression)
const STAGES = [
  { key: 'new', label: 'New', shortLabel: 'New' },
  { key: 'attempted_contact', label: 'Attempted Contact', shortLabel: 'Contact' },
  { key: 'prospect', label: 'Prospect', shortLabel: 'Prospect' },
  { key: 'application', label: 'Application', shortLabel: 'Application' },
  { key: 'pre_qualified', label: 'Pre-Qualified', shortLabel: 'Pre-Qual' },
  { key: 'pre_approved', label: 'Pre-Approved', shortLabel: 'Pre-Approved' },
];

// Exit stages (shown differently - not part of progress bar)
const EXIT_STAGES = ['nurture', 'withdrawn', 'does_not_qualify'];

// Map various status strings to our stage keys
const STATUS_MAP = {
  // New
  'new': 'new',
  'New': 'new',
  'new_lead': 'new',
  'lead': 'new',
  'Lead': 'new',

  // Attempted Contact
  'attempted_contact': 'attempted_contact',
  'Attempted Contact': 'attempted_contact',
  'contacted': 'attempted_contact',

  // Prospect
  'prospect': 'prospect',
  'Prospect': 'prospect',

  // Application
  'application': 'application',
  'Application': 'application',
  'app_submitted': 'application',
  'docs_requested': 'application',

  // Pre-Qualified
  'pre_qualified': 'pre_qualified',
  'Pre-Qualified': 'pre_qualified',
  'prequalified': 'pre_qualified',
  'pre-qualified': 'pre_qualified',
  'qualified': 'pre_qualified',

  // Pre-Approved
  'pre_approved': 'pre_approved',
  'Pre-Approved': 'pre_approved',
  'preapproved': 'pre_approved',
  'pre-approved': 'pre_approved',
  'preapproval': 'pre_approved',
  'conditional_approval': 'pre_approved',

  // Exit stages (map to themselves)
  'nurture': 'nurture',
  'Nurture': 'nurture',
  'withdrawn': 'withdrawn',
  'Withdrawn': 'withdrawn',
  'does_not_qualify': 'does_not_qualify',
  'Does Not Qualify': 'does_not_qualify',
  'dnq': 'does_not_qualify',
};

const MilestoneProgressTracker = ({ currentStatus, completedMilestones = [] }) => {
  // Normalize the current status
  const normalizedStatus = STATUS_MAP[currentStatus] || 'new';

  // Check if in an exit stage
  const isExitStage = EXIT_STAGES.includes(normalizedStatus);
  const currentIndex = isExitStage ? -1 : STAGES.findIndex(s => s.key === normalizedStatus);

  // Get display label for exit stages
  const getExitStageLabel = (status) => {
    const labels = {
      'nurture': 'Nurture',
      'withdrawn': 'Withdrawn',
      'does_not_qualify': 'Does Not Qualify'
    };
    return labels[status] || status;
  };

  // Determine which stages are completed
  const getStageStatus = (stageKey, index) => {
    // If this stage is in completedMilestones, it's complete
    if (completedMilestones.includes(stageKey)) {
      return 'completed';
    }

    // If in exit stage, show progress up to where they exited (assume last completed)
    if (isExitStage) {
      return 'upcoming';
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
    </div>
  );
};

export default MilestoneProgressTracker;
