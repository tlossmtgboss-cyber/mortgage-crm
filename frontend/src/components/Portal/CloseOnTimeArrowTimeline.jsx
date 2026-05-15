/**
 * CloseOnTimeArrowTimeline Component
 *
 * Arrow-style timeline visualization for Close On Time milestones (S3-S5 stages).
 * Features:
 * - Horizontal arrow visualization
 * - Partner view filtering (hides sensitive milestones)
 * - Expandable milestone cards
 * - Progress tracking & urgency levels
 * - Business day countdown
 */

import React, { useState, useMemo } from 'react';
import { useCloseCountdown } from '../../hooks/usePortalData';
import './CloseOnTimeArrowTimeline.css';

// Milestone configuration for the 9-step Close On Time process
const MILESTONE_CONFIG = [
  { id: 'application_date', name: 'Application Date', businessDaysBefore: 25, icon: '📋', partnerVisible: true },
  { id: 'insurance_quote', name: 'Insurance Quote', businessDaysBefore: 20, icon: '🛡️', partnerVisible: true },
  { id: 'appraisal_ordered', name: 'Appraisal Ordered', businessDaysBefore: 18, icon: '🏠', partnerVisible: true },
  { id: 'title_ordered', name: 'Title Ordered', businessDaysBefore: 17, icon: '📜', partnerVisible: false },
  { id: 'appraisal_received', name: 'Appraisal Received', businessDaysBefore: 12, icon: '✅', partnerVisible: false },
  { id: 'title_received', name: 'Title Received', businessDaysBefore: 10, icon: '📄', partnerVisible: false },
  { id: 'hoi_due', name: 'Home Owners Insurance Due', businessDaysBefore: 7, icon: '🏡', partnerVisible: true },
  { id: 'pre_closing_review', name: 'Pre-Closing Review Call', businessDaysBefore: 3, icon: '📞', partnerVisible: true },
  { id: 'closing_date', name: 'Closing Date', businessDaysBefore: 0, icon: '🎉', partnerVisible: true },
];

// Arrow gradient colors for each step
const ARROW_GRADIENTS = [
  'linear-gradient(135deg, #06b6d4 0%, #0891b2 100%)',   // Cyan
  'linear-gradient(135deg, #3b82f6 0%, #2563eb 100%)',   // Blue
  'linear-gradient(135deg, #B8924A 0%, #8A6D30 100%)',   // Indigo
  'linear-gradient(135deg, #B8924A 0%, #B8924A 100%)',   // Violet
  'linear-gradient(135deg, #C9A44E 0%, #B8924A 100%)',   // Purple
  'linear-gradient(135deg, #d946ef 0%, #c026d3 100%)',   // Fuchsia
  'linear-gradient(135deg, #ec4899 0%, #db2777 100%)',   // Pink
  'linear-gradient(135deg, #f97316 0%, #ea580c 100%)',   // Orange
  'linear-gradient(135deg, #2D7A52 0%, #2D7A52 100%)',   // Emerald
];

const URGENCY_STYLES = {
  normal: { border: '#2D7A52', bg: '#d1fae5', text: '#065f46', label: 'On Track' },
  attention: { border: '#f59e0b', bg: '#fef3c7', text: '#92400e', label: 'Attention' },
  warning: { border: '#f97316', bg: '#ffedd5', text: '#9a3412', label: 'Warning' },
  critical: { border: '#ef4444', bg: '#fee2e2', text: '#991b1b', label: 'Critical' },
  overdue: { border: '#dc2626', bg: '#fecaca', text: '#7f1d1d', label: 'Overdue' },
};

export default function CloseOnTimeArrowTimeline({
  loanId,
  milestones = [],
  targetCloseDate,
  businessDaysRemaining,
  isPartnerView = false,
  onMilestoneClick,
  compact = false,
}) {
  const [expandedMilestone, setExpandedMilestone] = useState(null);
  const { data: countdownData } = useCloseCountdown(loanId);

  // Filter milestones for partner view
  const visibleMilestones = useMemo(() => {
    const config = MILESTONE_CONFIG;
    if (isPartnerView) {
      return config.filter(m => m.partnerVisible);
    }
    return config;
  }, [isPartnerView]);

  // Map milestone data with config
  const processedMilestones = useMemo(() => {
    return visibleMilestones.map((config, index) => {
      const milestoneData = milestones.find(
        m => m.id === config.id || m.name?.toLowerCase().includes(config.name.toLowerCase())
      );

      return {
        ...config,
        index,
        status: milestoneData?.status || 'pending',
        completedAt: milestoneData?.completed_at,
        dueDate: milestoneData?.due_date,
        isOverdue: milestoneData?.is_overdue || false,
        gradient: ARROW_GRADIENTS[index % ARROW_GRADIENTS.length],
      };
    });
  }, [visibleMilestones, milestones]);

  // Calculate progress
  const completedCount = processedMilestones.filter(m => m.status === 'completed').length;
  const progressPercent = Math.round((completedCount / processedMilestones.length) * 100);

  // Get urgency styling
  const urgency = countdownData?.urgency || 'normal';
  const urgencyStyle = URGENCY_STYLES[urgency] || URGENCY_STYLES.normal;

  const handleMilestoneClick = (milestone) => {
    if (compact) return;
    setExpandedMilestone(expandedMilestone === milestone.id ? null : milestone.id);
    if (onMilestoneClick) {
      onMilestoneClick(milestone);
    }
  };

  return (
    <div className={`arrow-timeline ${compact ? 'compact' : ''} ${isPartnerView ? 'partner-view' : ''}`}>
      {/* Header with countdown */}
      <div className="arrow-timeline-header">
        <div className="timeline-title">
          <h3>Close On Time Tracker</h3>
          {isPartnerView && (
            <span className="partner-badge">Partner View</span>
          )}
        </div>

        <div className="countdown-display" style={{ borderColor: urgencyStyle.border }}>
          <div className="countdown-number" style={{ color: urgencyStyle.border }}>
            {businessDaysRemaining ?? countdownData?.business_days_remaining ?? '--'}
          </div>
          <div className="countdown-label">
            <span>Business Days</span>
            <span
              className="urgency-badge"
              style={{ backgroundColor: urgencyStyle.bg, color: urgencyStyle.text }}
            >
              {urgencyStyle.label}
            </span>
          </div>
        </div>
      </div>

      {/* Progress bar */}
      <div className="progress-section">
        <div className="progress-bar">
          <div
            className="progress-fill"
            style={{
              width: `${progressPercent}%`,
              background: `linear-gradient(90deg, #2D7A52 0%, ${urgencyStyle.border} 100%)`
            }}
          />
        </div>
        <span className="progress-text">{completedCount} of {processedMilestones.length} Complete</span>
      </div>

      {/* Arrow Timeline */}
      <div className="arrows-container">
        {processedMilestones.map((milestone, index) => (
          <div
            key={milestone.id}
            className={`arrow-step ${milestone.status} ${expandedMilestone === milestone.id ? 'expanded' : ''}`}
            onClick={() => handleMilestoneClick(milestone)}
          >
            {/* Arrow shape */}
            <div
              className="arrow-body"
              style={{
                background: milestone.status === 'completed'
                  ? milestone.gradient
                  : 'linear-gradient(135deg, #e5e7eb 0%, #d1d5db 100%)'
              }}
            >
              {/* Milestone icon */}
              <div className="milestone-icon">
                {milestone.status === 'completed' ? '✓' : milestone.icon}
              </div>

              {/* Milestone name */}
              <div className="milestone-name">
                {milestone.name}
              </div>

              {/* Days before close */}
              {!compact && milestone.businessDaysBefore > 0 && (
                <div className="days-before">
                  {milestone.businessDaysBefore}d before
                </div>
              )}

              {/* Status indicator */}
              <div className={`status-dot ${milestone.status} ${milestone.isOverdue ? 'overdue' : ''}`} />
            </div>

            {/* Arrow point */}
            <div
              className="arrow-point"
              style={{
                borderLeftColor: milestone.status === 'completed'
                  ? ARROW_GRADIENTS[index % ARROW_GRADIENTS.length].split(' ')[2]?.replace(',', '') || '#2D7A52'
                  : '#d1d5db'
              }}
            />

            {/* Connector line */}
            {index < processedMilestones.length - 1 && (
              <div className="connector-line" />
            )}
          </div>
        ))}
      </div>

      {/* Expanded detail card */}
      {expandedMilestone && !compact && (
        <MilestoneDetailCard
          milestone={processedMilestones.find(m => m.id === expandedMilestone)}
          onClose={() => setExpandedMilestone(null)}
        />
      )}

      {/* Target close date footer */}
      {targetCloseDate && (
        <div className="close-date-footer">
          <span className="close-icon">🎯</span>
          <span className="close-label">Target Close:</span>
          <span className="close-date">
            {new Date(targetCloseDate).toLocaleDateString('en-US', {
              weekday: 'long',
              month: 'long',
              day: 'numeric',
              year: 'numeric',
            })}
          </span>
        </div>
      )}
    </div>
  );
}

/**
 * Milestone Detail Card - Shows expanded info when clicking a milestone
 */
function MilestoneDetailCard({ milestone, onClose }) {
  if (!milestone) return null;

  return (
    <div className="milestone-detail-card">
      <div className="detail-header">
        <div className="detail-icon">{milestone.icon}</div>
        <div className="detail-title">
          <h4>{milestone.name}</h4>
          <span className={`status-badge ${milestone.status}`}>
            {milestone.status === 'completed' ? 'Completed' :
             milestone.status === 'in_progress' ? 'In Progress' : 'Pending'}
          </span>
        </div>
        <button className="close-btn" onClick={onClose}>×</button>
      </div>

      <div className="detail-body">
        <div className="detail-row">
          <span className="label">Days Before Close:</span>
          <span className="value">{milestone.businessDaysBefore}</span>
        </div>

        {milestone.dueDate && (
          <div className="detail-row">
            <span className="label">Due Date:</span>
            <span className="value">
              {new Date(milestone.dueDate).toLocaleDateString('en-US', {
                month: 'short',
                day: 'numeric',
              })}
            </span>
          </div>
        )}

        {milestone.completedAt && (
          <div className="detail-row">
            <span className="label">Completed:</span>
            <span className="value completed">
              {new Date(milestone.completedAt).toLocaleDateString('en-US', {
                month: 'short',
                day: 'numeric',
              })}
            </span>
          </div>
        )}

        {milestone.isOverdue && (
          <div className="overdue-warning">
            ⚠️ This milestone is overdue
          </div>
        )}
      </div>
    </div>
  );
}

/**
 * Compact Arrow Timeline for widgets
 */
export function CloseOnTimeArrowWidget({ loanId, milestones = [] }) {
  return (
    <CloseOnTimeArrowTimeline
      loanId={loanId}
      milestones={milestones}
      compact={true}
    />
  );
}
