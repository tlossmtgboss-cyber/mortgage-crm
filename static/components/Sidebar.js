import React from 'react';

const Sidebar = ({ currentView, onNavigate }) => {
  const navItems = [
    { id: 'dashboard', label: 'Dashboard', icon: '📊' },
    { id: 'leads', label: 'Leads', icon: '📋' },
    { id: 'active-loans', label: 'Active Loans', icon: '💼' },
    { id: 'portfolio', label: 'Portfolio', icon: '🏆' },
    { id: 'tasks', label: 'Tasks', icon: '✅' },
    { id: 'calendar', label: 'Calendar', icon: '📅' },
    { id: 'scorecard', label: 'Scorecard', icon: '📊' }
  ];

  return (
    <aside className="sidebar">
      <div className="sidebar-header">
        MortgageCRM
      </div>
      <nav className="sidebar-nav">
        {navItems.map(item => (
          <button
            key={item.id}
            className={`nav-button ${currentView === item.id ? 'active' : ''}`}
            onClick={() => onNavigate(item.id)}
          >
            <span className="nav-icon">{item.icon}</span>
            <span>{item.label}</span>
          </button>
        ))}
      </nav>
    </aside>
  );
};

export default Sidebar;
