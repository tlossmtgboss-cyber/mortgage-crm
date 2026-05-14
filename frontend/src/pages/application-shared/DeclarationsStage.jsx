/**
 * DeclarationsStage - Shared question-by-question declaration flow
 *
 * Renders one question at a time with animation transitions.
 * Supports input types: choice (default), currency, address, text,
 * state_select, phone, email, agent_info.
 *
 * Used by both Purchase and Refinance applications.
 *
 * Props:
 *   enabledQuestions - filtered question array
 *   currentQuestionIndex / setCurrentQuestionIndex - current question index
 *   declarations - current declaration answers
 *   isAnimating - animation state
 *   handleDeclarationAnswer - (questionId, value) => void
 *   handleInputAnswer - (questionId, value) => void
 *   submitInputAnswer - (questionId) => void
 *   goToPrevQuestion - go back handler
 *   getVisibleQuestions - () => filtered visible questions
 *   getVisibleQuestionNumber - () => number
 *   shouldShowQuestion - (question, declarations) => boolean
 *   Icon - icon component
 *   US_STATES - state dropdown options (optional, for state_select type)
 *   agentSearch / setAgentSearch - agent search text (optional, for agent_info type)
 *   agentSuggestions - agent suggestions array (optional)
 *   agentLoading - agent search loading (optional)
 *   showAgentDropdown / setShowAgentDropdown - agent dropdown visibility (optional)
 *   agentInfo - agent info object (optional)
 *   handleSelectAgent - (agent) => void (optional)
 *   handleAgentInfoChange - (field, value) => void (optional)
 *   searchRealtors - (searchTerm) => void (optional)
 */

import React from 'react';

export default function DeclarationsStage({
  enabledQuestions,
  currentQuestionIndex,
  setCurrentQuestionIndex,
  declarations,
  isAnimating,
  handleDeclarationAnswer,
  handleInputAnswer,
  submitInputAnswer,
  goToPrevQuestion,
  getVisibleQuestions,
  getVisibleQuestionNumber,
  Icon,
  US_STATES,
  // Agent info props (purchase-only, optional)
  agentSearch,
  setAgentSearch,
  agentSuggestions,
  agentLoading,
  showAgentDropdown,
  setShowAgentDropdown,
  agentInfo,
  handleSelectAgent,
  handleAgentInfoChange,
  searchRealtors,
}) {
  const question = enabledQuestions[currentQuestionIndex];
  const visibleQuestions = getVisibleQuestions();
  const visibleQuestionNum = getVisibleQuestionNumber();

  // Guard: if question is undefined, reset to first question
  if (!question) {
    setCurrentQuestionIndex(0);
    return <div className="stage-content">Loading...</div>;
  }

  // Render different input types
  const renderQuestionInput = () => {
    if (question.type === 'currency') {
      return (
        <div className="declaration-input-container">
          <div className="currency-input-wrapper" style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: '8px',
            maxWidth: '300px',
            margin: '0 auto'
          }}>
            <span style={{
              fontSize: '24px',
              fontWeight: '500',
              color: '#374151'
            }}>$</span>
            <input
              type="number"
              className="declaration-currency-input fun-input"
              value={declarations[question.id] || ''}
              onChange={(e) => handleInputAnswer(question.id, e.target.value)}
              placeholder={question.placeholder || '0'}
              onKeyPress={(e) => e.key === 'Enter' && submitInputAnswer(question.id)}
              style={{
                textAlign: 'center',
                fontSize: '20px',
                fontWeight: '500',
                flex: 1
              }}
            />
            <span style={{
              fontSize: '16px',
              fontWeight: '500',
              color: '#6b7280'
            }}>/month</span>
          </div>
          <button
            className="btn-continue declaration-continue"
            onClick={() => submitInputAnswer(question.id)}
            disabled={!declarations[question.id]}
          >
            Continue &rarr;
          </button>
        </div>
      );
    }

    if (question.type === 'address') {
      return (
        <div className="declaration-input-container">
          <div className="address-input-wrapper">
            <Icon name="mapPin" size={20} className="address-icon" />
            <input
              type="text"
              className="declaration-address-input fun-input"
              value={declarations[question.id] || ''}
              onChange={(e) => handleInputAnswer(question.id, e.target.value)}
              placeholder={question.placeholder || 'Enter address'}
              onKeyPress={(e) => e.key === 'Enter' && submitInputAnswer(question.id)}
            />
          </div>
          <button
            className="btn-continue declaration-continue"
            onClick={() => submitInputAnswer(question.id)}
            disabled={!declarations[question.id]}
          >
            Continue &rarr;
          </button>
        </div>
      );
    }

    // Text input type
    if (question.type === 'text') {
      return (
        <div className="declaration-input-container">
          <input
            type="text"
            className="declaration-text-input fun-input"
            value={declarations[question.id] || ''}
            onChange={(e) => handleInputAnswer(question.id, e.target.value)}
            placeholder={question.placeholder || 'Enter your answer'}
            onKeyPress={(e) => e.key === 'Enter' && submitInputAnswer(question.id)}
          />
          <button
            className="btn-continue declaration-continue"
            onClick={() => submitInputAnswer(question.id)}
            disabled={!declarations[question.id]}
          >
            Continue &rarr;
          </button>
        </div>
      );
    }

    // State select dropdown type
    if (question.type === 'state_select' && US_STATES) {
      return (
        <div className="declaration-input-container">
          <select
            className="declaration-text-input fun-input"
            value={declarations[question.id] || ''}
            onChange={(e) => handleInputAnswer(question.id, e.target.value)}
            style={{
              fontSize: '18px',
              padding: '16px 20px',
              maxWidth: '400px',
              margin: '0 auto',
              display: 'block',
              cursor: 'pointer'
            }}
          >
            {US_STATES.map(s => (
              <option key={s.value} value={s.value}>{s.label}</option>
            ))}
          </select>
          <button
            className="btn-continue declaration-continue"
            onClick={() => submitInputAnswer(question.id)}
            disabled={!declarations[question.id]}
            style={{ marginTop: '20px' }}
          >
            Continue &rarr;
          </button>
        </div>
      );
    }

    // Phone input type
    if (question.type === 'phone') {
      return (
        <div className="declaration-input-container">
          <input
            type="tel"
            className="declaration-text-input fun-input"
            value={declarations[question.id] || ''}
            onChange={(e) => handleInputAnswer(question.id, e.target.value)}
            placeholder={question.placeholder || '(555) 555-5555'}
            onKeyPress={(e) => e.key === 'Enter' && submitInputAnswer(question.id)}
          />
          <button
            className="btn-continue declaration-continue"
            onClick={() => submitInputAnswer(question.id)}
            disabled={!declarations[question.id]}
          >
            Continue &rarr;
          </button>
        </div>
      );
    }

    // Email input type
    if (question.type === 'email') {
      return (
        <div className="declaration-input-container">
          <input
            type="email"
            className="declaration-text-input fun-input"
            value={declarations[question.id] || ''}
            onChange={(e) => handleInputAnswer(question.id, e.target.value)}
            placeholder={question.placeholder || 'email@example.com'}
            onKeyPress={(e) => e.key === 'Enter' && submitInputAnswer(question.id)}
          />
          <button
            className="btn-continue declaration-continue"
            onClick={() => submitInputAnswer(question.id)}
            disabled={!declarations[question.id]}
          >
            Continue &rarr;
          </button>
        </div>
      );
    }

    // Agent info - combined form with autocomplete (purchase-only)
    if (question.type === 'agent_info' && agentInfo) {
      const isComplete = agentInfo.name && (agentInfo.phone || agentInfo.email);
      return (
        <div className="declaration-input-container agent-info-form">
          {/* Agent Name with Autocomplete */}
          <div className="form-group agent-search-container">
            <label>Agent Name</label>
            <div className="autocomplete-wrapper">
              <input
                type="text"
                className="declaration-text-input fun-input"
                value={agentSearch || agentInfo.name}
                onChange={(e) => {
                  const value = e.target.value;
                  if (setAgentSearch) setAgentSearch(value);
                  if (handleAgentInfoChange) handleAgentInfoChange('name', value);
                  if (searchRealtors) searchRealtors(value);
                }}
                onFocus={() => {
                  if (agentSuggestions?.length > 0 && setShowAgentDropdown) setShowAgentDropdown(true);
                }}
                placeholder="Start typing to search our partner network..."
              />
              {agentLoading && (
                <span className="autocomplete-loading">Searching...</span>
              )}
              {showAgentDropdown && agentSuggestions?.length > 0 && (
                <div className="autocomplete-dropdown">
                  {agentSuggestions.map((agent) => (
                    <div
                      key={agent.id}
                      className="autocomplete-item"
                      onClick={() => handleSelectAgent && handleSelectAgent(agent)}
                    >
                      <div className="agent-suggestion-name">{agent.name}</div>
                      {agent.company && (
                        <div className="agent-suggestion-company">{agent.company}</div>
                      )}
                    </div>
                  ))}
                  <div
                    className="autocomplete-item manual-entry"
                    onClick={() => setShowAgentDropdown && setShowAgentDropdown(false)}
                  >
                    <span>Enter details manually</span>
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Company (auto-filled or manual) */}
          <div className="form-group">
            <label>Company / Brokerage</label>
            <input
              type="text"
              className="declaration-text-input fun-input"
              value={agentInfo.company}
              onChange={(e) => handleAgentInfoChange && handleAgentInfoChange('company', e.target.value)}
              placeholder="Agent's company or brokerage"
            />
          </div>

          {/* Agent Phone */}
          <div className="form-group">
            <label>Agent Phone</label>
            <input
              type="tel"
              className="declaration-text-input fun-input"
              value={agentInfo.phone}
              onChange={(e) => handleAgentInfoChange && handleAgentInfoChange('phone', e.target.value)}
              placeholder="(555) 555-5555"
            />
          </div>

          {/* Agent Email */}
          <div className="form-group">
            <label>Agent Email</label>
            <input
              type="email"
              className="declaration-text-input fun-input"
              value={agentInfo.email}
              onChange={(e) => handleAgentInfoChange && handleAgentInfoChange('email', e.target.value)}
              placeholder="agent@example.com"
            />
          </div>

          {agentInfo.partnerId && (
            <div className="partner-badge">
              <Icon name="check" size={16} /> Found in our partner network
            </div>
          )}

          <button
            className="btn-continue declaration-continue"
            onClick={() => handleDeclarationAnswer('agent_info', 'completed')}
            disabled={!isComplete}
          >
            Continue &rarr;
          </button>
        </div>
      );
    }

    // Default: choice type
    if (!question.options) {
      return <div className="declaration-options">No options available</div>;
    }
    return (
      <div className="declaration-options">
        {question.options.map(option => (
          <button
            key={option.value}
            className={`declaration-option ${declarations[question.id] === option.value ? 'selected' : ''}`}
            onClick={() => handleDeclarationAnswer(question.id, option.value)}
          >
            <span className="option-icon"><Icon name={option.icon} size={32} /></span>
            <span className="option-label">{option.label}</span>
            {option.description && <span className="option-description">{option.description}</span>}
          </button>
        ))}
      </div>
    );
  };

  return (
    <div className={`declaration-screen ${isAnimating ? 'animating-out' : 'animating-in'}`}>
      <div className="question-number">
        Question {visibleQuestionNum} of {visibleQuestions.length}
      </div>
      <h2 className="declaration-question">{question.question}</h2>
      {question.hint && <p className="declaration-hint"><Icon name="info" size={16} /> {question.hint}</p>}
      {renderQuestionInput()}

      {currentQuestionIndex > 0 && (
        <button className="back-link" onClick={goToPrevQuestion}>
          &larr; Go back
        </button>
      )}
    </div>
  );
}
