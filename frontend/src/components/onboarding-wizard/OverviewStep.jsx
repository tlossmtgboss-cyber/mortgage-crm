import React from 'react';

const OverviewStep = () => {
  const steps = [
    { num: 1, title: 'User Registration', description: 'Set up your account with basic information', time: '5 min', icon: '👤' },
    { num: 2, title: 'Team Setup', description: 'Add team members and assign permissions', time: '10 min', icon: '👥' },
    { num: 3, title: 'Process Documents', description: 'Upload roles, responsibilities, and process docs for AI analysis', time: '15 min', icon: '📄' },
    { num: 4, title: 'Assign Roles', description: 'Map team members to roles and responsibilities', time: '10 min', icon: '🎯' },
    { num: 5, title: 'Review Tasks', description: 'Review and approve each team member\'s task assignments', time: '10 min', icon: '✅' },
    { num: 6, title: 'Data Preview', description: 'Upload sample emails to see AI parsing in action', time: '5 min', icon: '🔍' },
    { num: 7, title: 'Data Upload', description: 'Import your leads, active loans, and closed clients', time: '15 min', icon: '📊' },
    { num: 8, title: 'Review Data', description: 'Verify and approve data before import', time: '10 min', icon: '📋' },
    { num: 9, title: 'Connect Integrations', description: 'Link calendar, email, and other services', time: '10 min', icon: '🔗' },
    { num: 10, title: 'AI Receptionist Setup', description: 'Configure phone, voice, and call routing', time: '10 min', icon: '🤖' }
  ];

  const totalTime = steps.reduce((sum, step) => sum + parseInt(step.time), 0);

  return (
    <div className="overview-page">
      <div className="overview-header">
        <h1>Welcome to Your CRM Onboarding</h1>
        <p className="overview-subtitle">
          Let's get you set up in {totalTime} minutes. You can save your progress at any time and return later.
        </p>
      </div>

      <div className="overview-steps">
        {steps.map((step) => (
          <div key={step.num} className="overview-step-card">
            <div className="overview-step-icon">{step.icon}</div>
            <div className="overview-step-content">
              <div className="overview-step-header">
                <h3>Step {step.num}: {step.title}</h3>
                <span className="overview-step-time">{step.time}</span>
              </div>
              <p className="overview-step-description">{step.description}</p>
            </div>
          </div>
        ))}
      </div>

      <div className="overview-actions">
        <div className="overview-time-budget">
          <div className="time-icon">⏱️</div>
          <div>
            <strong>Total Time:</strong> Approximately {totalTime} minutes<br/>
            <span className="time-note">You can save and resume anytime</span>
          </div>
        </div>
      </div>
    </div>
  );
};

export default OverviewStep;
