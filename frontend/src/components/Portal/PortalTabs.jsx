/**
 * PortalTabs Component
 *
 * Reusable tab navigation component for portal pages.
 * Supports icons, badges, and disabled states.
 */

import React from 'react';
import './PortalTabs.css';

/**
 * Tab configuration for different portal modes
 */
export const PORTAL_TABS = {
  // Active loan (transaction) portal tabs
  TRANSACTION: [
    { id: 'overview', label: 'Overview', icon: '🏠' },
    { id: 'timeline', label: 'Timeline', icon: '📍' },
    { id: 'documents', label: 'Documents', icon: '📄' },
    { id: 'activity', label: 'Activity', icon: '📋' },
    { id: 'contacts', label: 'Team', icon: '👥' },
  ],

  // MUM (servicing) portal tabs
  SERVICING: [
    { id: 'overview', label: 'Overview', icon: '🏠' },
    { id: 'home-value', label: 'Home Value', icon: '📈' },
    { id: 'equity', label: 'Equity', icon: '💰' },
    { id: 'refinance', label: 'Opportunities', icon: '✨' },
    { id: 'documents', label: 'Documents', icon: '📄' },
    { id: 'contacts', label: 'Team', icon: '👥' },
  ],

  // Combined portal tabs (both transaction + MUM features)
  COMBINED: [
    { id: 'overview', label: 'Overview', icon: '🏠' },
    { id: 'timeline', label: 'Timeline', icon: '📍' },
    { id: 'documents', label: 'Documents', icon: '📄' },
    { id: 'activity', label: 'Activity', icon: '📋' },
    { id: 'home-value', label: 'Home Intelligence', icon: '📈', showInMum: true },
    { id: 'contacts', label: 'Team', icon: '👥' },
  ],
};

/**
 * Get tabs for a specific portal mode
 */
export function getTabsForMode(portalMode, isMumStage = false) {
  if (isMumStage) {
    return PORTAL_TABS.SERVICING;
  }

  switch (portalMode) {
    case 'servicing':
      return PORTAL_TABS.SERVICING;
    case 'transaction':
    default:
      return PORTAL_TABS.TRANSACTION;
  }
}

/**
 * Single Tab Button
 */
function TabButton({ tab, isActive, onClick, badge, disabled }) {
  return (
    <button
      className={`portal-tab-btn ${isActive ? 'active' : ''} ${disabled ? 'disabled' : ''}`}
      onClick={() => !disabled && onClick(tab.id)}
      disabled={disabled}
      role="tab"
      aria-selected={isActive}
      aria-controls={`tabpanel-${tab.id}`}
    >
      {tab.icon && <span className="tab-icon">{tab.icon}</span>}
      <span className="tab-label">{tab.label}</span>
      {badge !== undefined && badge > 0 && (
        <span className="tab-badge">{badge > 99 ? '99+' : badge}</span>
      )}
    </button>
  );
}

/**
 * Portal Tabs Component
 */
export default function PortalTabs({
  tabs,
  activeTab,
  onTabChange,
  badges = {},
  disabledTabs = [],
  variant = 'default', // default, compact, pills
  className = '',
}) {
  // Use provided tabs or default to transaction tabs
  const tabList = tabs || PORTAL_TABS.TRANSACTION;

  return (
    <nav
      className={`portal-tabs ${variant} ${className}`}
      role="tablist"
      aria-label="Portal navigation"
    >
      <div className="tabs-container">
        {tabList.map((tab) => (
          <TabButton
            key={tab.id}
            tab={tab}
            isActive={activeTab === tab.id}
            onClick={onTabChange}
            badge={badges[tab.id]}
            disabled={disabledTabs.includes(tab.id)}
          />
        ))}
      </div>
    </nav>
  );
}

/**
 * Tab Panel Wrapper
 * Use this to wrap tab content for proper accessibility
 */
export function TabPanel({ id, activeTab, children }) {
  const isActive = id === activeTab;

  return (
    <div
      role="tabpanel"
      id={`tabpanel-${id}`}
      aria-labelledby={`tab-${id}`}
      hidden={!isActive}
      className={`portal-tab-panel ${isActive ? 'active' : ''}`}
    >
      {isActive && children}
    </div>
  );
}
