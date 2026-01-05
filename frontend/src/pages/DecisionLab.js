import React, { useState, useEffect, useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import { decisionLabAPI } from '../services/decisionLabApi';
import ConfidenceAssessment from '../components/decisionlab/ConfidenceAssessment';
import ScenarioBuilder from '../components/decisionlab/ScenarioBuilder';
import LoanComparison from '../components/decisionlab/LoanComparison';
import ConfidenceResults from '../components/decisionlab/ConfidenceResults';
import EducationOverlayManager from '../components/decisionlab/EducationOverlayManager';
import './DecisionLab.css';

const STEPS = {
  WELCOME: 'welcome',
  ASSESSMENT: 'assessment',
  RESULTS: 'results',
  SCENARIO_BUILDER: 'scenario_builder',
  COMPARISON: 'comparison',
  EDUCATION_ADMIN: 'education_admin',
};

function DecisionLab() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [currentStep, setCurrentStep] = useState(STEPS.WELCOME);
  const [sessionId, setSessionId] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [progress, setProgress] = useState(null);
  const [confidenceScore, setConfidenceScore] = useState(null);
  const [scenarios, setScenarios] = useState([]);
  const [selectedScenarios, setSelectedScenarios] = useState([]);

  // Check URL params for admin mode
  const isAdminMode = searchParams.get('admin') === 'true';

  // Load existing session from localStorage
  useEffect(() => {
    const savedSession = localStorage.getItem('decisionLabSession');
    if (savedSession) {
      const { sessionId: savedId, step } = JSON.parse(savedSession);
      setSessionId(savedId);
      if (step && !isAdminMode) {
        setCurrentStep(step);
      }
    }
    if (isAdminMode) {
      setCurrentStep(STEPS.EDUCATION_ADMIN);
    }
  }, [isAdminMode]);

  // Save session state
  useEffect(() => {
    if (sessionId) {
      localStorage.setItem('decisionLabSession', JSON.stringify({
        sessionId,
        step: currentStep,
      }));
    }
  }, [sessionId, currentStep]);

  // Fetch progress when session exists
  const fetchProgress = useCallback(async () => {
    if (!sessionId) return;
    try {
      const data = await decisionLabAPI.getProgress(sessionId);
      setProgress(data);
    } catch (err) {
      console.error('Failed to fetch progress:', err);
    }
  }, [sessionId]);

  useEffect(() => {
    fetchProgress();
  }, [fetchProgress]);

  // Start a new session
  const handleStartSession = async () => {
    setLoading(true);
    setError('');
    try {
      const data = await decisionLabAPI.startSession();
      setSessionId(data.session_id);
      setCurrentStep(STEPS.ASSESSMENT);
    } catch (err) {
      setError('Failed to start session. Please try again.');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  // Handle assessment completion
  const handleAssessmentComplete = async (score) => {
    setConfidenceScore(score);
    setCurrentStep(STEPS.RESULTS);
    fetchProgress();
  };

  // Handle scenario creation
  const handleScenarioCreated = async (scenario) => {
    setScenarios(prev => [...prev, scenario]);
    fetchProgress();
  };

  // Handle scenario selection for comparison
  const handleSelectScenario = (scenarioId) => {
    setSelectedScenarios(prev => {
      if (prev.includes(scenarioId)) {
        return prev.filter(id => id !== scenarioId);
      }
      if (prev.length >= 3) {
        return [...prev.slice(1), scenarioId];
      }
      return [...prev, scenarioId];
    });
  };

  // Navigate to scenario builder
  const handleBuildScenario = () => {
    setCurrentStep(STEPS.SCENARIO_BUILDER);
  };

  // Navigate to comparison
  const handleCompare = () => {
    if (selectedScenarios.length >= 2) {
      setCurrentStep(STEPS.COMPARISON);
    }
  };

  // Reset session
  const handleReset = () => {
    localStorage.removeItem('decisionLabSession');
    setSessionId(null);
    setProgress(null);
    setConfidenceScore(null);
    setScenarios([]);
    setSelectedScenarios([]);
    setCurrentStep(STEPS.WELCOME);
  };

  // Toggle admin mode
  const toggleAdminMode = () => {
    if (isAdminMode) {
      searchParams.delete('admin');
      setSearchParams(searchParams);
      setCurrentStep(STEPS.WELCOME);
    } else {
      setSearchParams({ admin: 'true' });
      setCurrentStep(STEPS.EDUCATION_ADMIN);
    }
  };

  // Render step indicator
  const renderStepIndicator = () => {
    if (isAdminMode) return null;

    const steps = [
      { key: STEPS.ASSESSMENT, label: 'Assessment', icon: '1' },
      { key: STEPS.RESULTS, label: 'Results', icon: '2' },
      { key: STEPS.SCENARIO_BUILDER, label: 'Scenarios', icon: '3' },
      { key: STEPS.COMPARISON, label: 'Compare', icon: '4' },
    ];

    const currentIndex = steps.findIndex(s => s.key === currentStep);

    return (
      <div className="decision-lab-steps">
        {steps.map((step, index) => (
          <div
            key={step.key}
            className={`step-item ${currentStep === step.key ? 'active' : ''} ${index < currentIndex ? 'completed' : ''}`}
            onClick={() => {
              if (index < currentIndex || (sessionId && index <= currentIndex + 1)) {
                setCurrentStep(step.key);
              }
            }}
          >
            <div className="step-icon">
              {index < currentIndex ? '✓' : step.icon}
            </div>
            <span className="step-label">{step.label}</span>
          </div>
        ))}
      </div>
    );
  };

  // Render current step content
  const renderContent = () => {
    if (isAdminMode) {
      return <EducationOverlayManager />;
    }

    switch (currentStep) {
      case STEPS.WELCOME:
        return (
          <div className="decision-lab-welcome">
            <div className="welcome-hero">
              <div className="welcome-icon">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
              </div>
              <h1>Mortgage Decision Lab</h1>
              <p className="welcome-subtitle">
                Your personalized guide to understanding mortgage options and building confidence in your home buying journey.
              </p>
            </div>

            <div className="welcome-features">
              <div className="feature-card">
                <div className="feature-icon">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
                  </svg>
                </div>
                <h3>Confidence Assessment</h3>
                <p>Answer questions about your financial situation and mortgage knowledge to get a personalized readiness score.</p>
              </div>

              <div className="feature-card">
                <div className="feature-icon">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
                  </svg>
                </div>
                <h3>Learn Along the Way</h3>
                <p>Educational content explains key concepts like DTI, PMI, and credit scores as you go.</p>
              </div>

              <div className="feature-card">
                <div className="feature-icon">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M3 6l3 1m0 0l-3 9a5.002 5.002 0 006.001 0M6 7l3 9M6 7l6-2m6 2l3-1m-3 1l-3 9a5.002 5.002 0 006.001 0M18 7l3 9m-3-9l-6-2m0-2v2m0 16V5m0 16H9m3 0h3" />
                  </svg>
                </div>
                <h3>Compare Loan Options</h3>
                <p>Build and compare different loan scenarios to find the best fit for your situation.</p>
              </div>
            </div>

            <div className="welcome-actions">
              <button
                className="start-button"
                onClick={handleStartSession}
                disabled={loading}
              >
                {loading ? 'Starting...' : 'Start Your Assessment'}
              </button>
              {error && <p className="error-message">{error}</p>}
            </div>

            {progress && (
              <div className="resume-session">
                <p>You have an existing session in progress.</p>
                <div className="resume-actions">
                  <button className="resume-button" onClick={() => setCurrentStep(STEPS.ASSESSMENT)}>
                    Resume Session
                  </button>
                  <button className="reset-button" onClick={handleReset}>
                    Start Fresh
                  </button>
                </div>
              </div>
            )}
          </div>
        );

      case STEPS.ASSESSMENT:
        return (
          <ConfidenceAssessment
            sessionId={sessionId}
            onComplete={handleAssessmentComplete}
            onBack={() => setCurrentStep(STEPS.WELCOME)}
          />
        );

      case STEPS.RESULTS:
        return (
          <ConfidenceResults
            sessionId={sessionId}
            score={confidenceScore}
            onBuildScenario={handleBuildScenario}
            onRetakeAssessment={() => {
              handleReset();
              handleStartSession();
            }}
          />
        );

      case STEPS.SCENARIO_BUILDER:
        return (
          <ScenarioBuilder
            sessionId={sessionId}
            onScenarioCreated={handleScenarioCreated}
            onBack={() => setCurrentStep(STEPS.RESULTS)}
            existingScenarios={scenarios}
            selectedScenarios={selectedScenarios}
            onSelectScenario={handleSelectScenario}
            onCompare={handleCompare}
          />
        );

      case STEPS.COMPARISON:
        return (
          <LoanComparison
            scenarioIds={selectedScenarios}
            onBack={() => setCurrentStep(STEPS.SCENARIO_BUILDER)}
            onCreateNew={() => setCurrentStep(STEPS.SCENARIO_BUILDER)}
          />
        );

      default:
        return null;
    }
  };

  return (
    <div className="decision-lab-page">
      <div className="decision-lab-header">
        <div className="header-content">
          <h1 className="header-title">
            {isAdminMode ? 'Education Content Manager' : 'Mortgage Decision Lab'}
          </h1>
          {progress && !isAdminMode && (
            <div className="progress-badge">
              <span className="progress-text">
                {progress.questions_answered || 0} / {progress.total_questions || 13} questions
              </span>
            </div>
          )}
        </div>
        <div className="header-actions">
          <button
            className={`admin-toggle ${isAdminMode ? 'active' : ''}`}
            onClick={toggleAdminMode}
            title={isAdminMode ? 'Exit Admin Mode' : 'Manage Education Content'}
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
              <path d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
            </svg>
            {isAdminMode ? 'Exit Admin' : 'Admin'}
          </button>
        </div>
      </div>

      {renderStepIndicator()}

      <div className="decision-lab-content">
        {renderContent()}
      </div>
    </div>
  );
}

export default DecisionLab;
