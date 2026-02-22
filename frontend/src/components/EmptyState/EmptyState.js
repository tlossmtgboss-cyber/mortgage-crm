import React from 'react';
import './EmptyState.css';

/**
 * EmptyState - Reusable empty state component
 * Displays helpful messages and actions when lists/pages are empty
 */
const EmptyState = ({
  icon,
  title,
  description,
  primaryAction,
  secondaryAction,
  size = 'medium' // small, medium, large
}) => {
  return (
    <div className={`empty-state empty-state--${size}`}>
      {icon && <div className="empty-state-icon">{icon}</div>}
      <h2 className="empty-state-title">{title}</h2>
      <p className="empty-state-description">{description}</p>

      {(primaryAction || secondaryAction) && (
        <div className="empty-state-actions">
          {primaryAction && (
            <button
              className="empty-state-primary-btn"
              onClick={primaryAction.onClick}
            >
              {primaryAction.icon && <span className="btn-icon">{primaryAction.icon}</span>}
              {primaryAction.text}
            </button>
          )}

          {secondaryAction && (
            <button
              className="empty-state-secondary-btn"
              onClick={secondaryAction.onClick}
            >
              {secondaryAction.icon && <span className="btn-icon">{secondaryAction.icon}</span>}
              {secondaryAction.text}
            </button>
          )}
        </div>
      )}
    </div>
  );
};

/**
 * Pre-configured empty states for common use cases
 */

// Clips empty state
export const ClipsEmptyState = ({ onCreateClip, onWatchDemo }) => (
  <EmptyState
    icon="🎬"
    title="No clips yet"
    description="Record your first video clip to share with borrowers. Perfect for explaining rates, walking through documents, or congratulating on approval."
    primaryAction={{
      text: "Record Your First Clip",
      icon: "📹",
      onClick: onCreateClip
    }}
    secondaryAction={onWatchDemo && {
      text: "Watch Demo",
      icon: "▶️",
      onClick: onWatchDemo
    }}
  />
);

// Meetings empty state
export const MeetingsEmptyState = ({ onMakeCall, onLearnMore }) => (
  <EmptyState
    icon="📞"
    title="No recorded calls yet"
    description="All your Telnyx calls are automatically recorded and transcribed. Make your first call to see AI-powered insights and coaching."
    primaryAction={{
      text: "Make Your First Call",
      icon: "☎️",
      onClick: onMakeCall
    }}
    secondaryAction={onLearnMore && {
      text: "Learn How It Works",
      icon: "📚",
      onClick: onLearnMore
    }}
  />
);

// Tasks empty state
export const TasksEmptyState = ({ onCreateTask }) => (
  <EmptyState
    icon="✅"
    title="No tasks"
    description="You're all caught up! Create a new task or they'll be automatically generated from your call action items."
    primaryAction={onCreateTask && {
      text: "Create Task",
      icon: "➕",
      onClick: onCreateTask
    }}
  />
);

// Leads empty state
export const LeadsEmptyState = ({ onAddLead, onImport }) => (
  <EmptyState
    icon="👥"
    title="No leads yet"
    description="Start building your pipeline by adding leads or importing from your existing system."
    primaryAction={{
      text: "Add Lead",
      icon: "➕",
      onClick: onAddLead
    }}
    secondaryAction={onImport && {
      text: "Import Leads",
      icon: "📤",
      onClick: onImport
    }}
  />
);

// Loans empty state
export const LoansEmptyState = ({ onCreateLoan }) => (
  <EmptyState
    icon="🏠"
    title="No loans in pipeline"
    description="Create your first loan application or convert a lead to start tracking in your pipeline."
    primaryAction={onCreateLoan && {
      text: "Create Loan",
      icon: "➕",
      onClick: onCreateLoan
    }}
  />
);

// Analytics empty state
export const AnalyticsEmptyState = ({ onMakeCall }) => (
  <EmptyState
    icon="📊"
    title="No analytics data yet"
    description="Analytics will populate after you make calls and record clips. Start having conversations to see your performance metrics."
    primaryAction={onMakeCall && {
      text: "Make Your First Call",
      icon: "📞",
      onClick: onMakeCall
    }}
  />
);

// Search results empty state
export const SearchEmptyState = ({ searchTerm, onClear }) => (
  <EmptyState
    icon="🔍"
    title="No results found"
    description={`We couldn't find anything matching "${searchTerm}". Try adjusting your search or filters.`}
    primaryAction={onClear && {
      text: "Clear Search",
      icon: "✕",
      onClick: onClear
    }}
    size="small"
  />
);

// Generic error state
export const ErrorState = ({ message, onRetry }) => (
  <EmptyState
    icon="⚠️"
    title="Something went wrong"
    description={message || "We encountered an error loading this content. Please try again."}
    primaryAction={onRetry && {
      text: "Try Again",
      icon: "🔄",
      onClick: onRetry
    }}
  />
);

export default EmptyState;
