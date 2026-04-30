import React, { useState } from 'react';
import './Step5Confirmation.css';

const Step5Confirmation = ({ profileData, aiPreferences, trainingData, onComplete }) => {
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [agreed, setAgreed] = useState(false);

  const getCompletedModulesCount = () => {
    return (trainingData?.completed_modules || []).length;
  };

  const getEnabledActionsCount = () => {
    return (aiPreferences?.quick_actions || []).length;
  };

  const handleComplete = async () => {
    if (!agreed) {
      return;
    }

    setIsSubmitting(true);
    try {
      await onComplete();
    } catch (error) {
      console.error('Error completing onboarding:', error);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="step5-confirmation">
      <div className="confirmation-header">
        <div className="success-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="12" cy="12" r="10" />
            <polyline points="9 12 12 15 16 10" />
          </svg>
        </div>
        <h2>You're All Set!</h2>
        <p className="step-description">
          Review your setup and you're ready to start using your CRM.
        </p>
      </div>

      {/* Summary Cards */}
      <div className="summary-grid">
        {/* Profile Summary */}
        <div className="summary-card">
          <div className="card-header">
            <span className="card-icon">👤</span>
            <h3>Profile</h3>
          </div>
          <div className="card-content">
            <div className="summary-item">
              <span className="item-label">Name</span>
              <span className="item-value">
                {profileData?.first_name} {profileData?.last_name}
              </span>
            </div>
            {profileData?.department && (
              <div className="summary-item">
                <span className="item-label">Department</span>
                <span className="item-value">{profileData.department}</span>
              </div>
            )}
            {profileData?.job_title && (
              <div className="summary-item">
                <span className="item-label">Title</span>
                <span className="item-value">{profileData.job_title}</span>
              </div>
            )}
            <div className="summary-item">
              <span className="item-label">Timezone</span>
              <span className="item-value">
                {profileData?.timezone?.replace('_', ' ').split('/').pop() || 'Not set'}
              </span>
            </div>
          </div>
        </div>

        {/* AI Preferences Summary */}
        <div className="summary-card">
          <div className="card-header">
            <span className="card-icon">🤖</span>
            <h3>AI Assistant</h3>
          </div>
          <div className="card-content">
            <div className="summary-item">
              <span className="item-label">Status</span>
              <span className={`item-value ${aiPreferences?.ai_enabled ? 'enabled' : 'disabled'}`}>
                {aiPreferences?.ai_enabled ? 'Enabled' : 'Disabled'}
              </span>
            </div>
            {aiPreferences?.ai_enabled && (
              <>
                <div className="summary-item">
                  <span className="item-label">Communication Style</span>
                  <span className="item-value capitalize">
                    {aiPreferences?.ai_communication_style || 'Balanced'}
                  </span>
                </div>
                <div className="summary-item">
                  <span className="item-label">Quick Actions</span>
                  <span className="item-value">
                    {getEnabledActionsCount()} enabled
                  </span>
                </div>
                <div className="summary-item">
                  <span className="item-label">Daily Briefing</span>
                  <span className="item-value">
                    {aiPreferences?.daily_briefing_time || '08:00'}
                  </span>
                </div>
              </>
            )}
          </div>
        </div>

        {/* Training Summary */}
        <div className="summary-card">
          <div className="card-header">
            <span className="card-icon">📚</span>
            <h3>Training</h3>
          </div>
          <div className="card-content">
            <div className="summary-item">
              <span className="item-label">Modules Completed</span>
              <span className="item-value">
                {getCompletedModulesCount()} of 5
              </span>
            </div>
            <div className="summary-item">
              <span className="item-label">Mode</span>
              <span className="item-value capitalize">
                {trainingData?.training_mode === 'skip' ? 'Skipped' : 'Guided'}
              </span>
            </div>
            {getCompletedModulesCount() < 5 && (
              <p className="training-note">
                You can complete remaining modules anytime from Settings
              </p>
            )}
          </div>
        </div>

        {/* Notifications Summary */}
        <div className="summary-card">
          <div className="card-header">
            <span className="card-icon">🔔</span>
            <h3>Notifications</h3>
          </div>
          <div className="card-content">
            <div className="notification-list">
              {aiPreferences?.notification_preferences?.email_summaries && (
                <span className="notification-badge">Email Summaries</span>
              )}
              {aiPreferences?.notification_preferences?.task_reminders && (
                <span className="notification-badge">Task Reminders</span>
              )}
              {aiPreferences?.notification_preferences?.market_alerts && (
                <span className="notification-badge">Market Alerts</span>
              )}
              {aiPreferences?.notification_preferences?.pipeline_updates && (
                <span className="notification-badge">Pipeline Updates</span>
              )}
            </div>
            {!Object.values(aiPreferences?.notification_preferences || {}).some(v => v) && (
              <p className="no-notifications">No notifications enabled</p>
            )}
          </div>
        </div>
      </div>

      {/* Agreement Checkbox */}
      <div className="agreement-section">
        <label className="agreement-checkbox">
          <input
            type="checkbox"
            checked={agreed}
            onChange={(e) => setAgreed(e.target.checked)}
          />
          <span className="checkbox-text">
            I have reviewed my settings and I'm ready to start using the CRM.
            I understand I can update these preferences anytime from Settings.
          </span>
        </label>
      </div>

      {/* Complete Button */}
      <div className="completion-section">
        <button
          className="complete-button"
          onClick={handleComplete}
          disabled={!agreed || isSubmitting}
        >
          {isSubmitting ? (
            <>
              <span className="button-spinner"></span>
              Setting up your account...
            </>
          ) : (
            <>
              Complete Setup & Go to Dashboard
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M5 12h14M12 5l7 7-7 7" />
              </svg>
            </>
          )}
        </button>
      </div>

      {/* Support Info */}
      <div className="support-info">
        <p>
          Need help? Contact support at{' '}
          <a href="mailto:support@perenniaai.com">support@perenniaai.com</a>
        </p>
      </div>
    </div>
  );
};

export default Step5Confirmation;
