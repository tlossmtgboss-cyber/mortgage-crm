import React from 'react';
import { useNavigate } from 'react-router-dom';
import './Dashboard.css';

function Dashboard() {
  const navigate = useNavigate();

  const modules = [
    {
      id: 'leads',
      title: 'Leads',
      description: 'Manage and track new prospects',
      icon: '👥',
      path: '/leads',
    },
    {
      id: 'loans',
      title: 'Active Loans',
      description: 'Monitor in-process loans',
      icon: '💼',
      path: '/loans',
    },
    {
      id: 'portfolio',
      title: 'Portfolio',
      description: 'View closed client relationships',
      icon: '📊',
      path: '/portfolio',
    },
    {
      id: 'tasks',
      title: 'Tasks',
      description: 'Automated task management',
      icon: '✓',
      path: '/tasks',
    },
    {
      id: 'calendar',
      title: 'Calendar',
      description: 'Schedule appointments and events',
      icon: '📅',
      path: '/calendar',
    },
    {
      id: 'scorecard',
      title: 'Scorecard',
      description: 'Performance metrics and analytics',
      icon: '📈',
      path: '/scorecard',
    },
    {
      id: 'assistant',
      title: 'AI Assistant',
      description: 'Your intelligent CRM copilot',
      icon: '🤖',
      path: '/assistant',
    },
  ];

  return (
    <div className="dashboard">
      <div className="dashboard-header">
        <h1>Dashboard</h1>
        <p className="subtitle">Welcome to your AI-Powered Mortgage CRM</p>
      </div>

      <div className="modules-grid">
        {modules.map((module) => (
          <div
            key={module.id}
            className="module-card"
            onClick={() => navigate(module.path)}
          >
            <div className="module-icon">{module.icon}</div>
            <div className="module-content">
              <h3>{module.title}</h3>
              <p>{module.description}</p>
            </div>
          </div>
        ))}
      </div>

      <div className="ai-tips">
        <div className="tip-box">
          <h4>AI Assistant Tips</h4>
          <ul>
            <li>Click the "AI Assistant" button in the navigation to get help with any task</li>
            <li>The AI can help you schedule appointments, manage leads, and automate follow-ups</li>
            <li>Ask the AI to analyze your performance metrics and provide insights</li>
          </ul>
        </div>
      </div>
    </div>
  );
}

export default Dashboard;
