/**
 * Navigation Bar
 * Tab navigation for the video conference interactive content
 */
import React from 'react';

const TAB_LABELS = {
  process: 'Process',
  programs: 'Loan Programs',
  rates: 'Rates',
  comparison: 'Comparison',
  closing_costs: 'Closing Costs'
};

const TAB_ICONS = {
  process: '📋',
  programs: '🏠',
  rates: '💰',
  comparison: '⚖️',
  closing_costs: '💵'
};

const NavigationBar = ({
  tabs,
  activeTab,
  onTabChange,
  userRole
}) => {
  const canChangeTabs = userRole === 'lo';

  return (
    <div style={{
      backgroundColor: '#fff',
      borderBottom: '1px solid #e5e7eb',
      boxShadow: '0 1px 3px rgba(0,0,0,0.05)',
      padding: '0 16px'
    }}>
      <nav style={{
        display: 'flex',
        gap: '4px',
        maxWidth: '1400px',
        margin: '0 auto'
      }}>
        {tabs.map((tab) => {
          const isActive = activeTab === tab;

          return (
            <button
              key={tab}
              onClick={() => canChangeTabs && onTabChange(tab)}
              disabled={!canChangeTabs}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
                padding: '16px 24px',
                fontSize: '14px',
                fontWeight: isActive ? '600' : '500',
                color: isActive ? '#2563eb' : '#6b7280',
                backgroundColor: isActive ? '#eff6ff' : 'transparent',
                border: 'none',
                borderBottom: isActive ? '2px solid #2563eb' : '2px solid transparent',
                borderRadius: '8px 8px 0 0',
                cursor: canChangeTabs ? 'pointer' : 'default',
                transition: 'all 0.2s ease',
                opacity: canChangeTabs ? 1 : 0.8
              }}
              onMouseEnter={(e) => {
                if (canChangeTabs && !isActive) {
                  e.currentTarget.style.backgroundColor = '#f9fafb';
                  e.currentTarget.style.color = '#374151';
                }
              }}
              onMouseLeave={(e) => {
                if (!isActive) {
                  e.currentTarget.style.backgroundColor = 'transparent';
                  e.currentTarget.style.color = '#6b7280';
                }
              }}
            >
              <span style={{ fontSize: '16px' }}>{TAB_ICONS[tab]}</span>
              <span>{TAB_LABELS[tab]}</span>
            </button>
          );
        })}
      </nav>
    </div>
  );
};

export default NavigationBar;
export { NavigationBar };
