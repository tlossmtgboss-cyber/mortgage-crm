/**
 * Application Slides Editor
 *
 * Allows users to customize the mortgage application flow by:
 * - Separate configurations for Purchase and Refinance applications
 * - Enabling/disabling stages and questions
 * - Editing stage and question details
 * - Creating new stages and questions
 * - Reordering stages and questions
 */

import React, { useState, useEffect, useCallback } from 'react';
import './ApplicationSlidesEditor.css';

// Default stages for Purchase application
const DEFAULT_PURCHASE_STAGES = [
  { id: 'account', label: 'Get Started', description: 'Create your account', hideFromProgress: true, required: true },
  { id: 'declarations', label: 'Your Story', description: 'Quick questions to personalize', required: true },
  { id: 'planning', label: 'Your Goals', description: 'Mortgage preferences', required: false },
  { id: 'profile', label: 'About You', description: 'The basics about you', required: true },
  { id: 'income', label: 'Your Income', description: 'How you earn', required: true },
  { id: 'assets', label: 'Your Assets', description: 'Down payment funds', required: true },
  { id: 'property', label: 'New Home', description: 'Property details', required: true },
  { id: 'review', label: 'Review', description: 'Review your info', required: true },
  { id: 'schedule', label: 'Schedule', description: 'Book a call', required: false },
];

// Default stages for Refinance application
const DEFAULT_REFINANCE_STAGES = [
  { id: 'account', label: 'Get Started', description: 'Create your account', hideFromProgress: true, required: true },
  { id: 'declarations', label: 'Your Story', description: 'Quick questions', required: true },
  { id: 'planning', label: 'Planning', description: 'Your preferences', required: false },
  { id: 'profile', label: 'About You', description: 'The basics', required: true },
  { id: 'income', label: 'Your Income', description: 'How you earn', required: true },
  { id: 'property', label: 'Current Home', description: 'Property details', required: true },
  { id: 'goals', label: 'Refi Goals', description: 'Refinance options', required: true },
  { id: 'review', label: 'Review', description: 'Review your info', required: true },
  { id: 'schedule', label: 'Submit', description: 'Complete application', required: false },
];

// Default questions for Purchase application
const DEFAULT_PURCHASE_QUESTIONS = [
  { id: 'borrower_count', question: 'How many people will be on this loan?', category: 'Basic Info', required: true, type: 'choice' },
  { id: 'co_borrower_relationship', question: 'Relationship to other borrower(s)?', category: 'Basic Info', required: false, type: 'choice' },
  { id: 'citizenship_status', question: 'Citizenship status?', category: 'Basic Info', required: true, type: 'choice' },
  { id: 'first_time_buyer', question: 'First home purchase?', category: 'Home History', required: true, type: 'choice' },
  { id: 'desired_state', question: 'State looking to buy in?', category: 'Location', required: true, type: 'choice' },
  { id: 'desired_city', question: 'City or area?', category: 'Location', required: false, type: 'text' },
  { id: 'previous_home_status', question: 'Previous home status?', category: 'Home History', required: false, type: 'choice' },
  { id: 'previous_home_mortgage', question: 'Previous home mortgage?', category: 'Home History', required: false, type: 'choice' },
  { id: 'marital_status', question: 'Marital status?', category: 'Personal', required: true, type: 'choice' },
  { id: 'spouse_on_loan', question: 'Spouse on loan?', category: 'Personal', required: false, type: 'choice' },
  { id: 'divorce_finalized', question: 'Divorce finalized?', category: 'Personal', required: false, type: 'choice' },
  { id: 'child_support_alimony', question: 'Child support/alimony?', category: 'Financial', required: false, type: 'choice' },
  { id: 'military_status', question: 'Military service?', category: 'Military', required: true, type: 'choice' },
  { id: 'va_funding_fee', question: 'VA funding fee exempt?', category: 'Military', required: false, type: 'choice' },
  { id: 'self_employed', question: 'Self-employed?', category: 'Employment', required: true, type: 'choice' },
  { id: 'employer_name', question: 'Employer name?', category: 'Employment', required: true, type: 'text' },
  { id: 'credit_score_range', question: 'Credit score range?', category: 'Credit', required: true, type: 'choice' },
  { id: 'bankruptcy_history', question: 'Bankruptcy history?', category: 'Credit', required: true, type: 'choice' },
  { id: 'gift_funds', question: 'Gift funds for down payment?', category: 'Assets', required: false, type: 'choice' },
  { id: 'retirement_funds', question: 'Using retirement funds?', category: 'Assets', required: false, type: 'choice' },
];

// Default questions for Refinance application
const DEFAULT_REFINANCE_QUESTIONS = [
  { id: 'borrower_count', question: 'How many people will be on this loan?', category: 'Basic Info', required: true, type: 'choice' },
  { id: 'co_borrower_relationship', question: 'Relationship to other borrower(s)?', category: 'Basic Info', required: false, type: 'choice' },
  { id: 'refi_goal', question: "What's your main goal for refinancing?", category: 'Goals', required: true, type: 'choice' },
  { id: 'cash_out_amount', question: 'Approximately how much cash do you need?', category: 'Goals', required: false, type: 'currency' },
  { id: 'citizenship_status', question: 'Citizenship status?', category: 'Basic Info', required: true, type: 'choice' },
  { id: 'marital_status', question: 'Marital status?', category: 'Personal', required: true, type: 'choice' },
  { id: 'spouse_on_loan', question: 'Spouse on loan?', category: 'Personal', required: false, type: 'choice' },
  { id: 'military_status', question: 'Military service?', category: 'Military', required: true, type: 'choice' },
  { id: 'va_funding_fee', question: 'VA funding fee exempt?', category: 'Military', required: false, type: 'choice' },
  { id: 'self_employed', question: 'Self-employed?', category: 'Employment', required: true, type: 'choice' },
  { id: 'employer_name', question: 'Employer name?', category: 'Employment', required: true, type: 'text' },
  { id: 'credit_score_range', question: 'Credit score range?', category: 'Credit', required: true, type: 'choice' },
  { id: 'bankruptcy_history', question: 'Bankruptcy history?', category: 'Credit', required: true, type: 'choice' },
  { id: 'property_use', question: 'How do you use this property?', category: 'Property', required: true, type: 'choice' },
  { id: 'current_rate', question: 'Current interest rate?', category: 'Property', required: false, type: 'text' },
];

const API_URL = process.env.REACT_APP_API_URL || 'https://api.perenniaai.com';

const QUESTION_TYPES = [
  { value: 'choice', label: 'Multiple Choice' },
  { value: 'text', label: 'Text Input' },
  { value: 'currency', label: 'Currency Input' },
  { value: 'date', label: 'Date Picker' },
  { value: 'address', label: 'Address' },
];

const CATEGORIES = [
  'Basic Info', 'Home History', 'Location', 'Personal', 'Financial',
  'Military', 'Employment', 'Credit', 'Assets', 'Goals', 'Property'
];

const ApplicationSlidesEditor = () => {
  // Application type: 'purchase' or 'refinance'
  const [appType, setAppType] = useState('purchase');

  // Purchase configuration
  const [purchaseStages, setPurchaseStages] = useState([]);
  const [purchaseQuestions, setPurchaseQuestions] = useState([]);

  // Refinance configuration
  const [refinanceStages, setRefinanceStages] = useState([]);
  const [refinanceQuestions, setRefinanceQuestions] = useState([]);

  // UI state
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [hasChanges, setHasChanges] = useState(false);
  const [activeTab, setActiveTab] = useState('stages');
  const [saveMessage, setSaveMessage] = useState(null);

  // Edit modal state
  const [editModal, setEditModal] = useState({ open: false, type: null, item: null, isNew: false });

  // Preview modal state
  const [previewModal, setPreviewModal] = useState({ open: false, stage: null });

  // Get current stages and questions based on selected app type
  const stages = appType === 'purchase' ? purchaseStages : refinanceStages;
  const setStages = appType === 'purchase' ? setPurchaseStages : setRefinanceStages;
  const questions = appType === 'purchase' ? purchaseQuestions : refinanceQuestions;
  const setQuestions = appType === 'purchase' ? setPurchaseQuestions : setRefinanceQuestions;

  // Load configuration from backend
  const loadConfiguration = useCallback(async () => {
    setLoading(true);
    try {
      const token = localStorage.getItem('token');

      // Load purchase config
      const purchaseRes = await fetch(`${API_URL}/api/v1/settings/application-slides?app_type=purchase`, {
        headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' }
      });
      if (purchaseRes.ok) {
        const data = await purchaseRes.json();
        setPurchaseStages(data.stages || DEFAULT_PURCHASE_STAGES.map(s => ({ ...s, enabled: true })));
        setPurchaseQuestions(data.declarationQuestions || DEFAULT_PURCHASE_QUESTIONS.map(q => ({ ...q, enabled: true })));
      } else {
        setPurchaseStages(DEFAULT_PURCHASE_STAGES.map(s => ({ ...s, enabled: true })));
        setPurchaseQuestions(DEFAULT_PURCHASE_QUESTIONS.map(q => ({ ...q, enabled: true })));
      }

      // Load refinance config
      const refinanceRes = await fetch(`${API_URL}/api/v1/settings/application-slides?app_type=refinance`, {
        headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' }
      });
      if (refinanceRes.ok) {
        const data = await refinanceRes.json();
        setRefinanceStages(data.stages || DEFAULT_REFINANCE_STAGES.map(s => ({ ...s, enabled: true })));
        setRefinanceQuestions(data.declarationQuestions || DEFAULT_REFINANCE_QUESTIONS.map(q => ({ ...q, enabled: true })));
      } else {
        setRefinanceStages(DEFAULT_REFINANCE_STAGES.map(s => ({ ...s, enabled: true })));
        setRefinanceQuestions(DEFAULT_REFINANCE_QUESTIONS.map(q => ({ ...q, enabled: true })));
      }
    } catch (error) {
      console.error('Failed to load configuration:', error);
      setPurchaseStages(DEFAULT_PURCHASE_STAGES.map(s => ({ ...s, enabled: true })));
      setPurchaseQuestions(DEFAULT_PURCHASE_QUESTIONS.map(q => ({ ...q, enabled: true })));
      setRefinanceStages(DEFAULT_REFINANCE_STAGES.map(s => ({ ...s, enabled: true })));
      setRefinanceQuestions(DEFAULT_REFINANCE_QUESTIONS.map(q => ({ ...q, enabled: true })));
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

      // Save current app type config
      const response = await fetch(`${API_URL}/api/v1/settings/application-slides?app_type=${appType}`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({
          stages,
          declarationQuestions: questions,
          profileFields: []
        })
      });

      if (response.ok) {
        setHasChanges(false);
        setSaveMessage({ type: 'success', text: `${appType === 'purchase' ? 'Purchase' : 'Refinance'} configuration saved!` });
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

  // Toggle stage enabled
  const toggleStage = (stageId) => {
    setStages(prev => prev.map(stage =>
      stage.id === stageId && !stage.required ? { ...stage, enabled: !stage.enabled } : stage
    ));
    setHasChanges(true);
  };

  // Toggle question enabled
  const toggleQuestion = (questionId) => {
    setQuestions(prev => prev.map(q =>
      q.id === questionId && !q.required ? { ...q, enabled: !q.enabled } : q
    ));
    setHasChanges(true);
  };

  // Move stage
  const moveStage = (index, direction) => {
    const newIndex = direction === 'up' ? index - 1 : index + 1;
    if (newIndex < 0 || newIndex >= stages.length) return;
    const newStages = [...stages];
    [newStages[index], newStages[newIndex]] = [newStages[newIndex], newStages[index]];
    setStages(newStages);
    setHasChanges(true);
  };

  // Move question
  const moveQuestion = (index, direction) => {
    const newIndex = direction === 'up' ? index - 1 : index + 1;
    if (newIndex < 0 || newIndex >= questions.length) return;
    const newQuestions = [...questions];
    [newQuestions[index], newQuestions[newIndex]] = [newQuestions[newIndex], newQuestions[index]];
    setQuestions(newQuestions);
    setHasChanges(true);
  };

  // Open edit modal
  const openEditModal = (type, item = null) => {
    if (item) {
      setEditModal({ open: true, type, item: { ...item }, isNew: false });
    } else {
      // Create new item
      const newItem = type === 'stage'
        ? { id: '', label: '', description: '', required: false, enabled: true, hideFromProgress: false }
        : { id: '', question: '', category: 'Basic Info', type: 'choice', required: false, enabled: true };
      setEditModal({ open: true, type, item: newItem, isNew: true });
    }
  };

  // Save edit modal
  const saveEditModal = () => {
    const { type, item, isNew } = editModal;

    if (type === 'stage') {
      if (!item.id || !item.label) {
        alert('Stage ID and Label are required');
        return;
      }
      if (isNew) {
        // Check for duplicate ID
        if (stages.find(s => s.id === item.id)) {
          alert('A stage with this ID already exists');
          return;
        }
        setStages(prev => [...prev, item]);
      } else {
        setStages(prev => prev.map(s => s.id === item.id ? item : s));
      }
    } else {
      if (!item.id || !item.question) {
        alert('Question ID and text are required');
        return;
      }
      if (isNew) {
        if (questions.find(q => q.id === item.id)) {
          alert('A question with this ID already exists');
          return;
        }
        setQuestions(prev => [...prev, item]);
      } else {
        setQuestions(prev => prev.map(q => q.id === item.id ? item : q));
      }
    }

    setHasChanges(true);
    setEditModal({ open: false, type: null, item: null, isNew: false });
  };

  // Delete item
  const deleteItem = (type, id) => {
    if (!window.confirm('Are you sure you want to delete this item?')) return;

    if (type === 'stage') {
      setStages(prev => prev.filter(s => s.id !== id));
    } else {
      setQuestions(prev => prev.filter(q => q.id !== id));
    }
    setHasChanges(true);
  };

  // Reset to defaults
  const resetToDefaults = () => {
    if (!window.confirm('Reset to default settings? This will undo all customizations.')) return;

    if (appType === 'purchase') {
      setPurchaseStages(DEFAULT_PURCHASE_STAGES.map(s => ({ ...s, enabled: true })));
      setPurchaseQuestions(DEFAULT_PURCHASE_QUESTIONS.map(q => ({ ...q, enabled: true })));
    } else {
      setRefinanceStages(DEFAULT_REFINANCE_STAGES.map(s => ({ ...s, enabled: true })));
      setRefinanceQuestions(DEFAULT_REFINANCE_QUESTIONS.map(q => ({ ...q, enabled: true })));
    }
    setHasChanges(true);
  };

  // Get category color
  const getCategoryColor = (category) => {
    const colors = {
      'Basic Info': '#3b82f6', 'Home History': '#10b981', 'Location': '#f59e0b',
      'Personal': '#ec4899', 'Financial': '#8b5cf6', 'Military': '#059669',
      'Employment': '#6366f1', 'Credit': '#ef4444', 'Assets': '#14b8a6',
      'Goals': '#f97316', 'Property': '#0ea5e9'
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
      {/* Header */}
      <div className="slides-editor-header">
        <div>
          <h3>Application Flow Builder</h3>
          <p>Customize screens and questions for your mortgage applications</p>
        </div>
        <div className="header-actions">
          <button className="btn-secondary" onClick={resetToDefaults}>Reset to Defaults</button>
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
        <div className={`save-message ${saveMessage.type}`}>{saveMessage.text}</div>
      )}

      {/* Application Type Toggle */}
      <div className="app-type-toggle">
        <button
          className={`app-type-btn ${appType === 'purchase' ? 'active' : ''}`}
          onClick={() => setAppType('purchase')}
        >
          Purchase Application
        </button>
        <button
          className={`app-type-btn ${appType === 'refinance' ? 'active' : ''}`}
          onClick={() => setAppType('refinance')}
        >
          Refinance Application
        </button>
      </div>

      {/* Section Tabs */}
      <div className="slides-editor-tabs">
        <button className={activeTab === 'stages' ? 'active' : ''} onClick={() => setActiveTab('stages')}>
          Stages ({stages.filter(s => s.enabled).length}/{stages.length})
        </button>
        <button className={activeTab === 'questions' ? 'active' : ''} onClick={() => setActiveTab('questions')}>
          Questions ({questions.filter(q => q.enabled).length}/{questions.length})
        </button>
      </div>

      {/* Stages Tab */}
      {activeTab === 'stages' && (
        <div className="slides-content">
          <div className="content-header">
            <h4>Application Stages</h4>
            <button className="btn-add" onClick={() => openEditModal('stage')}>
              + Add Stage
            </button>
          </div>

          <div className="slides-grid">
            {stages.map((stage, index) => (
              <div
                key={stage.id}
                className={`slide-card ${!stage.enabled ? 'disabled' : ''} ${stage.required ? 'required' : ''}`}
              >
                <div className="slide-card-header">
                  <span className="slide-number">{index + 1}</span>
                  <div className="slide-card-actions">
                    <button onClick={() => moveStage(index, 'up')} disabled={index === 0} title="Move up">↑</button>
                    <button onClick={() => moveStage(index, 'down')} disabled={index === stages.length - 1} title="Move down">↓</button>
                    <button onClick={() => setPreviewModal({ open: true, stage })} className="preview-btn" title="Preview">👁️</button>
                    <button onClick={() => openEditModal('stage', stage)} title="Edit">Edit</button>
                    {!stage.required && (
                      <button onClick={() => deleteItem('stage', stage.id)} className="delete" title="Delete">×</button>
                    )}
                  </div>
                </div>

                <div className="slide-card-body">
                  <h5 className="slide-title">{stage.label}</h5>
                  <p className="slide-description">{stage.description}</p>
                  <div className="slide-meta">
                    <span className="slide-id">ID: {stage.id}</span>
                    {stage.hideFromProgress && <span className="badge-hidden">Hidden from progress</span>}
                  </div>
                </div>

                <div className="slide-card-footer">
                  {stage.required ? (
                    <span className="status-required">Required</span>
                  ) : (
                    <label className="toggle-switch">
                      <input type="checkbox" checked={stage.enabled} onChange={() => toggleStage(stage.id)} />
                      <span className="slider"></span>
                      <span className="toggle-label">{stage.enabled ? 'Enabled' : 'Disabled'}</span>
                    </label>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Questions Tab */}
      {activeTab === 'questions' && (
        <div className="slides-content">
          <div className="content-header">
            <h4>Declaration Questions</h4>
            <button className="btn-add" onClick={() => openEditModal('question')}>
              + Add Question
            </button>
          </div>

          <div className="questions-list">
            {questions.map((question, index) => (
              <div
                key={question.id}
                className={`question-row ${!question.enabled ? 'disabled' : ''} ${question.required ? 'required' : ''}`}
              >
                <span className="question-number">{index + 1}</span>

                <div className="question-content">
                  <div className="question-text">{question.question}</div>
                  <div className="question-meta">
                    <span className="question-id">ID: {question.id}</span>
                    <span className="question-type">{question.type || 'choice'}</span>
                  </div>
                </div>

                <span className="category-badge" style={{ backgroundColor: getCategoryColor(question.category) }}>
                  {question.category}
                </span>

                <div className="question-status">
                  {question.required ? (
                    <span className="status-required">Required</span>
                  ) : (
                    <label className="toggle-switch small">
                      <input type="checkbox" checked={question.enabled} onChange={() => toggleQuestion(question.id)} />
                      <span className="slider"></span>
                    </label>
                  )}
                </div>

                <div className="question-actions">
                  <button onClick={() => moveQuestion(index, 'up')} disabled={index === 0}>↑</button>
                  <button onClick={() => moveQuestion(index, 'down')} disabled={index === questions.length - 1}>↓</button>
                  <button onClick={() => openEditModal('question', question)}>Edit</button>
                  {!question.required && (
                    <button onClick={() => deleteItem('question', question.id)} className="delete">×</button>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Flow Preview */}
      <div className="flow-preview-section">
        <h4>Application Flow Preview</h4>
        <div className="flow-preview">
          {stages.filter(s => s.enabled && !s.hideFromProgress).map((stage, index, arr) => (
            <React.Fragment key={stage.id}>
              <div className="preview-stage">
                <span className="preview-number">{index + 1}</span>
                <span className="preview-label">{stage.label}</span>
              </div>
              {index < arr.length - 1 && <span className="preview-arrow">→</span>}
            </React.Fragment>
          ))}
        </div>
      </div>

      {/* Edit Modal */}
      {editModal.open && (
        <div className="modal-overlay" onClick={() => setEditModal({ open: false, type: null, item: null, isNew: false })}>
          <div className="modal-content" onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <h3>{editModal.isNew ? 'Add' : 'Edit'} {editModal.type === 'stage' ? 'Stage' : 'Question'}</h3>
              <button className="modal-close" onClick={() => setEditModal({ open: false, type: null, item: null, isNew: false })}>×</button>
            </div>

            <div className="modal-body">
              {editModal.type === 'stage' ? (
                <>
                  <div className="form-group">
                    <label>Stage ID (unique identifier)</label>
                    <input
                      type="text"
                      value={editModal.item.id}
                      onChange={e => setEditModal(prev => ({ ...prev, item: { ...prev.item, id: e.target.value.toLowerCase().replace(/\s+/g, '_') } }))}
                      placeholder="e.g., property_details"
                      disabled={!editModal.isNew}
                    />
                  </div>
                  <div className="form-group">
                    <label>Stage Label</label>
                    <input
                      type="text"
                      value={editModal.item.label}
                      onChange={e => setEditModal(prev => ({ ...prev, item: { ...prev.item, label: e.target.value } }))}
                      placeholder="e.g., Property Details"
                    />
                  </div>
                  <div className="form-group">
                    <label>Description</label>
                    <input
                      type="text"
                      value={editModal.item.description}
                      onChange={e => setEditModal(prev => ({ ...prev, item: { ...prev.item, description: e.target.value } }))}
                      placeholder="e.g., Enter your property information"
                    />
                  </div>
                  <div className="form-group checkbox-group">
                    <label>
                      <input
                        type="checkbox"
                        checked={editModal.item.hideFromProgress}
                        onChange={e => setEditModal(prev => ({ ...prev, item: { ...prev.item, hideFromProgress: e.target.checked } }))}
                      />
                      Hide from progress bar
                    </label>
                  </div>
                  <div className="form-group checkbox-group">
                    <label>
                      <input
                        type="checkbox"
                        checked={editModal.item.required}
                        onChange={e => setEditModal(prev => ({ ...prev, item: { ...prev.item, required: e.target.checked } }))}
                      />
                      Required (cannot be disabled)
                    </label>
                  </div>
                </>
              ) : (
                <>
                  <div className="form-group">
                    <label>Question ID (unique identifier)</label>
                    <input
                      type="text"
                      value={editModal.item.id}
                      onChange={e => setEditModal(prev => ({ ...prev, item: { ...prev.item, id: e.target.value.toLowerCase().replace(/\s+/g, '_') } }))}
                      placeholder="e.g., income_source"
                      disabled={!editModal.isNew}
                    />
                  </div>
                  <div className="form-group">
                    <label>Question Text</label>
                    <textarea
                      value={editModal.item.question}
                      onChange={e => setEditModal(prev => ({ ...prev, item: { ...prev.item, question: e.target.value } }))}
                      placeholder="e.g., What is your primary source of income?"
                      rows={3}
                    />
                  </div>
                  <div className="form-row">
                    <div className="form-group">
                      <label>Category</label>
                      <select
                        value={editModal.item.category}
                        onChange={e => setEditModal(prev => ({ ...prev, item: { ...prev.item, category: e.target.value } }))}
                      >
                        {CATEGORIES.map(cat => (
                          <option key={cat} value={cat}>{cat}</option>
                        ))}
                      </select>
                    </div>
                    <div className="form-group">
                      <label>Input Type</label>
                      <select
                        value={editModal.item.type || 'choice'}
                        onChange={e => setEditModal(prev => ({ ...prev, item: { ...prev.item, type: e.target.value } }))}
                      >
                        {QUESTION_TYPES.map(type => (
                          <option key={type.value} value={type.value}>{type.label}</option>
                        ))}
                      </select>
                    </div>
                  </div>
                  <div className="form-group checkbox-group">
                    <label>
                      <input
                        type="checkbox"
                        checked={editModal.item.required}
                        onChange={e => setEditModal(prev => ({ ...prev, item: { ...prev.item, required: e.target.checked } }))}
                      />
                      Required (cannot be disabled)
                    </label>
                  </div>
                </>
              )}
            </div>

            <div className="modal-footer">
              <button className="btn-secondary" onClick={() => setEditModal({ open: false, type: null, item: null, isNew: false })}>
                Cancel
              </button>
              <button className="btn-primary" onClick={saveEditModal}>
                {editModal.isNew ? 'Add' : 'Save'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Stage Preview Modal */}
      {previewModal.open && previewModal.stage && (
        <div className="modal-overlay preview-modal-overlay" onClick={() => setPreviewModal({ open: false, stage: null })}>
          <div className="preview-modal-content" onClick={e => e.stopPropagation()}>
            <div className="preview-modal-header">
              <h3>
                <span className="preview-icon">👁️</span>
                Preview: {previewModal.stage.label}
              </h3>
              <div className="preview-header-actions">
                <a
                  href={`/apply/preview?stage=${previewModal.stage.id}&type=${appType}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="btn-open-new-tab"
                >
                  Open in New Tab ↗
                </a>
                <button className="modal-close" onClick={() => setPreviewModal({ open: false, stage: null })}>×</button>
              </div>
            </div>
            <div className="preview-modal-body">
              <iframe
                src={`/apply/preview?stage=${previewModal.stage.id}&type=${appType}`}
                title={`Preview: ${previewModal.stage.label}`}
                className="preview-iframe"
              />
            </div>
            <div className="preview-modal-footer">
              <div className="preview-info">
                <span className="preview-stage-id">Stage ID: {previewModal.stage.id}</span>
                <span className="preview-app-type">{appType === 'purchase' ? 'Purchase' : 'Refinance'} Application</span>
              </div>
              <button className="btn-secondary" onClick={() => setPreviewModal({ open: false, stage: null })}>
                Close Preview
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default ApplicationSlidesEditor;
