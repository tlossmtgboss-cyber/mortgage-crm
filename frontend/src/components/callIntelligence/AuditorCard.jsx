// ─────────────────────────────────────────────────────────────
// AUDITOR CARD
// src/components/callIntelligence/AuditorCard.jsx
// ─────────────────────────────────────────────────────────────

import React, { useState } from 'react';
import { CallIntelligenceApi } from '../../services/callIntelligenceApi';
import './AuditorCard.css';

const FLAG_ICONS = {
  red_flag: '\u26A0',
  document_request: '\uD83D\uDCC4',
  task_created: '\u2713',
  compliance: '\uD83D\uDD12',
};

const SEVERITY_COLORS = {
  high: '#FF6B6B',
  medium: '#FBBC04',
  info: '#7EB8F7',
};

function FlagItem({ flag, sessionId }) {
  const [dismissed, setDismissed] = useState(flag.resolved);
  const color = SEVERITY_COLORS[flag.severity] ?? '#7EB8F7';
  const icon = FLAG_ICONS[flag.type] ?? '\u26A0';

  const handleDismiss = async () => {
    const confirmed = window.confirm('Mark this flag as resolved?');
    if (!confirmed) return;
    await CallIntelligenceApi.dismissFlag(sessionId, flag.id);
    setDismissed(true);
  };

  return (
    <div className={`auditor-card__flag-item ${dismissed ? 'auditor-card__flag-item--dismissed' : ''}`}>
      <div
        className="auditor-card__flag-icon"
        style={{ backgroundColor: `${color}20` }}
      >
        <span className="auditor-card__flag-icon-text">{icon}</span>
      </div>
      <div className="auditor-card__flag-body">
        <div className={`auditor-card__flag-title ${dismissed ? 'auditor-card__flag-title--dismissed' : ''}`}>
          {flag.title}
        </div>
        <div className="auditor-card__flag-desc">{flag.description}</div>
      </div>
      {!dismissed && (
        <button className="auditor-card__dismiss-btn" onClick={handleDismiss}>
          <span className="auditor-card__dismiss-text">&times;</span>
        </button>
      )}
    </div>
  );
}

function DocItem({ doc }) {
  const statusColor = doc.status === 'received' ? '#34A853' : '#FBBC04';
  return (
    <div className="auditor-card__doc-item">
      <div className="auditor-card__doc-icon">
        <span className="auditor-card__doc-icon-text">{'\uD83D\uDCC4'}</span>
      </div>
      <div className="auditor-card__doc-body">
        <div className="auditor-card__doc-name">{doc.document_name}</div>
        <div className="auditor-card__doc-meta">Sent to {doc.sent_to_email}</div>
      </div>
      <div
        className="auditor-card__doc-status"
        style={{ backgroundColor: `${statusColor}20` }}
      >
        <span
          className="auditor-card__doc-status-text"
          style={{ color: statusColor }}
        >
          {doc.status.charAt(0).toUpperCase() + doc.status.slice(1)}
        </span>
      </div>
    </div>
  );
}

function TaskItem({ task }) {
  const priorityColor = task.priority === 'high' ? '#FF6B6B'
    : task.priority === 'medium' ? '#FBBC04' : '#7EB8F7';
  return (
    <div className="auditor-card__task-item">
      <div
        className="auditor-card__task-dot"
        style={{ backgroundColor: priorityColor }}
      />
      <div className="auditor-card__task-body">
        <div className="auditor-card__task-title">{task.title}</div>
        <div className="auditor-card__task-meta">
          Due {task.due_date.slice(0, 10)} &middot; {task.priority} priority
        </div>
      </div>
    </div>
  );
}

export default function AuditorCard({ state, sessionId }) {
  const [activeTab, setActiveTab] = useState('flags');

  const unresolvedFlags = state.flags.filter((f) => !f.resolved);

  const tabs = [
    { key: 'flags', label: 'Flags', count: unresolvedFlags.length },
    { key: 'docs',  label: 'Docs',  count: state.document_requests.length },
    { key: 'tasks', label: 'Tasks', count: state.tasks_created.length },
  ];

  return (
    <div className="auditor-card">
      {/* Header */}
      <div className="auditor-card__header">
        <div className="auditor-card__title-row">
          <div className="auditor-card__dot" />
          <span className="auditor-card__agent-name">Auditor</span>
        </div>
        <div className="auditor-card__tag-wrap">
          <span className="auditor-card__tag-text">{state.action_count} Actions</span>
        </div>
      </div>

      {/* Sub-tabs */}
      <div className="auditor-card__tab-row">
        {tabs.map((tab) => (
          <button
            key={tab.key}
            className={`auditor-card__tab ${activeTab === tab.key ? 'auditor-card__tab--active' : ''}`}
            onClick={() => setActiveTab(tab.key)}
          >
            <span className="auditor-card__tab-text">
              {tab.label}
              {tab.count > 0 && (
                <span className="auditor-card__tab-count"> {tab.count}</span>
              )}
            </span>
          </button>
        ))}
      </div>

      {/* Content */}
      <div className="auditor-card__content">
        {activeTab === 'flags' && (
          state.flags.length === 0
            ? <p className="auditor-card__empty-text">No flags raised yet</p>
            : state.flags.map((f) => (
                <FlagItem key={f.id} flag={f} sessionId={sessionId} />
              ))
        )}
        {activeTab === 'docs' && (
          state.document_requests.length === 0
            ? <p className="auditor-card__empty-text">No document requests sent yet</p>
            : state.document_requests.map((d) => (
                <DocItem key={d.id} doc={d} />
              ))
        )}
        {activeTab === 'tasks' && (
          state.tasks_created.length === 0
            ? <p className="auditor-card__empty-text">No tasks created yet</p>
            : state.tasks_created.map((t) => (
                <TaskItem key={t.id} task={t} />
              ))
        )}
      </div>
    </div>
  );
}
