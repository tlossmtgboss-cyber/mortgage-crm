import React from 'react';
import { Icon } from '../application-shared';
import { PLANNING_QUESTIONS } from './planningQuestions';

/**
 * PlanningStage - Refinance version: single-page with all sections visible.
 * Unlike purchase (multi-step), refinance shows all planning sections at once:
 * mortgage priorities, personal goals, financial philosophy,
 * tax-deferred retirement, professional network.
 */
export default function PlanningStage({
  planningData,
  setPlanningData,
  goToPrevStage,
  goToNextStage,
}) {
  const togglePlanningOption = (field, value) => {
    setPlanningData(prev => {
      const current = prev[field] || [];
      if (current.includes(value)) {
        return { ...prev, [field]: current.filter(v => v !== value) };
      } else {
        return { ...prev, [field]: [...current, value] };
      }
    });
  };

  return (
    <div className="stage-content planning-stage">
      <div className="stage-header">
        <h2>Let's Plan Your Refinance</h2>
        <p>A few quick questions to help us find the perfect loan for your situation</p>
      </div>

      {/* Mortgage Priorities - Multi-select */}
      <div className="form-card planning-section">
        <h3>{PLANNING_QUESTIONS.mortgagePriorities.question}</h3>
        <p className="section-hint">{PLANNING_QUESTIONS.mortgagePriorities.hint}</p>
        <div className="multi-select-grid">
          {PLANNING_QUESTIONS.mortgagePriorities.options.map(option => (
            <button key={option.value} className={`multi-select-option ${planningData.mortgagePriorities.includes(option.value) ? 'selected' : ''}`} onClick={() => togglePlanningOption('mortgagePriorities', option.value)}>
              <span className="option-icon"><Icon name={option.icon} size={32} /></span>
              <span className="option-label">{option.label}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Personal Goals - Multi-select */}
      <div className="form-card planning-section">
        <h3>{PLANNING_QUESTIONS.personalGoals.question}</h3>
        <p className="section-hint">{PLANNING_QUESTIONS.personalGoals.hint}</p>
        <div className="multi-select-grid">
          {PLANNING_QUESTIONS.personalGoals.options.map(option => (
            <button key={option.value} className={`multi-select-option ${planningData.personalGoals.includes(option.value) ? 'selected' : ''}`} onClick={() => togglePlanningOption('personalGoals', option.value)}>
              <span className="option-icon"><Icon name={option.icon} size={32} /></span>
              <span className="option-label">{option.label}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Financial Philosophy - Single select */}
      <div className="form-card planning-section">
        <h3>{PLANNING_QUESTIONS.financialPhilosophy.question}</h3>
        <div className="philosophy-options">
          {PLANNING_QUESTIONS.financialPhilosophy.options.map(option => (
            <button key={option.value} className={`philosophy-option ${planningData.financialPhilosophy === option.value ? 'selected' : ''}`} onClick={() => setPlanningData(prev => ({ ...prev, financialPhilosophy: option.value }))}>
              <span className="option-icon"><Icon name={option.icon} size={32} /></span>
              <span className="option-label">{option.label}</span>
              <span className="option-description">{option.description}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Tax-Deferred Retirement - Single select */}
      <div className="form-card planning-section">
        <h3>{PLANNING_QUESTIONS.taxDeferredRetirement.question}</h3>
        <p className="section-hint">{PLANNING_QUESTIONS.taxDeferredRetirement.hint}</p>
        <div className="single-select-options">
          {PLANNING_QUESTIONS.taxDeferredRetirement.options.map(option => (
            <button key={option.value} className={`single-select-option ${planningData.taxDeferredRetirement === option.value ? 'selected' : ''}`} onClick={() => setPlanningData(prev => ({ ...prev, taxDeferredRetirement: option.value }))}>
              <span className="option-icon"><Icon name={option.icon} size={22} /></span>
              <span className="option-label">{option.label}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Professional Network - Multi-select */}
      <div className="form-card planning-section">
        <h3>{PLANNING_QUESTIONS.professionalNetwork.question}</h3>
        <p className="section-hint">{PLANNING_QUESTIONS.professionalNetwork.hint}</p>
        <div className="multi-select-grid compact">
          {PLANNING_QUESTIONS.professionalNetwork.options.map(option => (
            <button key={option.value} className={`multi-select-option ${planningData.professionalNetwork.includes(option.value) ? 'selected' : ''}`} onClick={() => togglePlanningOption('professionalNetwork', option.value)}>
              <span className="option-icon"><Icon name={option.icon} size={22} /></span>
              <span className="option-label">{option.label}</span>
            </button>
          ))}
        </div>
      </div>

      <div className="stage-navigation">
        <button className="btn-back" onClick={goToPrevStage}>{'←'} Back</button>
        <button className="btn-continue" onClick={goToNextStage}>Continue {'→'}</button>
      </div>
    </div>
  );
}
