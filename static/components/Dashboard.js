import React from 'react';

const Dashboard = () => {
  const modules = [
    {
      id: 'leads',
      icon: '📋',
      title: 'Leads',
      description: 'Manage new leads and track contact attempts'
    },
    {
      id: 'active-loans',
      icon: '💼',
      title: 'Active Loans',
      description: 'Monitor loans in process from application to approval'
    },
    {
      id: 'portfolio',
      icon: '🏆',
      title: 'Portfolio',
      description: 'View your closed borrowers and client relationships'
    },
    {
      id: 'tasks',
      icon: '✅',
      title: 'Tasks',
      description: 'AI-powered task completion and management'
    },
    {
      id: 'calendar',
      icon: '📅',
      title: 'Calendar',
      description: 'Schedule and manage appointments'
    },
    {
      id: 'scorecard',
      icon: '📊',
      title: 'Scorecard',
      description: 'Business metrics and performance analytics'
    }
  ];

  return (
    <div className="dashboard-container">
      <div className="ai-tips">
        <div className="ai-tips-title">
          💡 AI Assistant Tips
        </div>
        <div className="ai-tips-content">
          Welcome to your AI-Powered Mortgage CRM! I can help you navigate all features, 
          complete tasks automatically, and provide insights to grow your business. 
          Click on any module below to get started, or ask me for help using the Assistant button.
        </div>
      </div>

      <div className="page-header">
        <h1 className="page-title">Dashboard</h1>
        <p className="page-subtitle">Quick access to all your mortgage CRM tools</p>
      </div>

      <div className="dashboard-grid">
        {modules.map(module => (
          <div key={module.id} className="module-card">
            <div className="module-icon">{module.icon}</div>
            <h3 className="module-title">{module.title}</h3>
            <p className="module-description">{module.description}</p>
          </div>
        ))}
      </div>
    </div>
  );
};

export default Dashboard;
