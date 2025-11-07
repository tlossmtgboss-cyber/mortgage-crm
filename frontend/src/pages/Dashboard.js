import React from 'react';
import { useNavigate } from 'react-router-dom';
import './Dashboard.css';

function Dashboard() {
  const navigate = useNavigate();

  const modules = [
    {
      id: 'leads',
      emoji: '📋',
      title: 'Leads',
      description: 'Manage and track your mortgage leads',
      path: '/leads'
    },
    {
      id: 'active-loans',
      emoji: '💼',
      title: 'Active Loans',
      description: 'Monitor loans in progress',
      path: '/active-loans'
    },
    {
      id: 'portfolio',
      emoji: '🏆',
      title: 'Portfolio',
      description: 'View your complete loan portfolio',
      path: '/portfolio'
    },
    {
      id: 'tasks',
      emoji: '✅',
      title: 'Tasks',
      description: 'Manage your daily tasks and follow-ups',
      path: '/tasks'
    },
    {
      id: 'calendar',
      emoji: '📅',
      title: 'Calendar',
      description: 'Schedule and view appointments',
      path: '/calendar'
    },
    {
      id: 'scorecard',
      emoji: '📊',
      title: 'Scorecard',
      description: 'Track your performance metrics',
      path: '/scorecard'
    }
  ];

  return (
    <div className="dashboard-container">
      <div className="ai-tips-section">
        <h2>💡 AI Assistant Tips</h2>
        <p>
          Welcome to your Mortgage CRM! Use the AI Assistant to help you with tasks like:
          lead qualification, document processing, follow-up reminders, and generating
          personalized email templates. Click the 🤖 Assistant button in the navigation
          to get started.
        </p>
      </div>

      <div className="modules-grid">
        {modules.map((module) => (
          <div
            key={module.id}
            className="module-card"
            onClick={() => navigate(module.path)}
          >
            <div className="module-emoji">{module.emoji}</div>
            <h3 className="module-title">{module.title}</h3>
            <p className="module-description">{module.description}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

export default Dashboard;
