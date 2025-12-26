/**
 * Application Slides Editor
 *
 * Allows users to customize the mortgage application flow by:
 * - Enabling/disabling stages
 * - Enabling/disabling individual questions within stages
 * - Reordering stages and questions
 * - Previewing the application flow
 */

import React, { useState, useEffect, useCallback } from 'react';
import './ApplicationSlidesEditor.css';

// Default stages configuration - mirrors PurchaseApplication.js
const DEFAULT_STAGES = [
  { id: 'account', label: 'Get Started', icon: 'user', description: 'Create your account', hideFromProgress: true, required: true },
  { id: 'declarations', label: 'Your Story', icon: 'story', description: 'Quick questions to personalize', required: true },
  { id: 'planning', label: 'Your Goals', icon: 'goals', description: 'Mortgage preferences', required: false },
  { id: 'profile', label: 'About You', icon: 'profile', description: 'The basics about you', required: true },
  { id: 'income', label: 'Your Income', icon: 'income', description: 'How you earn', required: true },
  { id: 'assets', label: 'Your Assets', icon: 'assets', description: 'Down payment funds', required: true },
  { id: 'property', label: 'New Home', icon: 'home', description: 'Property details', required: true },
  { id: 'review', label: 'Review', icon: 'review', description: 'Review your info', required: true },
  { id: 'schedule', label: 'Schedule', icon: 'calendar', description: 'Book a call', required: false },
];

// Declaration questions that can be toggled
const DEFAULT_DECLARATION_QUESTIONS = [
  { id: 'borrower_count', question: 'How many people will be on this loan?', category: 'Basic Info', required: true },
  { id: 'co_borrower_relationship', question: 'Relationship to other borrower(s)?', category: 'Basic Info', required: false },
  { id: 'citizenship_status', question: 'Citizenship status?', category: 'Basic Info', required: true },
  { id: 'first_time_buyer', question: 'First home purchase?', category: 'Home History', required: true },
  { id: 'desired_state', question: 'State looking to buy in?', category: 'Location', required: true },
  { id: 'desired_city', question: 'City or area?', category: 'Location', required: false },
  { id: 'previous_home_status', question: 'Previous home status?', category: 'Home History', required: false },
  { id: 'previous_home_mortgage', question: 'Previous home mortgage?', category: 'Home History', required: false },
  { id: 'marital_status', question: 'Marital status?', category: 'Personal', required: true },
  { id: 'spouse_on_loan', question: 'Spouse on loan?', category: 'Personal', required: false },
  { id: 'divorce_finalized', question: 'Divorce finalized?', category: 'Personal', required: false },
  { id: 'child_support_alimony', question: 'Child support/alimony?', category: 'Financial', required: false },
  { id: 'military_status', question: 'Military service?', category: 'Military', required: true },
  { id: 'va_funding_fee', question: 'VA funding fee exempt?', category: 'Military', required: false },
  { id: 'self_employed', question: 'Self-employed?', category: 'Employment', required: true },
  { id: 'employer_name', question: 'Employer name?', category: 'Employment', required: true },
  { id: 'credit_score_range', question: 'Credit score range?', category: 'Credit', required: true },
  { id: 'bankruptcy_history', question: 'Bankruptcy history?', category: 'Credit', required: true },
  { id: 'gift_funds', question: 'Gift funds for down payment?', category: 'Assets', required: false },
  { id: 'retirement_funds', question: 'Using retirement funds?', category: 'Assets', required: false },
];

// Profile fields that can be toggled
const DEFAULT_PROFILE_FIELDS = [
  { id: 'firstName', label: 'First Name', required: true },
  { id: 'lastName', label: 'Last Name', required: true },
  { id: 'email', label: 'Email', required: true },
  { id: 'phone', label: 'Phone', required: true },
  { id: 'dateOfBirth', label: 'Date of Birth', required: true },
  { id: 'ssn', label: 'Social Security Number', required: true },
  { id: 'currentAddress', label: 'Current Address', required: true },
  { id: 'yearsAtAddress', label: 'Years at Address', required: false },
  { id: 'housingStatus', label: 'Housing Status (Rent/Own)', required: true },
  { id: 'monthlyPayment', label: 'Monthly Housing Payment', required: true },
];

const API_URL = process.env.REACT_APP_API_URL || 'https://api.perenniaai.com';

const ApplicationSlidesEditor = () => {
  const [stages, setStages] = useState([]);
  const [declarationQuestions, setDeclarationQuestions] = useState([]);
  const [profileFields, setProfileFields] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [hasChanges, setHasChanges] = useState(false);
  const [expandedStage, setExpandedStage] = useState(null);
  const [activeTab, setActiveTab] = useState('stages');
  const [saveMessage, setSaveMessage] = useState(null);

  // Load configuration from backend
  const loadConfiguration = useCallback(async () => {
    setLoading(true);
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(`${API_URL}/api/v1/settings/application-slides`, {
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        }
      });

      if (response.ok) {
        const data = await response.json();
        setStages(data.stages || DEFAULT_STAGES.map(s => ({ ...s, enabled: true })));
        setDeclarationQuestions(data.declarationQuestions || DEFAULT_DECLARATION_QUESTIONS.map(q => ({ ...q, enabled: true })));
        setProfileFields(data.profileFields || DEFAULT_PROFILE_FIELDS.map(f => ({ ...f, enabled: true })));
      } else {
        // Use defaults if no saved configuration
        setStages(DEFAULT_STAGES.map(s => ({ ...s, enabled: true })));
        setDeclarationQuestions(DEFAULT_DECLARATION_QUESTIONS.map(q => ({ ...q, enabled: true })));
        setProfileFields(DEFAULT_PROFILE_FIELDS.map(f => ({ ...f, enabled: true })));
      }
    } catch (error) {
      console.error('Failed to load configuration:', error);
      // Use defaults on error
      setStages(DEFAULT_STAGES.map(s => ({ ...s, enabled: true })));
      setDeclarationQuestions(DEFAULT_DECLARATION_QUESTIONS.map(q => ({ ...q, enabled: true })));
      setProfileFields(DEFAULT_PROFILE_FIELDS.map(f => ({ ...f, enabled: true })));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadConfiguration();
  }, [loadConfiguration]);

  // Save configuration to backend
  const saveConfiguration = async () => {
    setSaving(true);
    setSaveMessage(null);
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(`${API_URL}/api/v1/settings/application-slides`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          stages,
          declarationQuestions,
          profileFields
        })
      });

      if (response.ok) {
        setHasChanges(false);
        setSaveMessage({ type: 'success', text: 'Configuration saved successfully!' });
        setTimeout(() => setSaveMessage(null), 3000);
      } else {
        setSaveMessage({ type: 'error', text: 'Failed to save configuration' });
      }
    } catch (error) {
      console.error('Failed to save configuration:', error);
      setSaveMessage({ type: 'error', text: 'Failed to save configuration' });
    } finally {
      setSaving(false);
    }
  };

  // Toggle stage enabled state
  const toggleStage = (stageId) => {
    setStages(prev => prev.map(stage =>
      stage.id === stageId && !stage.required
        ? { ...stage, enabled: !stage.enabled }
        : stage
    ));
    setHasChanges(true);
  };

  // Toggle question enabled state
  const toggleQuestion = (questionId) => {
    setDeclarationQuestions(prev => prev.map(q =>
      q.id === questionId && !q.required
        ? { ...q, enabled: !q.enabled }
        : q
    ));
    setHasChanges(true);
  };

  // Toggle profile field enabled state
  const toggleProfileField = (fieldId) => {
    setProfileFields(prev => prev.map(f =>
      f.id === fieldId && !f.required
        ? { ...f, enabled: !f.enabled }
        : f
    ));
    setHasChanges(true);
  };

  // Move stage up
  const moveStageUp = (index) => {
    if (index === 0) return;
    const newStages = [...stages];
    [newStages[index - 1], newStages[index]] = [newStages[index], newStages[index - 1]];
    setStages(newStages);
    setHasChanges(true);
  };

  // Move stage down
  const moveStageDown = (index) => {
    if (index === stages.length - 1) return;
    const newStages = [...stages];
    [newStages[index], newStages[index + 1]] = [newStages[index + 1], newStages[index]];
    setStages(newStages);
    setHasChanges(true);
  };

  // Move question up
  const moveQuestionUp = (index) => {
    if (index === 0) return;
    const newQuestions = [...declarationQuestions];
    [newQuestions[index - 1], newQuestions[index]] = [newQuestions[index], newQuestions[index - 1]];
    setDeclarationQuestions(newQuestions);
    setHasChanges(true);
  };

  // Move question down
  const moveQuestionDown = (index) => {
    if (index === declarationQuestions.length - 1) return;
    const newQuestions = [...declarationQuestions];
    [newQuestions[index], newQuestions[index + 1]] = [newQuestions[index + 1], newQuestions[index]];
    setDeclarationQuestions(newQuestions);
    setHasChanges(true);
  };

  // Reset to defaults
  const resetToDefaults = () => {
    if (window.confirm('Are you sure you want to reset to default settings? This will undo all customizations.')) {
      setStages(DEFAULT_STAGES.map(s => ({ ...s, enabled: true })));
      setDeclarationQuestions(DEFAULT_DECLARATION_QUESTIONS.map(q => ({ ...q, enabled: true })));
      setProfileFields(DEFAULT_PROFILE_FIELDS.map(f => ({ ...f, enabled: true })));
      setHasChanges(true);
    }
  };

  // Get icon for stage
  const getStageIcon = (iconName) => {
    const icons = {
      user: '👤',
      story: '📖',
      goals: '🎯',
      profile: '📋',
      income: '💰',
      assets: '🏦',
      home: '🏠',
      review: '✅',
      calendar: '📅'
    };
    return icons[iconName] || '📄';
  };

  // Get category color
  const getCategoryColor = (category) => {
    const colors = {
      'Basic Info': '#3b82f6',
      'Home History': '#10b981',
      'Location': '#f59e0b',
      'Personal': '#ec4899',
      'Financial': '#8b5cf6',
      'Military': '#059669',
      'Employment': '#6366f1',
      'Credit': '#ef4444',
      'Assets': '#14b8a6'
    };
    return colors[category] || '#6b7280';
  };

  if (loading) {
    return (
      <div className="slides-editor-loading">
        <div className="loading-spinner"></div>
        <p>Loading configuration...</p>
      </div>
    );
  }

  return (
    <div className="slides-editor">
      <div className="slides-editor-header">
        <div>
          <h3>Application Flow Builder</h3>
          <p>Customize which screens and questions appear in your mortgage application</p>
        </div>
        <div className="header-actions">
          <button
            className="btn-secondary"
            onClick={resetToDefaults}
          >
            Reset to Defaults
          </button>
          <button
            className={`btn-primary ${saving ? 'saving' : ''}`}
            onClick={saveConfiguration}
            disabled={saving || !hasChanges}
          >
            {saving ? 'Saving...' : hasChanges ? 'Save Changes' : 'Saved'}
          </button>
        </div>
      </div>

      {saveMessage && (
        <div className={`save-message ${saveMessage.type}`}>
          {saveMessage.text}
        </div>
      )}

      {/* Tabs for different sections */}
      <div className="slides-editor-tabs">
        <button
          className={activeTab === 'stages' ? 'active' : ''}
          onClick={() => setActiveTab('stages')}
        >
          Application Stages ({stages.filter(s => s.enabled).length}/{stages.length})
        </button>
        <button
          className={activeTab === 'questions' ? 'active' : ''}
          onClick={() => setActiveTab('questions')}
        >
          Story Questions ({declarationQuestions.filter(q => q.enabled).length}/{declarationQuestions.length})
        </button>
        <button
          className={activeTab === 'profile' ? 'active' : ''}
          onClick={() => setActiveTab('profile')}
        >
          Profile Fields ({profileFields.filter(f => f.enabled).length}/{profileFields.length})
        </button>
      </div>

      {/* Stages Tab */}
      {activeTab === 'stages' && (
        <div className="slides-list">
          <div className="list-header">
            <span className="col-order">#</span>
            <span className="col-name">Stage</span>
            <span className="col-description">Description</span>
            <span className="col-status">Status</span>
            <span className="col-actions">Actions</span>
          </div>

          {stages.map((stage, index) => (
            <div
              key={stage.id}
              className={`slide-item ${!stage.enabled ? 'disabled' : ''} ${stage.required ? 'required' : ''}`}
            >
              <span className="col-order">{index + 1}</span>
              <span className="col-name">
                <span className="stage-icon">{getStageIcon(stage.icon)}</span>
                {stage.label}
                {stage.hideFromProgress && <span className="badge hidden">Hidden</span>}
              </span>
              <span className="col-description">{stage.description}</span>
              <span className="col-status">
                {stage.required ? (
                  <span className="status-badge required">Required</span>
                ) : (
                  <label className="toggle-switch">
                    <input
                      type="checkbox"
                      checked={stage.enabled}
                      onChange={() => toggleStage(stage.id)}
                    />
                    <span className="slider"></span>
                  </label>
                )}
              </span>
              <span className="col-actions">
                <button
                  className="btn-icon"
                  onClick={() => moveStageUp(index)}
                  disabled={index === 0}
                  title="Move up"
                >
                  ↑
                </button>
                <button
                  className="btn-icon"
                  onClick={() => moveStageDown(index)}
                  disabled={index === stages.length - 1}
                  title="Move down"
                >
                  ↓
                </button>
                <button
                  className="btn-icon expand"
                  onClick={() => setExpandedStage(expandedStage === stage.id ? null : stage.id)}
                  title="View details"
                >
                  {expandedStage === stage.id ? '−' : '+'}
                </button>
              </span>

              {expandedStage === stage.id && (
                <div className="stage-details">
                  <p><strong>Stage ID:</strong> {stage.id}</p>
                  <p><strong>Icon:</strong> {stage.icon}</p>
                  <p><strong>Hidden from Progress:</strong> {stage.hideFromProgress ? 'Yes' : 'No'}</p>
                  {stage.id === 'declarations' && (
                    <p className="hint">
                      Configure individual questions in the "Story Questions" tab
                    </p>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Questions Tab */}
      {activeTab === 'questions' && (
        <div className="slides-list">
          <div className="list-header">
            <span className="col-order">#</span>
            <span className="col-name">Question</span>
            <span className="col-category">Category</span>
            <span className="col-status">Status</span>
            <span className="col-actions">Actions</span>
          </div>

          {declarationQuestions.map((question, index) => (
            <div
              key={question.id}
              className={`slide-item ${!question.enabled ? 'disabled' : ''} ${question.required ? 'required' : ''}`}
            >
              <span className="col-order">{index + 1}</span>
              <span className="col-name">{question.question}</span>
              <span className="col-category">
                <span
                  className="category-badge"
                  style={{ backgroundColor: getCategoryColor(question.category) }}
                >
                  {question.category}
                </span>
              </span>
              <span className="col-status">
                {question.required ? (
                  <span className="status-badge required">Required</span>
                ) : (
                  <label className="toggle-switch">
                    <input
                      type="checkbox"
                      checked={question.enabled}
                      onChange={() => toggleQuestion(question.id)}
                    />
                    <span className="slider"></span>
                  </label>
                )}
              </span>
              <span className="col-actions">
                <button
                  className="btn-icon"
                  onClick={() => moveQuestionUp(index)}
                  disabled={index === 0}
                  title="Move up"
                >
                  ↑
                </button>
                <button
                  className="btn-icon"
                  onClick={() => moveQuestionDown(index)}
                  disabled={index === declarationQuestions.length - 1}
                  title="Move down"
                >
                  ↓
                </button>
              </span>
            </div>
          ))}
        </div>
      )}

      {/* Profile Fields Tab */}
      {activeTab === 'profile' && (
        <div className="slides-list">
          <div className="list-header">
            <span className="col-order">#</span>
            <span className="col-name">Field</span>
            <span className="col-description">Field ID</span>
            <span className="col-status">Status</span>
            <span className="col-actions">Actions</span>
          </div>

          {profileFields.map((field, index) => (
            <div
              key={field.id}
              className={`slide-item ${!field.enabled ? 'disabled' : ''} ${field.required ? 'required' : ''}`}
            >
              <span className="col-order">{index + 1}</span>
              <span className="col-name">{field.label}</span>
              <span className="col-description">{field.id}</span>
              <span className="col-status">
                {field.required ? (
                  <span className="status-badge required">Required</span>
                ) : (
                  <label className="toggle-switch">
                    <input
                      type="checkbox"
                      checked={field.enabled}
                      onChange={() => toggleProfileField(field.id)}
                    />
                    <span className="slider"></span>
                  </label>
                )}
              </span>
              <span className="col-actions">
                <button className="btn-icon" disabled title="Move up">↑</button>
                <button className="btn-icon" disabled title="Move down">↓</button>
              </span>
            </div>
          ))}
        </div>
      )}

      {/* Preview Section */}
      <div className="preview-section">
        <h4>Application Flow Preview</h4>
        <div className="flow-preview">
          {stages.filter(s => s.enabled).map((stage, index) => (
            <React.Fragment key={stage.id}>
              <div className="preview-stage">
                <span className="stage-icon">{getStageIcon(stage.icon)}</span>
                <span className="stage-label">{stage.label}</span>
              </div>
              {index < stages.filter(s => s.enabled).length - 1 && (
                <span className="preview-arrow">→</span>
              )}
            </React.Fragment>
          ))}
        </div>
      </div>
    </div>
  );
};

export default ApplicationSlidesEditor;
