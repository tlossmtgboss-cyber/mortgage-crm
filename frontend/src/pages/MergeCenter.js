import React, { useState, useEffect } from 'react';
import './MergeCenter.css';

const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

function MergeCenter() {
  const [duplicatePairs, setDuplicatePairs] = useState([]);
  const [currentPair, setCurrentPair] = useState(null);
  const [aiStatus, setAiStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [step, setStep] = useState(1); // 1: compare, 2: confirm, 3: success
  const [userChoices, setUserChoices] = useState({});
  const [principalRecord, setPrincipalRecord] = useState(1);
  const [processing, setProcessing] = useState(false);
  const [mergeResult, setMergeResult] = useState(null);

  useEffect(() => {
    fetchDuplicates();
  }, []);

  const fetchDuplicates = async () => {
    try {
      setLoading(true);
      const response = await fetch(`${API_BASE_URL}/api/v1/merge/duplicates`, {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        }
      });

      if (response.ok) {
        const data = await response.json();
        setDuplicatePairs(data.pending_pairs || []);
        setAiStatus(data.ai_training_status);

        // Auto-select first pair
        if (data.pending_pairs && data.pending_pairs.length > 0) {
          selectPair(data.pending_pairs[0]);
        }
      }
    } catch (error) {
      console.error('Error fetching duplicates:', error);
    } finally {
      setLoading(false);
    }
  };

  const selectPair = (pair) => {
    setCurrentPair(pair);
    setStep(1);
    setUserChoices({});
    setPrincipalRecord(1);
    setMergeResult(null);

    // Initialize choices with AI suggestions
    const initialChoices = {};
    Object.keys(pair.ai_suggestion || {}).forEach(field => {
      initialChoices[field] = pair.ai_suggestion[field].record;
    });
    setUserChoices(initialChoices);
  };

  const handleFieldChoice = (fieldName, recordNumber) => {
    setUserChoices(prev => ({
      ...prev,
      [fieldName]: recordNumber
    }));
  };

  const selectAllLeft = () => {
    const choices = {};
    Object.keys(currentPair.ai_suggestion || {}).forEach(field => {
      choices[field] = 1;
    });
    setUserChoices(choices);
    setPrincipalRecord(1);
  };

  const selectAllRight = () => {
    const choices = {};
    Object.keys(currentPair.ai_suggestion || {}).forEach(field => {
      choices[field] = 2;
    });
    setUserChoices(choices);
    setPrincipalRecord(2);
  };

  const handleNext = () => {
    // Determine principal record based on most selections
    const record1Count = Object.values(userChoices).filter(v => v === 1).length;
    const record2Count = Object.values(userChoices).filter(v => v === 2).length;
    setPrincipalRecord(record1Count >= record2Count ? 1 : 2);
    setStep(2);
  };

  const executeMerge = async () => {
    try {
      setProcessing(true);
      const response = await fetch(`${API_BASE_URL}/api/v1/merge/execute`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          pair_id: currentPair.id,
          choices: userChoices,
          principal_record: principalRecord
        })
      });

      if (response.ok) {
        const result = await response.json();
        setMergeResult(result);
        setStep(3);

        // Refresh duplicates list
        await fetchDuplicates();
      } else {
        alert('Failed to merge contacts');
      }
    } catch (error) {
      console.error('Error merging:', error);
      alert('Error merging contacts');
    } finally {
      setProcessing(false);
    }
  };

  const dismissPair = async () => {
    if (!window.confirm('Mark these contacts as NOT duplicates?')) {
      return;
    }

    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/merge/dismiss`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          pair_id: currentPair.id
        })
      });

      if (response.ok) {
        // Refresh list
        await fetchDuplicates();
      }
    } catch (error) {
      console.error('Error dismissing:', error);
    }
  };

  const formatFieldName = (fieldName) => {
    return fieldName
      .split('_')
      .map(word => word.charAt(0).toUpperCase() + word.slice(1))
      .join(' ');
  };

  const formatFieldValue = (field, value) => {
    if (!value) return '[empty]';

    if (field.includes('amount') || field === 'property_value' || field === 'down_payment') {
      return `$${parseFloat(value).toLocaleString()}`;
    }

    if (field.includes('date') || field.includes('contact')) {
      try {
        return new Date(value).toLocaleString();
      } catch {
        return value;
      }
    }

    return value;
  };

  const getConfidenceColor = (confidence) => {
    if (confidence >= 0.85) return '#10b981';
    if (confidence >= 0.65) return '#f59e0b';
    return '#ef4444';
  };

  if (loading) {
    return (
      <div className="merge-center">
        <div className="loading-state">
          <div className="spinner"></div>
          <p>Loading potential duplicates...</p>
        </div>
      </div>
    );
  }

  if (duplicatePairs.length === 0) {
    return (
      <div className="merge-center">
        <div className="merge-header">
          <h1>🎯 Duplicate Merge Center</h1>
          <p>AI-powered duplicate detection and merging</p>
        </div>
        <div className="empty-state">
          <div className="empty-icon">✓</div>
          <h2>No Duplicates Found!</h2>
          <p>Your contact database is clean. The AI will notify you when duplicates are detected.</p>
          {aiStatus && (
            <div className="ai-status-box">
              <h3>AI Training Status</h3>
              <div className="stat-grid">
                <div className="stat">
                  <div className="stat-value">{aiStatus.total_predictions}</div>
                  <div className="stat-label">Total Merges</div>
                </div>
                <div className="stat">
                  <div className="stat-value">{(aiStatus.accuracy * 100).toFixed(1)}%</div>
                  <div className="stat-label">Accuracy</div>
                </div>
                <div className="stat">
                  <div className="stat-value">{aiStatus.progress_to_autopilot}</div>
                  <div className="stat-label">Progress</div>
                </div>
                <div className="stat">
                  <div className="stat-value">{aiStatus.autopilot_enabled ? '🟢' : '🔴'}</div>
                  <div className="stat-label">Auto-Pilot</div>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    );
  }

  if (!currentPair) {
    return null;
  }

  return (
    <div className="merge-center">
      {/* Header with AI Status */}
      <div className="merge-header">
        <div className="header-left">
          <h1>🎯 Duplicate Merge Center</h1>
          <p>Reviewing {duplicatePairs.length} potential duplicate{duplicatePairs.length !== 1 ? 's' : ''}</p>
        </div>
        <div className="header-right">
          {aiStatus && (
            <div className="ai-training-widget">
              <div className="widget-title">🤖 AI Training Progress</div>
              <div className="progress-bar-container">
                <div
                  className="progress-bar-fill"
                  style={{width: `${(aiStatus.consecutive_correct / 100) * 100}%`}}
                ></div>
                <div className="progress-text">{aiStatus.progress_to_autopilot}</div>
              </div>
              <div className="widget-stats">
                <span>Accuracy: {(aiStatus.accuracy * 100).toFixed(1)}%</span>
                <span className={`autopilot-status ${aiStatus.autopilot_enabled ? 'enabled' : 'locked'}`}>
                  {aiStatus.autopilot_enabled ? '🟢 AUTO-PILOT' : '🔴 Training'}
                </span>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Step Indicator */}
      <div className="step-indicator">
        <div className={`step ${step >= 1 ? 'active' : ''}`}>
          <div className="step-number">1</div>
          <div className="step-label">Compare Contacts</div>
        </div>
        <div className="step-connector"></div>
        <div className={`step ${step >= 2 ? 'active' : ''}`}>
          <div className="step-number">2</div>
          <div className="step-label">Confirm Merge</div>
        </div>
        <div className="step-connector"></div>
        <div className={`step ${step >= 3 ? 'active' : ''}`}>
          <div className="step-number">3</div>
          <div className="step-label">Complete</div>
        </div>
      </div>

      {/* Step 1: Compare Contacts */}
      {step === 1 && (
        <div className="compare-section">
          <div className="compare-header">
            <h2>Compare contacts</h2>
            <p>When you merge, the principal record is updated with the values you choose, and relationships to other items are shifted to the principal record.</p>
            <div className="similarity-badge">
              Similarity: {(currentPair.similarity_score * 100).toFixed(0)}%
            </div>
          </div>

          <div className="compare-container">
            {/* Left Column */}
            <div className="record-column">
              <div className="column-header">
                <h3>{currentPair.lead1.name}</h3>
                <button className="btn-select-all" onClick={selectAllLeft}>
                  Select All
                </button>
              </div>
            </div>

            {/* Middle Column - Field Labels */}
            <div className="field-labels-column">
              <div className="column-header">
                <h3>PRINCIPAL RECORD ⓘ</h3>
              </div>
            </div>

            {/* Right Column */}
            <div className="record-column">
              <div className="column-header">
                <h3>{currentPair.lead2.name}</h3>
                <button className="btn-select-all" onClick={selectAllRight}>
                  Select All
                </button>
              </div>
            </div>
          </div>

          {/* Field Rows */}
          <div className="fields-container">
            {Object.keys(currentPair.ai_suggestion || {}).map(fieldName => {
              const val1 = currentPair.lead1[fieldName];
              const val2 = currentPair.lead2[fieldName];
              const aiSuggestion = currentPair.ai_suggestion[fieldName];
              const userChoice = userChoices[fieldName];

              // Skip if both empty
              if (!val1 && !val2) return null;

              return (
                <div key={fieldName} className="field-row">
                  {/* Left Value */}
                  <div className="field-cell">
                    <label className={`field-option ${userChoice === 1 ? 'selected' : ''} ${aiSuggestion?.record === 1 ? 'ai-suggested' : ''}`}>
                      <input
                        type="radio"
                        name={fieldName}
                        checked={userChoice === 1}
                        onChange={() => handleFieldChoice(fieldName, 1)}
                      />
                      <span className="field-value">{formatFieldValue(fieldName, val1)}</span>
                      {aiSuggestion?.record === 1 && (
                        <span
                          className="ai-badge"
                          style={{backgroundColor: getConfidenceColor(aiSuggestion.confidence)}}
                        >
                          AI: {Math.round(aiSuggestion.confidence * 100)}%
                        </span>
                      )}
                    </label>
                  </div>

                  {/* Field Name */}
                  <div className="field-name-cell">
                    <strong>{formatFieldName(fieldName).toUpperCase()}</strong>
                  </div>

                  {/* Right Value */}
                  <div className="field-cell">
                    <label className={`field-option ${userChoice === 2 ? 'selected' : ''} ${aiSuggestion?.record === 2 ? 'ai-suggested' : ''}`}>
                      <input
                        type="radio"
                        name={fieldName}
                        checked={userChoice === 2}
                        onChange={() => handleFieldChoice(fieldName, 2)}
                      />
                      <span className="field-value">{formatFieldValue(fieldName, val2)}</span>
                      {aiSuggestion?.record === 2 && (
                        <span
                          className="ai-badge"
                          style={{backgroundColor: getConfidenceColor(aiSuggestion.confidence)}}
                        >
                          AI: {Math.round(aiSuggestion.confidence * 100)}%
                        </span>
                      )}
                    </label>
                  </div>
                </div>
              );
            })}
          </div>

          <div className="showing-different-notice">
            Showing fields with different values. <a href="#">Show All Fields</a>
          </div>

          {/* Action Buttons */}
          <div className="action-bar">
            <button className="btn-secondary" onClick={dismissPair}>
              Not Duplicates
            </button>
            <button className="btn-primary" onClick={handleNext}>
              Next →
            </button>
          </div>
        </div>
      )}

      {/* Step 2: Confirm Merge */}
      {step === 2 && (
        <div className="confirm-section">
          <h2>Confirm merge</h2>
          <p>We're ready to merge these records</p>

          <div className="warning-box">
            <strong>⚠️ Important:</strong> You're about to merge these contacts. You can't undo merging.
          </div>

          <div className="merge-summary">
            <div className="summary-row">
              <strong>Principal Record:</strong>
              <span>{principalRecord === 1 ? currentPair.lead1.name : currentPair.lead2.name}</span>
            </div>
            <div className="summary-row">
              <strong>Will be merged:</strong>
              <span>{principalRecord === 2 ? currentPair.lead1.name : currentPair.lead2.name}</span>
            </div>
            <div className="summary-row">
              <strong>Fields updated:</strong>
              <span>{Object.keys(userChoices).length} fields</span>
            </div>
          </div>

          <div className="action-bar">
            <button className="btn-secondary" onClick={() => setStep(1)}>
              ← Back
            </button>
            <button
              className="btn-primary btn-danger"
              onClick={executeMerge}
              disabled={processing}
            >
              {processing ? 'Merging...' : 'Merge Contacts'}
            </button>
          </div>
        </div>
      )}

      {/* Step 3: Success */}
      {step === 3 && mergeResult && (
        <div className="success-section">
          <div className="success-icon">✓</div>
          <h2>Merge Successful!</h2>
          <p>The contacts have been merged and the AI has learned from your decisions.</p>

          <div className="ai-feedback">
            <h3>🤖 AI Training Results</h3>
            <div className="feedback-grid">
              <div className="feedback-item">
                <div className="feedback-value">{mergeResult.ai_training.fields_tracked}</div>
                <div className="feedback-label">Fields Tracked</div>
              </div>
              <div className="feedback-item">
                <div className="feedback-value">{mergeResult.ai_training.ai_correct}/{mergeResult.ai_training.fields_tracked}</div>
                <div className="feedback-label">AI Correct</div>
              </div>
              <div className="feedback-item">
                <div className="feedback-value">{mergeResult.ai_training.accuracy}</div>
                <div className="feedback-label">This Merge</div>
              </div>
              <div className="feedback-item">
                <div className="feedback-value">{mergeResult.ai_training.consecutive_correct}</div>
                <div className="feedback-label">Streak</div>
              </div>
            </div>

            {mergeResult.ai_training.autopilot_unlocked && (
              <div className="autopilot-unlocked">
                <h3>🎉 AUTO-PILOT UNLOCKED! 🎉</h3>
                <p>Your AI has achieved 100 consecutive correct predictions!</p>
                <p>It can now auto-merge duplicates for you.</p>
              </div>
            )}

            {!mergeResult.ai_training.autopilot_enabled && (
              <div className="progress-message">
                <strong>{100 - mergeResult.ai_training.consecutive_correct} more consecutive correct merges</strong> to unlock auto-pilot
              </div>
            )}
          </div>

          <div className="action-bar">
            {duplicatePairs.length > 1 ? (
              <button className="btn-primary" onClick={() => selectPair(duplicatePairs[0])}>
                Next Duplicate →
              </button>
            ) : (
              <button className="btn-primary" onClick={fetchDuplicates}>
                Done
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export default MergeCenter;
