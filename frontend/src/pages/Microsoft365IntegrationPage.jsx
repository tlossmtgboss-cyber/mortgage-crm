import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import CalendarMirrorStatus from '../features/microsoft365/CalendarMirrorStatus';
import ReconciliationTab from '../features/microsoft365/ReconciliationTab';

const tabs = [
  { key: 'connection', label: 'Connection & Calendar' },
  { key: 'reconciliation', label: 'Email & Teams Reconciliation' },
];

export default function Microsoft365IntegrationPage() {
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState('connection');

  return (
    <div style={{ padding: '24px', maxWidth: 1100 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 24 }}>
        <button
          onClick={() => navigate('/settings/integrations')}
          style={{
            background: 'none',
            border: 'none',
            color: '#7EB8F7',
            cursor: 'pointer',
            fontSize: 14,
            padding: 0,
          }}
        >
          &larr; Integrations
        </button>
        <h1 style={{ margin: 0, fontSize: 22, color: '#fff' }}>Microsoft 365</h1>
      </div>

      <div style={{ display: 'flex', gap: 8, marginBottom: 24 }}>
        {tabs.map((t) => (
          <button
            key={t.key}
            onClick={() => setActiveTab(t.key)}
            style={{
              padding: '8px 18px',
              borderRadius: 6,
              border: activeTab === t.key ? '1px solid #7EB8F7' : '1px solid #1a2332',
              background: activeTab === t.key ? 'rgba(126,184,247,0.12)' : '#0d1520',
              color: activeTab === t.key ? '#7EB8F7' : '#8899aa',
              cursor: 'pointer',
              fontSize: 13,
              fontWeight: 500,
            }}
          >
            {t.label}
          </button>
        ))}
      </div>

      {activeTab === 'connection' && <CalendarMirrorStatus />}
      {activeTab === 'reconciliation' && <ReconciliationTab />}
    </div>
  );
}
