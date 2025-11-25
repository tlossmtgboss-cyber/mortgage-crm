import React, { useState, useEffect } from 'react';
import './Step3AIPreferences.css';

const Step3AIPreferences = ({ data, onChange, availableActions = [] }) => {
  const [formData, setFormData] = useState({
    ai_enabled: true,
    notification_preferences: {
      email_summaries: true,
      task_reminders: true,
      market_alerts: true,
      pipeline_updates: true
    },
    quick_actions: [],
    ai_communication_style: 'balanced',
    auto_prioritization: true,
    daily_briefing_time: '08:00',
    ...data
  });

  const [errors, setErrors] = useState({});

  // Default quick actions if none provided from server
  const defaultQuickActions = [
    {
      id: 'daily_priorities',
      name: 'Daily Priority Tasks',
      description: 'AI generates your top tasks for the day based on pipeline status',
      category: 'productivity'
    },
    {
      id: 'rate_lock_recommendations',
      name: 'Rate Lock Recommendations',
      description: 'Get AI-powered rate lock timing suggestions',
      category: 'rates'
    },
    {
      id: 'client_follow_up',
      name: 'Client Follow-up Suggestions',
      description: 'AI suggests which clients need attention today',
      category: 'client_management'
    },
    {
      id: 'document_review',
      name: 'Document Completeness Check',
      description: 'AI reviews loan files for missing documents',
      category: 'compliance'
    },
    {
      id: 'market_briefing',
      name: 'Market Briefing',
      description: 'Get a morning summary of market conditions',
      category: 'rates'
    },
    {
      id: 'pipeline_analysis',
      name: 'Pipeline Health Analysis',
      description: 'AI analyzes your pipeline for bottlenecks',
      category: 'pipeline'
    }
  ];

  const quickActions = availableActions.length > 0 ? availableActions : defaultQuickActions;

  const communicationStyles = [
    { value: 'concise', label: 'Concise', description: 'Brief, to-the-point responses' },
    { value: 'balanced', label: 'Balanced', description: 'Standard detail level' },
    { value: 'detailed', label: 'Detailed', description: 'Comprehensive explanations' }
  ];

  useEffect(() => {
    onChange(formData);
  }, [formData]);

  const handleChange = (field, value) => {
    setFormData(prev => ({
      ...prev,
      [field]: value
    }));
  };

  const handleNotificationChange = (notifType, enabled) => {
    setFormData(prev => ({
      ...prev,
      notification_preferences: {
        ...prev.notification_preferences,
        [notifType]: enabled
      }
    }));
  };

  const handleQuickActionToggle = (actionId) => {
    setFormData(prev => {
      const currentActions = prev.quick_actions || [];
      const isEnabled = currentActions.includes(actionId);

      return {
        ...prev,
        quick_actions: isEnabled
          ? currentActions.filter(id => id !== actionId)
          : [...currentActions, actionId]
      };
    });
  };

  const isActionEnabled = (actionId) => {
    return (formData.quick_actions || []).includes(actionId);
  };

  return (
    <div className="step3-ai-preferences">
      <h2>AI Assistant Preferences</h2>
      <p className="step-description">
        Customize how the AI assistant helps you manage your workflow and client relationships.
      </p>

      {/* AI Enable Toggle */}
      <div className="form-section">
        <div className="toggle-section">
          <div className="toggle-info">
            <h3>Enable AI Assistant</h3>
            <p>Allow the AI to help prioritize tasks, suggest actions, and provide insights</p>
          </div>
          <label className="toggle-switch">
            <input
              type="checkbox"
              checked={formData.ai_enabled}
              onChange={(e) => handleChange('ai_enabled', e.target.checked)}
            />
            <span className="toggle-slider"></span>
          </label>
        </div>
      </div>

      {formData.ai_enabled && (
        <>
          {/* Communication Style */}
          <div className="form-section">
            <h3>Communication Style</h3>
            <p className="section-description">How would you like the AI to communicate with you?</p>
            <div className="style-options">
              {communicationStyles.map(style => (
                <label
                  key={style.value}
                  className={`style-option ${formData.ai_communication_style === style.value ? 'selected' : ''}`}
                >
                  <input
                    type="radio"
                    name="communication_style"
                    value={style.value}
                    checked={formData.ai_communication_style === style.value}
                    onChange={(e) => handleChange('ai_communication_style', e.target.value)}
                  />
                  <div className="style-content">
                    <span className="style-label">{style.label}</span>
                    <span className="style-description">{style.description}</span>
                  </div>
                </label>
              ))}
            </div>
          </div>

          {/* Quick Actions */}
          <div className="form-section">
            <h3>Quick Actions</h3>
            <p className="section-description">
              Select the AI-powered quick actions you want available from your dashboard
            </p>
            <div className="quick-actions-grid">
              {quickActions.map(action => (
                <div
                  key={action.id}
                  className={`quick-action-card ${isActionEnabled(action.id) ? 'enabled' : ''}`}
                  onClick={() => handleQuickActionToggle(action.id)}
                >
                  <div className="action-header">
                    <span className="action-name">{action.name}</span>
                    <div className={`action-toggle ${isActionEnabled(action.id) ? 'on' : ''}`}>
                      {isActionEnabled(action.id) ? 'ON' : 'OFF'}
                    </div>
                  </div>
                  <p className="action-description">{action.description}</p>
                  <span className="action-category">{action.category.replace('_', ' ')}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Notification Preferences */}
          <div className="form-section">
            <h3>Notification Preferences</h3>
            <p className="section-description">Choose what AI-generated notifications you want to receive</p>
            <div className="notification-options">
              <label className="notification-option">
                <input
                  type="checkbox"
                  checked={formData.notification_preferences.email_summaries}
                  onChange={(e) => handleNotificationChange('email_summaries', e.target.checked)}
                />
                <div className="notification-content">
                  <span className="notification-label">Daily Email Summaries</span>
                  <span className="notification-description">Receive a daily email with task priorities and insights</span>
                </div>
              </label>

              <label className="notification-option">
                <input
                  type="checkbox"
                  checked={formData.notification_preferences.task_reminders}
                  onChange={(e) => handleNotificationChange('task_reminders', e.target.checked)}
                />
                <div className="notification-content">
                  <span className="notification-label">Task Reminders</span>
                  <span className="notification-description">Get reminded about upcoming deadlines and tasks</span>
                </div>
              </label>

              <label className="notification-option">
                <input
                  type="checkbox"
                  checked={formData.notification_preferences.market_alerts}
                  onChange={(e) => handleNotificationChange('market_alerts', e.target.checked)}
                />
                <div className="notification-content">
                  <span className="notification-label">Market Alerts</span>
                  <span className="notification-description">Be notified of significant rate movements</span>
                </div>
              </label>

              <label className="notification-option">
                <input
                  type="checkbox"
                  checked={formData.notification_preferences.pipeline_updates}
                  onChange={(e) => handleNotificationChange('pipeline_updates', e.target.checked)}
                />
                <div className="notification-content">
                  <span className="notification-label">Pipeline Updates</span>
                  <span className="notification-description">Get alerts when loans change status or need attention</span>
                </div>
              </label>
            </div>
          </div>

          {/* Auto Prioritization & Briefing Time */}
          <div className="form-section">
            <div className="toggle-section">
              <div className="toggle-info">
                <h3>Auto-Prioritization</h3>
                <p>Let AI automatically prioritize your tasks based on urgency and importance</p>
              </div>
              <label className="toggle-switch">
                <input
                  type="checkbox"
                  checked={formData.auto_prioritization}
                  onChange={(e) => handleChange('auto_prioritization', e.target.checked)}
                />
                <span className="toggle-slider"></span>
              </label>
            </div>

            <div className="form-group briefing-time">
              <label htmlFor="daily_briefing_time">Daily Briefing Time</label>
              <input
                id="daily_briefing_time"
                type="time"
                value={formData.daily_briefing_time}
                onChange={(e) => handleChange('daily_briefing_time', e.target.value)}
              />
              <span className="field-hint">When should we send your morning briefing?</span>
            </div>
          </div>
        </>
      )}
    </div>
  );
};

export default Step3AIPreferences;
