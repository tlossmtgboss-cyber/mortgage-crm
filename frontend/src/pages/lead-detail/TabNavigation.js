import React from 'react';

const TABS = [
  { key: 'loan-details', label: 'Loan Details' },
  { key: 'personal', label: 'Personal' },
  { key: 'loan', label: 'Property' },
  { key: 'tasks', label: 'Tasks' },
  { key: 'conversation', label: 'Conversation Log' },
  { key: 'circle', label: 'Circle' },
  { key: 'smart-docs', label: 'Smart Docs' },
  { key: 'income', label: 'Income' },
  { key: 'credit', label: 'Credit' },
  { key: 'documents', label: 'Conditions' },
  { key: 'important-dates', label: 'SLA Dates' },
  { key: 'team', label: 'Team Members' },
  { key: 'call-intelligence', label: 'Call Intelligence' },
];

export default function TabNavigation({ activeTab, setActiveTab }) {
  return (
    <div className="profile-tabs">
      {TABS.map(tab => (
        <button
          key={tab.key}
          className={`tab-btn ${activeTab === tab.key ? 'active' : ''}`}
          onClick={() => setActiveTab(tab.key)}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}
