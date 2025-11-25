import React, { useState, useEffect } from 'react';
import './Step4Training.css';

const Step4Training = ({ data, onChange }) => {
  const [formData, setFormData] = useState({
    completed_modules: [],
    tour_completed: false,
    training_mode: 'guided',
    ...data
  });

  const [activeTour, setActiveTour] = useState(null);
  const [currentTourStep, setCurrentTourStep] = useState(0);

  const trainingModules = [
    {
      id: 'dashboard_overview',
      title: 'Dashboard Overview',
      description: 'Learn how to navigate the main dashboard and understand your KPIs',
      duration: '3 min',
      icon: '📊'
    },
    {
      id: 'ai_assistant',
      title: 'AI Assistant Features',
      description: 'Discover how the AI can help prioritize tasks and provide insights',
      duration: '5 min',
      icon: '🤖'
    },
    {
      id: 'pipeline_management',
      title: 'Pipeline Management',
      description: 'Master the loan pipeline view and status tracking',
      duration: '4 min',
      icon: '📈'
    },
    {
      id: 'client_communication',
      title: 'Client Communication',
      description: 'Learn about email templates, SMS, and voicemail drops',
      duration: '4 min',
      icon: '💬'
    },
    {
      id: 'task_management',
      title: 'Task Management',
      description: 'Understand how to create, assign, and complete tasks',
      duration: '3 min',
      icon: '✅'
    }
  ];

  const tourSteps = {
    dashboard_overview: [
      { title: 'Welcome to Your Dashboard', content: 'This is your command center. Here you can see all your important metrics at a glance.' },
      { title: 'KPI Cards', content: 'These cards show your key performance indicators: loans in pipeline, pending tasks, and conversion rates.' },
      { title: 'Quick Actions', content: 'Use these buttons to quickly create new loans, tasks, or access the AI assistant.' },
      { title: 'Recent Activity', content: 'This feed shows the latest updates across your pipeline and team activities.' }
    ],
    ai_assistant: [
      { title: 'AI Assistant', content: 'Click the AI icon in the sidebar to access your intelligent assistant.' },
      { title: 'Ask Questions', content: 'Type natural language questions about your pipeline, rates, or tasks.' },
      { title: 'Quick Actions', content: 'Use suggested quick actions for common tasks like daily priorities or rate lock recommendations.' },
      { title: 'Smart Insights', content: 'The AI will proactively surface important insights and recommendations.' }
    ],
    pipeline_management: [
      { title: 'Pipeline View', content: 'Access your pipeline from the sidebar to see all loans in progress.' },
      { title: 'Status Columns', content: 'Loans are organized by status - drag and drop to update.' },
      { title: 'Loan Details', content: 'Click any loan to see full details, documents, and history.' },
      { title: 'Filters & Search', content: 'Use filters to find specific loans by status, LO, or date range.' }
    ],
    client_communication: [
      { title: 'Communication Hub', content: 'Access all client communication tools from the contact view.' },
      { title: 'Email Templates', content: 'Use pre-built templates for common scenarios or create your own.' },
      { title: 'SMS & Text', content: 'Send quick text updates directly from the platform.' },
      { title: 'Call Logging', content: 'Log calls and notes to maintain a complete communication history.' }
    ],
    task_management: [
      { title: 'Task List', content: 'Your task list shows all pending items across all loans.' },
      { title: 'Creating Tasks', content: 'Create tasks manually or let the AI suggest them based on loan status.' },
      { title: 'Due Dates & Priorities', content: 'Set due dates and priority levels to stay organized.' },
      { title: 'Completing Tasks', content: 'Mark tasks complete and the system updates automatically.' }
    ]
  };

  useEffect(() => {
    onChange(formData);
  }, [formData]);

  const handleModuleComplete = (moduleId) => {
    setFormData(prev => {
      const completed = prev.completed_modules || [];
      if (completed.includes(moduleId)) {
        return prev;
      }
      return {
        ...prev,
        completed_modules: [...completed, moduleId]
      };
    });
    setActiveTour(null);
    setCurrentTourStep(0);
  };

  const startTour = (moduleId) => {
    setActiveTour(moduleId);
    setCurrentTourStep(0);
  };

  const nextTourStep = () => {
    const steps = tourSteps[activeTour];
    if (currentTourStep < steps.length - 1) {
      setCurrentTourStep(prev => prev + 1);
    } else {
      handleModuleComplete(activeTour);
    }
  };

  const prevTourStep = () => {
    if (currentTourStep > 0) {
      setCurrentTourStep(prev => prev - 1);
    }
  };

  const skipModule = () => {
    handleModuleComplete(activeTour);
  };

  const isModuleCompleted = (moduleId) => {
    return (formData.completed_modules || []).includes(moduleId);
  };

  const completedCount = (formData.completed_modules || []).length;
  const totalCount = trainingModules.length;
  const progressPercentage = (completedCount / totalCount) * 100;

  return (
    <div className="step4-training">
      <h2>Quick Start Training</h2>
      <p className="step-description">
        Complete these short training modules to get the most out of your CRM.
        You can always revisit these from your settings.
      </p>

      {/* Progress Overview */}
      <div className="training-progress">
        <div className="progress-header">
          <span className="progress-label">Training Progress</span>
          <span className="progress-count">{completedCount} of {totalCount} completed</span>
        </div>
        <div className="progress-bar">
          <div
            className="progress-fill"
            style={{ width: `${progressPercentage}%` }}
          ></div>
        </div>
      </div>

      {/* Training Mode Toggle */}
      <div className="training-mode-section">
        <label className="training-mode-label">Training Mode:</label>
        <div className="training-mode-options">
          <button
            className={`mode-button ${formData.training_mode === 'guided' ? 'active' : ''}`}
            onClick={() => setFormData(prev => ({ ...prev, training_mode: 'guided' }))}
          >
            Guided Tours
          </button>
          <button
            className={`mode-button ${formData.training_mode === 'skip' ? 'active' : ''}`}
            onClick={() => setFormData(prev => ({ ...prev, training_mode: 'skip' }))}
          >
            Skip for Now
          </button>
        </div>
      </div>

      {formData.training_mode === 'guided' && (
        <>
          {/* Training Modules List */}
          {!activeTour && (
            <div className="training-modules">
              {trainingModules.map(module => (
                <div
                  key={module.id}
                  className={`training-module ${isModuleCompleted(module.id) ? 'completed' : ''}`}
                >
                  <div className="module-icon">{module.icon}</div>
                  <div className="module-content">
                    <h4>{module.title}</h4>
                    <p>{module.description}</p>
                    <span className="module-duration">{module.duration}</span>
                  </div>
                  <div className="module-action">
                    {isModuleCompleted(module.id) ? (
                      <span className="completed-badge">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                          <polyline points="20 6 9 17 4 12"></polyline>
                        </svg>
                        Completed
                      </span>
                    ) : (
                      <button
                        className="start-button"
                        onClick={() => startTour(module.id)}
                      >
                        Start
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Active Tour Modal */}
          {activeTour && (
            <div className="tour-overlay">
              <div className="tour-modal">
                <div className="tour-progress">
                  {tourSteps[activeTour].map((_, idx) => (
                    <div
                      key={idx}
                      className={`tour-dot ${idx === currentTourStep ? 'active' : ''} ${idx < currentTourStep ? 'completed' : ''}`}
                    ></div>
                  ))}
                </div>

                <div className="tour-content">
                  <h3>{tourSteps[activeTour][currentTourStep].title}</h3>
                  <p>{tourSteps[activeTour][currentTourStep].content}</p>
                </div>

                <div className="tour-illustration">
                  <div className="illustration-placeholder">
                    <span>{trainingModules.find(m => m.id === activeTour)?.icon}</span>
                  </div>
                </div>

                <div className="tour-actions">
                  <button
                    className="tour-skip"
                    onClick={skipModule}
                  >
                    Skip Module
                  </button>
                  <div className="tour-navigation">
                    <button
                      className="tour-prev"
                      onClick={prevTourStep}
                      disabled={currentTourStep === 0}
                    >
                      Back
                    </button>
                    <button
                      className="tour-next"
                      onClick={nextTourStep}
                    >
                      {currentTourStep === tourSteps[activeTour].length - 1 ? 'Complete' : 'Next'}
                    </button>
                  </div>
                </div>
              </div>
            </div>
          )}
        </>
      )}

      {formData.training_mode === 'skip' && (
        <div className="skip-message">
          <div className="skip-icon">📚</div>
          <h3>No problem!</h3>
          <p>
            You can access these training modules anytime from <strong>Settings → Training</strong>.
            We recommend completing them when you have a few minutes to get the most out of your CRM.
          </p>
        </div>
      )}
    </div>
  );
};

export default Step4Training;
