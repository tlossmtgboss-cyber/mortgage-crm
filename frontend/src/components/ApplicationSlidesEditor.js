/**
 * Application Flow Builder - Three Panel Layout
 *
 * A Typeform-like editor for customizing mortgage application flows with:
 * - Left panel: Navigation tree of stages and questions
 * - Center panel: Live preview of the selected slide
 * - Right panel: Settings and options for the selected item
 * - Conditional logic support for personalized flows
 */

import React, { useState, useEffect, useCallback } from 'react';
import './ApplicationSlidesEditor.css';
import { getToken } from '../utils/tokenStore';

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
  { id: 'borrower_count', question: 'How many people will be on this loan?', stageId: 'declarations', required: true, type: 'choice', options: [{ value: '1', label: 'Just me' }, { value: '2', label: '2 people' }, { value: '3+', label: '3 or more' }] },
  { id: 'co_borrower_relationship', question: 'What is your relationship to the other borrower(s)?', stageId: 'declarations', required: false, type: 'choice', options: [{ value: 'spouse', label: 'Spouse' }, { value: 'partner', label: 'Partner' }, { value: 'family', label: 'Family Member' }, { value: 'other', label: 'Other' }], showIf: { field: 'borrower_count', values: ['2', '3+'] } },
  { id: 'citizenship_status', question: 'What is your citizenship status?', stageId: 'declarations', required: true, type: 'choice', options: [{ value: 'us_citizen', label: 'US Citizen' }, { value: 'permanent_resident', label: 'Permanent Resident' }, { value: 'visa', label: 'Visa Holder' }, { value: 'other', label: 'Other' }] },
  { id: 'first_time_buyer', question: 'Is this your first home purchase?', stageId: 'declarations', required: true, type: 'choice', options: [{ value: 'yes', label: 'Yes, first time' }, { value: 'no', label: 'No, I\'ve owned before' }] },
  { id: 'previous_home_status', question: 'What happened to your previous home?', stageId: 'declarations', required: false, type: 'choice', options: [{ value: 'sold', label: 'Sold it' }, { value: 'renting', label: 'Renting it out' }, { value: 'still_own', label: 'Still own it' }], showIf: { field: 'first_time_buyer', values: ['no'] } },
  { id: 'marital_status', question: 'What is your marital status?', stageId: 'profile', required: true, type: 'choice', options: [{ value: 'single', label: 'Single' }, { value: 'married', label: 'Married' }, { value: 'divorced', label: 'Divorced' }, { value: 'separated', label: 'Separated' }, { value: 'widowed', label: 'Widowed' }] },
  { id: 'spouse_on_loan', question: 'Will your spouse be on the loan?', stageId: 'profile', required: false, type: 'choice', options: [{ value: 'yes', label: 'Yes' }, { value: 'no', label: 'No' }], showIf: { field: 'marital_status', values: ['married'] } },
  { id: 'military_status', question: 'Have you or your spouse served in the military?', stageId: 'profile', required: true, type: 'choice', options: [{ value: 'active', label: 'Active Duty' }, { value: 'veteran', label: 'Veteran' }, { value: 'reserve', label: 'Reserve/Guard' }, { value: 'spouse', label: 'Military Spouse' }, { value: 'none', label: 'No Military Service' }] },
  { id: 'va_funding_fee', question: 'Are you exempt from the VA funding fee?', stageId: 'profile', required: false, type: 'choice', options: [{ value: 'yes', label: 'Yes' }, { value: 'no', label: 'No' }, { value: 'unsure', label: 'Not sure' }], showIf: { field: 'military_status', values: ['active', 'veteran', 'reserve', 'spouse'] } },
  { id: 'self_employed', question: 'Are you self-employed?', stageId: 'income', required: true, type: 'choice', options: [{ value: 'yes', label: 'Yes' }, { value: 'no', label: 'No' }] },
  { id: 'employer_name', question: 'What is your employer\'s name?', stageId: 'income', required: true, type: 'text', showIf: { field: 'self_employed', values: ['no'] } },
  { id: 'credit_score_range', question: 'What\'s your approximate credit score?', stageId: 'profile', required: true, type: 'choice', options: [{ value: '760+', label: '760+' }, { value: '720-759', label: '720-759' }, { value: '680-719', label: '680-719' }, { value: '640-679', label: '640-679' }, { value: 'below_640', label: 'Below 640' }, { value: 'unsure', label: 'Not sure' }] },
  { id: 'bankruptcy_history', question: 'Have you had a bankruptcy in the last 7 years?', stageId: 'profile', required: true, type: 'choice', options: [{ value: 'yes', label: 'Yes' }, { value: 'no', label: 'No' }] },
  { id: 'gift_funds', question: 'Will you receive gift funds for down payment?', stageId: 'assets', required: false, type: 'choice', options: [{ value: 'yes', label: 'Yes' }, { value: 'no', label: 'No' }, { value: 'maybe', label: 'Maybe' }] },
  { id: 'desired_state', question: 'What state are you looking to buy in?', stageId: 'property', required: true, type: 'choice', options: [{ value: 'CA', label: 'California' }, { value: 'TX', label: 'Texas' }, { value: 'FL', label: 'Florida' }, { value: 'NY', label: 'New York' }, { value: 'other', label: 'Other' }] },
  { id: 'desired_city', question: 'What city or area?', stageId: 'property', required: false, type: 'text' },
];

// Default questions for Refinance application
const DEFAULT_REFINANCE_QUESTIONS = [
  { id: 'borrower_count', question: 'How many people will be on this loan?', stageId: 'declarations', required: true, type: 'choice', options: [{ value: '1', label: 'Just me' }, { value: '2', label: '2 people' }, { value: '3+', label: '3 or more' }] },
  { id: 'citizenship_status', question: 'What is your citizenship status?', stageId: 'declarations', required: true, type: 'choice', options: [{ value: 'us_citizen', label: 'US Citizen' }, { value: 'permanent_resident', label: 'Permanent Resident' }, { value: 'visa', label: 'Visa Holder' }] },
  { id: 'refi_goal', question: 'What\'s your main goal for refinancing?', stageId: 'goals', required: true, type: 'choice', options: [{ value: 'lower_rate', label: 'Lower my rate' }, { value: 'cash_out', label: 'Cash out equity' }, { value: 'shorter_term', label: 'Shorter term' }, { value: 'lower_payment', label: 'Lower payment' }] },
  { id: 'cash_out_amount', question: 'Approximately how much cash do you need?', stageId: 'goals', required: false, type: 'currency', showIf: { field: 'refi_goal', values: ['cash_out'] } },
  { id: 'marital_status', question: 'What is your marital status?', stageId: 'profile', required: true, type: 'choice', options: [{ value: 'single', label: 'Single' }, { value: 'married', label: 'Married' }, { value: 'divorced', label: 'Divorced' }] },
  { id: 'military_status', question: 'Have you served in the military?', stageId: 'profile', required: true, type: 'choice', options: [{ value: 'yes', label: 'Yes' }, { value: 'no', label: 'No' }] },
  { id: 'self_employed', question: 'Are you self-employed?', stageId: 'income', required: true, type: 'choice', options: [{ value: 'yes', label: 'Yes' }, { value: 'no', label: 'No' }] },
  { id: 'employer_name', question: 'What is your employer\'s name?', stageId: 'income', required: true, type: 'text', showIf: { field: 'self_employed', values: ['no'] } },
  { id: 'credit_score_range', question: 'What\'s your approximate credit score?', stageId: 'profile', required: true, type: 'choice', options: [{ value: '760+', label: '760+' }, { value: '720-759', label: '720-759' }, { value: '680-719', label: '680-719' }, { value: 'below_680', label: 'Below 680' }] },
  { id: 'property_use', question: 'How do you use this property?', stageId: 'property', required: true, type: 'choice', options: [{ value: 'primary', label: 'Primary Residence' }, { value: 'second_home', label: 'Second Home' }, { value: 'investment', label: 'Investment Property' }] },
  { id: 'current_rate', question: 'What is your current interest rate?', stageId: 'property', required: false, type: 'text' },
];

const API_URL = process.env.REACT_APP_API_URL || 'https://api.perenniaai.com';

const QUESTION_TYPES = [
  { value: 'choice', label: 'Multiple Choice' },
  { value: 'text', label: 'Text Input' },
  { value: 'currency', label: 'Currency Input' },
  { value: 'date', label: 'Date Picker' },
  { value: 'address', label: 'Address' },
  { value: 'yes_no', label: 'Yes/No' },
];

const CATEGORIES = [
  'Basic Info', 'Home History', 'Location', 'Personal', 'Financial',
  'Military', 'Employment', 'Credit', 'Assets', 'Goals', 'Property'
];

// Helper to get category CSS class
const getCategoryClass = (category) => {
  return 'category-' + (category || 'basic-info').toLowerCase().replace(/\s+/g, '-');
};

// Helper to get category color
const getCategoryColor = (category) => {
  const colors = {
    'Basic Info': '#3b82f6', 'Home History': '#2D7A52', 'Location': '#f59e0b',
    'Personal': '#ec4899', 'Financial': '#B8924A', 'Military': '#2D7A52',
    'Employment': '#B8924A', 'Credit': '#ef4444', 'Assets': '#14b8a6',
    'Goals': '#f97316', 'Property': '#0ea5e9'
  };
  return colors[category] || '#6b7280';
};

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
  const [saveMessage, setSaveMessage] = useState(null);

  // Selection state
  const [selectedItem, setSelectedItem] = useState({ type: null, id: null });
  const [expandedSections, setExpandedSections] = useState({ stages: true, questions: true });

  // Preview state for mock answers
  const [previewAnswers, setPreviewAnswers] = useState({});

  // Preview mode: 'mobile' or 'web'
  const [previewMode, setPreviewMode] = useState('mobile');

  // Nav tab: 'stages' or 'questions'
  const [activeNavTab, setActiveNavTab] = useState('stages');

  // Get current stages and questions based on selected app type
  const stages = appType === 'purchase' ? purchaseStages : refinanceStages;
  const setStages = appType === 'purchase' ? setPurchaseStages : setRefinanceStages;
  const questions = appType === 'purchase' ? purchaseQuestions : refinanceQuestions;
  const setQuestions = appType === 'purchase' ? setPurchaseQuestions : setRefinanceQuestions;

  // Get selected item data
  const getSelectedData = () => {
    if (!selectedItem.type || !selectedItem.id) return null;
    if (selectedItem.type === 'stage') {
      return stages.find(s => s.id === selectedItem.id);
    } else {
      return questions.find(q => q.id === selectedItem.id);
    }
  };

  const selectedData = getSelectedData();

  // Merge loaded questions with defaults to preserve options
  const mergeQuestionsWithDefaults = (loadedQuestions, defaultQuestions) => {
    if (!loadedQuestions || loadedQuestions.length === 0) {
      return defaultQuestions.map(q => ({ ...q, enabled: true }));
    }

    return loadedQuestions.map(lq => {
      const defaultQ = defaultQuestions.find(dq => dq.id === lq.id);
      // If loaded question doesn't have options but default does, use default options
      if ((!lq.options || lq.options.length === 0) && defaultQ?.options) {
        return { ...lq, options: defaultQ.options, enabled: lq.enabled !== false };
      }
      return { ...lq, enabled: lq.enabled !== false };
    });
  };

  // Load configuration from backend
  const loadConfiguration = useCallback(async () => {
    setLoading(true);
    try {
      const token = getToken();

      // Load purchase config
      const purchaseRes = await fetch(`${API_URL}/api/v1/settings/application-slides?app_type=purchase`, {
        headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' }
      });
      if (purchaseRes.ok) {
        const data = await purchaseRes.json();
        setPurchaseStages(data.stages || DEFAULT_PURCHASE_STAGES.map(s => ({ ...s, enabled: true })));
        setPurchaseQuestions(mergeQuestionsWithDefaults(data.declarationQuestions, DEFAULT_PURCHASE_QUESTIONS));
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
        setRefinanceQuestions(mergeQuestionsWithDefaults(data.declarationQuestions, DEFAULT_REFINANCE_QUESTIONS));
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
      const token = getToken();

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

  // Update selected item
  const updateSelectedItem = (updates) => {
    if (!selectedItem.type || !selectedItem.id) return;

    // If updating the ID, also update the selectedItem reference
    const newId = updates.id || selectedItem.id;

    if (selectedItem.type === 'stage') {
      setStages(prev => prev.map(s => s.id === selectedItem.id ? { ...s, ...updates } : s));
    } else {
      setQuestions(prev => prev.map(q => q.id === selectedItem.id ? { ...q, ...updates } : q));
    }

    // Update selectedItem if ID changed
    if (updates.id && updates.id !== selectedItem.id) {
      setSelectedItem({ type: selectedItem.type, id: updates.id });
    }

    setHasChanges(true);
  };

  // Toggle item enabled
  const toggleItemEnabled = (type, id) => {
    if (type === 'stage') {
      setStages(prev => prev.map(s =>
        s.id === id && !s.required ? { ...s, enabled: !s.enabled } : s
      ));
    } else {
      setQuestions(prev => prev.map(q =>
        q.id === id && !q.required ? { ...q, enabled: !q.enabled } : q
      ));
    }
    setHasChanges(true);
  };

  // Add new item
  const addNewItem = (type) => {
    const newId = `new_${type}_${Date.now()}`;
    if (type === 'stage') {
      const newStage = { id: newId, label: 'New Stage', description: '', required: false, enabled: true, hideFromProgress: false };
      setStages(prev => [...prev, newStage]);
      setSelectedItem({ type: 'stage', id: newId });
    } else {
      const newQuestion = { id: newId, question: 'New Question', category: 'Basic Info', type: 'choice', required: false, enabled: true, options: [{ value: 'option1', label: 'Option 1' }] };
      setQuestions(prev => [...prev, newQuestion]);
      setSelectedItem({ type: 'question', id: newId });
    }
    setHasChanges(true);
  };

  // Move stage up or down
  const moveStage = (direction) => {
    if (!selectedItem.type || selectedItem.type !== 'stage') return;
    const currentIndex = stages.findIndex(s => s.id === selectedItem.id);
    if (currentIndex === -1) return;

    const newIndex = direction === 'up' ? currentIndex - 1 : currentIndex + 1;
    if (newIndex < 0 || newIndex >= stages.length) return;

    const newStages = [...stages];
    const [removed] = newStages.splice(currentIndex, 1);
    newStages.splice(newIndex, 0, removed);
    setStages(newStages);
    setHasChanges(true);
  };

  // Move question up or down
  const moveQuestion = (direction) => {
    if (!selectedItem.type || selectedItem.type !== 'question') return;
    const currentIndex = questions.findIndex(q => q.id === selectedItem.id);
    if (currentIndex === -1) return;

    const newIndex = direction === 'up' ? currentIndex - 1 : currentIndex + 1;
    if (newIndex < 0 || newIndex >= questions.length) return;

    const newQuestions = [...questions];
    const [removed] = newQuestions.splice(currentIndex, 1);
    newQuestions.splice(newIndex, 0, removed);
    setQuestions(newQuestions);
    setHasChanges(true);
  };

  // Delete item
  const deleteItem = () => {
    if (!selectedItem.type || !selectedItem.id) return;
    if (!window.confirm('Are you sure you want to delete this item?')) return;

    if (selectedItem.type === 'stage') {
      setStages(prev => prev.filter(s => s.id !== selectedItem.id));
    } else {
      setQuestions(prev => prev.filter(q => q.id !== selectedItem.id));
    }
    setSelectedItem({ type: null, id: null });
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
    setSelectedItem({ type: null, id: null });
    setHasChanges(true);
  };

  // Move item in list
  const moveItem = (type, index, direction) => {
    const list = type === 'stage' ? [...stages] : [...questions];
    const newIndex = direction === 'up' ? index - 1 : index + 1;
    if (newIndex < 0 || newIndex >= list.length) return;

    [list[index], list[newIndex]] = [list[newIndex], list[index]];

    if (type === 'stage') {
      setStages(list);
    } else {
      setQuestions(list);
    }
    setHasChanges(true);
  };

  // Update answer option
  const updateOption = (optionIndex, field, value) => {
    if (!selectedData || selectedItem.type !== 'question') return;
    const newOptions = [...(selectedData.options || [])];
    newOptions[optionIndex] = { ...newOptions[optionIndex], [field]: value };
    updateSelectedItem({ options: newOptions });
  };

  // Add option
  const addOption = () => {
    if (!selectedData || selectedItem.type !== 'question') return;
    const newOptions = [...(selectedData.options || []), { value: `option_${Date.now()}`, label: 'New Option' }];
    updateSelectedItem({ options: newOptions });
  };

  // Remove option
  const removeOption = (index) => {
    if (!selectedData || selectedItem.type !== 'question') return;
    const newOptions = (selectedData.options || []).filter((_, i) => i !== index);
    updateSelectedItem({ options: newOptions });
  };

  // Update conditional logic
  const updateConditionalLogic = (field, values) => {
    if (!selectedData || selectedItem.type !== 'question') return;
    if (field) {
      // Allow setting field even with empty values (user selects question first, then values)
      updateSelectedItem({ showIf: { field, values: values || [] } });
    } else {
      updateSelectedItem({ showIf: null });
    }
  };

  // Toggle conditional value
  const toggleConditionalValue = (value) => {
    if (!selectedData || !selectedData.showIf) return;
    const currentValues = selectedData.showIf.values || [];
    const newValues = currentValues.includes(value)
      ? currentValues.filter(v => v !== value)
      : [...currentValues, value];
    updateConditionalLogic(selectedData.showIf.field, newValues);
  };

  if (loading) {
    return (
      <div className="flow-builder-loading">
        <div className="loading-spinner"></div>
        <p>Loading configuration...</p>
      </div>
    );
  }

  return (
    <div className="flow-builder">
      {/* Header */}
      <div className="flow-builder-header">
        <div className="flow-builder-header-left">
          <h3>Application Flow Builder</h3>
          <p>Customize screens and questions for your mortgage applications</p>
        </div>
        <div className="flow-builder-header-right">
          <div className="app-type-toggle">
            <button
              className={`app-type-btn ${appType === 'purchase' ? 'active' : ''}`}
              onClick={() => { setAppType('purchase'); setSelectedItem({ type: null, id: null }); }}
            >
              Purchase
            </button>
            <button
              className={`app-type-btn ${appType === 'refinance' ? 'active' : ''}`}
              onClick={() => { setAppType('refinance'); setSelectedItem({ type: null, id: null }); }}
            >
              Refinance
            </button>
          </div>
          <button className="btn-secondary" onClick={resetToDefaults}>Reset</button>
          <button
            className="btn-primary"
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

      {/* Three Panel Content */}
      <div className="flow-builder-content">
        {/* Left Panel - Navigation */}
        <div className="flow-builder-nav">
          {/* Nav Tabs */}
          <div className="nav-tabs">
            <button
              className={`nav-tab ${activeNavTab === 'stages' ? 'active' : ''}`}
              onClick={() => setActiveNavTab('stages')}
            >
              Stages
              <span className="nav-tab-count">{stages.filter(s => s.enabled).length}/{stages.length}</span>
            </button>
            <button
              className={`nav-tab ${activeNavTab === 'questions' ? 'active' : ''}`}
              onClick={() => setActiveNavTab('questions')}
            >
              Questions
              <span className="nav-tab-count">{questions.filter(q => q.enabled).length}/{questions.length}</span>
            </button>
          </div>

          {/* Tab Content */}
          <div className="nav-tab-content">
            {activeNavTab === 'stages' && (
              <div className="nav-list">
                {stages.map((stage, index) => (
                  <div
                    key={stage.id}
                    className={`nav-item ${!stage.enabled ? 'disabled' : ''} ${selectedItem.type === 'stage' && selectedItem.id === stage.id ? 'selected' : ''}`}
                    onClick={() => setSelectedItem({ type: 'stage', id: stage.id })}
                  >
                    <div className="nav-item-indicator" />
                    <div className="nav-item-content">
                      <div className="nav-item-label">{stage.label}</div>
                      <div className="nav-item-meta">
                        <span className="nav-item-id">{stage.id}</span>
                      </div>
                    </div>
                    <div className="nav-item-icons">
                      {stage.required && <span className="nav-item-icon required" title="Required">★</span>}
                      {stage.hideFromProgress && <span className="nav-item-icon" title="Hidden">👁️</span>}
                    </div>
                  </div>
                ))}
                <button className="nav-add-btn" onClick={() => addNewItem('stage')}>+ Add Stage</button>
              </div>
            )}

            {activeNavTab === 'questions' && (
              <div className="nav-list">
                {questions.map((question, index) => {
                  // Support both stageId (new) and category (legacy)
                  const stage = stages.find(s => s.id === (question.stageId || question.category));
                  return (
                    <div
                      key={question.id}
                      className={`nav-item ${!question.enabled ? 'disabled' : ''} ${selectedItem.type === 'question' && selectedItem.id === question.id ? 'selected' : ''}`}
                      onClick={() => setSelectedItem({ type: 'question', id: question.id })}
                    >
                      <div className="nav-item-content">
                        <div className="nav-item-label">{question.question.substring(0, 30)}{question.question.length > 30 ? '...' : ''}</div>
                        <div className="nav-item-meta">
                          <span className="nav-item-stage">{stage?.label || 'Unassigned'}</span>
                          <span className="nav-item-type">{question.type}</span>
                        </div>
                      </div>
                      <div className="nav-item-icons">
                        {question.required && <span className="nav-item-icon required" title="Required">★</span>}
                        {question.showIf && <span className="nav-item-icon conditional" title="Has Conditional Logic">⚡</span>}
                      </div>
                    </div>
                  );
                })}
                <button className="nav-add-btn" onClick={() => addNewItem('question')}>+ Add Question</button>
              </div>
            )}
          </div>
        </div>

        {/* Center Panel - Preview */}
        <div className="flow-builder-preview">
          {/* Preview Mode Toggle */}
          <div className="preview-mode-toggle">
            <button
              className={`preview-mode-btn ${previewMode === 'mobile' ? 'active' : ''}`}
              onClick={() => setPreviewMode('mobile')}
              title="Mobile Preview"
            >
              📱 Mobile
            </button>
            <button
              className={`preview-mode-btn ${previewMode === 'web' ? 'active' : ''}`}
              onClick={() => setPreviewMode('web')}
              title="Web Preview"
            >
              🖥️ Web
            </button>
          </div>

          {!selectedData ? (
            <div className="preview-empty-state">
              <h4>Select an item to preview</h4>
              <p>Click on a stage or question from the left panel</p>
            </div>
          ) : (
            <div className={`device-frame ${previewMode === 'web' ? 'web-frame' : ''}`}>
              {previewMode === 'mobile' && <div className="device-notch" />}
              <div className={`device-screen ${previewMode === 'web' ? 'web-screen' : ''}`}>
                {selectedItem.type === 'stage' ? (
                  // Stage Preview
                  <div className="preview-stage">
                    <span className="preview-stage-badge">{selectedData.label}</span>
                    <div className="preview-progress">
                      <div className="preview-progress-bar">
                        <div className="preview-progress-fill" style={{ width: '30%' }} />
                      </div>
                      <div className="preview-progress-text">Step 2 of 8</div>
                    </div>
                    <div className="preview-question">
                      <div className="preview-question-text">{selectedData.description || 'Stage description will appear here'}</div>
                    </div>
                  </div>
                ) : (
                  // Question Preview
                  <div className="preview-question">
                    <div className="preview-question-text">{selectedData.question}</div>
                    {selectedData.helpText && (
                      <div className="preview-question-help">{selectedData.helpText}</div>
                    )}

                    {/* Render input based on type */}
                    {selectedData.type === 'choice' && selectedData.options && (
                      selectedData.options.length <= 4 ? (
                        <div className="preview-visual-options">
                          {selectedData.options.map((opt, idx) => (
                            <div
                              key={idx}
                              className={`preview-visual-option ${previewAnswers[selectedData.id] === opt.value ? 'selected' : ''}`}
                              onClick={() => setPreviewAnswers(prev => ({ ...prev, [selectedData.id]: opt.value }))}
                            >
                              <span className="preview-visual-option-label">{opt.label}</span>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <div className="preview-options">
                          {selectedData.options.map((opt, idx) => (
                            <div
                              key={idx}
                              className={`preview-option ${previewAnswers[selectedData.id] === opt.value ? 'selected' : ''}`}
                              onClick={() => setPreviewAnswers(prev => ({ ...prev, [selectedData.id]: opt.value }))}
                            >
                              <span className="preview-option-label">{opt.label}</span>
                            </div>
                          ))}
                        </div>
                      )
                    )}

                    {selectedData.type === 'yes_no' && (
                      <div className="preview-yes-no">
                        <button
                          className={`preview-yes-no-btn ${previewAnswers[selectedData.id] === 'yes' ? 'selected' : ''}`}
                          onClick={() => setPreviewAnswers(prev => ({ ...prev, [selectedData.id]: 'yes' }))}
                        >
                          Yes
                        </button>
                        <button
                          className={`preview-yes-no-btn ${previewAnswers[selectedData.id] === 'no' ? 'selected' : ''}`}
                          onClick={() => setPreviewAnswers(prev => ({ ...prev, [selectedData.id]: 'no' }))}
                        >
                          No
                        </button>
                      </div>
                    )}

                    {selectedData.type === 'text' && (
                      <input
                        type="text"
                        className="preview-input"
                        placeholder="Type your answer..."
                        value={previewAnswers[selectedData.id] || ''}
                        onChange={(e) => setPreviewAnswers(prev => ({ ...prev, [selectedData.id]: e.target.value }))}
                      />
                    )}

                    {selectedData.type === 'currency' && (
                      <div className="preview-input-wrapper">
                        <span className="preview-input-prefix">$</span>
                        <input
                          type="number"
                          className="preview-input with-prefix"
                          placeholder="0"
                          value={previewAnswers[selectedData.id] || ''}
                          onChange={(e) => setPreviewAnswers(prev => ({ ...prev, [selectedData.id]: e.target.value }))}
                        />
                      </div>
                    )}

                    {selectedData.type === 'date' && (
                      <input
                        type="date"
                        className="preview-input"
                        value={previewAnswers[selectedData.id] || ''}
                        onChange={(e) => setPreviewAnswers(prev => ({ ...prev, [selectedData.id]: e.target.value }))}
                      />
                    )}
                  </div>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Right Panel - Settings */}
        <div className="flow-builder-settings">
          {!selectedData ? (
            <div className="settings-empty">
              <div className="settings-empty-icon">⚙️</div>
              <h4>No Selection</h4>
              <p>Select an item from the left to edit its settings</p>
            </div>
          ) : (
            <>
              <div className="settings-header">
                <h4>{selectedItem.type === 'stage' ? 'Stage Settings' : 'Question Settings'}</h4>
                <p>Configure the selected {selectedItem.type}</p>
              </div>

              <div className="settings-content">
                {selectedItem.type === 'stage' ? (
                  // Stage Settings
                  <>
                    {/* Move Stage Buttons */}
                    <div className="settings-group settings-move-buttons">
                      <label>Reorder Stage</label>
                      <div className="move-buttons">
                        <button
                          className="move-btn"
                          onClick={() => moveStage('up')}
                          disabled={stages.findIndex(s => s.id === selectedItem.id) === 0}
                          title="Move Up"
                        >
                          ↑ Move Up
                        </button>
                        <button
                          className="move-btn"
                          onClick={() => moveStage('down')}
                          disabled={stages.findIndex(s => s.id === selectedItem.id) === stages.length - 1}
                          title="Move Down"
                        >
                          ↓ Move Down
                        </button>
                      </div>
                    </div>

                    <div className="settings-divider" />

                    <div className="settings-group">
                      <label>Stage ID</label>
                      <input
                        type="text"
                        className="settings-input"
                        value={selectedData.id}
                        onChange={(e) => updateSelectedItem({ id: e.target.value.toLowerCase().replace(/\s+/g, '_') })}
                        disabled={selectedData.required}
                      />
                      <small className="settings-hint">
                        {selectedData.required ? 'Required stages cannot be renamed' : 'Lowercase, underscores only'}
                      </small>
                    </div>

                    <div className="settings-group">
                      <label>Label</label>
                      <input
                        type="text"
                        className="settings-input"
                        value={selectedData.label}
                        onChange={(e) => updateSelectedItem({ label: e.target.value })}
                        placeholder="Stage label"
                      />
                    </div>

                    <div className="settings-group">
                      <label>Description</label>
                      <textarea
                        className="settings-textarea"
                        value={selectedData.description || ''}
                        onChange={(e) => updateSelectedItem({ description: e.target.value })}
                        placeholder="Brief description of this stage"
                      />
                    </div>

                    <div className="settings-divider" />

                    <div className="settings-group">
                      <label className="settings-checkbox">
                        <input
                          type="checkbox"
                          checked={selectedData.hideFromProgress || false}
                          onChange={(e) => updateSelectedItem({ hideFromProgress: e.target.checked })}
                        />
                        <span>Hide from progress bar</span>
                      </label>
                    </div>

                    <div className="settings-group">
                      <label className="settings-checkbox">
                        <input
                          type="checkbox"
                          checked={selectedData.required || false}
                          onChange={(e) => updateSelectedItem({ required: e.target.checked })}
                        />
                        <span>Required (cannot be disabled)</span>
                      </label>
                    </div>

                    {!selectedData.required && (
                      <div className="settings-group">
                        <label className="settings-checkbox">
                          <input
                            type="checkbox"
                            checked={selectedData.enabled !== false}
                            onChange={() => toggleItemEnabled('stage', selectedData.id)}
                          />
                          <span>Enabled</span>
                        </label>
                      </div>
                    )}
                  </>
                ) : (
                  // Question Settings
                  <>
                    {/* Move Question Buttons */}
                    <div className="settings-group settings-move-buttons">
                      <label>Reorder Question</label>
                      <div className="move-buttons">
                        <button
                          className="move-btn"
                          onClick={() => moveQuestion('up')}
                          disabled={questions.findIndex(q => q.id === selectedItem.id) === 0}
                          title="Move Up"
                        >
                          ↑ Move Up
                        </button>
                        <button
                          className="move-btn"
                          onClick={() => moveQuestion('down')}
                          disabled={questions.findIndex(q => q.id === selectedItem.id) === questions.length - 1}
                          title="Move Down"
                        >
                          ↓ Move Down
                        </button>
                      </div>
                    </div>

                    <div className="settings-divider" />

                    <div className="settings-group">
                      <label>Question ID</label>
                      <input
                        type="text"
                        className="settings-input"
                        value={selectedData.id}
                        onChange={(e) => updateSelectedItem({ id: e.target.value.toLowerCase().replace(/\s+/g, '_') })}
                        disabled={!selectedData.id.startsWith('new_')}
                      />
                    </div>

                    <div className="settings-group">
                      <label>Question Text</label>
                      <textarea
                        className="settings-textarea"
                        value={selectedData.question}
                        onChange={(e) => updateSelectedItem({ question: e.target.value })}
                        placeholder="Enter your question..."
                      />
                    </div>

                    <div className="settings-group">
                      <label>Help Text (optional)</label>
                      <input
                        type="text"
                        className="settings-input"
                        value={selectedData.helpText || ''}
                        onChange={(e) => updateSelectedItem({ helpText: e.target.value })}
                        placeholder="Additional context for the question"
                      />
                    </div>

                    <div className="settings-row">
                      <div className="settings-group">
                        <label>Type</label>
                        <select
                          className="settings-select"
                          value={selectedData.type || 'choice'}
                          onChange={(e) => updateSelectedItem({ type: e.target.value })}
                        >
                          {QUESTION_TYPES.map(type => (
                            <option key={type.value} value={type.value}>{type.label}</option>
                          ))}
                        </select>
                      </div>

                      <div className="settings-group">
                        <label>Stage</label>
                        <select
                          className="settings-select"
                          value={selectedData.stageId || selectedData.category || ''}
                          onChange={(e) => updateSelectedItem({ stageId: e.target.value, category: e.target.value })}
                        >
                          <option value="">Select stage...</option>
                          {stages.filter(s => s.enabled !== false).map(stage => (
                            <option key={stage.id} value={stage.id}>{stage.label}</option>
                          ))}
                        </select>
                      </div>
                    </div>

                    <div className="settings-group">
                      <label className="settings-checkbox">
                        <input
                          type="checkbox"
                          checked={selectedData.required || false}
                          onChange={(e) => updateSelectedItem({ required: e.target.checked })}
                        />
                        <span>Required</span>
                      </label>
                    </div>

                    {!selectedData.required && (
                      <div className="settings-group">
                        <label className="settings-checkbox">
                          <input
                            type="checkbox"
                            checked={selectedData.enabled !== false}
                            onChange={() => toggleItemEnabled('question', selectedData.id)}
                          />
                          <span>Enabled</span>
                        </label>
                      </div>
                    )}

                    {/* Answer Options */}
                    {(selectedData.type === 'choice' || !selectedData.type) && (
                      <>
                        <div className="settings-divider" />
                        <div className="settings-section">
                          <div className="settings-section-header">
                            <span className="settings-section-title">Answer Options</span>
                          </div>
                          <div className="options-list">
                            {(selectedData.options || []).map((opt, idx) => (
                              <div key={idx} className="option-item">
                                <span className="option-drag-handle">⋮⋮</span>
                                <div className="option-inputs">
                                  <input
                                    type="text"
                                    className="option-input"
                                    value={opt.value}
                                    onChange={(e) => updateOption(idx, 'value', e.target.value)}
                                    placeholder="Value"
                                  />
                                  <input
                                    type="text"
                                    className="option-input"
                                    value={opt.label}
                                    onChange={(e) => updateOption(idx, 'label', e.target.value)}
                                    placeholder="Label"
                                  />
                                </div>
                                <button className="option-remove" onClick={() => removeOption(idx)}>×</button>
                              </div>
                            ))}
                          </div>
                          <button className="add-option-btn" onClick={addOption}>+ Add Option</button>
                        </div>
                      </>
                    )}

                    {/* Conditional Logic */}
                    <div className="settings-divider" />
                    <div className="settings-section">
                      <div className="settings-section-header">
                        <span className="settings-section-title">Conditional Logic</span>
                      </div>
                      <div className="conditional-logic">
                        <label className="conditional-toggle">
                          <input
                            type="checkbox"
                            checked={!!selectedData.showIf}
                            onChange={(e) => {
                              if (e.target.checked) {
                                updateConditionalLogic(questions[0]?.id || '', []);
                              } else {
                                updateConditionalLogic(null, null);
                              }
                            }}
                          />
                          <span>Show based on another answer</span>
                        </label>

                        {selectedData.showIf && (
                          <div className="conditional-content">
                            <div className="conditional-row">
                              <span className="conditional-label">Show when</span>
                              <select
                                className="conditional-select"
                                value={selectedData.showIf.field || ''}
                                onChange={(e) => updateConditionalLogic(e.target.value, selectedData.showIf.values || [])}
                              >
                                <option value="">Select question...</option>
                                {questions.filter(q => q.id !== selectedData.id && q.type === 'choice').map(q => (
                                  <option key={q.id} value={q.id}>{q.question.substring(0, 40)}...</option>
                                ))}
                              </select>
                            </div>

                            {selectedData.showIf.field && (
                              <>
                                <div className="conditional-row">
                                  <span className="conditional-label">equals any of:</span>
                                </div>
                                <div className="conditional-values">
                                  {(() => {
                                    const sourceQuestion = questions.find(q => q.id === selectedData.showIf.field);
                                    return (sourceQuestion?.options || []).map(opt => (
                                      <div
                                        key={opt.value}
                                        className={`conditional-value-chip ${(selectedData.showIf.values || []).includes(opt.value) ? '' : 'inactive'}`}
                                        style={{
                                          opacity: (selectedData.showIf.values || []).includes(opt.value) ? 1 : 0.5,
                                          cursor: 'pointer'
                                        }}
                                        onClick={() => toggleConditionalValue(opt.value)}
                                      >
                                        {opt.label}
                                        {(selectedData.showIf.values || []).includes(opt.value) && (
                                          <button onClick={(e) => { e.stopPropagation(); toggleConditionalValue(opt.value); }}>×</button>
                                        )}
                                      </div>
                                    ));
                                  })()}
                                </div>
                              </>
                            )}
                          </div>
                        )}
                      </div>
                    </div>
                  </>
                )}
              </div>

              {/* Delete Button */}
              {!selectedData.required && (
                <div className="settings-footer">
                  <button className="btn-delete" onClick={deleteItem}>
                    Delete {selectedItem.type === 'stage' ? 'Stage' : 'Question'}
                  </button>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
};

export default ApplicationSlidesEditor;
